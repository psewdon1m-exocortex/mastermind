import json
import time
from types import SimpleNamespace

import pytest

from mastermind.audit import Audit
from mastermind.errors import DomainError
from mastermind.fs import sha_bytes
from mastermind.search_content import prepare
from mastermind.weaver import (
    ConsumerProfile,
    ExecutePlacement,
    Lookup,
    Placement,
    Scope,
    Similar,
    Walk,
    Weaver,
)
from mastermind.weaver.evidence import packet, selected_diagnostics
from mastermind.weaver.graph import Graph
from mastermind.weaver.knowledge import Knowledge
from mastermind.weaver.planning import directions


class Offline:
    worker = None
    def search(self, *args, **kwargs):
        raise DomainError('REINDEX_REQUIRED', 'Index rebuilding', 503)


@pytest.fixture
def engine(service):
    config, state, coordinator, vault = service
    context = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault,
                              audit=Audit(config, state), data_ready=lambda: None)
    return Weaver(context, semantic=Offline())


def seed(engine, notes):
    for path, text in notes.items():
        engine.service.vault.write(path, text, None, create=True)


def test_yeast_candidate_survives_lookup_but_not_similar_without_enough_confirmation(engine):
    seed(engine, {'Fact.md': 'Yeast releases carbon dioxide, causing bread dough to rise.',
                  'Other.md': 'Ocean water responds to the gravitational pull of the Moon.',
                  'Noise.md': 'An electronic diode conducts current in only one direction.'})
    graph = Graph(engine.service.vault, Scope('owner'))
    for task, accepted in [('knowledge_lookup', True), ('note_similarity', False)]:
        knowledge = Knowledge(engine.service.state, graph, set(graph.notes), task=task)
        knowledge.prepare({'text': 'Откуда берутся пузырьки газа, поднимающие дрожжевое тесто?'})
        items = [{'path': p, 'title': graph.notes[p]['name'], 'features':
                  {'vector': score, 'verification': 'verified'}} for p, score in
                 [('Fact.md', .797038), ('Other.md', .70), ('Noise.md', .69)]]
        found = next(i for i in knowledge.rank(items) if i['path'] == 'Fact.md')
        assert found['features']['supported'] is accepted
        if accepted:
            assert found['features']['acceptance'] == 'tentative'
            assert 'limited confirmation' in found['reason']


def test_scoped_single_candidate_does_not_compare_itself_as_unrelated_background(engine):
    seed(engine, {'Only.md': 'Roots exchange minerals with fungal mycelium.'})
    graph = Graph(engine.service.vault, Scope('owner'))
    knowledge = Knowledge(engine.service.state, graph, {'Only.md'})
    knowledge.prepare({'text': 'Обмен питательными веществами между корнями и грибницей'})
    found = knowledge.rank([{'path': 'Only.md', 'title': 'Only', 'features':
                            {'vector': .87, 'verification': 'verified'}}])[0]
    assert found['features']['acceptance'] == 'tentative'
    assert found['features']['acceptance_reason'] == 'NO_BACKGROUND_SAMPLE'
    assert found['features']['semantic_background'] is None


def test_alias_and_abbreviation_work_offline_without_private_metadata(engine):
    seed(engine, {'Public.md': '---\naliases: ["ДВС", "internal combustion"]\n---\nPistons compress fuel.',
                  'Private.md': '---\naliases: ["ДВС"]\n---\nHidden private material.'})
    found = engine.run(Lookup('Как работает ДВС?', scope=Scope('owner', frozenset({'Public.md'}))))
    assert [i['path'] for i in found['results']] == ['Public.md']
    assert found['results'][0]['features']['acceptance_reason'] == 'EXPLICIT_ALIAS'
    assert 'Private' not in json.dumps(found)
    evidence = found['evidence_packet']
    assert evidence['completeness']['vector_index']['state'] == 'rebuilding'
    assert evidence['completeness']['state'] == 'partial'
    assert evidence['score_semantics'] == 'ranking_not_probability'


def test_no_match_is_distinct_from_index_rebuilding(engine):
    seed(engine, {'Note.md': 'A periodic lattice arranges atoms.'})
    pending = engine.run(Lookup('неизвестная отсутствующая тема', refine=False))
    assert pending['outcome'] == 'incomplete'
    class EmptyReady:
        def search(self, *args, **kwargs):
            return {'results': [], 'index': {'status': 'READY'}}
        def compare(self, queries, documents, **kwargs):
            return [.5]*len(documents)
    engine.pipeline.semantic = EmptyReady()
    completed = engine.run(Lookup('неизвестная отсутствующая тема', refine=False))
    assert completed['outcome'] == 'no_match'
    assert completed['evidence_packet']['completeness']['state'] == 'complete'


