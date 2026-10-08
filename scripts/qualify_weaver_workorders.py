"""Independent synthetic typed work orders on the pinned local E5 model.

Labels are defined here before measurement. No operator Vault, provider API,
credentials, answer generation or automatic threshold tuning is involved.
"""
import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from qualify_weaver import LocalWorker

from mastermind.audit import Audit
from mastermind.config import Config
from mastermind.coordinator import Coordinator
from mastermind.runtime_client import RuntimeClient
from mastermind.semantic import Semantic
from mastermind.state import State
from mastermind.vault import Vault
from mastermind.weaver import Lookup, Scope, Similar, Walk, Weaver
from mastermind.weaver.graph import Graph


def dataset():
    filler = 'The register records stationery deliveries and meeting room reservations.\n\n'
    notes = {
        'root.md': '[[Flight]] [[Living systems]]',
        'Flight.md': '#main\n[[Airplanes]] [[Aircraft designers]] [[Composite wings]]',
        'Living systems.md': '#main\n[[Leaf physiology]]',
        'Airplanes.md': '#key\nAn airplane generates lift with fixed wings while engines provide forward thrust. [[Aircraft designers]]',
        'Aircraft designers.md': '#key\nAircraft designers specify airframe geometry and evaluate flight stability.',
        'Composite wings.md': '#key\nCarbon fibre laminates give aircraft wings high specific strength and resist bending loads.',
        'Archive 101.md': '---\naliases: ["CFRP", "углепластик"]\n---\n# Inventory\n'+filler*240+
            '\n## Wing mechanics\nCarbon fibre reinforced polymer laminates carry bending loads in lightweight wings. '
            'Delamination reduces their compressive strength.\n\nThe exception is a compressive load parallel to a damaged layer.',
        'Leaf physiology.md': '#key\nStomata regulate gas exchange and water vapour loss at the surface of plant leaves.',
        'Archive 202.md': '# Leaf pores\nLeaf pores close during drought to reduce evaporation, limiting carbon dioxide uptake.',
        'Шины.md': 'Зимние автомобильные шины сохраняют эластичность на морозе и улучшают сцепление с обледеневшей дорогой.',
        'Moulded tyre.md': 'Winter tyres grip icy roads through flexible rubber compounds and dense tread siping.',
        'Network plane.md': 'The network control plane distributes routing information between routers; it is not an aircraft.',
        'Typography.md': 'Composite glyphs combine accents with base letters in font rendering.',
        'Private.md': 'PRIVATE_ONLY flight documents.'}
    cases = [
        {'id': 'ru_to_en', 'task': 'lookup', 'query': 'Как устьица листьев регулируют испарение воды?',
         'relevant': ['Leaf physiology.md', 'Archive 202.md']},
        {'id': 'abbreviation', 'task': 'lookup', 'query': 'CFRP', 'relevant': ['Archive 101.md']},
        {'id': 'alias', 'task': 'lookup', 'query': 'углепластик', 'relevant': ['Archive 101.md', 'Composite wings.md']},
        {'id': 'russian_inflection', 'task': 'lookup', 'query': 'Почему зимняя шина цепляется за лёд?',
         'relevant': ['Шины.md', 'Moulded tyre.md']},
        {'id': 'late_fact', 'task': 'lookup', 'query': 'How does delamination affect compressive strength?',
         'relevant': ['Archive 101.md']},
        {'id': 'compound', 'task': 'lookup', 'query': 'Найди материалы про Airplanes, Aircraft designers и Composite wings',
         'relevant': ['Airplanes.md', 'Aircraft designers.md', 'Composite wings.md', 'Archive 101.md']},
        {'id': 'false_lexical_friend', 'task': 'lookup', 'query': 'How do airplane wings generate aerodynamic lift?',
         'relevant': ['Airplanes.md']},
        {'id': 'absent', 'task': 'lookup', 'query': 'Квантовая гравитация вблизи горизонта событий чёрной дыры', 'relevant': []},
        {'id': 'carbon_peer', 'task': 'similar', 'path': 'Composite wings.md',
         'query': notes['Composite wings.md'], 'relevant': ['Archive 101.md']},
        {'id': 'leaf_peer', 'task': 'similar', 'path': 'Leaf physiology.md',
         'query': notes['Leaf physiology.md'], 'relevant': ['Archive 202.md']},
        {'id': 'tyre_peer', 'task': 'similar', 'path': 'Шины.md', 'query': notes['Шины.md'], 'relevant': ['Moulded tyre.md']},
        {'id': 'lexical_noise', 'task': 'similar', 'path': 'Network plane.md', 'query': notes['Network plane.md'], 'relevant': []},
    ]
    return notes, cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    worker = LocalWorker(args.root)
    report = {'schema': 'weaver.workorders.quality.v1', 'model': worker.embeddings.model_sha,
              'limitations': ['Small authored synthetic corpus; not a production accuracy estimate.',
                              'Independent of qualify_weaver topics; no tuning from this run.'], 'cases': []}
    with tempfile.TemporaryDirectory(prefix='weaver-orders-') as directory:
        config = Config(home=Path(directory), runtime_mode='offline', test_mode=True)
        state = State(config.state/'mastermind.db')
        coordinator = Coordinator(config, state, RuntimeClient(config))
        vault = Vault(config, state, coordinator)
        service = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault,
                                  audit=Audit(config, state), data_ready=lambda: None)
        semantic = Semantic(service, worker=worker)
        engine = Weaver(service, semantic=semantic)
        try:
            notes, cases = dataset()
            coordinator.commit({p: t.encode() for p, t in notes.items()}, {p: None for p in notes})
            vault.index()
            started = time.perf_counter()
            for _ in range(1000):
                if not semantic.once():
                    break
            report['full_index_ms'] = round((time.perf_counter()-started)*1000)
            assert semantic.status()['status'] == 'READY'
            scope = Scope('owner', frozenset(set(notes)-{'Private.md'}))
            for case in cases:
                started = time.perf_counter()
                result = engine.run(Lookup(case['query'], scope=scope, refine=False, context='section')
                    if case['task'] == 'lookup' else Similar(case['path'], case['query'], scope=scope))
                assert 'Private.md' not in json.dumps(result)
                paths = [i['path'] for i in result.get('results', result.get('items', []))]
                positive = set(case['relevant'])
                lost = {p: 'ranking' if p in paths else next((d['stage'] for d in result['diagnostics']['candidates']
                        if d['path'] == p), 'candidate_generation') for p in positive-set(paths[:5])}
                if case['id'] in {'abbreviation', 'late_fact'}:
                    assert 'Archive 101.md' in paths[:3], (case['id'], paths)
                    if case['id'] == 'late_fact':
                        assert any('delamination' in f['text'].casefold() for s in result['evidence_packet']['sources']
                                   if s['path'] == 'Archive 101.md' for f in s['fragments'])
                if case['id'] == 'compound':
                    assert all(p['returned_paths'] for p in result['coverage'][1:]), result['coverage']
                report['cases'].append({**case, 'returned': paths, 'ms': round((time.perf_counter()-started)*1000),
                    'hit_at_3': bool(positive & set(paths[:3])) if positive else not paths,
                    'recall_at_5': len(positive & set(paths[:5]))/len(positive) if positive else None,
                    'false_at_3': len(set(paths[:3])-positive), 'lost': lost,
                    'diagnostics': result['diagnostics'], 'outcome': result['outcome'],
                    'context': result['evidence_packet']['context'], 'coverage': result.get('coverage', [])})
            walked = engine.run(Walk('Flight.md', scope=scope, direction='outgoing', depth=1))
            expected = {'Flight.md', 'Airplanes.md', 'Aircraft designers.md', 'Composite wings.md'}
            assert {n['id'] for n in walked['nodes']} == expected
            assert engine.run(Walk('Flight.md', scope=scope, limit=2))['truncated']
            assert engine.run(Walk('Archive 101.md', scope=scope))['nodes'][0]['id'] == 'Archive 101.md'
            report['walk'] = {'cases': 3, 'passed': 3, 'checks': ['directed edges', 'limit signaled', 'isolated note']}
            # Canonical edit invalidates vector and excerpt identity immediately.
            old = Graph(vault, scope).notes['Archive 101.md']['sha']
            vault.write('Archive 101.md', 'Replaced content about pottery.', old)
            changed = engine.run(Lookup('CFRP', scope=scope, refine=False))
            assert not any(s['sha256'] == old for s in changed['evidence_packet']['sources'])
            report['source_edit'] = {'stale_evidence_removed': True}
            report['metrics'] = {task: {
                'cases': len(rows := [r for r in report['cases'] if r['task'] == task]),
                'hit_at_3': statistics.mean(r['hit_at_3'] for r in rows),
                'recall_at_5': statistics.mean(r['recall_at_5'] for r in rows if r['recall_at_5'] is not None),
                'false_at_3': sum(r['false_at_3'] for r in rows), 'p50_ms': statistics.median(r['ms'] for r in rows)
            } for task in ('lookup', 'similar')}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            print(json.dumps(report['metrics']), flush=True)
        finally:
            semantic.close()
            state.close()


if __name__ == '__main__':
    main()
