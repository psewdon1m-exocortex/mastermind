import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from mastermind.context_indexing.graph import Scope
from mastermind.context_indexing.index import Index
from mastermind.context_indexing.pipeline import Pipeline
from mastermind.context_indexing.related import RelatedNotes
from mastermind.context_indexing.settings import Settings
from mastermind.search_content import Corpus, content


def test_content_preserves_topics_and_labels_without_technical_metadata():
    raw = ('---\ndataset: trial57\nkind: key\nid: private-id\naliases: [Мотор]\n'
           'description: Тяговые установки\ntags: [main, техника]\n---\n'
           '# Двигатели\n#key #trial57 #автомобили\n[[folder/Мотор.md|Электрический привод]]\n'
           '@saturn: private/resource-id\n@chronos: secret-event-id\n[Схема](https://private.invalid/secret)')
    result = content(raw)
    for term in ('Мотор', 'Тяговые установки', 'техника', 'Двигатели', 'автомобили', 'Электрический привод', 'Схема'):
        assert term in result
    for term in ('trial57', 'dataset', 'kind', 'private', 'secret', '#key', 'folder'):
        assert term not in result


def test_scope_local_template_detection_does_not_depend_on_dataset_name():
    template = 'Этот узел объединяет предметные заметки и служит разрешённой точкой размещения для Crusher.'
    docs = {str(i): f'Раздел {i}\nПодтема направления «{name}». {template}\n{fact}'
            for i, (name, fact) in enumerate([('Машины', 'Тяговая установка'), ('Птицы', 'Оперение крыла'),
                                              ('Цветы', 'Опыление насекомыми')])}
    corpus = Corpus(docs)
    result = corpus.clean(docs['0'])
    assert 'Тяговая установка' in result and 'Crusher' not in result and 'Подтема направления' not in result
    assert 'Crusher' in Corpus({'0': docs['0']}).clean(docs['0'])


@pytest.mark.parametrize('heading,caption', [('Учебное занятие', 'Событие Chronos:'),
                                            ('Workshop schedule', 'Calendar entry:')])
def test_short_recurring_blocks_are_not_topic_evidence(heading, caption):
    docs = {str(i): f'# {topic}\n{fact}\n## {heading}\n{caption} @chronos: private-{i}'
            for i, (topic, fact) in enumerate([('Engines', 'Diesel pistons compress fuel'),
                ('Birds', 'Feathers insulate hatchlings'), ('Botany', 'Roots absorb dissolved nutrients')])}
    corpus = Corpus(docs)
    for raw in docs.values():
        clean = corpus.clean(raw)
        assert heading not in clean and caption not in clean and 'private' not in clean
    assert 'Diesel pistons compress fuel' in corpus.clean(docs['0'])


def test_common_subjects_and_single_topical_headings_are_preserved():
    docs = {str(i): f'## Energy\n{fact}' for i, fact in enumerate([
        'Solar panels produce electricity', 'Batteries store chemical energy', 'Turbines convert airflow into electricity'])}
    corpus = Corpus(docs)
    assert all('Energy' in corpus.clean(t) for t in docs.values())
    assert corpus.weight('energy') > 0
    duplicate = 'Aircraft wings use carbon composites for structural strength.'
    copies = Corpus({str(i): duplicate for i in range(8)})
    assert copies.clean(duplicate) == duplicate
    assert copies.overlap(duplicate, duplicate)[0] == pytest.approx(1)


def test_unfilled_fields_do_not_supply_facts_but_template_prose_remains_searchable():
    raw = '# {{title}}\n## Summary\n{{summary}}\n## Body\n{{body}}\n## Aviation\nAircraft wings use carbon composites.'
    clean = Corpus({'one': raw}).clean(raw)
    assert 'Aircraft wings use carbon composites.' in clean and 'Aviation' in clean
    assert 'Summary' not in clean and 'Body' not in clean and '{{' not in clean


@pytest.mark.parametrize('title', ['Автомобили', 'Животные', 'Растения', 'Среда и экосистемы', 'Технологии'])
def test_all_demo_overviews_ignore_shared_short_sections(service, title):
    config, state, coordinator, vault = service
    ctx = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault, data_ready=lambda: None)
    notes = json.loads((Path(__file__).parent/'fixtures/related_demo50.json').read_text('utf-8'))['notes']
    coordinator.commit({p: t.encode() for p, t in notes.items()}, {p: None for p in notes})
    vault.index()
    engine = RelatedNotes(ctx, Pipeline(ctx, Index(ctx)), Settings(ctx))
    path = f'root/{title}.md'
    result = engine.recommend({'path': path, 'text': notes[path]})
    titles = {i['title'] for i in result['items']}
    assert not titles & ({'Автомобили', 'Животные', 'Растения', 'Среда и экосистемы', 'Технологии'}-{title})
    assert len(result['items']) >= 2
    assert all(not any(word in i['reason'] for word in ('занятие', 'обзор', 'подтемы', 'событие')) for i in result['items'])