def test_composite_plan_covers_parts_respects_filters_and_deduplicates(engine):
    seed(engine, {'Airplanes.md': '#public\nAircraft carry passengers using aerodynamic lift.',
        'Designers.md': '#public\nAircraft designers develop new aerodynamic shapes.',
        'Composite wings.md': '#public\nComposite wings have high specific strength.',
        'Hidden.md': 'Aircraft designers build composite wings.'})
    found = engine.run(Lookup('Find notes about Airplanes, Designers and Composite wings',
                             filters={'tags': ['public']}, limit=3, refine=False))
    assert {i['path'] for i in found['results']} == {'Airplanes.md', 'Designers.md', 'Composite wings.md'}
    assert found['search_passes'] == 4
    assert all(p['returned_paths'] for p in found['coverage'][1:])
    assert 'Hidden' not in json.dumps(found)
    assert all(s['query_parts'] for s in found['evidence_packet']['sources'])
    assert len(directions('Find aaaa, bbbb, cccc and dddd')) == 3
    assert 'dddd' in directions('Find aaaa, bbbb, cccc and dddd')[-1]
    assert directions('strength and stiffness') == []
    assert directions('Почему летом дни длиннее и солнце выше, чем зимой?') == []
    assert engine.run(Lookup('Airplanes', refine=False))['search_passes'] == 1


def test_refinement_cannot_change_scope_or_authorize_its_own_topic(engine):
    seed(engine, {'Unrelated.md': 'Hydraulic pumps lift water.', 'Secret.md': 'Hidden subject.'})
    engine.service.state.set_setting('context_indexing', {**engine.settings.get(), 'curator_enabled': True})
    class Assistant:
        calls = 0
        def refine(self, subject, result, status, **kwargs):
            self.calls += 1
            assert kwargs['deadline'] <= time.monotonic()+8.1
            return {**subject, 'text': subject['text']+'\nHydraulic pumps'}, {'passes': 1, 'outcome': 'refined'}
    assistant = Assistant()
    engine.pipeline.curator = assistant
    result = engine.run(Lookup('drifting winter snow', scope=Scope('owner', frozenset({'Unrelated.md'}))))
    assert assistant.calls == 1 and result['results'] == []
    assert result['search_passes'] == 2
    assert 'Secret' not in json.dumps(result)
    assert result['diagnostics']['candidates'][0]['stage'] == 'verification'
    engine.pipeline.curator.refine = lambda subject, *a, **k: (
        {**subject, 'text': subject['text']+'\nSecret', 'scope': 'all'}, {'passes': 1})
    invalid = engine.run(Lookup('drifting winter snow'))
    assert invalid['bibliotekar']['outcome'] == 'invalid_proposal'
    assert invalid['search_passes'] == 1


def test_document_context_has_real_coordinates_budget_and_no_graph_expansion(engine):
    raw = '# Mechanics\nStress is force divided by area.\n\n## Failure\nThis applies only under tension.\n\n'
    raw += 'The crack grows under cyclic loading.\n\nThe exception is a compressed specimen.\n\n'
    raw += '## Other\nUnrelated section must not be included.\n[[Neighbor]]'
    seed(engine, {'Long.md': raw, 'Neighbor.md': 'Hidden graph neighbor context.'})
    graph = Graph(engine.service.vault, Scope('owner'))
    item = {'path': 'Long.md', 'sha256': graph.notes['Long.md']['sha'], 'title': 'Long',
            'verified_excerpt': 'The crack grows under cyclic loading.', 'strategies': {'vector': 1}}
    result = packet({'task': 'knowledge_lookup'}, graph, [item], context='section', budget=500)
    fragments = result['sources'][0]['fragments']
    text = '\n'.join(v['text'] for v in fragments)
    assert 'Stress is force' in text and 'only under tension' in text and 'exception' in text
    assert 'Unrelated section' not in text and 'Hidden graph neighbor' not in text
    assert {'match', 'adjacent_paragraph', 'parent_section'} <= {v['kind'] for v in fragments}
    prepared = prepare(raw)['text']
    for fragment in fragments:
        coords = fragment['coordinates']
        assert prepared[coords['start']:coords['end']] == fragment['text']
        assert fragment['source_section']['end'] <= len(raw)
    tiny = packet({}, graph, [item], context='section', budget=17)
    assert tiny['context']['used_bytes'] <= 17 and tiny['context']['truncated']


