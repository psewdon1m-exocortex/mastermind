"""Root/main/key placement. Paths stay local; models receive only current-level cards."""
import hashlib
import json
import math
import re
import secrets
from collections import defaultdict, deque

from .errors import DomainError
from .gemini import Choice
from .references import masked


class Hierarchy:
    def __init__(self, vault, worker, provider):
        self.vault, self.state, self.worker, self.provider = vault, vault.state, worker, provider

    def skeleton(self):
        with self.vault.coordinator.lock:
            self.vault.index()
            notes = {row["path"]: {**row, "tags": json.loads(row["tags"])} for row in self.state.rows("SELECT * FROM notes")}
            names = {row["name_key"]: path for path, row in notes.items()}
            root = self.state.setting("crusher_root", "root.md")
            if root not in notes:
                return {"root": None, "nodes": {}, "children": {}, "counts": {}, "sha": "missing-root"}
            children = defaultdict(set)
            for edge in self.state.rows("SELECT source,target_key FROM edges WHERE kind='internal' AND broken=0"):
                source, destination = edge["source"], names.get(edge["target_key"])
                if source not in notes or destination not in notes:
                    continue
                tags = set(notes[destination]["tags"])
                if source == root and "main" in tags or source != root and set(notes[source]["tags"]) & {"main", "key"} and "key" in tags:
                    children[source].add(destination)
            # Cap path multiplicity at two. The fixed-point walk also labels
            # reachable cycles ambiguous without enumerating exponential paths.
            counts, queue, visited_edges = {root: 1}, deque([root]), set()
            while queue:
                parent = queue.popleft()
                for child in children[parent]:
                    edge = (parent, child, counts[parent])
                    if edge in visited_edges:
                        continue
                    visited_edges.add(edge)
                    before = counts.get(child, 0)
                    counts[child] = min(2, before+counts[parent])
                    if counts[child] != before:
                        queue.append(child)
            shaped = {path: {"sha": notes[path]["sha"], "tags": notes[path]["tags"],
                             "children": sorted(children[path])} for path in counts}
            digest = hashlib.sha256(json.dumps(shaped, sort_keys=True).encode()).hexdigest()
            return {"root": root, "nodes": notes, "children": {key: sorted(value) for key, value in children.items()},
                    "counts": counts, "sha": digest}

    def rank(self, paths, skeleton, summary):
        query_words = set(re.findall(r"\w+", summary.casefold()))
        terms = sorted(query_words, key=lambda word: (-len(word), word))[:20]
        query = " OR ".join('"' + word[:64].replace('"', '""') + '"' for word in terms)
        matches = self.state.rows("SELECT path FROM note_fts WHERE note_fts MATCH ? ORDER BY rank LIMIT 500", (query,)) if query else []
        fts = {row["path"]: 20/(index+1) for index, row in enumerate(matches)}
        cards = []
        for path in paths:
            note = skeleton["nodes"][path]
            # Only the currently traversed children are read, never unrelated
            # branches, attachments, plugin files or a full Vault context dump.
            excerpt = masked(self.vault.read(path)).replace("\0", "")[:512]
            words = set(re.findall(r"\w+", (note["name"]+" "+excerpt).casefold()))
            score = len(query_words & words) + fts.get(path, 0)
            cards.append({"path": path, "title": note["name"], "tags": note["tags"], "excerpt": excerpt, "score": score})
        cards.sort(key=lambda card: (-card["score"], card["title"].casefold()))
        # FTS/lexical narrowing is local; at most 48 candidates go to the local
        # embedding Worker in 16-chunk batches, and at most 12 reach the provider.
        candidates = cards[:48]
        try:
            query = self.worker.embed([summary[:4000]], query=True)["vectors"][0]
            for offset in range(0, len(candidates), 16):
                batch = candidates[offset:offset+16]
                vectors = self.worker.embed([card["title"]+"\n"+card["excerpt"] for card in batch])["vectors"]
                for card, vector in zip(batch, vectors, strict=True):
                    card["score"] = sum(a*b for a, b in zip(query, vector, strict=True))
            candidates.sort(key=lambda card: (-card["score"], card["title"].casefold()))
        except DomainError:
            # Model outage cannot broaden private context or block a safe Inbox placement.
            pass
        return candidates[:12]

    def place(self, understanding, model, *, checkpoint, budget):
        """checkpoint(key, callable) durably caches each provider selection and budget."""
        try:
            skeleton = self.skeleton()
        except DomainError:
            return self.inbox("HIERARCHY_UNAVAILABLE")
        if not skeleton["root"]:
            return self.inbox("ROOT_MISSING")
        parent, chain, confidence = skeleton["root"], [], 1.0
        breadcrumb = []
        for level in range(8):
            paths = skeleton["children"].get(parent, [])
            if not paths:
                return self.chosen(parent, chain, confidence, skeleton) if chain else self.inbox("MAIN_BRANCH_MISSING")
            local_cards = self.rank(paths, skeleton, understanding["summary"] + " " + " ".join(understanding["topics"]))
            key = "placement_" + str(level)
            # Persist handles/card bytes before provider execution so a restart
            # cannot reinterpret a returned handle as a different current note.
            packet = checkpoint(key + "_cards", lambda local_cards=local_cards: {"skeleton_sha": skeleton["sha"],
                "mapping": {secrets.token_hex(6): card for card in local_cards}, "breadcrumb": breadcrumb.copy()})
            if packet["skeleton_sha"] != skeleton["sha"]:
                return self.inbox("HIERARCHY_CHANGED")
            mapping = packet["mapping"]
            cards = [{"handle": handle, "title": card["title"], "tags": card["tags"], "excerpt": card["excerpt"]}
                     for handle, card in mapping.items()]
            if not cards:
                return self.inbox("CHILD_BRANCH_MISSING")
            context = {"candidates": cards, "breadcrumb": packet["breadcrumb"]}

            def choose(cards=cards, context=context):
                unique = []
                for card in cards:
                    value = json.dumps({key: value for key, value in card.items() if key != "handle"}, ensure_ascii=False, sort_keys=True)
                    digest = hashlib.sha256(value.encode()).hexdigest()
                    if digest not in budget["unique"]:
                        unique.append((digest, self.provider.token_count(model, value)))
                transmitted = self.provider.token_count(model, json.dumps(context, ensure_ascii=False))
                if sum(budget["unique"].values()) + sum(count for _, count in unique) > 12000 \
                        or budget["transmitted"]+transmitted > 24000:
                    return {"action": "inbox", "handle": None, "confidence": 0.0, "diagnostic": "CONTEXT_BUDGET"}
                budget["unique"].update(unique)
                budget["transmitted"] += transmitted
                # The engine persists this reservation before the remote call,
                # including uncertain outcomes that may need a paid retry.
                checkpoint("budget-reservation", lambda: None, persist_only=True)
                return self.provider.generate(model, "Choose one candidate for these source topics; stop at an adequate current branch or choose Inbox when uncertain.",
                    {"source_summary": understanding["summary"], "topics": understanding["topics"], **context}, Choice)

            decision = checkpoint(key + "_choice", choose)
            selected = decision.get("handle")
            score = decision.get("confidence")
            if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                raise DomainError("PLACEMENT_INVALID", "The model returned invalid placement confidence.", 422)
            confidence = min(confidence, score)
            if decision["action"] == "inbox":
                return self.inbox(decision.get("diagnostic", "MODEL_UNCERTAIN"), confidence=confidence)
            if decision["action"] == "stop":
                return self.chosen(parent, chain, confidence, skeleton) if chain else self.inbox("ROOT_NOT_DESTINATION")
            if decision["action"] != "choose" or selected not in mapping:
                raise DomainError("PLACEMENT_INVALID", "The model selected a candidate that was not offered.", 422)
            child = mapping[selected]["path"]
            if child not in paths or skeleton["counts"].get(child) != 1 or child in chain \
                    or {"main", "key"} <= set(skeleton["nodes"][child]["tags"]):
                return self.inbox("AMBIGUOUS_HIERARCHY", suggested=child, confidence=confidence)
            parent = child
            chain.append(child)
            breadcrumb.append({"title": skeleton["nodes"][child]["name"]})
        if skeleton["children"].get(parent):
            return self.inbox("HIERARCHY_DEPTH_LIMIT", suggested=parent, confidence=confidence)
        return self.chosen(parent, chain, confidence, skeleton)

    @staticmethod
    def inbox(diagnostic, *, suggested=None, confidence=0.0):
        return {"anchor": None, "suggested": suggested, "confidence": confidence, "diagnostic": diagnostic,
                "chain": [], "skeleton_sha": None}

    def chosen(self, path, chain, confidence, skeleton):
        if confidence < 0.90:
            return self.inbox("LOW_CONFIDENCE", suggested=path, confidence=confidence)
        return {"anchor": path, "suggested": None, "confidence": confidence, "diagnostic": None,
                "chain": chain, "skeleton_sha": skeleton["sha"]}

    def revalidate(self, placement):
        if not placement["anchor"]:
            return placement
        try:
            skeleton = self.skeleton()
            if placement["skeleton_sha"] == skeleton["sha"] and skeleton["counts"].get(placement["anchor"]) == 1:
                return placement
        except DomainError:
            pass
        return self.inbox("HIERARCHY_CHANGED", suggested=placement["anchor"])
