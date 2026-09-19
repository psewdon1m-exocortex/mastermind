"""Read-only recommendations from a bounded, possibly unsaved editor buffer."""
import threading
import time
from pathlib import PurePosixPath

from ..errors import DomainError
from ..fs import safe_relative
from .graph import Scope
from .pipeline import source_features, words


class RelatedNotes:
    def __init__(self, service, pipeline, settings):
        self.service, self.pipeline, self.settings = service, pipeline, settings
        # Typing must not queue unbounded inference work or occupy both common slots.
        self.slot = threading.BoundedSemaphore(1)

    def recommend(self, data):
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
        self.service.data_ready()
        # Verify the source is a real permitted note, but never save the supplied text.
        self.service.vault.read(path)
        result = {"path": path, "items": [], "degraded": False, "sampled": data.get("sampled", False)}
        if not words(data["text"]):
            return result
        if not self.slot.acquire(blocking=False):
            raise DomainError("CONTEXT_BUSY", "Related-note search is busy. Try again shortly.", 429)
        try:
            configuration = self.settings.get()
            excluded = {path, configuration["template_path"], configuration["fallback_note"],
                        self.service.state.setting("crusher_root", "root.md")}
            paths = frozenset(row["path"] for row in self.service.state.rows("SELECT path FROM notes")
                              if row["path"] not in excluded)
            subject = source_features({"title": PurePosixPath(path).stem,
                                       "summary": data.get("focus") or data["text"][:1600]}, data["text"])
            found, _ = self.pipeline.run(subject, scope=Scope("owner", paths), query_type="knowledge_lookup",
                configuration={"curator_enabled": False}, deadline=time.monotonic()+15)
            for item in found["results"]:
                features = item["features"]
                # Graph adjacency and the common E5 floor alone are not topic evidence.
                if item["path"] in excluded or not (features.get("lexical", 0) > 0
                        or features.get("title_match", 0) > 0 or features.get("vector", 0) >= .78):
                    continue
                result["items"].append({"path": item["path"], "title": item["title"],
                                        "excerpt": " ".join(item["excerpt"].split())[:320]})
                if len(result["items"]) == 8:
                    break
            self.service.data_ready()
            result["degraded"] = bool(found["degraded"] or found["truncated"])
            return result
        finally:
            self.slot.release()
