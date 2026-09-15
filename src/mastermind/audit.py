import json
import os
import re
import secrets
import sqlite3
import threading
import time
import zipfile
from contextlib import closing
from datetime import UTC, datetime

SENSITIVE = re.compile(
    r"password|passwd|secret|token|cookie|authorization|access.?key|api.?key|private.?key|"
    r"connection.?string|credential|request.?body|response.?body|content|note.?body|verifier|identity",
    re.IGNORECASE,
)
PATTERNS = (
    (re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----"), "[REDACTED]"),
    (re.compile(r"(?i)\bBearer\s+[^\s\"'<>]+"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)(?:https?|postgres(?:ql)?|redis|mysql)://[^\s\"'<>]+"), "[REDACTED_URL]"),
    (re.compile(r"/s/[A-Za-z0-9_-]+"), "/s/[REDACTED]"),
    (re.compile(r"\b(?:sk-[A-Za-z0-9_-]{8,}|AGE-SECRET-KEY-[A-Z0-9]+)\b"), "[REDACTED]"),
    (re.compile(r"(?i)\b(?:password|token|secret|api_key|access_key|cookie)\s*[=:]\s*[^\s,;]+"), "[REDACTED]"),
)


def redact(value, depth=0):
    if depth > 8:
        return "[DEPTH_LIMIT]"
    if isinstance(value, dict):
        return {str(k)[:128]: "[REDACTED]" if SENSITIVE.search(str(k)) else redact(v, depth+1)
                for k, v in list(value.items())[:64]}
    if isinstance(value, (list, tuple)):
        return [redact(item, depth+1) for item in value[:64]]
    if isinstance(value, str):
        for pattern, replacement in PATTERNS:
            value = pattern.sub(replacement, value)
        return value if len(value) <= 2048 else value[:2048] + " [TRUNCATED]"
    if isinstance(value, (float, int, bool)) or value is None:
        return value
    return "[UNSUPPORTED_VALUE]"


class Audit:
    def __init__(self, config, state):
        self.state = state
        self.directory = config.home / "logs"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def emit(self, action, *, outcome="success", actor="system", target=None, context=None,
             error=None, correlation_id=None):
        now = time.time()
        event = redact({
            "id": secrets.token_hex(16), "occurred_at": datetime.fromtimestamp(now, UTC).isoformat(),
            "severity": "info" if outcome == "success" else "warning" if outcome == "denied" else "error",
            "outcome": outcome, "action": action, "actor": {"type": actor, "id": actor},
            "target": {"type": "service_object", "id": target}, "summary": action,
            "correlation_id": correlation_id, "context": context or {}, "error": error,
        })
        encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > 16 * 1024:
            event["context"], event["error"] = {"truncated": True}, None
            encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with self.state.transaction() as db:
            db.execute("INSERT INTO audit(id,occurred_at,bytes,event) VALUES(?,?,?,?)",
                       (event["id"], now, len(encoded), encoded.decode("utf-8")))
            db.execute("DELETE FROM audit WHERE occurred_at<?", (now-30*86400,))
            db.execute("DELETE FROM audit WHERE sequence IN (SELECT sequence FROM audit "
                       "ORDER BY sequence DESC LIMIT -1 OFFSET 10000)")
            db.execute("DELETE FROM audit WHERE sequence IN (SELECT sequence FROM "
                       "(SELECT sequence,SUM(bytes) OVER (ORDER BY sequence DESC) AS size FROM audit) "
                       "WHERE size>?)", (64*1024**2,))
        self.append(encoded + b"\n")
        return event["id"]

    def append(self, encoded):
        with self.lock:
            active = self.directory / "events.jsonl"
            if active.exists() and active.stat().st_size + len(encoded) > 5*1024**2:
                active.rename(self.directory / f"events-{time.time_ns()}.jsonl")
            with os.fdopen(os.open(active, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600), "ab") as stream:
                stream.write(encoded)
            files = sorted(self.directory.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
            size = sum(p.stat().st_size for p in files)
            for path in files:
                if path != active and (path.stat().st_mtime < time.time()-30*86400 or size > 64*1024**2):
                    size -= path.stat().st_size
                    path.unlink()

    def page(self, after=0, limit=200):
        if after is None:
            rows = self.state.rows("SELECT sequence,event FROM audit ORDER BY sequence DESC LIMIT ?",
                                   (min(max(limit, 1), 1000),))
            return [{"sequence": r["sequence"], **json.loads(r["event"])} for r in reversed(rows)]
        rows = self.state.rows("SELECT sequence,event FROM audit WHERE sequence>? "
                               "ORDER BY sequence LIMIT ?", (max(0, after), min(max(limit, 1), 1000)))
        return [{"sequence": r["sequence"], **json.loads(r["event"])} for r in rows]

    def export(self, destination):
        self.emit("audit.export", actor="owner", target="audit")
        with closing(sqlite3.connect(self.state.path.as_uri()+"?mode=ro", uri=True)) as snapshot:
            snapshot.row_factory = sqlite3.Row
            snapshot.execute("BEGIN")
            boundary = snapshot.execute("SELECT COALESCE(MAX(sequence),0) FROM audit").fetchone()[0]
            deadline = time.monotonic()+120
            def page(after, limit):
                if time.monotonic() > deadline:
                    from .errors import DomainError
                    raise DomainError("EXPORT_TIMEOUT", "Log export exceeded its snapshot deadline.", 503)
                rows = snapshot.execute("SELECT sequence,event FROM audit WHERE sequence>? AND sequence<=? "
                                        "ORDER BY sequence LIMIT ?", (after, boundary, limit)).fetchall()
                return [{"sequence": row["sequence"], **json.loads(row["event"])} for row in rows]
            self._export_snapshot(destination, page, boundary)

    def _export_snapshot(self, destination, page, boundary):
        counts = {"events": 0, "errors": 0}
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            with archive.open("events.jsonl", "w", force_zip64=True) as stream:
                cursor = 0
                while values := page(cursor, 200):
                    for event in values:
                        stream.write(json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n")
                        counts["events"] += 1
                    cursor = values[-1]["sequence"]
            with archive.open("errors.json", "w", force_zip64=True) as stream:
                stream.write(b"[")
                cursor = 0
                while values := page(cursor, 200):
                    for event in values:
                        if event["error"] is not None:
                            if counts["errors"]:
                                stream.write(b",")
                            stream.write(json.dumps(event, ensure_ascii=False).encode("utf-8"))
                            counts["errors"] += 1
                    cursor = values[-1]["sequence"]
                stream.write(b"]")
            archive.writestr("manifest.json", json.dumps({"format": "mastermind-logs/v1", **counts, "boundary_sequence": boundary,
                                                         "limits": {"events": 10000, "days": 30,
                                                                    "bytes": 64*1024**2}}))
            archive.writestr("README.txt", "UTC timestamps; recursive redaction; correlation_id links events.\n"
                             "Retention: 10000 events, 30 days, 64 MiB. Unknown error fields remain null.\n")
