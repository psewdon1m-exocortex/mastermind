import json
import time

from .errors import DomainError
from .fs import file_inventory, name_key, open_under, resolve, sha_bytes, sha_file
from .references import masked, note_tags, parse


class Vault:
    def __init__(self, config, state, coordinator):
        self.config, self.state, self.coordinator = config, state, coordinator
        config.vault.mkdir(parents=True, exist_ok=True)
        self.conflicts = []

    def files(self):
        return [(rel, path) for rel, path in file_inventory(self.config.vault)
                if rel.lower().endswith(".md") and not any(p.startswith(".") for p in rel.split("/"))]

    def inventory(self):
        seen, conflicts, result = {}, [], {}
        for relative, path in self.files():
            key = name_key(path.stem)
            if key in seen:
                conflicts.append([seen[key], relative])
            seen[key] = relative
            result[relative] = (path, key)
        self.conflicts = conflicts
        if conflicts:
            raise DomainError("DUPLICATE_BASENAME", "Vault contains conflicting note basenames.", 503)
        return result

    def read(self, relative):
        with self.coordinator.lock:
            if self.coordinator.recovery_required:
                raise DomainError("RECOVERY_REQUIRED", "Canonical reads are blocked until recovery completes.", 503)
            return self._read(relative)

    def _read(self, relative):
        path = resolve(self.config.vault, relative)
        if not path.is_file() or path.suffix.lower() != ".md":
            raise DomainError("NOT_FOUND", "Note not found.", 404)
        if path.stat().st_size > self.config.max_note_bytes:
            raise DomainError("NOTE_TOO_LARGE", "Note exceeds the supported size.", 413)
        try:
            with open_under(self.config.vault, relative) as stream:
                data = stream.read(self.config.max_note_bytes + 1)
            if len(data) > self.config.max_note_bytes:
                raise DomainError("NOTE_TOO_LARGE", "Note exceeds the supported size.", 413)
            return data.decode("utf-8")
        except UnicodeDecodeError:
            raise DomainError("INVALID_ENCODING", "Notes must contain UTF-8 text.", 422) from None

    def index(self, *, force=False):
        with self.coordinator.lock:
            inventory = self.inventory()
            previous = {row["path"]: row for row in self.state.rows("SELECT * FROM notes")}
            current = {key: path.stem for path, key in inventory.values()}
            changed_names = set(current) != {r["name_key"] for r in previous.values()}
            history = [r["display"] for r in self.state.rows(
                "SELECT display FROM reference_history WHERE kind='internal'")]
            saturn = [r["display"] for r in self.state.rows(
                "SELECT display FROM reference_history WHERE kind='saturn'")]
            processed = 0
            dirty = set(previous.keys() - inventory.keys())
            with self.state.transaction() as db:
                for relative in previous.keys() - inventory.keys():
                    db.execute("DELETE FROM note_fts WHERE path=?", (relative,))
                    db.execute("DELETE FROM notes WHERE path=?", (relative,))
                    db.execute("DELETE FROM edges WHERE source=?", (relative,))
                # History survives target deletion and rebuild.
                for key, display in current.items():
                    db.execute("INSERT OR IGNORE INTO reference_history VALUES('internal',?,?)", (key, display))
                history = list(set(history) | set(current.values()))
                for relative, (path, key) in inventory.items():
                    stat = path.stat()
                    old = previous.get(relative)
                    if not force and not changed_names and old and old["mtime_ns"] == stat.st_mtime_ns \
                            and old["size"] == stat.st_size:
                        continue
                    text = self.read(relative)
                    digest = sha_bytes(text.encode("utf-8"))
                    if path.stat().st_mtime_ns != stat.st_mtime_ns or sha_file(path) != digest:
                        raise DomainError("VAULT_BUSY", "A note changed during indexing; retry.", 423)
                    if not old or old["sha"] != digest:
                        dirty.add(relative)
                    tags = note_tags(text)
                    db.execute("INSERT INTO notes VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
                               "name_key=excluded.name_key,name=excluded.name,sha=excluded.sha,size=excluded.size,"
                               "tags=excluded.tags,mtime_ns=excluded.mtime_ns",
                               (relative, key, path.stem, digest, stat.st_size, json.dumps(tags), stat.st_mtime_ns))
                    db.execute("DELETE FROM note_fts WHERE path=?", (relative,))
                    db.execute("INSERT INTO note_fts VALUES(?,?,?,?)",
                               (relative, path.stem, masked(text).replace("\0", ""), " ".join(tags)))
                    db.execute("DELETE FROM edges WHERE source=?", (relative,))
                    for ref in parse(text, current, history, saturn):
                        db.execute("INSERT OR REPLACE INTO edges VALUES(?,?,?,?)",
                                   (relative, ref.target, ref.kind, int(not ref.exists)))
                        if ref.kind == "saturn":
                            db.execute("INSERT OR IGNORE INTO reference_history VALUES('saturn',?,?)",
                                       (ref.target, ref.target))
                    processed += 1
                if dirty:
                    generation = int(db.execute("SELECT value FROM metadata WHERE key='generation'").fetchone()[0])+1
                    db.execute("UPDATE metadata SET value=? WHERE key='generation'", (str(generation),))
                    for relative in dirty:
                        db.execute("INSERT INTO outbox VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET "
                                   "generation=excluded.generation,occurred_at=excluded.occurred_at",
                                   (relative, generation, time.time()))
                    if db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] > 100_000:
                        db.execute("DELETE FROM outbox")
                        db.execute("INSERT INTO outbox VALUES('*',?,?)", (generation, time.time()))
            return {"indexed": processed, "notes": len(inventory)}

    def validate_destination(self, relative, exclude=()):
        path = resolve(self.config.vault, relative)
        if path.suffix.lower() != ".md":
            raise DomainError("INVALID_NOTE", "A note path must end in .md.")
        key = name_key(path.stem)
        for old, (_, other) in self.inventory().items():
            if old not in exclude and other == key:
                raise DomainError("DUPLICATE_BASENAME", "A note with this basename already exists.", 409)

    def write(self, relative, text, expected, *, create=False, metadata=None):
        data = text.encode("utf-8")
        if len(data) > self.config.max_note_bytes:
            raise DomainError("NOTE_TOO_LARGE", "Note exceeds the supported size.", 413)
        with self.coordinator.boundary() as operation_id:
            self.validate_destination(relative, exclude=() if create else (relative,))
            if not create and expected is None:
                raise DomainError("PRECONDITION_REQUIRED", "An expected content digest is required.", 428)
            if not create and not resolve(self.config.vault, relative).is_file():
                raise DomainError("NOT_FOUND", "Note not found.", 404)
            self.coordinator.commit({relative: data}, {relative: None if create else expected}, metadata,
                                    inside_boundary=True, operation_id=operation_id)
            self.index()
        return {"path": relative, "sha256": sha_file(resolve(self.config.vault, relative))}

    def delete(self, relative, expected):
        if expected is None:
            raise DomainError("PRECONDITION_REQUIRED", "An expected content digest is required.", 428)
        with self.coordinator.boundary() as operation_id:
            self.coordinator.commit({relative: None}, {relative: expected},
                                    inside_boundary=True, operation_id=operation_id)
            self.index()

    def list(self, query="", limit=100, offset=0):
        limit = min(max(limit, 1), 500)
        offset = max(offset, 0)
        if query.strip():
            # User text is a literal FTS phrase, never a raw FTS program.
            phrase = '"' + query.replace('"', '""') + '"'
            return self.state.rows("SELECT n.* FROM notes n JOIN note_fts f ON n.path=f.path "
                                   "WHERE note_fts MATCH ? ORDER BY rank LIMIT ? OFFSET ?",
                                   (phrase, limit, offset))
        return self.state.rows("SELECT * FROM notes ORDER BY name_key LIMIT ? OFFSET ?", (limit, offset))

    def graph(self):
        notes = self.state.rows("SELECT path,name_key,name,tags FROM notes ORDER BY path")
        paths = {n["name_key"]: n["path"] for n in notes}
        edges, broken = set(), 0
        for row in self.state.rows("SELECT * FROM edges WHERE kind='internal'"):
            target = paths.get(row["target_key"])
            if not target:
                broken += 1
            elif target != row["source"]:
                edges.add(tuple(sorted((target, row["source"]))))
        n = len(notes)
        return {"nodes": notes, "edges": [list(e) for e in sorted(edges)], "broken": broken,
                "connectedness": round(len(edges) / (n*(n-1)/2) * 100, 2) if n > 1 else 0.0}

    def links(self, relative, direction="outgoing"):
        path = resolve(self.config.vault, relative)
        if direction == "backlinks":
            return self.state.rows("SELECT DISTINCT n.path,n.name,'internal' AS kind,0 AS broken "
                                   "FROM edges e JOIN notes n ON n.path=e.source "
                                   "WHERE e.kind='internal' AND e.target_key=? ORDER BY n.name_key", (name_key(path.stem),))
        return self.state.rows("SELECT e.target_key,e.kind,e.broken,n.path,COALESCE(n.name,h.display,e.target_key) AS name "
                               "FROM edges e LEFT JOIN notes n ON e.kind='internal' AND n.name_key=e.target_key "
                               "LEFT JOIN reference_history h ON h.kind=e.kind AND h.name_key=e.target_key "
                               "WHERE e.source=? ORDER BY e.kind,name", (relative,))

    def graph_projection(self):
        result = self.graph()
        result["external"] = self.state.rows("SELECT source,target_key,kind,broken FROM edges "
                                             "WHERE kind IN ('chronos','saturn') ORDER BY source,kind,target_key")
        return result

    def event(self, event):
        if event["kind"] not in ("CREATE", "EDIT", "RENAME", "MOVE"):
            raise DomainError("INVALID_ACTIVITY", "Unsupported owner activity.")
        resolve(self.config.vault, event["path"])
        when = float(event["occurred_at"])
        if abs(time.time() - when) > 31*86400:
            raise DomainError("INVALID_ACTIVITY", "Activity timestamp is outside the replay window.")
        with self.state.transaction() as db:
            db.execute("INSERT OR IGNORE INTO activity VALUES(?,?,?,?,?)",
                       (event["id"], event.get("session_id"), event["kind"], event["path"], when))
