"""Common context-indexing retrieval. No placement eligibility or filesystem mutations."""
import json
import math
import re
import secrets
import threading
import time
from datetime import date

from ..errors import DomainError
from ..fs import sha_bytes
from .graph import Graph, Scope

VERSION = "context-indexing.retrieval.v1"
STOP = {"the", "a", "an", "of", "on", "in", "and", "or", "to", "for", "from", "with", "this", "that", "is", "are", "by", "as", "at", "it", "be", "into", "и", "в", "во", "на", "для", "из", "по", "с", "со", "о", "об", "как", "что", "это", "или", "к", "от", "до", "не", "а", "но", "при", "source", "facts", "about", "note", "summary", "material", "заметка", "материал", "источник", "сведения"}


def words(text):
    return {v for v in re.findall(r"[^\W_]{2,64}", text.casefold(), re.UNICODE) if v not in STOP}


def bounded(text, size):
    return text.encode()[:size].decode("utf-8", errors="ignore")


def explicitly_negated(title, text):
    """A narrow counter-evidence signal; never interprets source text as an instruction."""
    prefix = r"(?:not\s+about|unrelated\s+to|no\s+(?:statement|information|evidence)\s+about|не\s+касается|не\s+относится\s+к|нет\s+(?:сведений|информации)\s+о)\s+"
    return bool(re.search(prefix+re.escape(title)+r"(?!\w)", text, re.IGNORECASE))


def positive_query(text):
    # A stated absence of information is counter-evidence, not query expansion.
    return re.sub(r"(?:not\s+about|unrelated\s+to|no\s+(?:statement|information|evidence)\s+about|не\s+касается|не\s+относится\s+к|нет\s+(?:сведений|информации)\s+о)\s+[^.!?\n]+", "", text, flags=re.IGNORECASE)


