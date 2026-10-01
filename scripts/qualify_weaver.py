"""Offline real-E5 ablations, independent tasks and bounded latency measurements.

Use PYTHONPATH to select the implementation under test. No network/provider,
operator Vault, external credentials or non-synthetic text is used.
"""
import argparse
import inspect
import json
import math
import statistics
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from mastermind.audit import Audit
from mastermind.config import Config
from mastermind.context_indexing.graph import Scope
from mastermind.context_indexing.index import Index
from mastermind.context_indexing.pipeline import Pipeline
from mastermind.context_indexing.related import RelatedNotes
from mastermind.context_indexing.settings import Settings
from mastermind.coordinator import Coordinator
from mastermind.embeddings import Embeddings
from mastermind.runtime_client import RuntimeClient
from mastermind.semantic import Semantic
from mastermind.state import State
from mastermind.vault import Vault

TOPICS = [
    ('Aurora', 'Charged particles from the solar wind collide with atmospheric gases near magnetic poles, producing polar lights.',
     'Почему около полюсов ночью светится небо?', 'Solar particles excite oxygen and nitrogen above the poles.'),
    ('Sonar', 'Bats emit ultrasonic pulses and determine insect positions from returning echoes in darkness.',
     'Как летучая мышь находит насекомых в полной темноте?', 'Flying mammals locate prey by timing reflected high-frequency sounds.'),
    ('Symbiosis', 'Fungal mycelium exchanges soil phosphorus with tree roots in return for carbohydrates through mycorrhizal symbiosis.',
     'Как грибы и корни деревьев обмениваются питательными веществами?', 'Root fungi supply mineral nutrients and receive sugars from plants.'),
    ('Braking', 'Regenerative braking converts vehicle kinetic energy into electrical energy and stores it in the traction battery.',
     'Как автомобиль возвращает энергию в аккумулятор при замедлении?', 'An electric motor becomes a generator during deceleration and charges the battery.'),
    ('Diodes', 'A semiconductor diode conducts current predominantly in one direction and can rectify alternating voltage.',
     'Какой электронный компонент превращает переменный ток в односторонний?', 'Rectification uses the asymmetric conductivity of a semiconductor junction.'),
    ('Seasons', 'The axial tilt of Earth changes sunlight angles and daylight duration over the year, causing seasons.',
     'Почему летом дни длиннее и солнце выше, чем зимой?', 'Annual seasonal temperature changes result from tilted planetary rotation, not orbital distance.'),
    ('Platelets', 'Blood platelets aggregate at damaged vessels and activate coagulation to stop bleeding.',
     'Какие клетки помогают остановить кровотечение после повреждения сосуда?', 'Tiny blood cell fragments form a plug at an injury and trigger clotting.'),
    ('Fermentation', 'Yeast converts sugars into ethanol and carbon dioxide in anaerobic fermentation, making bread dough rise.',
     'Откуда берутся пузырьки газа, поднимающие дрожжевое тесто?', 'Baker yeast releases carbon dioxide while metabolizing glucose without oxygen.'),
    ('Tides', 'The gravitational pull of the Moon and Sun produces periodic rises and falls of ocean water.',
     'Почему уровень моря регулярно поднимается и опускается?', 'Lunar gravity creates oceanic bulges responsible for coastal high and low water.'),
    ('Vaccination', 'Vaccines expose immune cells to harmless antigens, generating memory lymphocytes for faster future responses.',
     'Как прививка помогает организму быстрее распознать инфекцию в будущем?', 'Immunization trains adaptive defenses to remember specific pathogens.'),
    ('Insulation', 'A vacuum between double glass walls reduces heat transfer by conduction and convection in a thermos.',
     'Почему напиток долго остаётся горячим в термосе?', 'An evacuated gap suppresses thermal transport between inner and outer flask walls.'),
    ('Seismology', 'Earthquake P waves travel through solids and liquids, while S waves cannot propagate through liquid layers.',
     'Как сейсмические волны показывают, что внешнее ядро Земли жидкое?', 'Missing shear waves reveal a molten layer deep inside our planet.'),
]


def dataset():
    notes, cases = {}, []
    filler = 'The archive lists historical meeting dates and administrative inventory records.\n\n'
    for i, (topic, fact, query, peer) in enumerate(TOPICS):
        # Opaque names ensure labels cannot be inferred from the query or folders.
        path, related = f'notes/Record {i:02d}.md', f'elsewhere/Observation {i:02d}.md'
        notes[path] = '# Records\n'+filler*240+'\n## Finding\n'+fact
        notes[related] = '# Observation\n'+peer
        cases += [{'id': topic+'-lookup', 'task': 'lookup', 'query': query, 'relevant': [path, related],
                   'split': 'calibration' if i < 6 else 'test'},
                  {'id': topic+'-similar', 'task': 'similar', 'path': related, 'query': peer, 'relevant': [path],
                   'split': 'calibration' if i < 6 else 'test'}]
    notes['Counterexample.md'] = '# Electrical recipes\nKitchen utensils are stored beside a printed wiring diagram.'
    notes['Empty template.md'] = '# {{title}}\n## Facts\n{{body}}\n## Sources\n{{sources}}'
    return notes, cases


