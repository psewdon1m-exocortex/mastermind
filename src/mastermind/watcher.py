"""A separate FULL-synchronous journal keeps native dirty intents off the index lock."""
import sqlite3
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class DirtyJournal(FileSystemEventHandler):
    def __init__(self, config, state):
        self.config, self.state = config, state
        self.lock = threading.RLock()
        self.db = sqlite3.connect(config.state / "native-dirty.sqlite3", check_same_thread=False,
                                  isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS dirty(path TEXT PRIMARY KEY,sequence INTEGER,occurred_at REAL)")
        self.sequence = self.db.execute("SELECT COALESCE(MAX(sequence),0) FROM dirty").fetchone()[0]
        self.observer = None
        self.last_event = 0.0
        self.first_event = 0.0
        self.failure = None

    def record(self, relative):
        now = time.time()
        with self.lock:
            self.sequence += 1
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("INSERT INTO dirty VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET "
                                "sequence=excluded.sequence,occurred_at=excluded.occurred_at",
                                (relative, self.sequence, now))
                if self.db.execute("SELECT COUNT(*) FROM dirty").fetchone()[0] > 100_000:
                    self.db.execute("DELETE FROM dirty")
                    self.db.execute("INSERT INTO dirty VALUES('*',?,?)", (self.sequence, now))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.last_event = time.monotonic()
            self.first_event = self.first_event or self.last_event

    def on_any_event(self, event):
        if event.event_type not in ("created", "modified", "deleted", "moved", "closed"):
            return
        try:
            for value in (event.src_path, getattr(event, "dest_path", "")):
                if not value:
                    continue
                path = Path(value)
                if not path.is_relative_to(self.config.vault):
                    if path == self.config.vault.parent or path == self.config.vault:
                        self.record("*")
                    continue
                relative = path.relative_to(self.config.vault).as_posix()
                if relative == "." or event.is_directory:
                    self.record("*")
                elif not path.name.startswith(".mastermind-"):
                    self.record(relative)
        except (OSError, sqlite3.Error):
            # Never silently lose the observer thread and report a healthy service.
            self.failure = "DIRTY_JOURNAL_UNAVAILABLE"

    def pending(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM dirty").fetchone()[0]

    def flush(self):
        # Copy the cut before waiting for the main DB; recording remains independent.
        with self.lock:
            rows = self.db.execute("SELECT path,sequence,occurred_at FROM dirty").fetchall()
        if not rows:
            return 0
        with self.state.transaction() as db:
            generation = int(db.execute("SELECT value FROM metadata WHERE key='generation'").fetchone()[0])+1
            db.execute("UPDATE metadata SET value=? WHERE key='generation'", (str(generation),))
            for path, _, occurred_at in rows:
                db.execute("INSERT INTO outbox VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET "
                           "generation=excluded.generation,occurred_at=excluded.occurred_at",
                           (path, generation, occurred_at))
            if db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] > 100_000:
                db.execute("DELETE FROM outbox")
                db.execute("INSERT INTO outbox VALUES('*',?,?)", (generation, time.time()))
        # A crash between the two commits causes harmless replay, never omission.
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.executemany("DELETE FROM dirty WHERE path=? AND sequence=?", [(r[0], r[1]) for r in rows])
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            if not self.pending():
                self.first_event = 0
        return len(rows)

    def start(self):
        self.observer = Observer()
        self.observer.schedule(self, str(self.config.vault.parent), recursive=True)
        self.observer.start()

    def close(self):
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=10)
        with self.lock:
            self.db.close()