def test_unverified_retrieval_vectors_never_authorize_a_suggestion(quality):
    related, _, _ = quality
    from mastermind.errors import DomainError
    class Semantic:
        def search(self, query, **kwargs):
            return {'results': [{'path': 'c/deep/Дуб.md', 'score': .99, 'excerpt': ''}], 'index': {'status': 'READY'}}
        def compare(self, *args, **kwargs):
            raise DomainError('WORKER_BUSY', 'Busy', 429)
    related.pipeline.semantic = Semantic()
    result = related.recommend({'path': 'Draft.md', 'text': 'Квантовая запутанность фотонов и интерференция лазера'})
    assert not result['items'] and result['degraded']


def test_disabled_vector_channel_also_disables_semantic_verification(quality):
    related, _, _ = quality
    class Semantic:
        def compare(self, *args, **kwargs):
            pytest.fail('Disabled vectors must not run verification')
        def search(self, *args, **kwargs):
            pytest.fail('Disabled vectors must not run retrieval')
    related.pipeline.semantic = Semantic()
    related.pipeline.disabled = frozenset({'vector'})
    result = related.recommend({'path': 'Draft.md', 'text': 'Бензиновый мотор использует топливо для получения тяги.'})
    assert result['degraded'] and 'Бензиновый мотор' in {i['title'] for i in result['items']}


def test_short_standalone_queries_can_match_without_shared_words(quality):
    related, _, _ = quality
    class Semantic:
        def search(self, query, **kwargs):
            return {'results': [{'path': p, 'score': .8, 'excerpt': ''} for p in kwargs['allowed_paths']],
                    'index': {'status': 'READY'}}
        def compare(self, queries, documents, **kwargs):
            return [.93 if 'Бензиновый мотор использует' in text else .70 for text in documents]
    related.pipeline.semantic = Semantic()
    result = related.recommend({'path': 'Draft.md', 'text': 'Combustion'})
    assert 'Бензиновый мотор' in {i['title'] for i in result['items']}


@pytest.fixture
def quality(service):
    config, state, coordinator, vault = service
    ctx = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault, data_ready=lambda: None)
    intro = 'Подтема направления «{theme}». Этот узел объединяет предметные заметки и служит разрешённой точкой размещения для Crusher.'
    notes = {'root.md': '[[Двигатели]]\n[[Птицы]]\n[[Деревья]]\n[[pool]]',
             'root/pool.md': 'Здесь находятся результаты Crusher, ещё не отнесённые к тематической ветке.',
             'root/templates/example crusher.md': '{{crusher.body}}',
             'a/Двигатели.md': intro.format(theme='Машины')+'\n[[Бензиновый мотор]]\n[[Электрический мотор]]',
             'b/Птицы.md': intro.format(theme='Животные')+'\n[[Воробей]]\n[[Синица]]',
             'c/Деревья.md': intro.format(theme='Растения')+'\n[[Дуб]]\n[[Сосна]]',
             'a/deep/Бензиновый мотор.md': 'Бензиновый мотор использует топливо для получения тяги. [[Двигатели]]',
             'a/deep/Электрический мотор.md': 'Электрический мотор использует ток для получения тяги. [[Двигатели]]',
             'b/deep/Воробей.md': 'Воробей собирает зёрна и строит гнездо. [[Птицы]]',
             'b/deep/Синица.md': 'Синица поедает насекомых и живёт в дупле. [[Птицы]]',
             'c/deep/Дуб.md': 'Дуб имеет широкие листья и даёт жёлуди. [[Деревья]]',
             'c/deep/Сосна.md': 'Сосна сохраняет хвою круглый год. [[Деревья]]',
             'Draft.md': 'Original text'}
    for path, body in notes.items():
        text = '---\ndataset: verification82\nkind: example\n---\n#verification82\n'+body
        vault.write(path, text, None, create=True)
        notes[path] = text
    pipeline = Pipeline(ctx, Index(ctx))
    return RelatedNotes(ctx, pipeline, Settings(ctx)), ctx, notes


