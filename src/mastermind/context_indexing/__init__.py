"""Context-indexing: reusable local retrieval with an independent Crusher placement policy."""
import time

from ..errors import DomainError
from ..semantic import Semantic
from .curator import Curator
from .graph import Graph, Scope
from .index import Index
from .pipeline import Pipeline, source_features
from .policy import PlacementPolicy
from .related import RelatedNotes
from .settings import Settings


class ContextIndexing:
    def __init__(self, service, *, worker=None, semantic=None, calibration=None):
        self.service = service
        self.settings = Settings(service)
        self.index = Index(service)
        self.semantic = semantic or getattr(service, "semantic", None) or Semantic(service, worker=worker)
        self.curator = Curator(worker or self.semantic.worker)
        self.pipeline = Pipeline(service, self.index, semantic=self.semantic, curator=self.curator)
        self.related = RelatedNotes(service, self.pipeline, self.settings)
        self.policy = PlacementPolicy(self.settings, calibration=calibration)
        self.next_batch = 0
        self.completed_batch = None
        self.index_failure = None

    def place(self, understanding, raw, snapshot, *, checkpoint=None, query_id=None, deadline=None):
        if deadline is not None and deadline <= time.time():
            return self.policy.pool(snapshot, Graph(self.service.vault, Scope("crusher")),
                                    "PLACEMENT_DEADLINE", query_id=query_id)
        result, graph = self.pipeline.run(source_features(understanding, raw), scope=Scope("crusher"),
            query_type="placement_analysis", configuration=snapshot["configuration"],
            assessment=lambda value, graph: self.policy.assess(value, graph, snapshot["configuration"]),
            checkpoint=checkpoint, query_id=query_id,
            deadline=time.monotonic()+max(0, deadline-time.time()) if deadline else None)
        return self.policy.decide(result, graph, snapshot)

    def status(self):
        value = self.settings.get()
        errors = {}
        try:
            self.settings.validate(value)
        except DomainError as error:
            errors["configuration"] = error.code
        try:
            search = self.semantic.status()
        except DomainError as error:
            search = {"status": "UNAVAILABLE", "error": error.code}
        curator = self.curator.status()
        if self.index_failure:
            search = {**search, "status": "DEGRADED", "error": self.index_failure}
        return {**value, "graph_root": self.service.state.setting("crusher_root", "root.md"),
                "readiness": {"configuration": "READY" if not errors else "INVALID", "errors": errors,
                    "search": search, "curator": {**curator, "requested": value["curator_enabled"],
                    "effective": value["curator_enabled"] and curator["ready"]}}}

    def maintain(self):
        if time.monotonic() < self.next_batch:
            return
        self.next_batch = time.monotonic()+2
        self.index.expire_traces()
        state = self.service.state
        signature = (state.one("SELECT value FROM metadata WHERE key='generation'")["value"],
                     state.one("SELECT COUNT(*) AS n FROM semantic_chunks")["n"],
                     state.setting("semantic_model_sha"), self.settings.get()["revision"])
        if self.completed_batch == signature:
            return
        graph = Graph(self.service.vault, Scope("crusher"), refresh=False)
        metadata = self.index.sync(graph, limit=32, deadline=time.monotonic()+1)
        configuration = self.settings.get()
        profiles = self.index.profiles(graph, graph.structure(), configuration, limit=8, deadline=time.monotonic()+1)
        required = graph.structure().eligible-{configuration["fallback_note"], configuration["template_path"], graph.root}
        if len(metadata) == len(graph.notes) and required <= profiles.keys():
            self.completed_batch = signature
        self.index_failure = None


__all__ = ["ContextIndexing", "Scope"]
