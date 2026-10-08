"""Trusted consumer policies; graph-link execution shares the canonical journal.

Registration is an in-process bootstrap action, never a public request field.
A policy proposes targets and renders validated content; Weaver owns scope,
revision checks, mutation serialization and durable replay.
"""
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from ..errors import DomainError
from ..fs import sha_bytes
from .evidence import packet
from .graph import Graph, Scope, digest
from .pipeline import source_features


@dataclass(frozen=True)
class ConsumerProfile:
    name: str
    version: str
    scope: Scope
    assess: Callable
    decide: Callable
    # Optional pure renderer returns {existing_note_path: new_markdown}. It must
    # enforce the consumer's permissible links and structural rules.
    render: Callable | None = None
    writable_paths: frozenset[str] = frozenset()


class Profiles:
    def __init__(self, weaver, profiles=()):
        self.weaver, self.entries = weaver, {}
        for profile in profiles:
            if not isinstance(profile, ConsumerProfile) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', profile.name) \
                    or profile.name == 'crusher' or profile.name in self.entries or not profile.version \
                    or any(not profile.scope.permits(p) for p in profile.writable_paths):
                raise DomainError('PLACEMENT_PROFILE', 'Invalid or duplicate trusted consumer profile.', 422)
            self.entries[profile.name] = profile

    def get(self, name, operation):
        profile = self.entries.get(name)
        if not profile:
            raise DomainError('PLACEMENT_PROFILE', 'This placement profile is not registered.', 422)
        if operation != 'graph_link':
            raise DomainError('PLACEMENT_OPERATION', 'This profile supports graph links, not file moves or creation.', 422)
        return profile

    def prepare(self, request):
        profile = self.get(request.profile, request.operation)
        engine = self.weaver
        if request.deadline is not None and request.deadline <= time.time():
            raise DomainError('PLACEMENT_DEADLINE', 'The placement request expired.', 408)
        subject = source_features(request.understanding, request.text)
        if not subject['text'].strip():
            subject['text'] = request.text.encode()[:4096].decode(errors='ignore')
        result, graph = engine.pipeline.run(subject, scope=profile.scope,
            # Consumer-specific assessment; Crusher structural eligibility and
            # branch profiles are intentionally not used for another consumer.
            query_type='knowledge_lookup', configuration={'curator_enabled': False},
            policy_version=profile.name+'.'+profile.version,
            assessment=lambda value, graph: profile.assess(value, graph, request.snapshot),
            deadline=time.monotonic()+max(0, request.deadline-time.time()) if request.deadline else time.monotonic()+30)
        decision = profile.decide(result, graph, request.snapshot)
        if not isinstance(decision, dict) or decision.get('outcome') not in {'planned', 'refused'}:
            raise DomainError('PLACEMENT_PLAN', 'A consumer must plan or refuse placement explicitly.', 422)
        return {**decision, 'schema': 'weaver.consumer-placement.v1', 'profile': profile.name,
                'profile_version': profile.version, 'operation': request.operation, 'snapshot_id': graph.sha,
                'operation_id': request.operation_id, 'deadline': request.deadline,
                'evidence_packet': packet(result, graph, result['results'][:20], query=request.text, budget=8192),
                'diagnostics': result['diagnostics']}

    def execute(self, request):
        profile = self.get(request.profile, request.operation)
        service, plan = self.weaver.service, request.plan
        if getattr(request.job, 'service', None) is not service:
            raise DomainError('PLACEMENT_SCOPE', 'The consumer belongs to another Vault.', 403)
        if not profile.render or not profile.writable_paths:
            raise DomainError('PLACEMENT_READ_ONLY', 'This consumer has no write authority.', 403)
        if plan.get('profile') != profile.name or plan.get('profile_version') != profile.version \
                or plan.get('operation') != request.operation or plan.get('outcome') != 'planned':
            raise DomainError('PLACEMENT_PLAN', 'The plan does not match the registered consumer and operation.', 409)
        identity = plan.get('operation_id')
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', identity):
            raise DomainError('PRECONDITION_REQUIRED', 'Provide a stable placement operation ID.', 428)
        fingerprint = digest({'plan': plan, 'content': request.content})
        operation_id = digest({'consumer': profile.name, 'id': identity})[:32]
        with service.coordinator.boundary(operation_id):
            service.data_ready()
            previous = service.state.one('SELECT * FROM operations WHERE id=?', (operation_id,))
            if previous:
                recorded = json.loads(previous['metadata'])
                if recorded.get('weaver_fingerprint') != fingerprint:
                    raise DomainError('IDEMPOTENCY_CONFLICT', 'This operation ID has a different placement payload.', 409)
                if previous['state'] == 'COMMITTED':
                    return recorded['weaver_receipt']
                raise DomainError('PLACEMENT_RETRY_REQUIRED', 'Recover and prepare a new plan before retrying.', 409)
            if plan.get('deadline') is not None and time.time() >= plan['deadline']:
                raise DomainError('PLACEMENT_DEADLINE', 'The placement plan expired.', 408)
            graph = Graph(service.vault, profile.scope)
            if graph.sha != plan.get('snapshot_id'):
                raise DomainError('EVIDENCE_CHANGED', 'The scoped graph changed; prepare a new placement plan.', 409)
            rendered = profile.render(plan, request.content, graph)
            if not isinstance(rendered, dict) or not 1 <= len(rendered) <= 16:
                raise DomainError('PLACEMENT_WRITE_LIMIT', 'A graph-link plan may update 1–16 existing notes.', 422)
            changes, expected = {}, {}
            for path, text in rendered.items():
                if path not in profile.writable_paths or path not in graph.notes:
                    raise DomainError('PLACEMENT_SCOPE', 'The consumer may not write this note.', 403)
                if not isinstance(text, str) or len(text.encode()) > service.config.max_note_bytes:
                    raise DomainError('PLACEMENT_CONTENT', 'The rendered Markdown exceeds the note limit.', 422)
                expected[path] = graph.notes[path]['sha']
                if sha_bytes(service.vault.read(path).encode()) != expected[path]:
                    raise DomainError('EVIDENCE_CHANGED', 'The note changed; prepare a new placement plan.', 409)
                changes[path] = text.encode()
            # Renderer may take time; check all dependencies again while the
            # Runtime remains paused, then use the coordinator's final CAS.
            if Graph(service.vault, profile.scope).sha != graph.sha:
                raise DomainError('EVIDENCE_CHANGED', 'The evidence changed while rendering the plan.', 409)
            receipt = {'schema': 'weaver.placement.v1', 'profile': profile.name, 'operation': request.operation,
                       'operation_id': identity, 'changes': [{'path': p, 'sha256': sha_bytes(v)} for p, v in changes.items()]}
            service.coordinator.commit(changes, expected,
                {'weaver_fingerprint': fingerprint, 'weaver_receipt': receipt},
                inside_boundary=True, operation_id=operation_id)
            service.vault.index()
            return receipt
