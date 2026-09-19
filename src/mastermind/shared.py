"""One-note capabilities. Public callers never choose a Vault path or a resolver."""
import base64
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
from pathlib import PurePosixPath

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from . import share_projection
from .auth import digest
from .errors import DomainError
from .fs import open_under, safe_relative, sha_bytes

PASSWORDS = PasswordHasher(memory_cost=19456, time_cost=2, parallelism=1, hash_len=32, salt_len=16)
SESSION_TTL = 1800


class SharedConflict(DomainError):
    def __init__(self, projection):
        super().__init__("CONFLICT", "The note changed. Merge into the fresh safe projection.", 409)
        self.projection = projection


class Shared:
    def __init__(self, vault, auth, secrets_store, audit, ready=lambda: None):
        self.vault, self.state, self.auth = vault, vault.state, auth
        self.secrets, self.audit, self.ready = secrets_store, audit, ready
        self.lock = vault.coordinator.lock
        self.unlock_lock = threading.Lock()

    def mac(self, purpose, value):
        pepper = self.secrets.read("share_pepper_v1").encode("utf-8")
        return hmac.new(pepper, (purpose + "\0" + value).encode("utf-8"), hashlib.sha256).hexdigest()

    def password(self, value):
        if value is None or value == "":
            return None
        if not isinstance(value, str) or len(value.encode("utf-8")) > 4096:
            raise DomainError("INVALID_PASSWORD", "The password exceeds the supported request size.", 422)
        if not self.auth.kdf_slots.acquire(blocking=False):
            raise DomainError("RATE_LIMITED", "Authentication is busy; try again later.", 429)
        try:
            return PASSWORDS.hash(value)
        finally:
            self.auth.kdf_slots.release()

    @staticmethod
    def policy(permission, expires_at):
        if permission not in ("view", "edit"):
            raise DomainError("INVALID_PERMISSION", "Share permission must be view or edit.", 422)
        if expires_at is not None and (isinstance(expires_at, bool) or not isinstance(expires_at, (int, float))
                or not math.isfinite(expires_at) or not time.time() < expires_at <= time.time() + 365*86400):
            raise DomainError("INVALID_EXPIRATION", "Expiration must be in the next 365 days.", 422)

    def create(self, path, permission="view", password=None, expires_at=None):
        self.ready()
        safe_relative(path)
        self.policy(permission, expires_at)
        verifier = self.password(password)
        identifier, now = secrets.token_hex(16), time.time()
        token = self.link_token(identifier)
        token_hmac = self.mac("share-token", token)
        with self.lock, self.state.transaction() as db:
            self.vault.read(path)
            if db.execute("SELECT COUNT(*) FROM shares").fetchone()[0] >= 100_000:
                raise DomainError("SHARE_LIMIT", "The Share record limit has been reached.", 409)
            db.execute("INSERT INTO shares VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (identifier, token_hmac, "v1", path, permission, verifier, now, now, expires_at, None, 1))
        self.audit.emit("share.create", actor="owner", target=identifier)
        return {"share_id": identifier, "url": self.vault.config.public_url.rstrip("/") + "/s/" + token,
                "permission": permission, "expires_at": expires_at}

    def link_token(self, identifier):
        """Recoverable, domain-separated capability with a full 256-bit MAC.

        Original random capabilities keep working. This signed alias targets the
        same Share record, so policy, revocation and restore retain one authority.
        No raw capability or reversible credential is persisted in the database.
        """
        signature = bytes.fromhex(self.mac("share-link-v2", identifier))
        return "v2_" + base64.urlsafe_b64encode(bytes.fromhex(identifier) + signature).decode().rstrip("=")

    def copy_link(self, identifier):
        self.ready()
        row = self.state.one("SELECT id,revoked_at FROM shares WHERE id=?", (identifier,))
        if not row or row["revoked_at"] is not None:
            raise DomainError("NOT_FOUND", "Share not found.", 404)
        return {"url": self.vault.config.public_url.rstrip("/") + "/s/" + self.link_token(identifier)}

    def list(self, limit=100, offset=0):
        self.ready()
        rows = self.state.rows("SELECT id AS share_id,path,permission,password_hash IS NOT NULL AS password_required,"
                               "created_at,updated_at,expires_at,revoked_at,policy_version FROM shares WHERE revoked_at IS NULL "
                               "ORDER BY created_at DESC LIMIT ? OFFSET ?", (min(max(limit, 1), 500), max(offset, 0)))
        with self.lock:
            for row in rows:
                row["state"] = "revoked" if row["revoked_at"] else "expired" if row["expires_at"] \
                    and row["expires_at"] <= time.time() else "active"
                try:
                    text = self.vault.read(row["path"])
                    with open_under(self.vault.config.vault, row["path"]) as source:
                        row["modified_at"] = os.fstat(source.fileno()).st_mtime
                    row["size_bytes"] = len(text.encode("utf-8"))
                    row["target_missing"] = False
                except DomainError as error:
                    if error.status != 404:
                        raise
                    row["target_missing"] = True
                    row["modified_at"] = row["size_bytes"] = None
        return rows

    def change(self, identifier, values):
        self.ready()
        if not values or set(values) - {"permission", "password", "expires_at", "revoke"} \
                or "revoke" in values and values["revoke"] is not True:
            raise DomainError("INVALID_POLICY", "Share policy update is invalid.", 422)
        verifier = self.password(values["password"]) if "password" in values else None
        with self.lock, self.state.transaction() as db:
            row = self.state.one("SELECT * FROM shares WHERE id=?", (identifier,))
            if not row:
                raise DomainError("NOT_FOUND", "Share not found.", 404)
            if row["revoked_at"] is not None:
                if values == {"revoke": True}:
                    return {"updated": True}
                raise DomainError("SHARE_REVOKED", "Revocation is irreversible for this Share.", 409)
            permission = values.get("permission", row["permission"])
            expires = values.get("expires_at", row["expires_at"])
            # Changing another field must not silently extend an already expired policy.
            self.policy(permission, expires if "expires_at" in values else None)
            now = time.time()
            db.execute("UPDATE shares SET permission=?,password_hash=?,expires_at=?,revoked_at=?,"
                       "updated_at=?,policy_version=policy_version+1 WHERE id=?",
                       (permission, verifier if "password" in values else row["password_hash"], expires,
                        now if values.get("revoke") else None, now, identifier))
            db.execute("DELETE FROM sessions WHERE kind='share' AND principal=?", (identifier,))
            db.execute("DELETE FROM projections WHERE share_id=?", (identifier,))
        self.audit.emit("share.revoke" if values.get("revoke") else "share.policy", actor="owner", target=identifier)
        return {"updated": True}

    def active(self, token):
        self.ready()
        if not isinstance(token, str):
            raise DomainError("NOT_FOUND", "Share not found.", 404)
        if re.fullmatch(r"v2_[A-Za-z0-9_-]{64}", token):
            raw = base64.urlsafe_b64decode(token[3:])
            identifier = raw[:16].hex()
            if not hmac.compare_digest(token, self.link_token(identifier)):
                raise DomainError("NOT_FOUND", "Share not found.", 404)
            row = self.state.one("SELECT * FROM shares WHERE id=?", (identifier,))
        elif re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            row = self.state.one("SELECT * FROM shares WHERE token_hmac=?", (self.mac("share-token", token),))
        else:
            raise DomainError("NOT_FOUND", "Share not found.", 404)
        if not row or row["revoked_at"] is not None or row["expires_at"] is not None and row["expires_at"] <= time.time():
            raise DomainError("NOT_FOUND", "Share not found.", 404)
        return row

    def describe(self, token):
        row = self.active(token)
        return {"password_required": row["password_hash"] is not None}

    def unlock(self, token, password, address):
        row = self.active(token)
        if row["password_hash"]:
            scope = "share-unlock:" + self.mac("source-ip", address)
            with self.unlock_lock:
                count = self.state.one("SELECT COUNT(*) AS n FROM rate_limits WHERE scope=? AND occurred_at>?",
                                       (scope, time.time() - 900))["n"]
                if count >= 5 or not self.auth.kdf_slots.acquire(blocking=False):
                    raise DomainError("RATE_LIMITED", "Too many attempts; try again later.", 429)
                started = time.monotonic()
                try:
                    accepted = isinstance(password, str) and len(password.encode("utf-8")) <= 4096 \
                        and PASSWORDS.verify(row["password_hash"], password)
                except (InvalidHashError, VerificationError):
                    accepted = False
                finally:
                    self.auth.kdf_slots.release()
                if not accepted:
                    self.auth.rate(scope, count=5, seconds=900)
                    time.sleep(max(0, 0.15 - (time.monotonic()-started)))
                    raise DomainError("UNAUTHORIZED", "The Share password was not accepted.", 401)
        with self.lock:
            current = self.active(token)
            if current["policy_version"] != row["policy_version"]:
                raise DomainError("UNAUTHORIZED", "Share policy changed. Unlock again.", 401)
            return self.auth.issue(row["id"], "share", SESSION_TTL, row["policy_version"])

    def authorize(self, token, session_token, *, edit=False):
        row = self.active(token)
        session = self.auth.session(session_token, kind="share")
        if session["principal"] != row["id"] or session["policy_version"] != row["policy_version"]:
            raise DomainError("UNAUTHORIZED", "Unlock this Share again.", 401)
        if edit and row["permission"] != "edit":
            raise DomainError("FORBIDDEN", "This Share allows viewing only.", 403)
        return row, session

    def source(self, row):
        try:
            text = self.vault.read(row["path"])
        except DomainError as error:
            if error.status == 404:
                raise DomainError("TARGET_MISSING", "The shared note is currently unavailable.", 410) from None
            raise
        if len(text.encode("utf-8")) > self.vault.config.max_share_bytes:
            raise DomainError("SIZE_LIMIT", "The note exceeds the Shared size limit.", 413)
        return text

    def project(self, token, session_token):
        with self.lock:
            row, session = self.authorize(token, session_token)
            text = self.source(row)
            record = share_projection.partition(text)
            record.update(session_hash=digest(session_token), policy_version=row["policy_version"])
            identifier, sha, now = secrets.token_hex(16), sha_bytes(text.encode("utf-8")), time.time()
            encoded = json.dumps(record, ensure_ascii=False)
            with self.state.transaction() as db:
                db.execute("DELETE FROM projections WHERE expires_at<=?", (now,))
                db.execute("DELETE FROM projections WHERE share_id=? AND id IN (SELECT id FROM projections "
                           "WHERE share_id=? ORDER BY expires_at DESC LIMIT -1 OFFSET 9)", (row["id"], row["id"]))
                while True:
                    size, count = db.execute("SELECT COALESCE(SUM(length(CAST(record AS BLOB))),0), COUNT(*) FROM projections").fetchone()
                    if count < 1000 and size + len(encoded.encode("utf-8")) <= 64*1024**2:
                        break
                    db.execute("DELETE FROM projections WHERE id=(SELECT id FROM projections ORDER BY expires_at LIMIT 1)")
                db.execute("INSERT INTO projections VALUES(?,?,?,?,?)",
                           (identifier, row["id"], sha, min(now+SESSION_TTL, session["expires_at"]), encoded))
            return {"projection_id": identifier, "sha256": sha, "permission": row["permission"],
                    "title": PurePosixPath(row["path"]).stem,
                    **share_projection.public(record)}

    def save(self, token, session_token, projection_id, values, expected):
        if expected is None:
            raise DomainError("PRECONDITION_REQUIRED", "If-Match is required.", 428)
        with self.vault.coordinator.boundary() as operation_id:
            row, session = self.authorize(token, session_token, edit=True)
            projected = self.state.one("SELECT * FROM projections WHERE id=? AND share_id=? AND expires_at>?",
                                       (projection_id, row["id"], time.time()))
            if not projected:
                raise DomainError("PROJECTION_EXPIRED", "Reload the safe projection before saving.", 409)
            record = json.loads(projected["record"])
            if record["session_hash"] != session["token_hash"] or record["policy_version"] != row["policy_version"]:
                raise DomainError("UNAUTHORIZED", "This projection belongs to another session or policy.", 401)
            text = self.source(row)
            if expected != projected["sha"] or sha_bytes(text.encode("utf-8")) != expected:
                raise SharedConflict(self.project(token, session_token))
            result = share_projection.reconstruct(record, values, self.vault.config.max_share_bytes)
            # Recheck expiry/session after potentially expensive parsing, immediately before commit.
            self.authorize(token, session_token, edit=True)
            self.vault.coordinator.commit({row["path"]: result.encode("utf-8")}, {row["path"]: expected},
                                          inside_boundary=True, operation_id=operation_id)
            self.vault.index()
            self.audit.emit("share.edit", actor="share:" + row["id"], target=row["id"])
            return self.project(token, session_token)
