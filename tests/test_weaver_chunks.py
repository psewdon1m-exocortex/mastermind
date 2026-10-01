import re
import time
from types import SimpleNamespace

import pytest
from test_semantic import semantic  # noqa: F401 - shared fixture

from mastermind.embeddings import Embeddings
from mastermind.errors import DomainError
from mastermind.search_content import chunk_text, prepare


class Tokenizer:
    def no_truncation(self):
        pass

    def enable_truncation(self, **kwargs):
        pass

    def encode(self, text, **kwargs):
        spans = [(m.start(), m.end()) for m in re.finditer(r'\S+', text)]
        return SimpleNamespace(ids=list(range(len(spans))), offsets=spans)


def test_sections_overlap_and_complete_coverage_do_not_cross_topics():
    raw = '# Birds\n\n'+('wing feather migration '*400)+'\n\n## Navigation\n'+('magnetic compass '*400)
    prepared = prepare(raw)
    engine = Embeddings(None, None)
    engine.tokenizer = Tokenizer()
    plans = {}
    for overlap in (0, 32, 64):
        spans = engine.chunks(prepared['text'], sections=prepared['sections'], overlap=overlap)
        plans[overlap] = spans
        covered = set()
        for span in spans:
            section = next(s for s in prepared['sections'] if s['start'] == span['section_start'])
            assert section['start'] <= span['start'] < span['end'] <= section['end']
            assert len(engine.tokenizer.encode('passage: '+chunk_text(prepared['text'], span)).ids) <= 512
            covered.update(range(span['start'], span['end']))
        assert all(i in covered for i, c in enumerate(prepared['text']) if not c.isspace())
        assert any('Navigation' in span['heading'] for span in spans)
    assert len(plans[64]) >= len(plans[0])


def test_preparation_is_shared_and_preserves_source_section_receipts():
    raw = '---\ndataset: sample\nkind: key\n---\n# Engines\n#key #sample\n\nElectric motors provide torque.\n\n## Files\n[Diagram](https://private.invalid/secret)\n@chronos: private-id'
    value = prepare(raw)
    assert 'private' not in value['text'] and '#key' not in value['text'] and 'sample' not in value['text']
    assert 'Electric motors' in value['text'] and 'Diagram' in value['text']
    for section in value['sections']:
        assert 0 <= section['source_start'] <= section['source_end'] <= len(raw)
        assert value['text'][section['start']:section['end']].strip()


def test_code_heading_does_not_create_a_section():
    value = prepare('# Code\n\n```python\n# Not a section\nprint(1)\n```\n\n## Real section\nElectrical circuits conduct current.')
    assert [s['heading'] for s in value['sections']] == ['Code', 'Code / Real section']
    assert 'Not a section' in value['text']


def test_query_similarity_prefix_and_variant_rebuild(semantic):  # noqa: F811 - pytest fixture
    index = semantic
    index.similarity_mode = 'query'
    index.vault.write('Source.md', 'Knowledge passage', None, create=True)
    from test_semantic import drain
    drain(index)
    assert index.state.one('SELECT COUNT(*) AS n FROM semantic_variants')['n'] == 1
    assert index.search('knowledge', task='note_similarity')['results'][0]['path'] == 'Source.md'
    index.compare(['knowledge'], ['a new knowledge body'], task='note_similarity', deadline=time.monotonic()+5)
    assert index.worker.batches[-1][1] is True
    index.compare(['knowledge'], ['another knowledge body'], task='knowledge_lookup', deadline=time.monotonic()+5)
    assert index.worker.batches[-1][1] is False
    with index.state.transaction() as db:
        db.execute("UPDATE semantic_variants SET source_sha='stale'")
    with pytest.raises(DomainError) as error:
        index.search('knowledge', task='note_similarity')
    assert error.value.code == 'SIMILARITY_INDEXING'
    drain(index)
    assert index.search('knowledge', task='note_similarity')['results']


@pytest.mark.parametrize('sections,overlap', [('bad',0), ([{'start':0,'end':5},{'start':1,'end':6}],0), (None,True)])
def test_invalid_chunk_plans_are_rejected(sections, overlap):
    engine = Embeddings(None, None)
    engine.tokenizer = Tokenizer()
    with pytest.raises(DomainError):
        engine.chunks('abcdef', sections=sections, overlap=overlap)
