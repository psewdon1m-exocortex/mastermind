"""Owner edit-session checkpoints survive restart and full disaster recovery."""
import math
import re
import time

from .errors import DomainError
from .fs import safe_relative

IDENTITY = re.compile(r"[A-Za-z0-9_-]{1,128}$")


class Activity:
    def __init__(self, state):
        self.state = state

    @property
    def epoch(self):
        return self.state.one("SELECT value FROM metadata WHERE key='activity_epoch'")["value"]

    def ingest(self, envelope):
        if not isinstance(envelope, dict):
            raise DomainError("INVALID_ACTIVITY", "Activity checkpoint must be an object.", 422)
        epoch = self.epoch
        if envelope.get("epoch") != epoch:
            return {"accepted": 0, "reset": True, "epoch": epoch}
        events, sessions = envelope.get("events", []), envelope.get("sessions", [])
        if not isinstance(events, list) or not isinstance(sessions, list) or len(events)+len(sessions) > 10000:
            raise DomainError("INVALID_ACTIVITY", "Activity checkpoint exceeds its bounds.", 422)
        now = time.time()
        for record, time_key in [(e, "occurred_at") for e in events] + [(s, "last_activity_at") for s in sessions]:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) \
                    or not IDENTITY.fullmatch(record["id"]):
                raise DomainError("INVALID_ACTIVITY", "Activity identity is invalid.", 422)
            safe_relative(record.get("path"))
            value = record.get(time_key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(value) or value < 0 or value > now+300:
                raise DomainError("INVALID_ACTIVITY", "Activity time is invalid or in the future.", 422)
        with self.state.transaction() as db:
            for event in events:
                if event.get("kind") not in ("CREATE", "EDIT", "RENAME", "MOVE"):
                    raise DomainError("INVALID_ACTIVITY", "Activity kind is invalid.", 422)
                session_id = event.get("session_id")
                if session_id is not None and (not isinstance(session_id, str) or not IDENTITY.fullmatch(session_id)):
                    raise DomainError("INVALID_ACTIVITY", "Edit-session identity is invalid.", 422)
                db.execute("INSERT OR IGNORE INTO activity VALUES(?,?,?,?,?)",
                           (event["id"], session_id, event["kind"], event["path"], event["occurred_at"]))
                if session_id:
                    db.execute("DELETE FROM edit_sessions WHERE id=?", (session_id,))
            for session in sessions:
                if db.execute("SELECT 1 FROM activity WHERE session_id=?", (session["id"],)).fetchone():
                    continue
                db.execute("INSERT INTO edit_sessions VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET "
                           "path=excluded.path,last_activity_at=MAX(last_activity_at,excluded.last_activity_at)",
                           (session["id"], session["path"], session["last_activity_at"]))
            if db.execute("SELECT COUNT(*) FROM edit_sessions").fetchone()[0] > 10000:
                raise DomainError("INVALID_ACTIVITY", "Too many active edit sessions.", 429)
            self.expire(now=now)
        return {"accepted": len(events), "reset": False, "epoch": epoch}

    def expire(self, now=None):
        now = time.time() if now is None else now
        with self.state.transaction() as db:
            db.execute("INSERT OR IGNORE INTO activity SELECT id,id,'EDIT',path,last_activity_at FROM edit_sessions "
                       "WHERE last_activity_at<=?", (now-300,))
            db.execute("DELETE FROM edit_sessions WHERE last_activity_at<=?", (now-300,))
