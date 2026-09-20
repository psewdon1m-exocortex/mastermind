"""Durable source acceptance and scoped, progress-only Crusher capabilities."""
import hashlib
import json
import os
import re
import secrets
import shutil
import threading
import time
from pathlib import PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from .auth import digest
from .errors import DomainError
from .fs import atomic_write, sha_bytes, sha_file, write_existing_under

PROGRESS = {"QUEUED": 0, "ACQUIRING": 5, "NORMALIZING": 15, "EXTRACTING": 20, "UNDERSTANDING": 40,
            "PLACING": 55, "GENERATING": 65, "VALIDATING": 85, "COMMITTING": 95, "COMPLETED": 100}
TERMINAL = ("COMPLETED", "FAILED")


def label(value):
    return "".join(c for c in value if c.isprintable() and c not in "<>\\/")[:160] or "Source"


def public_url(value):
    try:
        if not isinstance(value, str) or len(value) > 8192 or any(c.isspace() or ord(c) < 32 for c in value):
            raise ValueError
        parsed = urlsplit(value)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username is not None \
                or parsed.password is not None or parsed.port not in (None, 80, 443) or "\\" in value:
            raise ValueError
        # DNS/address validation and pinning happen at the actual worker connection.
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
    except (ValueError, TypeError):
        raise DomainError("SOURCE_URL_INVALID", "Use a public HTTP or HTTPS URL without credentials or a custom port.", 422) from None


