"""Disposable, versioned metadata and branch profiles with bounded source representation."""
import json
import math
import re
import struct
import time
from datetime import datetime

import yaml

from ..errors import DomainError
from ..fs import sha_bytes
from ..semantic import VECTOR
from .graph import digest

VERSION = "context-indexing.profiles.v1"


def metadata(text):
    value = {}
    match = re.match(r"---\r?\n([\s\S]{0,65536}?)\r?\n---(?:\r?\n|$)", text)
    if match:
        try:
            # Aliases/recursive YAML are not needed to read scalar search metadata.
            if any(isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
                   for token in yaml.scan(match[1])):
                return value
            front = yaml.safe_load(match[1])
            if isinstance(front, dict):
                aliases = front.get("aliases", front.get("alias", []))
                if isinstance(aliases, str):
                    aliases = [aliases]
                if isinstance(aliases, list):
                    value["aliases"] = [v[:200] for v in aliases[:32] if isinstance(v, str)]
                for key in ("type", "project", "author", "created", "date", "event_date"):
                    field = front.get(key)
                    if isinstance(field, (str, datetime)) or hasattr(field, "isoformat"):
                        value[key] = str(field)[:200]
        except (yaml.YAMLError, ValueError, RecursionError):
            pass
    return value


class Index:
    def __init__(self, service):
        self.service, self.state, self.vault = service, service.state, service.vault

    def sync(self, graph, *, limit=32, deadline=None):
        deadline = deadline or time.monotonic()+5
        with self.state.transaction() as db:
            db.execute("DELETE FROM context_documents WHERE NOT EXISTS(SELECT 1 FROM notes n "
                       "WHERE n.path=context_documents.path AND n.sha=context_documents.source_sha)")
        missing = self.state.rows("SELECT n.path,n.sha FROM notes n LEFT JOIN context_documents c "
                                 "ON c.path=n.path AND c.source_sha=n.sha WHERE c.path IS NULL "
                                 "AND n.path IN (SELECT value FROM json_each(?)) ORDER BY n.path LIMIT ?",
                                 (json.dumps(sorted(graph.notes)), limit))
        for note in missing:
            if time.monotonic() >= deadline:
                break
            if note["path"] not in graph.notes:
                continue
            text = self.vault.read(note["path"])
            if sha_bytes(text.encode()) != note["sha"]:
                continue
            item = metadata(text)
            item["automated"] = "<!-- mastermind:crusher" in text
            with self.state.transaction() as db:
                db.execute("INSERT OR REPLACE INTO context_documents VALUES(?,?,?)",
                           (note["path"], note["sha"], json.dumps(item, ensure_ascii=False)))
        return {row["path"]: json.loads(row["record"]) for row in self.state.rows(
            "SELECT c.* FROM context_documents c JOIN notes n ON n.path=c.path AND n.sha=c.source_sha")
            if row["path"] in graph.notes}

    def profiles(self, graph, structure, configuration, *, limit=32, deadline=None):
        deadline = deadline or time.monotonic()+5
        records = {r["path"]: r for r in self.state.rows("SELECT * FROM context_profiles")}
        retained_bytes = sum(len(r["record"].encode()) for r in records.values())
        active, built = {}, 0
        excluded = {configuration["fallback_note"], configuration["template_path"], graph.root}
        for anchor in sorted(structure.eligible-excluded):
            if time.monotonic() >= deadline:
                break
            members = sorted(p for p in structure.members(anchor) if p not in excluded
                             and not p.startswith("root/templates/"))
            selected = [members[i*len(members)//min(12, len(members))] for i in range(min(12, len(members)))]
            if anchor not in selected:
                selected = [anchor, *selected[:11]]
            model = self.state.setting("semantic_model_sha")
            vectors = []
            for path in selected:
                for row in self.state.rows("SELECT vector FROM semantic_chunks WHERE path=? AND source_sha=? "
                                           "AND model_sha=? ORDER BY ordinal LIMIT 2", (path, graph.notes[path]["sha"], model)):
                    try:
                        vector = VECTOR.unpack(row["vector"])
                        if all(math.isfinite(n) for n in vector):
                            vectors.append(vector)
                    except (ValueError, struct.error):
                        pass
            version = digest({"version": VERSION, "chain": structure.paths[anchor], "model": model,
                              "vectors": len(vectors), "sources": [(p, graph.notes[p]["sha"]) for p in members]})
            old = records.get(anchor)
            if old and old["source_sha"] == version:
                active[anchor] = json.loads(old["record"])
                continue
            if built >= limit:
                continue
            evidence, excerpts = {}, []
            for path in selected:
                row = self.state.one("SELECT substr(body,1,2400) AS body FROM note_fts WHERE path=?", (path,))
                if row:
                    evidence[path] = graph.notes[path]["sha"]
                    excerpts.append(graph.notes[path]["name"]+"\n"+row["body"])
            profile = {"version": VERSION, "path": anchor, "sha256": version,
                       "chain": structure.paths[anchor], "members": len(members), "sources": evidence,
                       "text": "\n\n".join(excerpts), "generation": graph.generation}
            profile["model_sha"] = model
            if vectors:
                centroid = [sum(v[i] for v in vectors)/len(vectors) for i in range(384)]
                norm = math.sqrt(sum(v*v for v in centroid))
                profile["vector"] = [v/max(norm, 1e-12) for v in centroid]
            encoded = json.dumps(profile, ensure_ascii=False)
            if len(encoded.encode()) > 64*1024:
                raise DomainError("PROFILE_LIMIT", "Branch profile exceeds its bounded representation.", 503)
            next_bytes = retained_bytes - (len(old["record"].encode()) if old else 0) + len(encoded.encode())
            if next_bytes > 64*1024**2:
                continue
            if graph.scope.paths is None:
                with self.state.transaction() as db:
                    db.execute("INSERT OR REPLACE INTO context_profiles VALUES(?,?,?)", (anchor, version, encoded))
                    db.execute("DELETE FROM context_profile_fts WHERE path=?", (anchor,))
                    db.execute("INSERT INTO context_profile_fts VALUES(?,?)", (anchor, profile["text"]))
            active[anchor], built = profile, built+1
            retained_bytes = next_bytes
        # A scoped view cannot determine that profiles outside its view are stale.
        with self.state.transaction() as db:
            removable = records.keys()-structure.eligible | records.keys() & excluded
            if graph.scope.paths is not None:
                removable = set()
            for path in removable:
                db.execute("DELETE FROM context_profiles WHERE path=?", (path,))
                db.execute("DELETE FROM context_profile_fts WHERE path=?", (path,))
        return active

    def expire_traces(self):
        with self.state.transaction() as db:
            db.execute("DELETE FROM context_traces WHERE created_at<?", (time.time()-7*86400,))

    def trace(self, result):
        # Explicit allowlist: query text, excerpts, prompts and source material stay out.
        value = {key: result.get(key) for key in ("query_id", "schema", "status", "degraded", "missing_strategies",
                 "truncated", "snapshot_id", "policy_version", "curator", "timings", "channels")}
        value["evidence"] = [{"path": v["path"], "sha256": v["sha256"], "strategies": v["strategies"]}
                             for v in result.get("results", [])[:100]]
        value.update(settings_revision=result.get("settings_revision"), calibration=result.get("calibration"),
                     index_model=self.state.setting("semantic_model_sha"), profile_version=VERSION)
        encoded = json.dumps(value, ensure_ascii=False)
        if len(encoded.encode()) > 64*1024:
            value["evidence"] = value["evidence"][:20]
            encoded = json.dumps(value, ensure_ascii=False)
        with self.state.transaction() as db:
            db.execute("INSERT OR REPLACE INTO context_traces VALUES(?,?,?,?)",
                       (result["query_id"], time.time(), len(encoded.encode()), encoded))
            db.execute("DELETE FROM context_traces WHERE created_at<?", (time.time()-7*86400,))
            db.execute("DELETE FROM context_traces WHERE id NOT IN (SELECT id FROM context_traces ORDER BY created_at DESC LIMIT 10000)")
            size = db.execute("SELECT COALESCE(SUM(bytes),0) FROM context_traces").fetchone()[0]
            while size > 64*1024**2:
                row = db.execute("SELECT id,bytes FROM context_traces ORDER BY created_at LIMIT 1").fetchone()
                db.execute("DELETE FROM context_traces WHERE id=?", (row[0],))
                size -= row[1]
