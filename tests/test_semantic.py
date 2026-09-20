import json
import time
from types import SimpleNamespace

import pytest

from mastermind.audit import Audit
from mastermind.errors import DomainError
from mastermind.semantic import Semantic


class Worker:
    model = "a"*64
    ready = True
    mutate = lambda self: None

    def __init__(self):
        self.batches = []

    def request(self, method, path, data=None, **kwargs):
        if path == "/healthz":
            return {"embeddings_ready": self.ready, "model_sha256": self.model}
        assert path == "/chunks"
        text = data["text"]
        return {"model_sha256": self.model, "chunks": [{"start": i, "end": min(len(text), i+32)} for i in range(0, len(text), 32)]}

    def embed(self, texts, *, query=False):
        assert len(texts) <= 16
        self.batches.append((texts, query))
        vectors = []
        for text in texts:
            vector = [0.0]*384
            vector[0 if "knowledge" in text.lower() else 1] = 1.0
            vectors.append(vector)
        self.mutate()
        return {"model_sha256": self.model, "vectors": vectors}

    def close(self):
        pass


@pytest.fixture
def semantic(service):
    config, state, coordinator, vault = service
    context = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault,
                              data_ready=lambda: None, audit=Audit(config, state))
    return Semantic(context, worker=Worker())


def drain(index):
    for _ in range(50):
        if not index.once():
            return
    raise AssertionError("Index did not finish its bounded fixture")


def test_content_verification_cache_is_bounded_and_invalidates_on_content_and_model(semantic):
    index = semantic
    deadline = time.monotonic()+30
    assert index.compare(['knowledge'], ['knowledge body', 'garden'], deadline=deadline) == [1, 0]
    calls = len(index.worker.batches)
    index.compare(['knowledge'], ['knowledge body', 'garden'], deadline=deadline)
    assert len(index.worker.batches) == calls
    assert index.compare(['knowledge'], ['changed garden'], deadline=deadline) == [0]
    for i in range(5):
        index.compare(['knowledge'], [f'document {i}-{j}' for j in range(64)], deadline=deadline)
    assert len(index.comparison_cache) <= 256
    assert all(len(k[2]) == 64 for k in index.comparison_cache)
    index.worker.model, index.next_health = 'b'*64, 0
    with pytest.raises(DomainError, match='model changed'):
        index.compare(['knowledge'], ['knowledge body'], deadline=deadline)


def test_content_verification_honors_deadline_and_model_identity(semantic):
    index = semantic
    with pytest.raises(DomainError) as error:
        index.compare(['knowledge'], ['garden'], deadline=time.monotonic()-1)
    assert error.value.code == 'CONTEXT_DEADLINE'
    index.refresh()
    index.worker.model = 'b'*64
    with pytest.raises(DomainError) as error:
        index.compare(['knowledge'], ['garden'], deadline=time.monotonic()+5)
    assert error.value.code == 'REINDEX_REQUIRED'


def test_incremental_local_search_excludes_deleted_and_changed_sources(semantic):
    index = semantic
    knowledge = index.vault.write("Architecture.md", "Knowledge architecture", None, create=True)
    recipe = index.vault.write("Cooking.md", "Chocolate cake recipe", None, create=True)
    drain(index)
    assert index.search("knowledge")["results"][0]["path"] == "Architecture.md"
    assert index.status()["status"] == "READY"
    index.vault.delete("Cooking.md", recipe["sha256"])
    index.vault.write("Architecture.md", "Replacement prose", knowledge["sha256"])
    assert index.search("knowledge")["results"] == []
    drain(index)
    assert index.status()["notes_indexed"] == 1
    assert index.state.one("SELECT COUNT(*) AS n FROM semantic_chunks")["n"] == 1
    assert index.search("replacement")["results"][0]["excerpt"] == "Replacement prose"


def test_concurrent_edit_during_embedding_cannot_publish_stale_vectors(semantic):
    index = semantic
    note = index.vault.write("Live.md", "Knowledge before edit", None, create=True)
    index.worker.mutate = lambda: index.vault.write("Live.md", "Knowledge after edit", note["sha256"])
    assert not index.once()
    assert index.state.one("SELECT COUNT(*) AS n FROM semantic_chunks")["n"] == 0
    index.worker.mutate = lambda: None
    drain(index)
    assert index.search("knowledge")["results"][0]["excerpt"] == "Knowledge after edit"


