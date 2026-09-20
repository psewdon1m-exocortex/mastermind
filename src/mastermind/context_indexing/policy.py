"""Crusher-only eligibility and calibrated decisions over unrestricted retrieval evidence."""
import json
import math
from pathlib import Path

from ..errors import DomainError
from .graph import Graph, Scope

VERSION = "crusher.placement.v1"


class PlacementPolicy:
    def __init__(self, settings, *, calibration=None):
        self.settings = settings
        self.calibration = calibration

    def thresholds(self, result):
        value = self.calibration
        if value is None:
            try:
                value = json.loads((Path(__file__).parent / "calibration.json").read_text("utf-8"))
            except (OSError, ValueError):
                return None
        if value.get("policy_version") != VERSION or value.get("qualified") is not True:
            return None
        representation = self.settings.state.setting("semantic_representation")
        if representation and "vector" not in result["missing_strategies"] \
                and value.get("search_representation") != representation:
            return None
        if value.get("embedding_sha256") and "vector" not in result["missing_strategies"] \
                and self.settings.state.setting("semantic_model_sha") != value["embedding_sha256"]:
            return None
        variant = ",".join(result["missing_strategies"]) or "complete"
        if result.get("curator_pass"):
            variant += ":curator"
        thresholds = value.get("variants", {}).get(variant)
        if not thresholds:
            return None
        return {**thresholds, "version": value["version"], "variant": variant}

    def assess(self, result, graph, configuration=None):
        structure = graph.structure()
        config = configuration or self.settings.get()
        excluded = {config["fallback_note"], config["template_path"], graph.root, *result.get("negated_entities", [])}
        candidates = {}
        for item in result["results"]:
            if item["path"] in excluded or item["path"].startswith("root/templates/"):
                continue
            for anchor in sorted(structure.memberships(item["path"])-excluded):
                if any(c in graph.notes[anchor]["name"] for c in "[]#^|"):
                    continue
                chain = structure.paths[anchor]
                evidence = {item["path"]: item["sha256"], **item.get("profile_sources", {})}
                candidate = candidates.setdefault(anchor, {"path": anchor, "chain": chain, "score": 0,
                    "support": {}, "evidence": {}, "profiles": {}, "features": {}})
                candidate["support"][item["path"]] = item["score"]
                candidate["evidence"].update(evidence)
                if item.get("profile_sha"):
                    candidate["profiles"][item["path"]] = item["profile_sha"]
                if item["score"] >= candidate["score"]:
                    candidate["features"] = item["features"].copy()
                candidate["score"] = max(candidate["score"], item["score"])
        for candidate in candidates.values():
            # At most a small bounded contribution from distinct source notes.
            candidate["score"] = round(candidate["score"] + .025*min(4, math.log2(1+len(candidate["support"])))
                                       + .005*min(8, len(candidate["chain"])), 6)
        ranked = sorted(candidates.values(), key=lambda v: (-v["score"], -len(v["chain"]), v["path"]))[:20]
        if not ranked:
            return {"status": "insufficient_evidence", "reason": "NO_ELIGIBLE_TARGET", "placement_candidates": []}
        threshold = self.thresholds(result)
        top = ranked[0]
        # Profiles of broad parents pool their descendants' vocabulary. Prefer
        # a nearly equivalent, more specific supported descendant before
        # evaluating unrelated alternatives.
        descendants = [v for v in ranked[1:] if top["path"] in v["chain"] and v["score"] >= top["score"]-.04]
        if descendants:
            top = descendants[0]
            ranked = [top, *[v for v in ranked if v is not top]]
        # Parent/child alternatives are structurally related, not independent conflicting branches.
        competitors = [v for v in ranked[1:] if v["path"] not in top["chain"] and top["path"] not in v["chain"]]
        gap = top["score"]-(competitors[0]["score"] if competitors else 0)
        explicitly_multiple = top["features"].get("title_match", 0) == 1 and any(
            v["features"].get("title_match", 0) == 1 and v["features"].get("lexical", 0) >= .3
            for v in competitors)
        segment_targets = []
        for segment in result.get("segment_evidence", []):
            scores = {}
            for evidence in segment:
                for anchor in structure.memberships(evidence["path"])-excluded:
                    scores[anchor] = max(scores.get(anchor, -1), evidence["score"])
            ordered = sorted(scores, key=lambda path: (-scores[path], -len(structure.paths[path]), path))
            if not ordered:
                continue
            winner = ordered[0]
            descendants = [path for path in ordered[1:] if winner in structure.paths[path] and scores[path] >= scores[winner]-.03]
            if descendants:
                winner = descendants[0]
            alternatives = [path for path in ordered if path not in structure.paths[winner] and winner not in structure.paths[path]]
            if scores[winner] >= .8 and (not alternatives or scores[winner]-max(scores[path] for path in alternatives) >= .01):
                segment_targets.append(winner)
        segment_conflict = any(a not in structure.paths[b] and b not in structure.paths[a]
                               for a in segment_targets for b in segment_targets)
        explicitly_multiple = explicitly_multiple or segment_conflict
        weak_counterevidence = bool(result.get("topic_exclusions")) or (
            bool(result.get("negated_entities")) and top["features"].get("lexical", 0) < .3
            and top["features"].get("title_match", 0) < 1)
        sufficient = threshold and top["score"] >= threshold["score"] and gap >= threshold["gap"] \
            and top["features"].get("lexical", 0) >= threshold.get("lexical", 0) and not result["truncated"] \
            and not explicitly_multiple and not weak_counterevidence
        return {"status": "sufficient" if sufficient else "ambiguous", "reason": "SUPPORTED" if sufficient else
                "SOURCE_TOPIC_CONFLICT" if explicitly_multiple else "SOURCE_COUNTEREVIDENCE" if weak_counterevidence else
                "UNCALIBRATED" if threshold is None else "LOW_EVIDENCE", "placement_candidates": ranked[:3],
                "refinement_may_help": not (explicitly_multiple or weak_counterevidence),
                "calibration": threshold["version"] if threshold else None, "gap": round(gap, 6),
                "multiple_topics": explicitly_multiple, "counterevidence": weak_counterevidence}

    def decide(self, result, graph, snapshot):
        if result["status"] == "sufficient" and result.get("placement_candidates"):
            top = result["placement_candidates"][0]
            note = graph.notes[top["path"]]
            return {"outcome": "placed", "anchor": top["path"], "anchor_sha": note["sha"], "anchor_name": note["name"],
                    "chain": top["chain"], "skeleton_sha": graph.structure().sha, "evidence": top["evidence"],
                    "profiles": top["profiles"], "ranking_score": top["score"], "confidence": None, "suggested": None,
                    "graph_sha": graph.sha,
                    "diagnostic": None, "calibration": result.get("calibration"), "policy_version": VERSION,
                    "query_id": result["query_id"], "curator": result["curator"]}
        return self.pool(snapshot, graph, result.get("reason", "INSUFFICIENT_EVIDENCE"), query_id=result["query_id"])

    def pool(self, snapshot, graph, reason, *, query_id=None):
        fallback = self.settings.fallback(snapshot["configuration"], graph)
        return {"outcome": "pooled", "anchor": fallback["path"], "anchor_sha": fallback["sha256"],
                "anchor_name": fallback["name"], "chain": graph.path(fallback["path"]), "skeleton_sha": None,
                "evidence": {}, "profiles": {}, "confidence": None, "suggested": None, "diagnostic": reason,
                "policy_version": VERSION, "query_id": query_id}

    def fresh(self, decision, graph):
        if decision.get("policy_version") != VERSION or decision["anchor"] not in graph.notes:
            return False
        if graph.notes[decision["anchor"]]["sha"] != decision["anchor_sha"]:
            return False
        if decision["outcome"] == "placed":
            if decision.get("profiles") and decision.get("graph_sha") != graph.sha:
                return False
            structure = graph.structure()
            if decision["anchor"] not in structure.eligible or structure.sha != decision["skeleton_sha"]:
                return False
            if any(p not in graph.notes or graph.notes[p]["sha"] != sha for p, sha in decision["evidence"].items()):
                return False
        return True

    def revalidate(self, decision, snapshot):
        graph = Graph(self.settings.vault, Scope("crusher"))
        if self.fresh(decision, graph):
            if decision["outcome"] == "pooled":
                self.settings.fallback(snapshot["configuration"], graph)
            name = graph.notes[decision["anchor"]]["name"]
            if any(c in name for c in "[]#^|"):
                raise DomainError("FALLBACK_INVALID", "The selected note name cannot form a safe link.", 422)
            return decision
        return self.pool(snapshot, graph, "EVIDENCE_CHANGED", query_id=decision.get("query_id"))