def test_boilerplate_hubs_do_not_recommend_other_topics(quality):
    related, _, notes = quality
    result = related.recommend({'path': 'a/Двигатели.md', 'text': notes['a/Двигатели.md']})
    titles = [i['title'] for i in result['items']]
    assert set(titles) == {'Бензиновый мотор', 'Электрический мотор'}
    assert all(i['relation'] == 'linked' and 'Linked' in i['reason'] for i in result['items'])
    assert all('dataset' not in i['excerpt'] and 'Crusher' not in i['excerpt'] for i in result['items'])


def test_all_note_roles_use_the_same_content_rules(quality):
    related, _, notes = quality
    query = 'Бензиновый мотор использует топливо для получения тяги.'
    for path in ('root/pool.md', 'root/templates/example crusher.md', 'root.md'):
        result = related.recommend({'path': path, 'text': query})
        assert 'Бензиновый мотор' in {i['title'] for i in result['items']}
        assert 'empty_reason' not in result
        assert all(i['path'] != path for i in result['items'])
    root = related.recommend({'path': 'root.md', 'text': notes['root.md']})
    assert {'Двигатели', 'Птицы', 'Деревья'} <= {i['title'] for i in root['items']}


def test_directory_move_preserves_order_and_keeps_canonical_bytes(quality):
    related, ctx, notes = quality
    query = {'path': 'a/Двигатели.md', 'text': notes['a/Двигатели.md']}
    before = related.recommend(query)
    moves = [(p, 'arbitrary/deeper/'+p.rsplit('/', 1)[-1]) for p in notes]
    for old, new in moves:
        row = ctx.state.one('SELECT sha FROM notes WHERE path=?', (old,))
        ctx.coordinator.commit({old: None, new: notes[old].encode()}, {old: row['sha'], new: None}, {'moves': [[old, new]]})
    ctx.vault.index()
    after = related.recommend({**query, 'path': 'arbitrary/deeper/Двигатели.md'})
    assert [i['title'] for i in before['items']] == [i['title'] for i in after['items']]
    assert all(ctx.vault.read(new) == notes[old] for old, new in moves)


def test_graph_context_cannot_pull_private_notes_into_scoped_lookup(quality):
    related, _, _ = quality
    scope = Scope('owner', frozenset({'a/Двигатели.md'}))
    result, _ = related.pipeline.run({'text': 'Двигатели [[Воробей]] [[Синица]]'}, scope=scope)
    encoded = json.dumps(result, ensure_ascii=False)
    assert 'зёрна' not in encoded and 'дупле' not in encoded and 'b/deep/' not in encoded


def test_high_common_vector_floor_is_not_enough_without_topical_evidence(quality):
    related, _, _ = quality
    class Semantic:
        def compare(self, queries, documents, **kwargs):
            return [.9] * len(documents)
        def search(self, query, **kwargs):
            return {'results': [{'path': p, 'score': .9, 'excerpt': ''} for p in kwargs['allowed_paths']],
                    'index': {'status': 'READY'}}
    related.pipeline.semantic = Semantic()
    result = related.recommend({'path': 'Draft.md', 'text': 'Квантовая запутанность фотонов и интерференция лазера'})
    assert not result['items']


def test_semantic_verification_keeps_late_source_passages_and_cursor_context(quality):
    related, _, _ = quality
    calls = []
    class Semantic:
        def search(self, query, **kwargs):
            return {'results': [], 'index': {'status': 'READY'}}
        def compare(self, queries, documents, **kwargs):
            calls.append(queries)
            return [.7] * len(documents)
    related.pipeline.semantic = Semantic()
    body = 'A long introduction without a filename. '*120+'\nБензиновый мотор использует топливо для получения тяги.'
    related.recommend({'path': 'Draft.md', 'text': body, 'focus': 'A distinct cursor passage about the engine.'})
    assert calls and 1 <= len(calls[-1]) <= 5
    assert any('Бензиновый мотор' in query for query in calls[-1])
    assert any('distinct cursor passage' in query for query in calls[-1])
    assert all(len(query) <= 1600 and not query.startswith('Draft\n') for query in calls[-1])


def test_unsaved_links_supply_graph_context_without_canonical_write(quality):
    related, ctx, notes = quality
    result = related.recommend({'path': 'Draft.md', 'text': 'Двигатели\n[[Бензиновый мотор]]\n[[Электрический мотор]]'})
    assert {'Бензиновый мотор', 'Электрический мотор'} <= {i['title'] for i in result['items']}
    assert ctx.vault.read('Draft.md') == notes['Draft.md']