def test_model_change_needs_explicit_reindex_and_confirmed_digest(semantic):
    index = semantic
    index.vault.write("Knowledge.md", "Knowledge", None, create=True)
    drain(index)
    index.worker.model, index.next_health = "b"*64, 0
    with pytest.raises(DomainError) as failure:
        index.search("knowledge")
    assert failure.value.code == "REINDEX_REQUIRED"
    with pytest.raises(DomainError):
        index.reindex("a"*64)
    index.reindex("b"*64)
    drain(index)
    assert index.search("knowledge")["index"]["model_sha256"] == "b"*64
    assert index.state.one("SELECT model_sha FROM semantic_chunks")["model_sha"] == "b"*64


def test_rebuild_progress_and_deadline_survive_engine_restart(semantic):
    index = semantic
    index.vault.write("Long.md", "Knowledge architecture "*100, None, create=True)
    assert index.once()
    initial = index.state.one("SELECT next_chunk FROM semantic_documents")["next_chunk"]
    assert initial == 16
    restarted = Semantic(index.service, worker=index.worker)
    assert restarted.once()
    assert index.state.one("SELECT next_chunk FROM semantic_documents")["next_chunk"] == 32
    with index.state.transaction() as db:
        db.execute("UPDATE semantic_run SET deadline=?", (time.time()-1,))
    assert not restarted.once()
    assert restarted.status()["error"] == "REINDEX_DEADLINE"
    restarted.reindex(index.worker.model)
    drain(restarted)
    assert restarted.status()["status"] == "READY"


def test_deleted_derived_index_rebuild_does_not_change_canonical_markdown(semantic):
    index = semantic
    index.vault.write("Source.md", "# Heading\n\nKnowledge source with `literal syntax`.", None, create=True)
    before = index.vault.read("Source.md")
    drain(index)
    with index.state.transaction() as db:
        db.execute("DELETE FROM semantic_documents")
        db.execute("DELETE FROM semantic_chunks")
    drain(index)
    assert index.vault.read("Source.md") == before
    index.worker.ready, index.next_health = False, 0
    with pytest.raises(DomainError) as failure:
        index.search("knowledge")
    assert failure.value.code == "EMBEDDINGS_UNAVAILABLE"
    assert index.vault.list("Knowledge")


def test_representation_upgrade_rebuilds_derived_text_without_changing_sources(semantic):
    index = semantic
    raw = '---\ndataset: fixture\nkind: key\n---\n#key #fixture\nKnowledge architecture'
    index.vault.write('Source.md', raw, None, create=True)
    index.vault.write('Empty.md', '---\nkind: key\n---\n#key', None, create=True)
    drain(index)
    assert index.status()['notes_indexed'] == 2
    assert all('dataset' not in text and 'fixture' not in text
               for texts, _ in index.worker.batches for text in texts)
    assert index.search('knowledge')['results'][0]['excerpt'] == 'Knowledge architecture'
    index.state.set_setting('semantic_representation', 'older-format')
    index.next_health = 0
    index.refresh()
    assert index.status()['notes_indexed'] == 0
    assert index.search('knowledge')['results'] == []
    drain(index)
    assert index.status()['status'] == 'READY'
    assert index.vault.read('Source.md') == raw


def test_foreground_job_yields_rebuild_and_public_sources_are_never_context(semantic):
    index = semantic
    index.vault.write("Source.md", "Knowledge from owner Vault", None, create=True)
    with index.state.transaction() as db:
        db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,NULL,NULL)",
            ("a"*32, "public-source", "idempotency-fixture", "source-sha", "UNDERSTANDING", "UNDERSTANDING", 40, 0, 0, json.dumps({"source": "private input"})))
    assert not index.once() and not index.worker.batches
    with index.state.transaction() as db:
        db.execute("UPDATE jobs SET state='PLACING'")
    drain(index)
    assert index.status()["status"] == "READY"
    assert all("private input" not in text for texts, _ in index.worker.batches for text in texts)