def test_changed_evidence_is_removed_and_diagnosed_at_return_boundary(engine, monkeypatch):
    import mastermind.weaver.evidence as module
    seed(engine, {'Note.md': 'The original searchable evidence.'})
    graph = Graph(engine.service.vault, Scope('owner'))
    item = {'path': 'Note.md', 'sha256': graph.notes['Note.md']['sha']}
    def interrupted(raw):
        engine.service.vault.write('Note.md', 'Concurrent editor version.', item['sha256'])
        return prepare(raw)
    monkeypatch.setattr(module, 'prepare', interrupted)
    evidence = packet({}, graph, [item])
    assert not evidence['sources'] and evidence['stale_paths'] == ['Note.md']
    assert evidence['completeness']['freshness'] == 'changed'
    diagnostic = selected_diagnostics({'results': [item]}, [], evidence)
    assert diagnostic['candidates'][0]['stage'] == 'freshness'


def test_diagnostics_explain_limit_and_rejection_without_persisting_text(engine):
    seed(engine, {f'Note {i}.md': 'Quantum entanglement correlations violate classical bounds.' for i in range(4)})
    result = engine.run(Lookup('Quantum entanglement', limit=1))
    assert result['diagnostics']['counts']['returned'] == 1
    assert result['diagnostics']['counts']['limit'] == 3
    trace = engine.index.state.one('SELECT record FROM context_traces WHERE id=?', (result['query_id'],))['record']
    assert 'Quantum' not in trace and 'entanglement' not in trace
    assert 'RESULT_LIMIT' in trace


def test_similar_empty_and_nonempty_and_walk_share_the_evidence_contract(engine):
    seed(engine, {'Start.md': '[[Peer]]\nMagnetic navigation directs migrating birds.',
                  'Peer.md': '[[Start]]\nMagnetic navigation guides birds along migration routes.'})
    for result in [engine.run(Similar('Start.md', '')), engine.run(Similar('Start.md', 'Magnetic navigation migrating birds')),
                   engine.run(Walk('Start.md', depth=1))]:
        assert result['evidence_packet']['schema'] == 'weaver.evidence.v1'
    walk = engine.run(Walk('Start.md', depth=1))
    assert {(e['source'], e['target']) for e in walk['edges']} == {('Start.md', 'Peer.md'), ('Peer.md', 'Start.md')}


def profile(engine, *, write=False, render=None):
    return ConsumerProfile('second', 'v1', Scope('owner', frozenset({'Draft.md', 'Target.md'})),
        assess=lambda result, graph, snapshot: {'status': 'sufficient'},
        decide=lambda result, graph, snapshot: {'outcome': 'planned', 'target': 'Target.md'},
        render=render or (lambda plan, content, graph: {'Draft.md': content['markdown']+'\n[[Target]]'}) if write else None,
        writable_paths=frozenset({'Draft.md'}) if write else frozenset())


def test_consumer_profile_is_read_only_by_default_and_operation_is_explicit(engine):
    seed(engine, {'Draft.md': 'Draft.', 'Target.md': 'Magnetic navigation.'})
    custom = Weaver(engine.service, semantic=Offline(), profiles=[profile(engine)])
    request = Placement({}, 'magnetic navigation', {}, profile='second', operation='graph_link', operation_id='consumer-operation-1')
    plan = custom.run(request)
    assert plan['evidence_packet']['schema'] == 'weaver.evidence.v1' and plan['profile'] == 'second'
    assert plan['outcome'] == 'planned'
    with pytest.raises(DomainError, match='write authority'):
        custom.run(ExecutePlacement(SimpleNamespace(service=engine.service), {}, plan, profile='second', operation='graph_link'))
    with pytest.raises(DomainError, match='file moves'):
        custom.run(Placement({}, 'magnetic', {}, profile='second', operation='file_move'))


def test_consumer_commit_rechecks_versions_authority_and_replays_durably(engine):
    seed(engine, {'Draft.md': 'Draft.', 'Target.md': 'Magnetic navigation.', 'Private.md': 'Private.'})
    custom = Weaver(engine.service, semantic=Offline(), profiles=[profile(engine, write=True)])
    request = Placement({}, 'magnetic navigation', {}, profile='second', operation='graph_link', operation_id='consumer-operation-1')
    plan = custom.run(request)
    command = ExecutePlacement(SimpleNamespace(service=engine.service), {'markdown': 'New draft.'}, plan,
                               profile='second', operation='graph_link')
    receipt = custom.run(command)
    # Replay must work after the graph changed as a result of the first commit,
    # including across reconstruction of the registry, without a second write.
    count = engine.service.state.one('SELECT COUNT(*) AS n FROM operations')['n']
    restarted = Weaver(engine.service, semantic=Offline(), profiles=[profile(engine, write=True)])
    assert restarted.run(command) == receipt
    assert engine.service.state.one('SELECT COUNT(*) AS n FROM operations')['n'] == count
    assert engine.service.vault.read('Draft.md') == 'New draft.\n[[Target]]'
    with pytest.raises(DomainError, match='different placement payload'):
        restarted.run(ExecutePlacement(command.job, {'markdown': 'Different.'}, plan, profile='second', operation='graph_link'))
    stale = custom.run(Placement({}, 'magnetic navigation', {}, profile='second', operation='graph_link', operation_id='consumer-operation-2'))
    engine.service.vault.write('Target.md', 'Changed target.', sha_bytes(b'Magnetic navigation.'))
    with pytest.raises(DomainError, match='graph changed'):
        custom.run(ExecutePlacement(command.job, {}, stale, profile='second', operation='graph_link'))
    assert engine.service.vault.read('Private.md') == 'Private.'


