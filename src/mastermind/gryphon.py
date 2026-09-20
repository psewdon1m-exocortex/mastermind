"""Service-scoped Gryphon transport and atomic, encrypted command replay receipts."""
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from datetime import UTC, datetime

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .auth import digest
from .errors import DomainError
from .secret_store import read_credential_file

CATALOG = [
    {"name": "crusher", "description": "Create a Mastermind Crusher code", "adapterCommand": "crusher"},
    {"name": "crusher_status", "description": "Show Mastermind Crusher access", "adapterCommand": "status"},
    {"name": "crusher_revoke", "description": "Revoke Mastermind Crusher access", "adapterCommand": "revoke"},
]


def catalog_matches(commands):
    return isinstance(commands, list) and len(commands) == len(CATALOG) and all(item in commands for item in CATALOG)


def invalid():
    return DomainError("GRYPHON_PROTOCOL", "Gryphon returned an incompatible service response. Upgrade or repair the gateway.", 503)


def response(text, buttons=None):
    action = {"type": "send_message", "text": text}
    if buttons:
        action["buttons"] = buttons
    return {"schema": "exocortex.telegram.response.v1", "actions": [action]}


class Gryphon:
    def __init__(self, service, *, transport=None):
        self.service, self.config = service, service.config
        self.transport = transport
        self.command_lock = threading.RLock()
        self.last_status = None
        self.next_reconcile = 0
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        def maintain():
            while not self.service.stop_event.is_set():
                self.reconcile()
                if self.service.stop_event.wait(60):
                    break
        self.thread = threading.Thread(target=maintain, name="mastermind-gryphon", daemon=True)
        self.thread.start()

    def close(self):
        if self.thread:
            self.thread.join(timeout=15)

    def token(self):
        path = self.config.gryphon_token_file
        if path is None:
            raise DomainError("GRYPHON_NOT_CONFIGURED", "Initialize the scoped Gryphon client first.", 503)
        value = read_credential_file(path).rstrip("\r\n")
        if not value or len(value) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise DomainError("GRYPHON_CREDENTIAL", "The Gryphon client credential is unavailable.", 503)
        return value

    def authenticate(self, authorization):
        supplied = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        if not supplied or not hmac.compare_digest(digest(supplied), digest(self.token())):
            raise DomainError("UNAUTHORIZED", "Gryphon service authentication is required.", 401)

    def call(self, method, route, data=None):
        if not self.config.gryphon_socket:
            raise DomainError("GRYPHON_NOT_CONFIGURED", "Initialize the scoped Gryphon client first.", 503)
        token = self.token()
        try:
            with httpx.Client(transport=self.transport or httpx.HTTPTransport(uds=self.config.gryphon_socket),
                              base_url="http://gryphon.local", timeout=httpx.Timeout(5, connect=2),
                              follow_redirects=False, trust_env=False) as client, \
                    client.stream(method, route, headers={"Authorization": "Bearer " + token, "Accept-Encoding": "identity"},
                                  **({"json": data} if data is not None else {})) as remote:
                if remote.status_code >= 300:
                    status = remote.status_code if remote.status_code in (401, 403, 404, 409, 429) else 503
                    raise DomainError("GRYPHON_REJECTED", "Gryphon rejected this operation. Refresh the connection and retry.", status)
                body, deadline = bytearray(), time.monotonic()+5
                for block in remote.iter_bytes(16384):
                    body.extend(block)
                    if len(body) > 65536 or time.monotonic() > deadline:
                        raise invalid()
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise invalid()
                return result
        except (httpx.HTTPError, OSError, ValueError, RecursionError):
            raise DomainError("GRYPHON_UNAVAILABLE", "Gryphon is unavailable. The last verified binding is retained.", 503) from None

    def observed(self):
        value = self.call("GET", "/v1/service")
        if value.get("schema") != "exocortex.gryphon.service-status.v1" or value.get("serviceId") != "mastermind" \
                or type(value.get("connected")) is not bool or not isinstance(value.get("version"), str):
            raise invalid()
        if value["connected"]:
            if not isinstance(value.get("connectionId"), str) or not isinstance(value.get("bot"), dict) \
                    or value.get("commandPrefix") != "mastermind":
                raise invalid()
            binding = value.get("binding")
            if binding is not None and (not isinstance(binding, dict) or any(
                not isinstance(binding.get(key), str) or not re.fullmatch(r"[1-9][0-9]{0,18}", binding[key])
                for key in ("telegramUserId", "chatId")
            )):
                raise invalid()
        elif value.get("bot") is not None or value.get("binding") is not None:
            raise invalid()
        # Project only documented fields; credentials or future admin fields never reach the browser.
        bot = value.get("bot")
        binding = value.get("binding")
        result = {key: value.get(key) for key in ("schema", "version", "serviceId", "state", "connected", "connectionId", "commandPrefix", "commands")}
        result["bot"] = {key: bot.get(key) for key in ("id", "alias", "username", "state")} if bot else None
        result["binding"] = {key: binding.get(key) for key in ("linkedAt", "telegramUserId", "chatId")} if binding else None
        result.update(reachable=True, enrolled=True, verified_at=time.time())
        self.last_status = result
        return result

    def status(self):
        try:
            return self.observed()
        except DomainError as error:
            return {**(self.last_status or {}), "reachable": False, "enrolled": False,
                    "state": "UNAVAILABLE" if self.last_status else "NOT_CONFIGURED" if error.code in {
                        "GRYPHON_NOT_CONFIGURED", "SECRET_UNAVAILABLE"} else "UNAVAILABLE",
                    "code": error.code, "message": str(error), "last_known": bool(self.last_status)}

    def bots(self):
        value = self.call("GET", "/v1/service/bots")
        if value.get("schema") != "exocortex.gryphon.service-bots.v1" or value.get("serviceId") != "mastermind" \
                or not isinstance(value.get("bots"), list) or len(value["bots"]) > 100:
            raise invalid()
        return {"bots": [{key: item.get(key) for key in ("id", "alias", "username", "state", "selected")}
                         for item in value["bots"] if isinstance(item, dict)]}

    def sync_catalog(self):
        result = self.call("PUT", "/v1/service/command-catalog", {"schema": "exocortex.telegram.command-catalog.v1", "commands": CATALOG})
        if result.get("serviceId") != "mastermind" or not catalog_matches(result.get("commands")):
            raise invalid()

    def reconcile(self):
        if time.monotonic() < self.next_reconcile:
            return
        self.next_reconcile = time.monotonic()+60
        with self.service.state.transaction() as db:
            db.execute("DELETE FROM gryphon_events WHERE created_at<=?", (time.time()-7*86400,))
            db.execute("DELETE FROM gryphon_access WHERE expires_at<=?", (time.time(),))
        if not self.config.gryphon_socket:
            return
        try:
            status = self.observed()
            if status["connected"] and not catalog_matches(status.get("commands")):
                self.sync_catalog()
        except DomainError:
            pass  # Optional gateway readiness does not block Vault or owner Crusher access.

    @staticmethod
    def validate(data):
        if not isinstance(data, dict) or set(data) != {"schema", "eventId", "correlationId", "connectionId", "serviceId", "actor", "command", "arguments"} \
                or data["schema"] != "exocortex.telegram.command.v1" or data["serviceId"] != "mastermind" \
                or any(not isinstance(data[key], str) or not re.fullmatch(r"[A-Za-z0-9:_-]{1,200}", data[key])
                       for key in ("eventId", "correlationId", "connectionId")) \
                or data["command"] not in ("start", "menu", "crusher", "status", "revoke", "binding_revoked") \
                or not isinstance(data["arguments"], dict) or set(data["arguments"]) - {"text"} \
                or not isinstance(data["arguments"].get("text", ""), str) or len(data["arguments"].get("text", "")) > 1000:
            raise DomainError("INVALID_COMMAND", "Invalid Mastermind command envelope.", 422)
        actor = data["actor"]
        if not isinstance(actor, dict) or set(actor) - {"telegramUserId", "chatId", "chatType", "displayName"} \
                or actor.get("chatType") != "private" or any(
                    not isinstance(actor.get(key), str) or not re.fullmatch(r"[1-9][0-9]{0,18}", actor[key])
                    for key in ("telegramUserId", "chatId")) \
                or not isinstance(actor.get("displayName", ""), str) or len(actor.get("displayName", "")) > 256:
            raise DomainError("INVALID_ACTOR", "A stable private Telegram identity is required.", 422)

    def command(self, data):
        self.validate(data)
        self.service.data_ready()
        with self.command_lock:
            status = self.observed()
            actor, binding = data["actor"], status.get("binding")
            if not status["connected"] or status["state"] != "enabled" or status["bot"]["state"] != "ready" \
                    or status["connectionId"] != data["connectionId"] or not binding \
                    or any(binding[key] != actor[key] for key in ("telegramUserId", "chatId")):
                raise DomainError("GRYPHON_ACTOR_DENIED", "This Telegram identity is not linked to Mastermind.", 403)
            actor_key = digest(json.dumps([data["connectionId"], actor["telegramUserId"], actor["chatId"]]))
            # correlationId changes on gateway retries; display names are not authorization data.
            identity = {key: data[key] for key in ("connectionId", "serviceId", "command", "arguments")}
            identity["actor"] = actor_key
            request_sha = digest(json.dumps(identity, sort_keys=True, separators=(",", ":")))
            cipher = AESGCM(hashlib.sha256(("mastermind.gryphon.receipt.v1:"+self.token()).encode()).digest())
            associated = (data["eventId"]+":"+request_sha).encode()
            state = self.service.state
            with state.transaction() as db:
                db.execute("DELETE FROM gryphon_events WHERE created_at<=?", (time.time()-7*86400,))
                previous = state.one("SELECT * FROM gryphon_events WHERE event_id=?", (data["eventId"],))
                if previous:
                    if previous["request_sha"] != request_sha:
                        raise DomainError("GRYPHON_REPLAY_CONFLICT", "This event was already used for another command.", 409)
                    try:
                        packed = previous["response"]
                        return json.loads(cipher.decrypt(packed[:12], packed[12:], associated))
                    except (InvalidTag, ValueError):
                        raise DomainError("GRYPHON_REPLAY_UNAVAILABLE", "This old event cannot be replayed. Send a new command.", 409) from None
                if db.execute("SELECT COUNT(*) FROM gryphon_events").fetchone()[0] >= 10000:
                    raise DomainError("GRYPHON_EVENT_LIMIT", "The command replay journal is full. Retry later.", 503)
                access = self.service.crusher_access
                command = data["command"]
                if command == "crusher":
                    self.service.auth.rate("gryphon-code:"+actor_key, count=10, seconds=600)
                    code = access.code(actor_key=actor_key)
                    expires = datetime.fromtimestamp(code["expires_at"], UTC).isoformat()
                    result = response(f"Mastermind Crusher code: {code['code']}\nOpen Crusher: {self.config.public_url.rstrip('/')}/crusher\n"
                                      f"Expires: {expires}\nUse this code once on that page. It grants source submission only.")
                elif command in ("revoke", "binding_revoked"):
                    revoked = access.revoke_telegram(actor_key)
                    result = response(f"Mastermind Crusher access revoked: {revoked['sessions']} session(s), {revoked['codes']} code(s).")
                elif command == "status":
                    codes = state.one("SELECT COUNT(*) AS n FROM codes JOIN gryphon_access USING(code_hash) "
                                      "WHERE actor_key=? AND codes.expires_at>? AND consumed_at IS NULL", (actor_key, time.time()))["n"]
                    sessions = state.one("SELECT COUNT(*) AS n FROM sessions JOIN gryphon_access ON principal=session_principal "
                                         "WHERE actor_key=? AND sessions.expires_at>?", (actor_key, time.time()))["n"]
                    result = response(f"Mastermind Crusher: {codes} active code(s), {sessions} active session(s).\n{self.config.public_url.rstrip('/')}/crusher")
                else:
                    result = response("Mastermind Crusher — submit links or files to create notes.", [
                        [{"text": "Create Crusher code", "command": "crusher"}, {"text": "Status", "command": "status"}],
                        [{"text": "Revoke Crusher access", "command": "revoke"}]])
                nonce = secrets.token_bytes(12)
                packed = nonce+cipher.encrypt(nonce, json.dumps(result).encode(), associated)
                db.execute("INSERT INTO gryphon_events VALUES(?,?,?,?)", (data["eventId"], request_sha, time.time(), packed))
            self.service.audit.emit("gryphon.command", actor="telegram", target="crusher", context={"command": command})
            return result