def source_features(understanding, raw=""):
    chunks = []
    if raw:
        width = min(len(raw), 1600)
        count = min(8, max(1, math.ceil(len(raw)/width)))
        chunks = [raw[i*max(0, len(raw)-width)//max(1, count-1):i*max(0, len(raw)-width)//max(1, count-1)+width]
                  for i in range(count)]
    core = "\n".join([understanding.get("title", ""), understanding.get("summary", ""),
                       " ".join(understanding.get("topics", [])), " ".join(understanding.get("entities", []))])
    return {"text": bounded(core, 4096), "raw_chunks": chunks,
            "entities": understanding.get("entities", [])[:50], "source_sampled": len(raw) > sum(map(len, chunks)),
            "topic_exclusions": positive_query(raw) != raw or positive_query(core) != core,
            "truncated": False}


class Pipeline:
    def __init__(self, service, index, *, semantic=None, curator=None, disabled=()):
        self.service, self.state, self.vault = service, service.state, service.vault
        self.index, self.semantic, self.curator = index, semantic, curator
        self.disabled = frozenset(disabled)
        self.slots = threading.BoundedSemaphore(2)

    def run(self, subject, *, scope=None, query_type="knowledge_lookup", filters=None, configuration=None,
            assessment=None, checkpoint=None, query_id=None, deadline=None):
        scope = scope or Scope("owner")
        if query_type not in {"knowledge_lookup", "placement_analysis"}:
            raise DomainError("QUERY_TYPE", "Unsupported context-indexing query type.", 422)
        if not isinstance(subject, dict) or not isinstance(subject.get("text"), str) \
                or not subject["text"].strip() or len(subject["text"].encode()) > 16*1024:
            raise DomainError("INVALID_QUERY", "Provide a nonempty query up to 16 KiB.", 422)
        if not self.slots.acquire(blocking=False):
            raise DomainError("CONTEXT_BUSY", "Context-indexing is at its bounded concurrency limit.", 429)
        try:
            started = time.monotonic()
            deadline = min(started+90, deadline or started+90)
            graph = Graph(self.vault, scope)
            metadata = self.index.sync(graph, deadline=min(started+5, deadline))
            plan = {"schema": VERSION, "query_id": query_id or secrets.token_hex(16), "query_type": query_type,
                    "snapshot_id": graph.sha, "policy_version": "crusher.placement.v1" if assessment else None,
                    "filters": filters or {}, "configuration": configuration or {}, "scope": scope,
                    "deadline": deadline}
            if query_type == "placement_analysis" and "profiles" not in self.disabled:
                plan["profiles"] = self.index.profiles(graph, graph.structure(), plan["configuration"],
                                                       deadline=min(started+7, deadline))
            allowed = self.allowed(graph, metadata, plan["filters"])
            first = self.retrieve(subject, graph, metadata, plan, allowed)
            # A sparse/technical anchor name need not equal its subject. Preserve
            # explicit exclusions independently of the names found by retrieval.
            # Consumers decide whether they can safely resolve that counterevidence.
            first["topic_exclusions"] = bool(subject.get("topic_exclusions")) or positive_query(subject["text"]) != subject["text"]
            status = assessment(first, graph) if assessment else self.assess(first)
            curator = {"requested": bool(plan["configuration"].get("curator_enabled")), "effective": False,
                       "invoked": False, "outcome": "disabled", "passes": 0}
            if curator["requested"]:
                curator["outcome"] = "not_needed"
                if status["status"] in {"ambiguous", "insufficient_evidence"} and status.get("refinement_may_help", True) and self.curator:
                    refined, curator = self.curator.refine(subject, first, status, checkpoint=checkpoint,
                                                           deadline=plan["deadline"])
                    if refined:
                        second = self.retrieve(refined, graph, metadata, plan, allowed)
                        first = self.merge(first, second, refined)
                        first["curator_pass"] = True
                        status = assessment(first, graph) if assessment else self.assess(first)
            result = {**first, **status, "query_id": plan["query_id"], "schema": VERSION,
                      "snapshot_id": graph.sha, "policy_version": plan["policy_version"], "curator": curator,
                      "timings": {"total_ms": round((time.monotonic()-started)*1000)},
                      "settings_revision": plan["configuration"].get("revision", 0)}
            # Validate the actual bytes of the bounded returned evidence, not just an old index row.
            fresh = []
            for item in result["results"]:
                try:
                    if sha_bytes(self.vault.read(item["path"]).encode()) == item["sha256"]:
                        fresh.append(item)
                except DomainError:
                    pass
            if len(fresh) != len(result["results"]):
                result.update(results=fresh, status="insufficient_evidence", degraded=True, stale_evidence=True)
                result.pop("placement", None)
            self.index.trace(result)
            return result, graph
        finally:
            self.slots.release()

    @staticmethod
    def allowed(graph, metadata, filters):
        if not isinstance(filters, dict) or set(filters)-{"tags", "path_prefix", "date_field", "date_from", "date_to"}:
            raise DomainError("QUERY_FILTER", "Unsupported search filters.", 422)
        tags = filters.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(v, str) for v in tags):
            raise DomainError("QUERY_FILTER", "Tags must be a list of names.", 422)
        if any(not isinstance(v, str) for k, v in filters.items() if k != "tags"):
            raise DomainError("QUERY_FILTER", "Filter values must be strings.", 422)
        if filters.get("date_field") not in (None, "created", "date", "event_date"):
            raise DomainError("QUERY_FILTER", "Choose an explicit metadata date field.", 422)
        if ("date_from" in filters or "date_to" in filters) and "date_field" not in filters:
            raise DomainError("QUERY_FILTER", "Date filtering requires an explicit date field.", 422)
        try:
            for key in ("date_from", "date_to"):
                if key in filters:
                    date.fromisoformat(filters[key])
            if filters.get("date_from", "") > filters.get("date_to", "9999-12-31"):
                raise ValueError
        except ValueError:
            raise DomainError("QUERY_FILTER", "Use an ordered ISO calendar date interval.", 422) from None
        result = set()
        for path, note in graph.notes.items():
            if not set(tags) <= set(note["tags"]) or not path.startswith(filters.get("path_prefix", "")):
                continue
            if "date_field" in filters:
                value = metadata.get(path, {}).get(filters["date_field"])
                if not value or value < filters.get("date_from", "") or value > filters.get("date_to", "9999"):
                    continue
            result.add(path)
        return result

    def retrieve(self, subject, graph, metadata, plan, allowed):
        deadline = min(plan["deadline"], time.monotonic()+15)
        query = subject["text"]
        negated_paths = sorted(path for path in allowed if explicitly_negated(graph.notes[path]["name"], query))
        if negated_paths:
            query = positive_query(query)
            subject = {**subject, "text": query}
        raw = subject.get("raw_chunks", [])
        if not isinstance(raw, list) or len(raw) > 8 or any(not isinstance(v, str) or len(v) > 1600 for v in raw):
            raise DomainError("INVALID_QUERY", "Use at most eight bounded source chunks.", 422)
        if not isinstance(subject.get("entities", []), list) or len(subject.get("entities", [])) > 50 \
                or any(not isinstance(v, str) or len(v) > 200 for v in subject.get("entities", [])):
            raise DomainError("INVALID_QUERY", "Use at most fifty bounded entity names.", 422)
        query_terms = sorted(words(query+"\n"+"\n".join(raw)), key=lambda v: (-len(v), v))[:40]
        fts_query = " OR ".join('"'+term.replace('"', '""')+'"' for term in query_terms)
        rows, missing, channels, truncated = {}, [], {}, bool(subject.get("truncated"))
        query_vector = None
        segments = []
        paragraphs = [bounded(part, 1600) for part in query.splitlines() if len(words(part)) >= 5]
        evidence_queries = paragraphs[:7] if len(paragraphs) > 1 else []

        def add(path, channel, rank, *, vector=None, excerpt=None, graph_path=None):
            if path not in allowed or len(rows) >= 300 and path not in rows:
                return
            note = graph.notes[path]
            item = rows.setdefault(path, {"path": path, "sha256": note["sha"], "title": note["name"],
                "kind": "note", "strategies": {}, "features": {}, "graph_paths": [], "excerpt": ""})
            item["strategies"][channel] = min(rank, item["strategies"].get(channel, rank))
            if vector is not None:
                item["features"]["vector"] = max(vector, item["features"].get("vector", -1))
            if excerpt:
                item["excerpt"] = excerpt[:2400]
            if graph_path and graph_path not in item["graph_paths"]:
                item["graph_paths"].append(graph_path)

        scope_json = json.dumps(sorted(allowed))
        if fts_query and "fts" not in self.disabled:
            matches = self.state.rows("SELECT path,substr(body,1,2400) AS body FROM note_fts WHERE note_fts MATCH ? "
                "AND path IN (SELECT value FROM json_each(?)) ORDER BY rank,path LIMIT 50", (fts_query, scope_json))
            for rank, row in enumerate(matches, 1):
                add(row["path"], "fts", rank, excerpt=row["body"])
            channels["fts"] = len(matches)
        if self.semantic and "vector" not in self.disabled:
            try:
                found = self.semantic.search(bounded(query, 4096), limit=50, allowed_paths=allowed, deadline=deadline,
                                             include_vector=True, source_chunks=raw, evidence_queries=evidence_queries)
                query_vector = found.get("query_vector")
                segments = found.get("segment_evidence", [])
                for rank, item in enumerate(found["results"], 1):
                    add(item["path"], "vector", rank, vector=item["score"], excerpt=item["excerpt"])
                channels["vector"] = len(found["results"])
                if found["index"]["status"] != "READY":
                    missing.append("vector_partial")
            except DomainError:
                missing.append("vector")
        else:
            missing.append("vector")
        if "profiles" in plan:
            profiles = plan["profiles"]
            profile_hits = []
            if fts_query and graph.scope.paths is not None:
                # Shared FTS rows include unrestricted profile members.
                # Restricted callers rank only their scoped profile text.
                local_matches = [(len(set(query_terms) & words(profile["text"])), path) for path, profile in profiles.items()]
                profile_hits = [{"path": path} for score, path in sorted(local_matches, key=lambda v: (-v[0], v[1]))[:50] if score]
            elif fts_query:
                profile_hits = self.state.rows("SELECT path FROM context_profile_fts WHERE context_profile_fts MATCH ? "
                    "AND path IN (SELECT value FROM json_each(?)) ORDER BY rank,path LIMIT 50", (fts_query, json.dumps(sorted(profiles))))
            for rank, row in enumerate(profile_hits, 1):
                profile = profiles[row["path"]]
                add(row["path"], "profile_fts", rank, excerpt=profile["text"])
                if row["path"] in rows:
                    rows[row["path"]]["profile_sources"] = profile["sources"]
                    rows[row["path"]]["profile_sha"] = profile["sha256"]
            if query_vector:
                vector_profiles = []
                for path, profile in profiles.items():
                    if profile.get("vector") and profile.get("model_sha") == self.semantic.model:
                        score = sum(a*b for a, b in zip(query_vector, profile["vector"], strict=True))
                        vector_profiles.append((score, path))
                for rank, (score, path) in enumerate(sorted(vector_profiles, key=lambda v: (-v[0], v[1]))[:50], 1):
                    add(path, "profile_vector", rank, vector=score, excerpt=profiles[path]["text"])
                    if path in rows:
                        rows[path]["profile_sources"] = profiles[path]["sources"]
                        rows[path]["profile_sha"] = profiles[path]["sha256"]
            channels["profiles"] = len(profiles)
            if len(profiles) < len(graph.structure().eligible-{plan["configuration"]["fallback_note"], plan["configuration"]["template_path"]}):
                missing.append("profiles_partial")
        entity_matches = []
        explicit = set(subject.get("entities", []))
        normalized = " "+query.casefold()+" "
        for path in sorted(allowed):
            terms = [graph.notes[path]["name"], *metadata.get(path, {}).get("aliases", [])]
            if any(term in explicit or re.search(r"(?<!\w)"+re.escape(term.casefold())+r"(?!\w)", normalized)
                   for term in terms):
                entity_matches.append(path)
        for rank, path in enumerate(entity_matches[:50], 1):
            add(path, "entity", rank)
        channels["entity"] = min(50, len(entity_matches))
        if len(metadata) < len(graph.notes):
            missing.append("metadata_partial")
        meta_matches = [p for p in sorted(allowed) if set(graph.notes[p]["tags"]) & set(query_terms)
                        or words(str(metadata.get(p, {}).get("project", ""))) & set(query_terms)]
        for rank, path in enumerate(meta_matches[:50], 1):
            add(path, "metadata", rank)
        channels["metadata"] = min(50, len(meta_matches))
        if "date_field" in plan["filters"]:
            for rank, path in enumerate(sorted(allowed)[:50], 1):
                add(path, "temporal", rank)
            channels["temporal"] = min(50, len(allowed))
        # Explicit entity/name hits seed a bounded two-hop directed traversal.
        frontier = [(p, [p]) for p in entity_matches[:12]]
        visited = set(entity_matches)
        graph_count = 0
        for _ in range(0 if "graph" in self.disabled else 2):
            next_frontier = []
            for parent, chain in frontier:
                for target in sorted(graph.outgoing[parent]):
                    if target in allowed and target not in visited and graph_count < 50:
                        visited.add(target)
                        graph_count += 1
                        add(target, "graph", graph_count, graph_path=[*chain, target])
                        next_frontier.append((target, [*chain, target]))
            frontier = next_frontier
        channels["graph"] = graph_count
        ranked = self.rank(list(rows.values()), subject)[:100]
        # Expansion follows both real directions and records the actual directed edge.
        expanded = 0
        for item in ranked[:0 if "expansion" in self.disabled else 20]:
            for neighbor in sorted(graph.outgoing[item["path"]] | graph.incoming[item["path"]]):
                if time.monotonic() >= deadline or expanded >= 64:
                    truncated = True
                    break
                if neighbor in allowed and neighbor not in rows:
                    expanded += 1
                    edge = [item["path"], neighbor] if neighbor in graph.outgoing[item["path"]] else [neighbor, item["path"]]
                    add(neighbor, "expansion", expanded, graph_path=edge)
        # Newly expanded objects get their own content and complete reranking.
        for item in rows.values():
            if not item["excerpt"]:
                excerpt = self.state.one("SELECT substr(body,1,2400) AS body FROM note_fts WHERE path=?", (item["path"],))
                item["excerpt"] = excerpt["body"] if excerpt else ""
        if time.monotonic() >= deadline:
            missing.append("deadline")
        return {"results": self.rank(list(rows.values()), subject)[:200], "channels": channels,
                "negated_entities": negated_paths, "segment_evidence": segments,
                "missing_strategies": sorted(set(missing)), "degraded": bool(missing), "truncated": truncated}

    @staticmethod
    def rank(items, subject):
        terms = words(subject["text"]+"\n"+"\n".join(subject.get("raw_chunks", [])))
        for item in items:
            title, body = words(item["title"]), words(item["excerpt"])
            title_match = len(terms & title)/max(1, len(title))
            lexical = len(terms & body)/max(1, min(len(terms), 12))
            rrf = sum(1/(60+rank) for rank in item["strategies"].values())
            vector = max(0, item["features"].get("vector", 0))
            item["features"].update(title_match=title_match, lexical=min(1, lexical), rrf=rrf)
            # E5 cosine scores have a high common floor. Center them before
            # fusion so semantic evidence can outweigh a coincidental title word.
            semantic = max(0, min(1, (vector-.7)/.3))
            item["score"] = round(.05*title_match+.1*min(1, lexical)+.8*semantic+.05*min(1, rrf*30), 6)
        return sorted(items, key=lambda v: (-v["score"], v["path"]))

    @classmethod
    def merge(cls, first, second, subject):
        values = {v["path"]: v for v in first["results"]}
        for item in second["results"]:
            if item["path"] not in values:
                values[item["path"]] = item
                continue
            old = values[item["path"]]
            for strategy, rank in item["strategies"].items():
                old["strategies"][strategy] = min(rank, old["strategies"].get(strategy, rank))
            if item["features"].get("vector", -1) > old["features"].get("vector", -1):
                old["features"]["vector"] = item["features"]["vector"]
        return {**first, "results": cls.rank(list(values.values()), subject)[:200],
                "channels": {key: max(first["channels"].get(key, 0), second["channels"].get(key, 0))
                             for key in first["channels"].keys() | second["channels"].keys()},
                "missing_strategies": sorted(set(first["missing_strategies"]) | set(second["missing_strategies"])),
                "degraded": first["degraded"] or second["degraded"], "truncated": first["truncated"] or second["truncated"]}

    @staticmethod
    def assess(result):
        items = result["results"]
        if not items or items[0]["score"] < .2:
            return {"status": "insufficient_evidence"}
        if len(items) > 1 and items[0]["score"]-items[1]["score"] < .05:
            return {"status": "ambiguous"}
        return {"status": "sufficient"}