class LocalWorker:
    def __init__(self, root):
        self.embeddings = Embeddings(root/'.local/models/multilingual-e5-small', root/'embedding-model.lock.json')
        self.embeddings.load()
        assert self.embeddings.session is not None, 'Verified local E5 model required'

    def request(self, method, route, data=None, **options):
        if route == '/healthz':
            return {'embeddings_ready': True, 'model_sha256': self.embeddings.model_sha}
        if route == '/chunks':
            kwargs = {k: data[k] for k in ('sections', 'overlap') if k in data and k in inspect.signature(self.embeddings.chunks).parameters}
            return {'model_sha256': self.embeddings.model_sha, 'chunks': self.embeddings.chunks(data['text'], **kwargs)}
        if route == '/curator/status':
            return {'schema': 'context-indexing.curator.v1', 'ready': False, 'reason': 'DISABLED_FOR_ABLATION'}
        raise ValueError(route)

    def embed(self, texts, *, query=False):
        return self.embeddings.embed(texts, query=query)

    def close(self):
        pass


def percentile(values, p):
    return sorted(values)[min(len(values)-1, math.ceil(p*len(values))-1)]


def metrics(rows):
    return {'cases': len(rows), 'hit_at_3': statistics.mean(r['hit_at_3'] for r in rows),
            'precision_at_3': statistics.mean(r['precision_at_3'] for r in rows),
            'recall_at_5': statistics.mean(r['recall_at_5'] for r in rows),
            'false_matches_at_3': sum(r['false_matches_at_3'] for r in rows),
            'p50_ms': round(statistics.median(r['ms'] for r in rows)),
            'p95_ms': round(percentile([r['ms'] for r in rows], .95)),
            'degraded': sum(r['degraded'] for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--mode', choices=['query', 'passage'], default='passage')
    parser.add_argument('--overlap', type=int, choices=[0, 32, 64], default=0)
    parser.add_argument('--backend', choices=['python', 'faiss'], default='faiss')
    args = parser.parse_args()
    worker = LocalWorker(args.root)
    notes, cases = dataset()
    report = {'schema': 'weaver.qualification.v1', 'model': worker.embeddings.model_sha,
              'configuration': {'mode': args.mode, 'overlap': args.overlap, 'backend': args.backend},
              'limitations': ['Authored synthetic relevance labels; no universal quality claim.',
                              'Similarity and information retrieval have separate judgments.',
                              'Scores contain no external-provider or operator data.'], 'cases': []}
    with tempfile.TemporaryDirectory(prefix='weaver-qualification-') as directory:
        config = Config(home=Path(directory), runtime_mode='offline', test_mode=True)
        state = State(config.state/'mastermind.sqlite3')
        coordinator = Coordinator(config, state, RuntimeClient(config))
        vault = Vault(config, state, coordinator)
        service = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault,
                                  audit=Audit(config, state), data_ready=lambda: None)
        options = {'backend': args.backend, 'similarity_mode': args.mode, 'overlap': args.overlap}
        options = {k: v for k, v in options.items() if k in inspect.signature(Semantic).parameters}
        semantic = Semantic(service, worker=worker, **options)
        try:
            coordinator.commit({p: t.encode() for p, t in notes.items()}, {p: None for p in notes})
            vault.index()
            started = time.perf_counter()
            for _ in range(10000):
                if not semantic.once():
                    break
            assert semantic.status()['status'] == 'READY', semantic.status()
            report['full_index_ms'] = round((time.perf_counter()-started)*1000)
            report['chunks'] = state.one('SELECT COUNT(*) AS n FROM semantic_chunks')['n']
            class MeasuredPipeline(Pipeline):
                def run(self, *args, **kwargs):
                    value = super().run(*args, **kwargs)
                    self.last = value[0]
                    return value
            pipeline = MeasuredPipeline(service, Index(service), semantic=semantic)
            related = RelatedNotes(service, pipeline, Settings(service))
            for case in cases:
                start = time.perf_counter()
                if case['task'] == 'lookup':
                    found, _ = pipeline.run({'text': case['query']}, scope=Scope('owner'),
                                            query_type='knowledge_lookup', configuration={'curator_enabled': False})
                    items = [i for i in found['results'] if i['features'].get('supported')]
                else:
                    found = related.recommend({'path': case['path'], 'text': case['query']})
                    items = found['items']
                paths = [i['path'] for i in items]
                positive = set(case['relevant'])
                hits = len(positive & set(paths[:3]))
                report['cases'].append({**case, 'top5': paths[:5], 'ms': round((time.perf_counter()-start)*1000),
                    'hit_at_3': bool(hits), 'precision_at_3': hits/max(1, len(paths[:3])),
                    'recall_at_5': len(positive & set(paths[:5]))/len(positive),
                    'false_matches_at_3': len(set(paths[:3])-positive), 'degraded': found['degraded'],
                    'judged_evidence': [{'path': i['path'], 'score': i['score'], 'features': i['features']}
                                        for i in pipeline.last['results'] if i['path'] in positive]})
            # Update visibility includes both canonical mutation and incremental inference.
            path = next(iter(notes))
            start = time.perf_counter()
            vault.write(path, notes[path]+'\nA newly edited evidence sentence.', state.one('SELECT sha FROM notes WHERE path=?', (path,))['sha'])
            for _ in range(10000):
                if not semantic.once():
                    break
            report['edit_to_index_ms'] = round((time.perf_counter()-start)*1000)
            assert all(vault.read(p) == text for p, text in notes.items() if p != path)
            report['index'] = semantic.status()
            report['metrics'] = {task+'_'+split: metrics([r for r in report['cases'] if r['task'] == task and r['split'] == split])
                                 for task in ('lookup', 'similar') for split in ('calibration', 'test')}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            print(json.dumps(report['metrics'], ensure_ascii=False), flush=True)
        finally:
            semantic.close()
            state.close()


if __name__ == '__main__':
    main()
