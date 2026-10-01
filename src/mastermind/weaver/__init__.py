"""Weaver: scoped retrieval, graph work and policy-controlled note placement."""
import time

from ..errors import DomainError
from ..semantic import Semantic
from .bibliotekar import Bibliotekar
from .execution import PlacementExecutor
from .graph import Graph, Scope
from .index import Index
from .objects import walk
from .pipeline import Pipeline, source_features
from .policy import PlacementPolicy
from .related import RelatedNotes
from .requests import ExecutePlacement, Lookup, Placement, Similar, Walk
from .settings import Settings


class Weaver:
    def __init__(self, service, *, worker=None, semantic=None, calibration=None):
        self.service = service
        self.settings = Settings(service)
        self.index = Index(service)
        self.semantic = semantic or getattr(service, "semantic", None) or Semantic(service, worker=worker)
        self.bibliotekar = Bibliotekar(worker or self.semantic.worker)
        self.pipeline = Pipeline(service, self.index, semantic=self.semantic, curator=self.bibliotekar)
        self.related = RelatedNotes(service, self.pipeline, self.settings)
        self.policy = PlacementPolicy(self.settings, calibration=calibration)
        self.executor = PlacementExecutor(self)
        self.curator = self.bibliotekar  # Legacy in-process clients.
        self.next_batch = 0
        self.completed_batch = None
        self.index_failure = None

    def run(self, request):
        """Dispatch a bounded work order from an authenticated internal consumer."""
        self.service.data_ready()
        if isinstance(request, Lookup):
            if not isinstance(request.query, str) or not request.query.strip() or len(request.query.encode()) > 4096 \
                    or type(request.limit) is not int or not 1 <= request.limit <= 50:
                raise DomainError('INVALID_QUERY', 'Use a query up to 4 KiB and 1–50 results.', 422)
            result, _ = self.pipeline.run({'text': request.query}, scope=request.scope,
                query_type='knowledge_lookup', filters=request.filters, deadline=request.deadline,
                configuration={'curator_enabled': False})
            supported = [item for item in result['results'] if item['features'].get('supported')]
            return {**result, 'schema': 'weaver.lookup.v1', 'results': supported[:request.limit],
                    'status': 'supported' if supported else 'insufficient_evidence'}
        if isinstance(request, Similar):
            return self.related.recommend({'path': request.path, 'text': request.text, 'focus': request.focus},
                                          scope=request.scope)
        if isinstance(request, Walk):
            return walk(self.service.vault, request)
        if isinstance(request, (Placement, ExecutePlacement)) and request.profile != 'crusher':
            raise DomainError('PLACEMENT_PROFILE', 'This placement profile is not registered.', 422)
        if isinstance(request, Placement):
            return self.place(request.understanding, request.text, request.snapshot,
                              query_id=request.operation_id, deadline=request.deadline)
        if isinstance(request, ExecutePlacement):
            return self.execute_placement(request.job, request.content, request.plan)
        raise DomainError('WEAVER_REQUEST', 'Unsupported Weaver work order.', 422)

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

    def execute_placement(self, job, validated, placement):
        """Execute an accepted Crusher job; replay uses the existing durable journal."""
        return self.executor.commit(job, validated, placement)

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
        curator = self.bibliotekar.status()
        if self.index_failure:
            search = {**search, "status": "DEGRADED", "error": self.index_failure}
        assistant = {**curator, 'requested': value['curator_enabled'],
                     'effective': value['curator_enabled'] and curator['ready']}
        return {**value, 'bibliotekar_enabled': value['curator_enabled'], "graph_root": self.service.state.setting("crusher_root", "root.md"),
                "readiness": {"configuration": "READY" if not errors else "INVALID", "errors": errors,
                    "search": search, 'bibliotekar': assistant, 'curator': assistant}}

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


ContextIndexing = Weaver  # Legacy Python callers.
__all__ = ["ExecutePlacement", "Lookup", "Placement", "Scope", "Similar", "Walk", "Weaver"]