class CrusherAccess:
    def __init__(self, config, state, auth, audit, ready=lambda: None):
        self.config, self.state, self.auth, self.audit, self.ready = config, state, auth, audit, ready
        self.directory = config.home / "incoming"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.upload_slots = threading.BoundedSemaphore(2)
        self.uploading = set()
        self.configuration_snapshot = lambda: None

    def code(self, *, actor_key=None):
        self.ready()
        now = time.time()
        with self.state.transaction() as db:
            db.execute("DELETE FROM codes WHERE expires_at<=? OR consumed_at IS NOT NULL", (now,))
            if db.execute("SELECT COUNT(*) FROM codes").fetchone()[0] >= 10:
                raise DomainError("CODE_LIMIT", "At most ten unconsumed Crusher codes can be active.", 409)
            for _ in range(100):
                code = f"{secrets.randbelow(1_000_000):06d}"
                if not db.execute("SELECT 1 FROM codes WHERE code_hash=? UNION ALL SELECT 1 FROM gryphon_access WHERE code_hash=?",
                                  (digest(code), digest(code))).fetchone():
                    break
            else:
                raise DomainError("CODE_UNAVAILABLE", "Could not allocate a Crusher code.", 503)
            db.execute("INSERT INTO codes VALUES(?,?,?,NULL)", (digest(code), now, now+1800))
            if actor_key is not None:
                db.execute("INSERT INTO gryphon_access VALUES(?,?,NULL,?)", (digest(code), actor_key, now+1800))
        self.audit.emit("crusher.access.create", actor="telegram" if actor_key else "owner", target="crusher")
        return {"code": code, "expires_at": now+1800}

    def activate(self, code, address):
        self.ready()
        self.auth.rate("crusher-activation:" + digest(address), count=10, seconds=600)
        self.auth.rate("crusher-activation-global", count=30, seconds=600)
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
            raise DomainError("CODE_INVALID", "The code is invalid, expired or already used.", 401)
        with self.state.transaction() as db:
            changed = db.execute("UPDATE codes SET consumed_at=? WHERE code_hash=? AND consumed_at IS NULL AND expires_at>?",
                                 (time.time(), digest(code), time.time())).rowcount
            if changed != 1:
                raise DomainError("CODE_INVALID", "The code is invalid, expired or already used.", 401)
            principal = "crusher:" + secrets.token_hex(16)
            session = self.auth.issue(principal, "crusher", 1800)
            db.execute("UPDATE gryphon_access SET session_principal=?,expires_at=? WHERE code_hash=?",
                       (principal, session["expires_at"], digest(code)))
        return {"token": session["token"], "expires_at": session["expires_at"]}

    def principal(self, bearer):
        return self.auth.session(bearer, kind="crusher")

    def revoke_telegram(self, actor_key=None):
        with self.state.transaction() as db:
            clause, args = (" WHERE actor_key=?", (actor_key,)) if actor_key else ("", ())
            codes = db.execute("DELETE FROM codes WHERE code_hash IN (SELECT code_hash FROM gryphon_access" + clause + ")", args).rowcount
            sessions = db.execute("DELETE FROM sessions WHERE kind='crusher' AND principal IN "
                                  "(SELECT session_principal FROM gryphon_access" + clause + ")", args).rowcount
            db.execute("DELETE FROM gryphon_access" + clause, args)
        self.audit.emit("crusher.access.revoke", actor="telegram" if actor_key else "owner", target="crusher",
                        context={"codes": codes, "sessions": sessions})
        return {"codes": codes, "sessions": sessions}

    def check_principal(self, principal):
        if principal == "owner":
            return
        if not isinstance(principal, str) or not self.state.one(
            "SELECT 1 FROM sessions WHERE principal=? AND kind='crusher' AND expires_at>?", (principal, time.time())
        ):
            raise DomainError("UNAUTHORIZED", "An active Crusher session is required for acceptance.", 401)

    def reserved(self):
        uploads = self.state.one("SELECT COALESCE(SUM(size),0) AS n FROM uploads WHERE state!='ACCEPTED'")["n"]
        jobs = sum(json.loads(row["record"]).get("reserved_bytes", 0) for row in self.state.rows(
            "SELECT record FROM jobs WHERE state NOT IN ('COMPLETED','FAILED') OR updated_at>?", (time.time()-86400,)))
        return uploads + jobs

    def reserve(self, required, credit=0):
        if required < 0 or self.reserved() + required - credit > self.config.incoming_quota \
                or shutil.disk_usage(self.directory).free < required + 64*1024**2:
            raise DomainError("INSUFFICIENT_SPACE", "Crusher incoming/work space cannot cover this source.", 507)

    def upload(self, principal, name, size):
        self.ready()
        if not isinstance(name, str) or not name or len(name) > 255 or PurePosixPath(name).name != name \
                or any(c in name for c in "\\/\0\r\n"):
            raise DomainError("SOURCE_NAME_INVALID", "Use a file name without directory components.", 422)
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= self.config.max_upload_bytes:
            raise DomainError("SOURCE_SIZE_INVALID", "Source size must be between one byte and 2 GiB.", 413)
        with self.lock, self.state.transaction() as db:
            self.check_principal(principal)
            self.cleanup()
            if db.execute("SELECT COUNT(*) FROM uploads WHERE state IN ('RESERVED','RECEIVING')").fetchone()[0] >= 2:
                raise DomainError("UPLOAD_BUSY", "Two source uploads are already reserved.", 429)
            self.reserve(size)
            identifier, now = secrets.token_hex(16), time.time()
            expires = now+1800
            if principal != "owner":
                expires = min(expires, self.state.one("SELECT MAX(expires_at) AS until FROM sessions WHERE principal=? AND kind='crusher'",
                                                       (principal,))["until"])
            db.execute("INSERT INTO uploads VALUES(?,?,?,?,?,NULL,'RESERVED',?)",
                       (identifier, principal, now, expires, size, name))
            try:
                atomic_write(self.directory / identifier, b"")
            except OSError:
                db.execute("DELETE FROM uploads WHERE id=?", (identifier,))
                raise
        return {"upload_id": identifier, "size": size, "expires_at": expires}

    def upload_row(self, identifier, principal):
        row = self.state.one("SELECT * FROM uploads WHERE id=? AND principal=? AND expires_at>?",
                             (identifier, principal, time.time()))
        if not row:
            raise DomainError("UPLOAD_UNAVAILABLE", "The upload is missing, expired or belongs to another session.", 404)
        return row

    def begin_upload(self, identifier, principal):
        self.ready()
        with self.lock:
            self.check_principal(principal)
            row = self.upload_row(identifier, principal)
            if row["state"] != "RESERVED" or identifier in self.uploading or not self.upload_slots.acquire(blocking=False):
                raise DomainError("UPLOAD_BUSY", "The upload cannot be written in its current state.", 409)
            self.uploading.add(identifier)
            with self.state.transaction() as db:
                db.execute("UPDATE uploads SET state='RECEIVING' WHERE id=?", (identifier,))
            return row

    def finish_upload(self, identifier, principal, size, content_sha, success):
        with self.lock:
            try:
                row = self.upload_row(identifier, principal)
                self.check_principal(principal)
                if not success or size != row["size"]:
                    raise DomainError("UPLOAD_INCOMPLETE", "The source length did not match its reservation.", 422)
                with self.state.transaction() as db:
                    db.execute("UPDATE uploads SET state='RECEIVED',sha=? WHERE id=?", (content_sha, identifier))
            except BaseException:
                self.discard_upload(identifier)
                raise
            finally:
                self.uploading.discard(identifier)
                self.upload_slots.release()

    def complete_upload(self, identifier, principal, expected):
        self.ready()
        with self.lock, self.state.transaction() as db:
            self.check_principal(principal)
            row = self.upload_row(identifier, principal)
            if row["state"] not in ("RECEIVED", "COMPLETE") or not isinstance(expected, str) \
                    or not re.fullmatch(r"[a-f0-9]{64}", expected) or expected != row["sha"] \
                    or sha_file(self.directory / identifier) != expected:
                raise DomainError("SOURCE_INTEGRITY", "The completed source failed its integrity check.", 422)
            db.execute("UPDATE uploads SET state='COMPLETE' WHERE id=?", (identifier,))
            return {"upload_id": identifier, "size": row["size"], "sha256": row["sha"]}

    def discard_upload(self, identifier):
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise ValueError("Invalid upload identity")
        (self.directory / identifier).unlink(missing_ok=True)
        with self.state.transaction() as db:
            db.execute("DELETE FROM uploads WHERE id=?", (identifier,))

    def accept(self, principal, key, source):
        self.ready()
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
            raise DomainError("IDEMPOTENCY_REQUIRED", "Provide a stable 16–128 character Idempotency-Key.", 428)
        if not isinstance(source, dict) or source.get("type") not in ("text", "url", "youtube", "git", "upload", "saturn"):
            raise DomainError("SOURCE_INVALID", "Choose a supported source type.", 422)
        kind = source["type"]
        fields = {"text": "text", "url": "url", "youtube": "url", "git": "url", "upload": "upload_id", "saturn": "path"}
        field = fields[kind]
        if set(source) != {"type", field} or not isinstance(source[field], str):
            raise DomainError("SOURCE_INVALID", "Source fields do not match its type.", 422)
        payload = None
        if kind == "text":
            payload = source["text"].encode("utf-8")
            if not payload or len(payload) > 1024**2:
                raise DomainError("SIZE_LIMIT", "Text sources must contain between one byte and 1 MiB.", 413)
            accepted_label, required = "Text source", len(payload)*2 + 1024**2
        elif kind in ("url", "youtube", "git"):
            source = {"type": kind, "url": public_url(source["url"])}
            accepted_label = kind.capitalize() + " · " + urlsplit(source["url"]).hostname
            required = self.config.max_upload_bytes*2 + 8*1024**3
        elif kind == "saturn":
            if principal != "owner":
                raise DomainError("FORBIDDEN", "Saturn sources require an owner selection.", 403)
            from .integrations import resource_path
            resource_path(source["path"])
            accepted_label = "Saturn file"
            required = self.config.max_upload_bytes*2 + 8*1024**3
        else:
            accepted_label, required = "Uploaded file", 0
        source_digest = sha_bytes(json.dumps(source, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
        # Snapshot before acquiring the State transaction: canonical reads use the
        # opposite (coordinator, State) lock order. Replays do not depend on current config.
        previous = self.state.one("SELECT * FROM jobs WHERE principal=? AND idempotency_key=?", (principal, key))
        if previous:
            self.check_principal(principal)
            if previous["source_digest"] != source_digest:
                raise DomainError("IDEMPOTENCY_CONFLICT", "This key was already used for a different source.", 409)
            return self.receipt(previous)
        configuration = self.configuration_snapshot()
        now, identifier = time.time(), secrets.token_hex(16)
        with self.lock, self.state.transaction() as db:
            self.check_principal(principal)
            previous = self.state.one("SELECT * FROM jobs WHERE principal=? AND idempotency_key=?", (principal, key))
            if previous:
                if previous["source_digest"] != source_digest:
                    raise DomainError("IDEMPOTENCY_CONFLICT", "This key was already used for a different source.", 409)
                return self.receipt(previous)
            counts = db.execute("SELECT COUNT(*),COALESCE(SUM(principal=?),0) FROM jobs WHERE state NOT IN ('COMPLETED','FAILED')",
                                (principal,)).fetchone()
            if counts[0] >= 100 or principal != "owner" and counts[1] >= 20:
                raise DomainError("QUEUE_FULL", "The Crusher acceptance queue is full.", 429)
            record = {"source": source.copy(), "source_label": accepted_label, "deadline": now+3600,
                      "transitions": [{"state": "QUEUED", "at": now}], "attempts": {}, "results": {}}
            if configuration is not None:
                record["context_snapshot"] = configuration
                record["pipeline_version"] = "context-indexing.v1"
            upload = None
            if kind == "upload":
                upload = self.upload_row(source["upload_id"], principal)
                if upload["state"] != "COMPLETE":
                    raise DomainError("SOURCE_UNAVAILABLE", "Complete this upload before accepting a job.", 409)
                if sha_file(self.directory / upload["id"]) != upload["sha"]:
                    raise DomainError("SOURCE_INTEGRITY", "The source changed after completion.", 409)
                required = upload["size"]*2 + 8*1024**3
                record.update(source_label=label(upload["name"]), local_source=upload["id"],
                              source_name=upload["name"], local_sha=upload["sha"])
            self.reserve(required, upload["size"] if upload else 0)
            record["reserved_bytes"] = required
            if payload is not None:
                atomic_write(self.directory / identifier, payload)
                record.update(local_source=identifier, local_sha=sha_bytes(payload), source_name="source.txt")
                record["source"] = {"type": "text"}
            try:
                db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,NULL,NULL)",
                           (identifier, principal, key, source_digest, "QUEUED", "QUEUED", 0, now, now, json.dumps(record)))
                if upload:
                    db.execute("UPDATE uploads SET state='ACCEPTED' WHERE id=?", (upload["id"],))
                row = self.state.one("SELECT * FROM jobs WHERE id=?", (identifier,))
                result = self.receipt(row)
            except BaseException:
                if payload is not None:
                    (self.directory / identifier).unlink(missing_ok=True)
                raise
        self.audit.emit("crusher.accept", actor=principal, target=identifier)
        return result

    def receipt(self, row):
        ticket = self.auth.issue(row["id"], "crusher-status", 86400)
        return {**self.sanitize(row), "status_ticket": ticket["token"], "ticket_expires_at": ticket["expires_at"]}

    @staticmethod
    def sanitize(row):
        record = json.loads(row["record"])
        return {"job_id": row["id"], "source_label": record.get("source_label", "Source"), "state": row["state"],
                "stage": row["stage"], "progress_percent": row["progress"], "created_at": row["created_at"],
                "updated_at": row["updated_at"], "error": record.get("public_error", record.get("error"))}

    def status(self, identifier, principal=None, ticket=None):
        row = self.state.one("SELECT * FROM jobs WHERE id=?", (identifier,))
        if ticket:
            session = self.auth.session(ticket, kind="crusher-status")
            allowed = session["principal"] == identifier
        else:
            allowed = row and (principal == "owner" or row["principal"] == principal)
        if not row or not allowed:
            raise DomainError("NOT_FOUND", "Job not found.", 404)
        return self.sanitize(row)

    def list(self, principal, limit=100, offset=0):
        return [self.sanitize(row) for row in self.state.rows("SELECT * FROM jobs WHERE principal=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                                                             (principal, min(max(limit, 1), 100), max(offset, 0)))]

    def cleanup(self):
        with self.lock:
            for row in self.state.rows("SELECT * FROM uploads WHERE expires_at<=? AND state!='ACCEPTED'", (time.time(),)):
                if row["id"] not in self.uploading:
                    self.discard_upload(row["id"])
            retained = {json.loads(row["record"]).get("local_source") for row in self.state.rows(
                "SELECT record FROM jobs WHERE state NOT IN ('COMPLETED','FAILED') OR updated_at>?", (time.time()-86400,))}
            retained.update(row["id"] for row in self.state.rows("SELECT id FROM uploads WHERE state!='ACCEPTED'"))
            for path in self.directory.iterdir():
                if re.fullmatch(r"[a-f0-9]{32}", path.name) and path.name not in retained and path.name not in self.uploading \
                        and path.is_file() and path.stat().st_mtime < time.time()-1800:
                    path.unlink()
            with self.state.transaction() as db:
                db.execute("DELETE FROM uploads WHERE state='ACCEPTED' AND expires_at<?", (time.time()-86400,))
                db.execute("DELETE FROM gryphon_access WHERE expires_at<=?", (time.time(),))
                db.execute("DELETE FROM gryphon_events WHERE created_at<=?", (time.time()-7*86400,))

    async def receive(self, identifier, principal, chunks):
        import asyncio
        row = self.begin_upload(identifier, principal)
        size, content_hash, success = 0, hashlib.sha256(), False
        try:
            with write_existing_under(self.directory, identifier) as output:
                async with asyncio.timeout(900):
                    iterator = chunks.__aiter__()
                    while True:
                        try:
                            chunk = await asyncio.wait_for(iterator.__anext__(), timeout=60)
                        except StopAsyncIteration:
                            break
                        if size + len(chunk) > row["size"] or time.time() >= row["expires_at"]:
                            raise DomainError("UPLOAD_INCOMPLETE", "Upload exceeded its reservation or session lifetime.", 413)
                        output.write(chunk)
                        content_hash.update(chunk)
                        size += len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
            success = True
        except TimeoutError:
            raise DomainError("SOURCE_TIMEOUT", "Upload did not finish within its deadline.", 408) from None
        finally:
            if success:
                self.finish_upload(identifier, principal, size, content_hash.hexdigest(), True)
            else:
                with self.lock:
                    self.discard_upload(identifier)
                    self.uploading.discard(identifier)
                    self.upload_slots.release()
        return {"received": True, "size": size, "sha256": content_hash.hexdigest()}
