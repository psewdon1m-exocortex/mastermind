"""Offline real-model recommendation regression on a supplied synthetic Vault copy.

Run in the Worker image with --network none and read-only source/model mounts.
Only the disposable fixture and the requested report are written.
"""
import argparse
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from qualify_context_indexing import OfflineWorker

from mastermind.audit import Audit
from mastermind.config import Config
from mastermind.context_indexing.index import Index
from mastermind.context_indexing.pipeline import Pipeline
from mastermind.context_indexing.related import RelatedNotes
from mastermind.context_indexing.settings import Settings
from mastermind.coordinator import Coordinator
from mastermind.runtime_client import RuntimeClient
from mastermind.semantic import Semantic
from mastermind.state import State
from mastermind.vault import Vault


class DiagnosticPipeline(Pipeline):
    last = None

    def run(self, *args, **kwargs):
        result, graph = super().run(*args, **kwargs)
        self.last = result
        return result, graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--vault', type=Path)
    source.add_argument('--corpus', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check-demo50', action='store_true', help='Assert the labeled demo50 regressions and directory invariance')
    args = parser.parse_args()
    worker = OfflineWorker(Path('/opt/mastermind/model'), Path('/app/embedding-model.lock.json'),
                           '/opt/mastermind/curator', '/app/curator-model.lock.json')
    with tempfile.TemporaryDirectory(prefix='related-quality-') as directory:
        config = Config(home=Path(directory), runtime_mode='offline', test_mode=True)
        state = State(config.state/'mastermind.sqlite3')
        coordinator = Coordinator(config, state, RuntimeClient(config))
        vault = Vault(config, state, coordinator)
        context = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault,
                                  audit=Audit(config, state), data_ready=lambda: None)
        notes = json.loads(args.corpus.read_text('utf-8'))['notes'] if args.corpus else {
            p.relative_to(args.vault).as_posix(): p.read_text('utf-8') for p in args.vault.rglob('*.md')
            if not any(part.startswith('.') for part in p.relative_to(args.vault).parts)}
        coordinator.commit({p: t.encode() for p, t in notes.items()}, {p: None for p in notes})
        vault.index()
        semantic = Semantic(context, worker=worker)
        for _ in range(2000):
            if not semantic.once():
                break
        assert semantic.status()['status'] == 'READY'
        pipeline = DiagnosticPipeline(context, Index(context), semantic=semantic)
        engine = RelatedNotes(context, pipeline, Settings(context))
        cases = {}
        for path, text in notes.items():
            pipeline.last = None
            result = engine.recommend({'path': path, 'text': text, 'focus': text[:600]})
            cases[path] = result
            if pipeline.last:
                cases[path]['total_ms'] = pipeline.last['timings']['total_ms']
                cases[path]['diagnostic'] = [{k: v[k] for k in ('title', 'score', 'features')}
                                            for v in pipeline.last['results']]
        assert all(vault.read(p) == t for p, t in notes.items())
        checks = []
        if args.check_demo50:
            by_title = {Path(p).stem: result for p, result in cases.items()}
            engines = [i['title'] for i in by_title['Двигатели и приводы']['items']]
            assert set(engines[:4]) == {'Бензиновый двигатель', 'Гибридный привод', 'Тормозная рекуперация', 'Электродвигатель автомобиля'}, engines
            assert not {'Деревья', 'Природные процессы', 'Наблюдения и данные'} & set(engines), engines
            main_topics = {'Автомобили', 'Животные', 'Растения', 'Среда и экосистемы', 'Технологии'}
            for title in main_topics:
                items = by_title[title]['items']
                assert len(items) >= 2
                assert not (main_topics-{title}) & {i['title'] for i in items}, (title, items)
                assert all(not any(word in i['reason'] for word in ('занятие', 'обзор', 'подтемы', 'событие')) for i in items)
            pool = {i['title'] for i in by_title['pool']['items']}
            assert 'root' in pool and not main_topics & pool
            assert not {'Природные процессы', 'Энергия', 'Деревья', 'Наблюдения и данные'} & pool
            for path in ('root.md', 'root/pool.md', 'root/templates/example crusher.md'):
                result = engine.recommend({'path': path, 'text': 'Гибридная силовая установка сочетает двигатель внутреннего сгорания с электрической машиной и накопителем энергии.'})
                assert 'Гибридный привод' in {i['title'] for i in result['items']}, path
                assert 'empty_reason' not in result
            assert 'Литий-ионный аккумулятор' in [i['title'] for i in by_title['Гибридный привод']['items']]
            assert all('dataset:' not in i['excerpt'] and 'kind:' not in i['excerpt']
                       for result in cases.values() for i in result['items'])
            checks += ['engine hub: four topical children first, no unrelated template hubs',
                       'all five main topics reject siblings supported only by shared scaffolding',
                       'pool returns contextual references without unrelated thematic branches',
                       'root, pool and template accept thematic unsaved text under universal rules',
                       'hybrid drive retains cross-branch battery recommendation', 'clean excerpts']
            mapping = {path: f'relocated/{len(notes)-i:03d}/deep/{Path(path).name}'
                       for i, path in enumerate(sorted(notes))}
            changes, expected, moves = {}, {}, []
            for old, new in mapping.items():
                if old != new:
                    changes.update({old: None, new: notes[old].encode()})
                    expected.update({old: state.one('SELECT sha FROM notes WHERE path=?', (old,))['sha'], new: None})
                    moves.append([old, new])
            coordinator.commit(changes, expected, {'moves': moves})
            vault.index()
            for _ in range(2000):
                if not semantic.once():
                    break
            assert semantic.status()['status'] == 'READY'
            for old, new in mapping.items():
                result = engine.recommend({'path': new, 'text': notes[old], 'focus': notes[old][:600]})
                assert [i['title'] for i in result['items']] == [i['title'] for i in cases[old]['items']], old
                assert vault.read(new) == notes[old]
            checks.append('all 50 sources preserve recommendation order after directory relocation')
        args.output.write_text(json.dumps({'index': semantic.status(), 'checks': checks, 'cases': cases}, ensure_ascii=False, indent=2), 'utf-8')
        for path, result in cases.items():
            if Path(path).stem in {'Двигатели и приводы', 'Гибридный привод', 'pool', 'Среда и экосистемы', 'Технологии'}:
                print(json.dumps({'source': path, 'titles': [v['title'] for v in result['items']]}, ensure_ascii=False), flush=True)
        semantic.close()
        state.close()


if __name__ == '__main__':
    main()
