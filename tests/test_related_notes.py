import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mastermind.api import create_app
from mastermind.config import Config
from mastermind.context_indexing.index import Index
from mastermind.context_indexing.pipeline import Pipeline
from mastermind.context_indexing.related import RelatedNotes
from mastermind.context_indexing.settings import Settings
from mastermind.errors import DomainError
from mastermind.fs import atomic_write


@pytest.fixture
def related(service):
    config, state, coordinator, vault = service
    context = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault, data_ready=lambda: None)
    notes = {"Draft.md": "Canonical text must remain unchanged.",
             "Aviation/Designers.md": "Aircraft airplane designers build wings and aerodynamic structures.",
             "Aviation/Materials.md": "Aircraft airplane materials include aluminium and carbon composites for wings.",
             "Garden.md": "Garden soil irrigation feeds flowers and plants.",
             "root/pool.md": "Aircraft airplane wings carbon composites.",
             "root/templates/example crusher.md": "Aircraft airplane wings carbon composites."}
    for path, text in notes.items():
        vault.write(path, text, None, create=True)
    pipeline = Pipeline(context, Index(context))
    return RelatedNotes(context, pipeline, Settings(context)), context, notes


def test_unsaved_context_changes_recommendations_without_writing_notes(related):
    engine, context, notes = related
    first = engine.recommend({"path": "Draft.md", "text": "Aircraft airplane wings and carbon composites"})
    assert {item["path"] for item in first["items"]} == {"Aviation/Designers.md", "Aviation/Materials.md"}
    second = engine.recommend({"path": "Draft.md", "text": "Garden soil irrigation and flowers"})
    assert [item["path"] for item in second["items"]] == ["Garden.md"]
    assert first["degraded"]  # lexical retrieval remains useful without the vector model
    assert {path: context.vault.read(path) for path in notes} == notes
    assert all(set(item) == {"path", "title", "excerpt"} for item in first["items"])
    traces = context.state.rows("SELECT record FROM context_traces")
    assert "Aircraft airplane wings and carbon composites" not in json.dumps(traces)


def test_related_notes_never_invokes_curator_or_placement_policy(related):
    engine, context, _ = related
    context.state.set_setting("context_indexing", {**engine.settings.get(), "curator_enabled": True})
    class ForbiddenCurator:
        def refine(self, *args, **kwargs):
            pytest.fail("Interactive recommendations must not invoke Curator")
    engine.pipeline.curator = ForbiddenCurator()
    assert engine.recommend({"path": "Draft.md", "text": "Aircraft wings"})["items"]


def test_scope_excludes_source_and_templates_before_channel_limits(related):
    engine, _context, _ = related
    calls = []
    class Semantic:
        def search(self, query, **kwargs):
            calls.append(kwargs)
            return {"results": [], "index": {"status": "READY"}}
    engine.pipeline.semantic = Semantic()
    engine.recommend({"path": "Draft.md", "text": "Aviation aircraft"})
    assert calls and not {"Draft.md", "root/pool.md", "root/templates/example crusher.md"} & calls[0]["allowed_paths"]
    assert "Garden.md" in calls[0]["allowed_paths"]


def test_empty_note_and_unrelated_graph_neighbors_do_not_produce_noise(related):
    engine, context, _ = related
    assert not engine.recommend({"path": "Draft.md", "text": "\n  "})["items"]
    old = context.vault.read("Aviation/Materials.md")
    context.vault.write("Aviation/Materials.md", old+"\n[[Garden]]", context.state.one(
        "SELECT sha FROM notes WHERE path='Aviation/Materials.md'")["sha"])
    result = engine.recommend({"path": "Draft.md", "text": "Aircraft airplane wings carbon composites"})
    assert "Garden.md" not in {item["path"] for item in result["items"]}


@pytest.mark.parametrize("data", [
    {"path": "../secret.md", "text": "Aircraft"}, {"path": ".obsidian/private.md", "text": "Aircraft"},
    {"path": "Missing.md", "text": "Aircraft"}, {"path": "Draft.md", "text": "a"*16385},
    {"path": "Draft.md", "text": "Airplane", "focus": "x"*4097},
    {"path": "Draft.md", "text": "Airplane", "sampled": "yes"},
    {"path": "Draft.md", "text": "Airplane", "curator_enabled": True},
    {"path": "Draft.md", "text": "\ud800"}, {"path": None, "text": "Aircraft"},
])
def test_invalid_or_private_context_is_rejected(related, data):
    engine, _, _ = related
    with pytest.raises(DomainError):
        engine.recommend(data)


def test_busy_recommendations_do_not_queue_and_release_slot_after_failure(related):
    engine, _, _ = related
    query = {"path": "Draft.md", "text": "Aircraft wings"}
    engine.slot.acquire()
    try:
        with pytest.raises(DomainError, match="busy") as failure:
            engine.recommend(query)
        assert failure.value.status == 429
    finally:
        engine.slot.release()
    original = engine.pipeline.run
    def fail(*args, **kwargs):
        raise DomainError("TEST_FAILURE", "Test failure", 503)
    engine.pipeline.run = fail
    with pytest.raises(DomainError):
        engine.recommend(query)
    engine.pipeline.run = original
    assert engine.recommend(query)["items"]


def test_related_endpoint_requires_bridge_identity_and_bounds_request(tmp_path):
    directory = tmp_path / "secrets"
    directory.mkdir()
    atomic_write(directory / "bootstrap_access_key", b"test-related-owner")
    atomic_write(directory / "bridge_token", b"test-related-bridge")
    config = Config(home=tmp_path / "data", secret_directory=directory, public_url="https://mastermind.test",
                    runtime_mode="offline", test_mode=True)
    application = create_app(config)
    with TestClient(application, base_url=config.public_url) as client:
        deadline = time.monotonic()+5
        while client.get("/readyz").status_code != 200 and time.monotonic() < deadline:
            time.sleep(.01)
        assert client.get("/readyz").status_code == 200
        route = "/internal/bridge/related-notes"
        query = {"path": "Draft.md", "text": "Aircraft wings"}
        assert client.post(route, json=query).status_code == 401
        login = client.post("/api/auth/login", json={"access_key": "test-related-owner"}, headers={"Origin": config.public_url})
        assert login.status_code == 200
        assert client.post(route, json=query, headers={"X-CSRF-Token": login.json()["csrf"], "Origin": config.public_url}).status_code == 401
        service = application.state.service
        service.vault.write("Draft.md", "Original content", None, create=True)
        calls = []
        def recommend(data):
            calls.append(data)
            return {"path": data["path"], "items": [], "degraded": False, "sampled": False}
        service.context_indexing.related.recommend = recommend
        auth = {"Authorization": "Bearer test-related-bridge"}
        response = client.post(route, json=query, headers=auth)
        assert response.status_code == 200 and calls == [query]
        assert client.post(route, content=b"x"*(128*1024+1), headers=auth).status_code == 413
        assert len(calls) == 1
        assert client.get("/api/related-notes").status_code == 404