def test_profile_renderer_cannot_write_outside_its_authority(engine):
    seed(engine, {'Draft.md': 'Draft.', 'Target.md': 'Magnetic navigation.'})
    custom = Weaver(engine.service, semantic=Offline(), profiles=[profile(engine, write=True,
        render=lambda *args: {'Target.md': 'Unauthorized change.'})])
    plan = custom.run(Placement({}, 'magnetic', {}, profile='second', operation='graph_link', operation_id='consumer-operation-3'))
    with pytest.raises(DomainError, match='may not write'):
        custom.run(ExecutePlacement(SimpleNamespace(service=engine.service), {}, plan, profile='second', operation='graph_link'))
    assert engine.service.vault.read('Target.md') == 'Magnetic navigation.'


def test_consumer_replay_after_lost_commit_response_does_not_write_twice(engine):
    seed(engine, {'Draft.md': 'Draft.', 'Target.md': 'Magnetic navigation.'})
    custom = Weaver(engine.service, semantic=Offline(), profiles=[profile(engine, write=True)])
    plan = custom.run(Placement({}, 'magnetic', {}, profile='second', operation='graph_link', operation_id='consumer-operation-4'))
    command = ExecutePlacement(SimpleNamespace(service=engine.service), {'markdown': 'New.'}, plan,
                               profile='second', operation='graph_link')
    def crash(point):
        if point == 'committed':
            raise OSError('Simulated lost response after durable commit')
    engine.service.coordinator.fault = crash
    with pytest.raises(OSError):
        custom.run(command)
    engine.service.coordinator.fault = lambda point: None
    engine.service.coordinator.recover()
    receipt = custom.run(command)
    assert receipt['changes'][0]['sha256'] == sha_bytes(b'New.\n[[Target]]')
    assert engine.service.vault.read('Draft.md').count('[[Target]]') == 1


def test_deadline_omits_unchecked_evidence_and_does_not_claim_no_match(engine):
    seed(engine, {'Note.md': 'Useful evidence.'})
    graph = Graph(engine.service.vault, Scope('owner'))
    item = {'path': 'Note.md', 'sha256': graph.notes['Note.md']['sha']}
    evidence = packet({}, graph, [item], deadline=time.monotonic()-1)
    assert evidence['sources'] == [] and evidence['completeness']['state'] == 'partial'
    assert selected_diagnostics({'results': [item]}, [], evidence)['candidates'][0]['reason'] == 'EVIDENCE_DEADLINE'


def test_branch_profile_dependency_revision_is_part_of_evidence_freshness(engine):
    seed(engine, {'Anchor.md': '#key\n[[Member]]', 'Member.md': 'Original supporting evidence.'})
    graph = Graph(engine.service.vault, Scope('owner'))
    item = {'path': 'Anchor.md', 'sha256': graph.notes['Anchor.md']['sha'],
            'profile_sources': {'Member.md': graph.notes['Member.md']['sha']}}
    fresh = packet({}, graph, [item])
    assert fresh['sources'][0]['profile_sources'][0]['path'] == 'Member.md'
    engine.service.vault.write('Member.md', 'Changed supporting evidence.', graph.notes['Member.md']['sha'])
    assert packet({}, graph, [item])['stale_paths'] == ['Anchor.md']


def test_crusher_pool_and_expired_plan_keep_common_evidence(engine):
    seed(engine, {'root.md': '[[Science]]', 'Science.md': '#main\nMagnetic materials.'})
    engine.settings.bootstrap()
    snapshot = engine.settings.snapshot()
    plan = engine.run(Placement({'summary': 'Unrelated subject.'}, 'Unrelated subject.', snapshot, deadline=time.time()-1))
    assert plan['outcome'] == 'pooled' and plan['operation'] == 'create_and_link'
    assert plan['evidence_packet']['completeness']['state'] == 'partial'
    assert plan['anchor'] in {s['path'] for s in plan['evidence_packet']['sources']}
