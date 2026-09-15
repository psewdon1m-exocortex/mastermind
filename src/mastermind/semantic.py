"""Disposable, local semantic index with durable bounded rebuilds and source checks."""
import json
import math
import re
import struct
import threading
import time

from .errors import DomainError
from .fs import sha_bytes
from .worker_client import WorkerClient

VECTOR = struct.Struct("<384f")
MAX_CHUNKS = 300000  # About 440 MiB of vectors; refuse, never silently drop notes.


class Semantic:
    def __init__(self, service, *, worker=None):
        self.service, self.state, self.vault = service, service.state, service.vault
        self.worker = worker or WorkerClient(service.config, service.secrets)
        self.stop_event, self.lock = threading.Event(), threading.RLock()
        self.thread = None
        self.model = None
        self.failure = "EMBEDDINGS_UNAVAILABLE"
        self.next_health = 0

    def start(self):
        if self.service.config.worker_url:
            self.thread = threading.Thread(target=self.run, name="mastermind-semantic", daemon=True)
            self.thread.start()

    def close(self):
        self.stop_event.set()
        self.worker.close()
        if self.thread:
            self.thread.join(timeout=15)

    def refresh(self):
        value = self.worker.request("GET", "/healthz", timeout=5)
        digest = value.get("model_sha256")
        if not value.get("embeddings_ready") or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            self.failure = "EMBEDDINGS_UNAVAILABLE"
            raise DomainError("EMBEDDINGS_UNAVAILABLE", "The local embedding model is unavailable.", 503)
        self.model = digest
        approved = self.state.setting("semantic_model_sha")
        if approved is None:
            self.state.set_setting("semantic_model_sha", digest)
            approved = digest
        if approved != digest:
            self.failure = "REINDEX_REQUIRED"
            raise DomainError("REINDEX_REQUIRED", "The embedding model changed; confirm a full local reindex.", 409)
        self.failure = None
        self.next_health = time.monotonic()+30

    def status(self):
        with self.service.coordinator.lock:
            total = self.state.one("SELECT COUNT(*) AS n FROM notes")["n"]
            complete = self.state.one("SELECT COUNT(*) AS n FROM semantic_documents s JOIN notes n ON n.path=s.path "
                "AND n.sha=s.source_sha WHERE s.completed=1 AND s.model_sha=?", (self.model or "",))["n"]
            run = self.state.one("SELECT * FROM semantic_run WHERE id=1")
            error = self.failure or (run or {}).get("error")
            return {"status": "UNAVAILABLE" if error else "READY" if complete == total else "INDEXING",
                    "error": error, "model_sha256": self.model, "notes_total": total, "notes_indexed": complete,
                    "deadline": (run or {}).get("deadline")}

    def reindex(self, expected_model):
        with self.lock, self.service.coordinator.lock:
            self.service.data_ready()
            try:
                self.refresh()
            except DomainError as error:
                if error.code != "REINDEX_REQUIRED":
                    raise
            if expected_model != self.model:
                raise DomainError("MODEL_CHANGED", "Confirm the currently available model digest.", 409)
            with self.state.transaction() as db:
                db.execute("DELETE FROM semantic_chunks")
                db.execute("DELETE FROM semantic_documents")
                db.execute("INSERT OR REPLACE INTO semantic_run VALUES(1,?,NULL)", (time.time()+1800,))
                self.state.set_setting("semantic_model_sha", self.model)
            self.failure = None
            self.service.audit.emit("semantic.reindex", actor="owner", context={"model_sha256": self.model})
            return self.status()

    def once(self):
        with self.lock:
            self.service.data_ready()
            if time.monotonic() >= self.next_health:
                self.refresh()
            if self.failure:
                return False
            # Crusher is foreground work. A rebuild yields after every batch and
            # does not take the source pipeline's sole processing slot.
            if self.state.one("SELECT 1 FROM jobs WHERE state NOT IN ('COMPLETED','FAILED') LIMIT 1"):
                return False
            with self.service.coordinator.lock:
                self.service.data_ready()
                with self.state.transaction() as db:
                    db.execute("DELETE FROM semantic_chunks WHERE NOT EXISTS(SELECT 1 FROM notes n "
                               "WHERE n.path=semantic_chunks.path AND n.sha=semantic_chunks.source_sha)")
                    db.execute("DELETE FROM semantic_documents WHERE NOT EXISTS(SELECT 1 FROM notes n "
                               "WHERE n.path=semantic_documents.path AND n.sha=semantic_documents.source_sha)")
                note = self.state.one("SELECT n.path,n.sha FROM notes n LEFT JOIN semantic_documents s ON n.path=s.path "
                    "AND n.sha=s.source_sha AND s.model_sha=? WHERE s.path IS NULL OR s.completed=0 ORDER BY n.path LIMIT 1", (self.model,))
                if not note:
                    with self.state.transaction() as db:
                        db.execute("DELETE FROM semantic_run")
                    return False
                run = self.state.one("SELECT * FROM semantic_run WHERE id=1")
                if run is None:
                    with self.state.transaction() as db:
                        db.execute("INSERT INTO semantic_run VALUES(1,?,NULL)", (time.time()+1800,))
                elif run["error"] or time.time() >= run["deadline"]:
                    with self.state.transaction() as db:
                        db.execute("UPDATE semantic_run SET error='REINDEX_DEADLINE' WHERE id=1 AND error IS NULL")
                    return False
                text = self.vault.read(note["path"])
                if sha_bytes(text.encode()) != note["sha"]:
                    return False
                document = self.state.one("SELECT * FROM semantic_documents WHERE path=?", (note["path"],))
            if document is None:
                value = self.worker.request("POST", "/chunks", {"text": text}, timeout=60)
                spans = value.get("chunks")
                if value.get("model_sha256") != self.model or not isinstance(spans, list) or len(spans) > MAX_CHUNKS:
                    raise DomainError("EMBEDDINGS_INVALID", "The tokenizer returned an invalid index plan.", 503)
                end = 0
                for span in spans:
                    if not isinstance(span, dict) or set(span) != {"start", "end"} \
                            or type(span["start"]) is not int or type(span["end"]) is not int \
                            or not end <= span["start"] < span["end"] <= len(text) \
                            or len(text[span["start"]:span["end"]].encode()) > 64*1024:
                        raise DomainError("EMBEDDINGS_INVALID", "The tokenizer returned invalid source spans.", 503)
                    end = span["end"]
                document = {"spans": json.dumps(spans), "next_chunk": 0}
            spans, start = json.loads(document["spans"]), document["next_chunk"]
            batch = spans[start:start+16]
            response = self.worker.embed([text[span["start"]:span["end"]] for span in batch]) if batch else {"vectors": [], "model_sha256": self.model}
            if response["model_sha256"] != self.model:
                raise DomainError("REINDEX_REQUIRED", "The model changed during embedding rebuild.", 409)
            with self.service.coordinator.lock:
                self.service.data_ready()
                current = self.state.one("SELECT sha FROM notes WHERE path=?", (note["path"],))
                if self.stop_event.is_set() or current != {"sha": note["sha"]} \
                        or sha_bytes(self.vault.read(note["path"]).encode()) != note["sha"]:
                    return False
                count = self.state.one("SELECT COUNT(*) AS n FROM semantic_chunks")["n"]
                if count + len(batch) > MAX_CHUNKS:
                    with self.state.transaction() as db:
                        db.execute("UPDATE semantic_run SET error='SEMANTIC_CAPACITY' WHERE id=1")
                    return False
                with self.state.transaction() as db:
                    db.execute("INSERT OR REPLACE INTO semantic_documents VALUES(?,?,?,?,?,?)",
                        (note["path"], note["sha"], self.model, document["spans"], start+len(batch), int(start+len(batch) == len(spans))))
                    for offset, (span, vector) in enumerate(zip(batch, response["vectors"], strict=True), start):
                        db.execute("INSERT OR REPLACE INTO semantic_chunks VALUES(?,?,?,?,?,?,?)",
                            (note["path"], offset, span["start"], span["end"], note["sha"], self.model, VECTOR.pack(*vector)))
            return True

    def search(self, query, limit=20):
        if not isinstance(query, str) or not query.strip() or len(query.encode()) > 4096 or not 1 <= limit <= 50:
            raise DomainError("INVALID_QUERY", "Use a nonempty query up to 4 KiB and 1–50 results.", 422)
        self.service.data_ready()
        # A failed model is explicit even when an older vector index remains.
        if time.monotonic() >= self.next_health:
            self.refresh()
        if self.failure:
            raise DomainError(self.failure, "Local semantic search is unavailable.", 503)
        response = self.worker.embed([query], query=True)
        if response["model_sha256"] != self.model:
            raise DomainError("REINDEX_REQUIRED", "The query model does not match the stored index.", 409)
        query_vector, best, cursor = response["vectors"][0], {}, ("", -1)
        while True:
            rows = self.state.rows("SELECT c.* FROM semantic_chunks c JOIN notes n ON n.path=c.path AND n.sha=c.source_sha "
                "JOIN semantic_documents s ON s.path=c.path AND s.completed=1 AND s.source_sha=c.source_sha "
                "WHERE c.model_sha=? AND (c.path,c.ordinal)>(?,?) ORDER BY c.path,c.ordinal LIMIT 256", (self.model, *cursor))
            if not rows:
                break
            for row in rows:
                try:
                    vector = VECTOR.unpack(row["vector"])
                    score = sum(a*b for a, b in zip(vector, query_vector, strict=True))
                    if not math.isfinite(score):
                        raise ValueError
                except (struct.error, ValueError):
                    raise DomainError("REINDEX_REQUIRED", "The derived vector index failed integrity; rebuild it.", 503) from None
                if row["path"] not in best or score > best[row["path"]][0]:
                    best[row["path"]] = (score, row)
            cursor = rows[-1]["path"], rows[-1]["ordinal"]
        results = []
        for score, row in sorted(best.values(), key=lambda item: (-item[0], item[1]["path"])):
            try:
                with self.service.coordinator.lock:
                    self.service.data_ready()
                    text = self.vault.read(row["path"])
                    if sha_bytes(text.encode()) != row["source_sha"]:
                        continue
                    excerpt = text[row["start"]:min(row["end"], row["start"]+512)]
            except DomainError as error:
                if error.code == "NOT_FOUND":
                    continue
                raise
            results.append({"path": row["path"], "sha256": row["source_sha"], "score": round(score, 6),
                            "start": row["start"], "end": row["end"], "excerpt": excerpt})
            if len(results) == limit:
                break
        return {"results": results, "index": self.status()}

    def run(self):
        while not self.stop_event.wait(0.25):
            try:
                if not self.once():
                    self.stop_event.wait(1)
            except DomainError as error:
                if error.code not in ("NOT_READY", "UPDATE_IN_PROGRESS", "RECOVERY_REQUIRED"):
                    self.failure = error.code
                    self.next_health = 0
                    self.stop_event.wait(15)
            except Exception:  # noqa: BLE001 - derived work must not kill Core or log private text
                if self.stop_event.is_set() or self.state.closed:
                    return
                self.failure = "SEMANTIC_INDEX_FAILED"
                self.next_health = 0
                self.stop_event.wait(15)
