import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from .errors import DomainError

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reference_history(kind TEXT NOT NULL,name_key TEXT NOT NULL,display TEXT NOT NULL,
 PRIMARY KEY(kind,name_key));
CREATE TABLE IF NOT EXISTS notes(path TEXT PRIMARY KEY,name_key TEXT NOT NULL UNIQUE,name TEXT NOT NULL,
 sha TEXT NOT NULL,size INTEGER NOT NULL,tags TEXT NOT NULL DEFAULT '[]',mtime_ns INTEGER NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5(path UNINDEXED,name,body,tags,tokenize='unicode61');
CREATE TABLE IF NOT EXISTS edges(source TEXT NOT NULL,target_key TEXT NOT NULL,kind TEXT NOT NULL,
 broken INTEGER NOT NULL,PRIMARY KEY(source,target_key,kind));
CREATE TABLE IF NOT EXISTS semantic_documents(path TEXT PRIMARY KEY,source_sha TEXT NOT NULL,model_sha TEXT NOT NULL,
 spans TEXT NOT NULL,next_chunk INTEGER NOT NULL DEFAULT 0,completed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS semantic_chunks(path TEXT NOT NULL,ordinal INTEGER NOT NULL,start INTEGER NOT NULL,
 end INTEGER NOT NULL,source_sha TEXT NOT NULL,model_sha TEXT NOT NULL,vector BLOB NOT NULL,
 PRIMARY KEY(path,ordinal));
CREATE TABLE IF NOT EXISTS semantic_run(id INTEGER PRIMARY KEY CHECK(id=1),deadline REAL NOT NULL,error TEXT);
CREATE TABLE IF NOT EXISTS activity(id TEXT PRIMARY KEY,session_id TEXT,kind TEXT NOT NULL,path TEXT NOT NULL,
 occurred_at REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS activity_session ON activity(session_id) WHERE session_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS edit_sessions(id TEXT PRIMARY KEY,path TEXT NOT NULL,last_activity_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS shares(id TEXT PRIMARY KEY,token_hmac TEXT NOT NULL UNIQUE,pepper_key_id TEXT NOT NULL,
 path TEXT NOT NULL,permission TEXT NOT NULL,password_hash TEXT,created_at REAL NOT NULL,updated_at REAL NOT NULL,
 expires_at REAL,revoked_at REAL,policy_version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,principal TEXT NOT NULL,kind TEXT NOT NULL,
 created_at REAL NOT NULL,expires_at REAL NOT NULL,policy_version INTEGER NOT NULL DEFAULT 0,csrf_hash TEXT);
CREATE TABLE IF NOT EXISTS codes(code_hash TEXT PRIMARY KEY,created_at REAL NOT NULL,expires_at REAL NOT NULL,
 consumed_at REAL);
CREATE TABLE IF NOT EXISTS rate_limits(scope TEXT NOT NULL,occurred_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS rate_scope ON rate_limits(scope,occurred_at);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,principal TEXT NOT NULL,idempotency_key TEXT NOT NULL,
 source_digest TEXT NOT NULL,state TEXT NOT NULL,stage TEXT NOT NULL,progress INTEGER NOT NULL DEFAULT 0,
 created_at REAL NOT NULL,updated_at REAL NOT NULL,record TEXT NOT NULL,
 leased_by TEXT,lease_expires_at REAL,UNIQUE(principal,idempotency_key));
CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY,principal TEXT NOT NULL,created_at REAL NOT NULL,
 expires_at REAL NOT NULL,size INTEGER NOT NULL DEFAULT 0,sha TEXT,state TEXT NOT NULL,name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,state TEXT NOT NULL,created_at REAL NOT NULL,
 metadata TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(path TEXT PRIMARY KEY,generation INTEGER NOT NULL,occurred_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit(sequence INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL UNIQUE,
 occurred_at REAL NOT NULL,bytes INTEGER NOT NULL,event TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS projections(id TEXT PRIMARY KEY,share_id TEXT NOT NULL,sha TEXT NOT NULL,
 expires_at REAL NOT NULL,record TEXT NOT NULL);
"""
MANDATORY_TABLES = (
    "metadata", "settings", "reference_history", "activity", "edit_sessions", "shares", "jobs", "operations", "outbox"
)
DERIVED_TABLES = ("notes", "note_fts", "edges", "semantic_documents", "semantic_chunks", "semantic_run")
EPHEMERAL_TABLES = ("sessions", "codes", "rate_limits", "uploads", "projections")


class State:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.reopen()

    def reopen(self):
        self.closed = True
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=30)
        self.db.row_factory = sqlite3.Row
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'").fetchone():
            version = self.db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()
            if version and version[0] != "1":
                self.db.close()
                raise DomainError("SCHEMA_UNSUPPORTED", "This Core image cannot open the stored schema.", 503)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES('schema','1')")
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES('generation','0')")
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES('activity_epoch',?)", (uuid.uuid4().hex,))
        self.closed = False

    @contextmanager
    def transaction(self):
        with self.lock:
            if self.db.in_transaction:
                yield self.db
                return
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield self.db
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def rows(self, sql: str, parameters=()):
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, parameters).fetchall()]

    def one(self, sql: str, parameters=()):
        with self.lock:
            row = self.db.execute(sql, parameters).fetchone()
            return dict(row) if row else None

    def setting(self, key, default=None):
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    def set_setting(self, key, value):
        with self.transaction() as db:
            db.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (key, json.dumps(value, ensure_ascii=False)))

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.db.close()
            self.closed = True
