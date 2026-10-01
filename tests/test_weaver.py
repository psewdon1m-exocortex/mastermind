import json
import time
from types import SimpleNamespace

import pytest

from mastermind.audit import Audit
from mastermind.errors import DomainError
from mastermind.weaver import Lookup, Scope, Similar, Walk, Weaver
from mastermind.weaver.graph import Graph
from mastermind.weaver.knowledge import Knowledge


@pytest.fixture
def weaver(service):
    config, state, coordinator, vault = service
    context = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault,
                              audit=Audit(config, state), data_ready=lambda: None, secrets=None)
    return Weaver(context)


def test_legacy_imports_share_the_same_engine_and_persisted_configuration(weaver):
    from mastermind.context_indexing import ContextIndexing
    from mastermind.context_indexing.curator import Curator
    from mastermind.weaver.bibliotekar import Bibliotekar
    assert ContextIndexing is Weaver and Curator is Bibliotekar
    weaver.service.state.set_setting('context_indexing', {'curator_enabled': True, 'revision': 7})
    assert weaver.settings.get()['revision'] == 7
    assert weaver.settings.get()['curator_enabled'] is True
    assert weaver.bibliotekar is weaver.curator


def test_graph_work_order_follows_real_scoped_edges_and_external_objects(weaver):
    vault = weaver.service.vault
    vault.write('Start.md', '[[Peer]] [[Hidden]]\n@chronos: t-public\n@saturn: root/object.pdf', None, create=True)
    vault.write('Peer.md', '[[Start]]\nUseful prose', None, create=True)
    vault.write('Hidden.md', '@chronos: secret-event', None, create=True)
    scope = Scope('owner', frozenset({'Start.md', 'Peer.md'}))
    result = weaver.run(Walk('Start.md', scope=scope))
    assert {v['kind'] for v in result['nodes']} == {'note', 'chronos', 'saturn'}
    assert 'Hidden' not in json.dumps(result) and 'secret-event' not in json.dumps(result)
    assert len([n for n in result['nodes'] if n['id'] == 'Start.md']) == 1
    assert all(n.get('availability') == 'unverified' for n in result['nodes'] if n['kind'] != 'note')
    limited = weaver.run(Walk('Start.md', scope=scope, limit=1))
    assert limited['truncated'] and len(limited['nodes']) == 1
    with pytest.raises(DomainError):
        weaver.run(Walk('Hidden.md', scope=scope))
    with pytest.raises(DomainError):
        weaver.run(Walk('Start.md', scope=Scope('shared')))
    with pytest.raises(DomainError):
        weaver.run(Walk('Start.md', depth=99))


def test_work_orders_separate_query_and_similarity_and_never_save_editor_buffer(weaver):
    vault = weaver.service.vault
    vault.write('Draft.md', 'Stored original', None, create=True)
    vault.write('Birds.md', 'Migrating birds navigate using magnetic fields.', None, create=True)
    calls = []
    def run(subject, **options):
        calls.append(options['query_type'])
        return {'results': [], 'degraded': False, 'truncated': False}, None
    weaver.pipeline.run = run
    weaver.run(Lookup('How do migrating birds navigate?'))
    weaver.run(Similar('Draft.md', 'Migrating birds orient using magnetic fields.'))
    assert calls == ['knowledge_lookup', 'note_similarity']
    assert vault.read('Draft.md') == 'Stored original'
    with pytest.raises(DomainError):
        weaver.run(Similar('Draft.md', 'not allowed', scope=Scope('owner', frozenset({'Birds.md'}))))


def test_verification_uses_retrieved_late_passage_not_note_prefix(weaver):
    vault = weaver.service.vault
    vault.write('Long.md', '# Cooking\n'+('A recipe describes kitchen utensils and soup.\n'*600)+
                '\n## Electronics\nA diode permits electrical current in only one direction.', None, create=True)
    graph = Graph(vault, Scope('owner'))
    knowledge = Knowledge(vault.state, graph, {'Long.md'}, task='note_similarity')
    knowledge.prepare({'text': 'Electrical rectification with semiconductor diodes'})
    item = {'path': 'Long.md', 'title': 'Long', 'features': {'vector': .9}, 'passages': [
        {'text': 'A diode permits electrical current in only one direction.'}]}
    class Verifier:
        similarity_mode = 'query'
        def compare(self, queries, documents, **kwargs):
            assert kwargs['task'] == 'note_similarity'
            assert any('diode permits' in d for d in documents)
            return [.96 if 'diode' in d else .70 for d in documents]
    assert knowledge.verify([item], Verifier(), time.monotonic()+5)
    assert 'diode' in item['verified_excerpt']
    assert item['features']['vector'] == .96


def test_bibliotekar_setting_alias_preserves_conflicts_and_legacy_wire():
    from mastermind.weaver.routes import changes
    assert changes({'retrieval': {'bibliotekar_enabled': True}}) == {'curator_enabled': True}
    with pytest.raises(DomainError):
        changes({'retrieval': {'bibliotekar_enabled': False, 'curator_enabled': True}})


def test_lookup_never_exposes_unsupported_candidates(weaver):
    weaver.pipeline.run = lambda *a, **k: ({'results': [
        {'path': 'Noise.md', 'features': {'supported': False}},
        {'path': 'Match.md', 'features': {'supported': True}}]}, None)
    assert [i['path'] for i in weaver.run(Lookup('evidence'))['results']] == ['Match.md']
    with pytest.raises(DomainError):
        weaver.run(Lookup('x', limit=1000))


def test_walk_includes_only_permitted_local_attachment_metadata(weaver):
    from mastermind.fs import atomic_write
    vault = weaver.service.vault
    atomic_write(vault.config.vault/'assets/picture.svg', b'<svg/>')
    vault.write('Start.md', '![[assets/picture.svg]]\n[Remote](https://example.invalid/a.pdf)', None, create=True)
    result = weaver.run(Walk('Start.md'))
    assert any(n.get('path') == 'assets/picture.svg' and n['size'] == 6 for n in result['nodes'])
    assert len(result['nodes']) == 2
    scoped = weaver.run(Walk('Start.md', scope=Scope('owner', frozenset({'Start.md'}))))
    assert len(scoped['nodes']) == 1


def test_restore_keeps_weaver_settings_but_rebuilds_disposable_vectors(recovery, tmp_path):
    from test_semantic import Worker, drain

    from mastermind.semantic import Semantic
    backup, restore, _auth = recovery
    service = SimpleNamespace(state=backup.state, vault=backup.vault, coordinator=backup.coordinator,
                              audit=backup.audit, config=backup.config, data_ready=lambda: None)
    index = Semantic(service, worker=Worker(), similarity_mode='query')
    service.vault.write('Note.md', 'Knowledge about birds', None, create=True)
    from mastermind.weaver.settings import DEFAULTS
    service.state.set_setting('context_indexing', {**DEFAULTS, 'curator_enabled': True, 'revision': 7})
    drain(index)
    archive = tmp_path/'weaver-restore.zip'
    backup.create(archive)
    service.state.set_setting('context_indexing', {**DEFAULTS, 'curator_enabled': False, 'revision': 8})
    assert restore.apply(archive)['state'] == 'COMPLETED'
    assert service.state.setting('context_indexing')['curator_enabled'] is True
    assert service.state.one('SELECT COUNT(*) AS n FROM semantic_variants')['n'] == 0
    drain(index)
    assert index.search('knowledge', task='note_similarity')['results'][0]['path'] == 'Note.md'
    index.close()
