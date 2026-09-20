"""Disposable, local semantic index with durable bounded rebuilds and source checks."""
import json
import math
import re
import struct
import threading
import time
from collections import OrderedDict

from .errors import DomainError
from .fs import sha_bytes
from .search_content import VERSION as CONTENT_VERSION
from .search_content import content
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
        self.comparison_cache = OrderedDict()
        self.comparison_lock = threading.Lock()

    def start(self):
        if self.service.config.worker_url:
            self.thread = threading.Thread(target=self.run, name="mastermind-semantic", daemon=True)
            self.thread.start()

    def close(self):
        self.stop_event.set()
        self.worker.close()
        if self.thread:
            self.thread.join(timeout=15)

    def compare(self, queries, documents, *, deadline):
        """Verify bounded, scope-cleaned evidence; never persist editor text.

        Retrieval vectors may contain recurring scaffolding. This second pass
        compares the actual evidence that knowledge lookup retained instead.
        Cache keys contain only model identity, prefix mode and a content hash.
        """
        if time.monotonic() >= deadline:
            raise DomainError("CONTEXT_DEADLINE", "Semantic verification exceeded its deadline.", 408)
        if not 1 <= len(queries) <= 5 or len(documents) > 64 or any(
                not isinstance(t, str) or not t.strip() or len(t.encode()) > 6400
                for t in [*queries, *documents]):
            raise DomainError("INVALID_QUERY", "Semantic evidence exceeds comparison limits.", 422)
        if time.monotonic() >= self.next_health:
            self.refresh()
        if self.failure:
            raise DomainError(self.failure, "Local semantic verification is unavailable.", 503)

        def embed(texts, query):
            keys = [(self.model, query, sha_bytes(t.encode())) for t in texts]
            vectors = {}
            with self.comparison_lock:
                for key in keys:
                    if key in self.comparison_cache:
                        vectors[key] = self.comparison_cache[key]
                        self.comparison_cache.move_to_end(key)
            missing = list(dict.fromkeys(k for k in keys if k not in vectors))
            values = dict(zip(keys, texts, strict=True))
            for start in range(0, len(missing), 16):
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise DomainError("CONTEXT_DEADLINE", "Semantic verification exceeded its deadline.", 408)
                batch = missing[start:start+16]
                options = {"timeout": remaining} if isinstance(self.worker, WorkerClient) else {}
                response = self.worker.embed([values[k] for k in batch], query=query, **options)
                if response['model_sha256'] != self.model:
                    raise DomainError("REINDEX_REQUIRED", "Evidence model does not match the index.", 409)
                for key, vector in zip(batch, response['vectors'], strict=True):
                    vectors[key] = vector
                with self.comparison_lock:
                    for key in batch:
                        self.comparison_cache[key] = vectors[key]
                    while len(self.comparison_cache) > 256:
                        self.comparison_cache.popitem(last=False)
            return [vectors[k] for k in keys]

        query_vectors, document_vectors = embed(queries, True), embed(documents, False)
        if time.monotonic() >= deadline:
            raise DomainError("CONTEXT_DEADLINE", "Semantic verification exceeded its deadline.", 408)
        return [max(sum(a*b for a, b in zip(q, d, strict=True)) for q in query_vectors) for d in document_vectors]

    def refresh(self):
        # Representation changes invalidate only disposable search data, never Vault files.
        with self.service.coordinator.lock, self.state.transaction() as db:
            if self.state.setting("semantic_representation") != CONTENT_VERSION:
                for table in ("semantic_chunks", "semantic_documents", "semantic_text", "semantic_run",
                              "context_profiles", "context_profile_fts"):
                    db.execute("DELETE FROM " + table)
                self.state.set_setting("semantic_representation", CONTENT_VERSION)
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
                    "representation": CONTENT_VERSION,
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
                db.execute("DELETE FROM semantic_text")
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
            # Source extraction/inference has priority. Waiting/placing jobs must
            # not prevent the very index progress they may need.
            if self.state.one("SELECT 1 FROM jobs WHERE state IN ('ACQUIRING','EXTRACTING','UNDERSTANDING','GENERATING') LIMIT 1"):
                return False
            with self.service.coordinator.lock:
                self.service.data_ready()
                with self.state.transaction() as db:
                    db.execute("DELETE FROM semantic_chunks WHERE NOT EXISTS(SELECT 1 FROM notes n "
                               "WHERE n.path=semantic_chunks.path AND n.sha=semantic_chunks.source_sha)")
                    db.execute("DELETE FROM semantic_documents WHERE NOT EXISTS(SELECT 1 FROM notes n "
                               "WHERE n.path=semantic_documents.path AND n.sha=semantic_documents.source_sha)")
                    db.execute("DELETE FROM semantic_text WHERE NOT EXISTS(SELECT 1 FROM notes n "
                               "WHERE n.path=semantic_text.path AND n.sha=semantic_text.source_sha)")
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
                text = content(text)
                document = self.state.one("SELECT * FROM semantic_documents WHERE path=?", (note["path"],))
            if document is None:
                value = self.worker.request("POST", "/chunks", {"text": text}, timeout=60) if text.strip() else {
                    "chunks": [], "model_sha256": self.model}
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
                    db.execute("INSERT OR REPLACE INTO semantic_text VALUES(?,?,?)", (note["path"], note["sha"], text))
                    for offset, (span, vector) in enumerate(zip(batch, response["vectors"], strict=True), start):
                        db.execute("INSERT OR REPLACE INTO semantic_chunks VALUES(?,?,?,?,?,?,?)",
                            (note["path"], offset, span["start"], span["end"], note["sha"], self.model, VECTOR.pack(*vector)))
            return True

    def search(self, query, limit=20, *, allowed_paths=None, deadline=None, include_vector=False, source_chunks=None, evidence_queries=None):
        if not isinstance(query, str) or not query.strip() or len(query.encode()) > 4096 or not 1 <= limit <= 50:
            raise DomainError("INVALID_QUERY", "Use a nonempty query up to 4 KiB and 1–50 results.", 422)
        self.service.data_ready()
        # A failed model is explicit even when an older vector index remains.
        if time.monotonic() >= self.next_health:
            self.refresh()
        if self.failure:
            raise DomainError(self.failure, "Local semantic search is unavailable.", 503)
        source_chunks = source_chunks or []
        evidence_queries = evidence_queries or []
        if not isinstance(source_chunks, list) or len(source_chunks) > 8 or any(
                not isinstance(chunk, str) or len(chunk.encode()) > 6400 for chunk in source_chunks):
            raise DomainError("INVALID_QUERY", "Use at most eight bounded source feature chunks.", 422)
        if not isinstance(evidence_queries, list) or len(evidence_queries) > 7 or any(
                not isinstance(chunk, str) or len(chunk.encode()) > 6400 for chunk in evidence_queries):
            raise DomainError("INVALID_QUERY", "Use at most seven bounded evidence queries.", 422)
        options = {}
        if deadline is not None:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise DomainError("CONTEXT_DEADLINE", "Semantic search exceeded the query deadline.", 408)
            if isinstance(self.worker, WorkerClient):
                options["timeout"] = max(.01, remaining)
        response = self.worker.embed([content(query), *[content(s) for s in source_chunks],
                                      *[content(s) for s in evidence_queries]], query=True, **options)
        if response["model_sha256"] != self.model:
            raise DomainError("REINDEX_REQUIRED", "The query model does not match the stored index.", 409)
        query_vector, best, cursor = response["vectors"][0], {}, ("", -1)
        segment_vectors = response["vectors"][1+len(source_chunks):]
        segment_best = [{} for _ in segment_vectors]
        if source_chunks:
            count = len(source_chunks)
            query_vector = [0.5*value + 0.5*sum(vector[i] for vector in response["vectors"][1:1+count])/count
                            for i, value in enumerate(query_vector)]
            norm = math.sqrt(sum(value*value for value in query_vector))
            query_vector = [value/max(norm, 1e-12) for value in query_vector]
        scope = " AND c.path IN (SELECT value FROM json_each(?))" if allowed_paths is not None else ""
        scope_args = (json.dumps(sorted(allowed_paths)),) if allowed_paths is not None else ()
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise DomainError("CONTEXT_DEADLINE", "Semantic search exceeded the query deadline.", 408)
            rows = self.state.rows("SELECT c.* FROM semantic_chunks c JOIN notes n ON n.path=c.path AND n.sha=c.source_sha "
                "JOIN semantic_documents s ON s.path=c.path AND s.completed=1 AND s.source_sha=c.source_sha "
                "WHERE c.model_sha=? AND (c.path,c.ordinal)>(?,?)"+scope+" ORDER BY c.path,c.ordinal LIMIT 256",
                (self.model, *cursor, *scope_args))
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
                for feature, segment in zip(segment_vectors, segment_best, strict=True):
                    score = sum(a*b for a, b in zip(vector, feature, strict=True))
                    segment[row["path"]] = max(score, segment.get(row["path"], -1))
            cursor = rows[-1]["path"], rows[-1]["ordinal"]
        results = []
        for score, row in sorted(best.values(), key=lambda item: (-item[0], item[1]["path"])):
            try:
                with self.service.coordinator.lock:
                    self.service.data_ready()
                    text = self.vault.read(row["path"])
                    if sha_bytes(text.encode()) != row["source_sha"]:
                        continue
                    prepared = self.state.one("SELECT body FROM semantic_text WHERE path=? AND source_sha=?",
                                              (row["path"], row["source_sha"]))
                    if prepared is None:
                        continue
                    text = prepared["body"]
                    excerpt = text[row["start"]:min(row["end"], row["start"]+512)]
            except DomainError as error:
                if error.code == "NOT_FOUND":
                    continue
                raise
            results.append({"path": row["path"], "sha256": row["source_sha"], "score": round(score, 6),
                            "start": row["start"], "end": row["end"], "excerpt": excerpt,
                            "representation": CONTENT_VERSION})
            if len(results) == limit:
                break
        segments = [[{"path": path, "score": round(score, 6)} for path, score in sorted(
            values.items(), key=lambda v: (-v[1], v[0]))[:20]] for values in segment_best]
        return {"results": results, "index": self.status(), "segment_evidence": segments,
                **({"query_vector": query_vector} if include_vector else {})}

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
