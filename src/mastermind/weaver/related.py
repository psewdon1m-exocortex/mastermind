"""Read-only recommendations from a bounded, possibly unsaved editor buffer."""
import threading
import time
from pathlib import PurePosixPath

from ..errors import DomainError
from ..fs import safe_relative
from .evidence import packet, selected_diagnostics
from .graph import Scope
from .pipeline import source_features, words


class RelatedNotes:
    def __init__(self, service, pipeline, settings):
        self.service, self.pipeline, self.settings = service, pipeline, settings
        # Typing must not queue unbounded inference work or occupy both common slots.
        self.slot = threading.BoundedSemaphore(1)

    def recommend(self, data, *, scope=None):
        if not isinstance(data, dict) or set(data)-{"path", "text", "focus", "sampled"}:
            raise DomainError("INVALID_REQUEST", "Invalid related-note request.", 422)
        for field, maximum in (("path", 2048), ("text", 16384), ("focus", 4096)):
            value = data.get(field, "" if field == "focus" else None)
            try:
                valid = isinstance(value, str) and len(value.encode()) <= maximum
            except UnicodeError:
                valid = False
            if not valid:
                raise DomainError("INVALID_REQUEST", "Related-note context exceeds its text limits.", 422)
        if type(data.get("sampled", False)) is not bool:
            raise DomainError("INVALID_REQUEST", "Invalid context sampling flag.", 422)
        path = safe_relative(data["path"])
        scope = scope or Scope('owner')
        if not scope.permits(path):
            raise DomainError('FORBIDDEN', 'The source note is outside the authorized scope.', 403)
        self.service.data_ready()
        # Verify the source is a real permitted note, but never save the supplied text.
        self.service.vault.read(path)
        result = {"path": path, "items": [], "degraded": False, "sampled": data.get("sampled", False)}
        if not words(data["text"]):
            result.update(outcome='no_match', evidence_packet=packet({'task': 'note_similarity'}, None, []),
                          diagnostics=selected_diagnostics({}, []))
            return result
        if not self.slot.acquire(blocking=False):
            raise DomainError("CONTEXT_BUSY", "Related-note search is busy. Try again shortly.", 429)
        try:
            # Note roles belong to Crusher placement, not knowledge lookup.
            # Every authorized note can supply evidence; only self is excluded.
            excluded = {path}
            paths = frozenset(row["path"] for row in self.service.state.rows("SELECT path FROM notes")
                              if row["path"] not in excluded and scope.permits(row['path']))
            subject = source_features({"title": PurePosixPath(path).stem,
                                       "summary": data.get("focus") or data["text"][:1600]}, data["text"])
            subject.update(source_title=PurePosixPath(path).stem, source_body=data["text"],
                           source_focus=data.get("focus", ""))
            deadline = time.monotonic()+15
            found, graph = self.pipeline.run(subject, scope=Scope(scope.principal, paths), query_type="note_similarity",
                configuration={"curator_enabled": False}, deadline=deadline)
            selected = []
            for item in found["results"]:
                features = item["features"]
                # Graph adjacency and the common E5 floor alone are not topic evidence.
                if item["path"] in excluded or item["path"] in found.get("negated_entities", []) or not features.get("supported"):
                    continue
                result["items"].append({"path": item["path"], "title": item["title"],
                                        "excerpt": " ".join(item["excerpt"].split())[:320],
                                        "relation": item["relation"], "reason": item["reason"]})
                selected.append(item)
                if len(result["items"]) == 8:
                    break
            self.service.data_ready()
            result["degraded"] = bool(found["degraded"] or found["truncated"])
            result['evidence_packet'] = packet(found, graph, selected, query=data.get('focus') or data['text'],
                                        context='none', budget=8192, deadline=deadline)
            if graph is not None:
                fresh = {s['path'] for s in result['evidence_packet']['sources']}
                result['items'] = [i for i in result['items'] if i['path'] in fresh]
                selected = [i for i in selected if i['path'] in fresh]
            result['diagnostics'] = selected_diagnostics(found, selected, result['evidence_packet'])
            result['degraded'] |= result['evidence_packet']['completeness']['state'] == 'partial'
            result['outcome'] = 'matches' if result['items'] else 'incomplete' if result['degraded'] else 'no_match'
            return result
        finally:
            self.slot.release()
