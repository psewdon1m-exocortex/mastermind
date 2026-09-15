import hashlib
import hmac
import secrets
import threading
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .errors import DomainError

HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
SESSION_SECONDS = 12 * 3600


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def exact_value(value):
    if not isinstance(value, str):
        raise DomainError("ACCESS_KEY_REQUIRED", "An explicit Access Key value is required.", 422)
    return value


def verify(verifier, value):
    try:
        return HASHER.verify(verifier, exact_value(value))
    except (InvalidHashError, VerificationError):
        return False


class Auth:
    def __init__(self, state, audit):
        self.state, self.audit = state, audit
        self.kdf_slots = threading.BoundedSemaphore(2)
        self.revoke_listeners = []

    def initialize(self, access_key):
        value = exact_value(access_key)
        with self.state.transaction() as db:
            if self.state.setting("access_key_verifier") is not None:
                raise DomainError("ALREADY_INITIALIZED", "Owner authentication is already configured.", 409)
            self.state.set_setting("access_key_verifier", HASHER.hash(value))
            db.execute("DELETE FROM sessions")
        self.audit.emit("auth.initialize", actor="installer", target="owner")

    def rate(self, scope, *, count=5, seconds=60):
        now = time.time()
        with self.state.transaction() as db:
            db.execute("DELETE FROM rate_limits WHERE occurred_at<?", (now - 86400,))
            total = db.execute("SELECT COUNT(*) FROM rate_limits WHERE scope=? AND occurred_at>?",
                               (scope, now-seconds)).fetchone()[0]
            if total >= count:
                raise DomainError("RATE_LIMITED", "Too many attempts; try again later.", 429)
            db.execute("INSERT INTO rate_limits VALUES(?,?)", (scope, now))
            # Unknown clients cannot grow persistent abuse state without a bound.
            db.execute("DELETE FROM rate_limits WHERE rowid IN (SELECT rowid FROM rate_limits "
                       "ORDER BY occurred_at DESC LIMIT -1 OFFSET 10000)")

    def login(self, access_key, address):
        value = exact_value(access_key)
        self.rate("owner-login:" + digest(address))
        self.rate("owner-login-global", count=30)
        verifier = self.state.setting("access_key_verifier")
        if verifier is None:
            raise DomainError("NOT_CONFIGURED", "Owner authentication is not configured.", 503)
        if not self.kdf_slots.acquire(blocking=False):
            raise DomainError("RATE_LIMITED", "Authentication is busy; try again later.", 429)
        try:
            accepted = verify(verifier, value)
        finally:
            self.kdf_slots.release()
        if not accepted:
            self.audit.emit("auth.login", outcome="denied", actor="anonymous", target="owner")
            raise DomainError("UNAUTHORIZED", "The Access Key was not accepted.", 401)
        result = self.issue("owner", "owner", SESSION_SECONDS)
        self.audit.emit("auth.login", actor="owner", target="owner")
        return result

    def issue(self, principal, kind, ttl, policy_version=0):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = time.time()
        with self.state.transaction() as db:
            db.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                       (digest(token), principal, kind, now, now+ttl, policy_version, digest(csrf)))
            db.execute("DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM sessions "
                       "WHERE principal=? AND kind=? ORDER BY created_at DESC LIMIT -1 OFFSET 10)",
                       (principal, kind))
        return {"token": token, "csrf": csrf, "expires_at": now+ttl}

    def session(self, token, *, kind="owner"):
        if not token:
            raise DomainError("UNAUTHORIZED", "Authentication is required.", 401)
        row = self.state.one("SELECT * FROM sessions WHERE token_hash=? AND kind=? AND expires_at>?",
                             (digest(token), kind, time.time()))
        if not row:
            raise DomainError("UNAUTHORIZED", "The session is no longer valid.", 401)
        return row

    def csrf(self, session, value, origin, public_url):
        if not value or not hmac.compare_digest(session["csrf_hash"], digest(value)) \
                or origin != public_url.rstrip("/"):
            raise DomainError("CSRF_REJECTED", "The request origin or CSRF token was not accepted.", 403)

    def revoke(self, token=None):
        with self.state.transaction() as db:
            if token is None:
                db.execute("DELETE FROM sessions")
            else:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))
        for listener in self.revoke_listeners:
            listener(digest(token) if token else None)

    def rotate(self, current_value, new_value, current_token):
        self.session(current_token)
        self.rate("owner-rotation", count=3, seconds=300)
        if not verify(self.state.setting("access_key_verifier"), current_value):
            raise DomainError("UNAUTHORIZED", "Current Access Key proof was not accepted.", 401)
        verifier = HASHER.hash(exact_value(new_value))
        with self.state.transaction():
            self.state.set_setting("access_key_verifier", verifier)
            self.revoke()
            result = self.issue("owner", "owner", SESSION_SECONDS)
        self.audit.emit("auth.rotate", actor="owner", target="owner")
        return result
