import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from mastermind import __version__
from mastermind.api import CSRF_COOKIE, OWNER_COOKIE, create_app
from mastermind.config import Config
from mastermind.errors import DomainError
from mastermind.fs import atomic_write


@pytest.fixture
def api(tmp_path):
    directory = tmp_path / "secrets-outside-home"
    directory.mkdir()
    atomic_write(directory / "bootstrap_access_key", " exact 🔐 key ".encode())
    atomic_write(directory / "bridge_token", b"bridge-test-token")
    atomic_write(directory / "neptune_export_token", b"neptune-export-test-token")
    config = Config(home=tmp_path / "data", public_url="https://mastermind.test", secret_directory=directory,
                    runtime_mode="offline", test_mode=True, neptune_export_token_file=directory / "neptune_export_token")
    application = create_app(config)
    with TestClient(application, base_url=config.public_url) as client:
        deadline = time.monotonic()+5
        while client.get("/readyz").status_code != 200 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert client.get("/readyz").status_code == 200
        yield client, application.state.service


def authenticate(client):
    response = client.post("/api/auth/login", json={"access_key": " exact 🔐 key "},
                           headers={"Origin": "https://mastermind.test"})
    assert response.status_code == 200
    client.headers.update({"Origin": "https://mastermind.test", "X-CSRF-Token": response.json()["csrf"]})
    return response


def test_context_indexing_settings_are_owner_only_atomic_and_csrf_protected(api):
    client, service = api
    base = "/api/owner/context-indexing"
    assert client.get(base+"/settings").status_code == 401
    assert client.get(base+"/waiting").status_code == 401
    authenticate(client)
    service.vault.write("root.md", "# root", None, create=True)
    assert client.post(base+"/initialize", json={}).status_code == 200
    initial = client.get(base+"/settings").json()
    assert initial["crusher"]["output_dir"] == "root/crusher"
    assert initial["retrieval"]["curator_enabled"] is False
    draft = {"expected_revision": initial["revision"], "operation_id": "settings-test-operation-01",
             "retrieval": {"curator_enabled": True}}
    assert client.patch(base+"/settings", json=draft, headers={"X-CSRF-Token": "invalid"}).status_code == 403
    saved = client.patch(base+"/settings", json=draft)
    assert saved.status_code == 200 and saved.json()["revision"] == initial["revision"]+1
    assert client.patch(base+"/settings", json=draft).json() == saved.json()
    assert client.patch(base+"/settings", json={**draft, "operation_id": "settings-test-operation-02"}).status_code == 409
    invalid = {"expected_revision": saved.json()["revision"], "operation_id": "settings-test-operation-03",
               "crusher": {"template_path": "missing.md"}, "retrieval": {"curator_enabled": False}}
    assert client.patch(base+"/settings", json=invalid).status_code == 404
    assert client.get(base+"/settings").json()["retrieval"]["curator_enabled"] is True
    assert client.post(base+"/validate", json={"crusher": {"output_dir": "elsewhere"}}).status_code == 422
    assert client.get("/api/context-indexing/search?query=private").status_code == 404


def test_second_core_is_rejected_before_opening_or_migrating_the_database(api, monkeypatch):
    _, service = api
    def forbidden(*args, **kwargs):
        raise AssertionError("A nonleader attempted to open SQLite")
    monkeypatch.setattr("mastermind.api.State", forbidden)
    with pytest.raises(DomainError) as failure:
        create_app(service.config)
    assert failure.value.code == "VAULT_BUSY"


def test_neptune_exports_require_separate_capability_and_exact_receipts(api):
    client, service = api
    authenticate(client)
    client.post("/api/notes", json={"path": "A.md", "text": "opaque test note"})
    route = "/api/internal/neptune/mirror"
    assert client.post(route).status_code == 401
    assert client.post(route, headers={"Authorization": "Bearer bridge-test-token"}).status_code == 401
    headers = {"Authorization": "Bearer neptune-export-test-token", "X-Neptune-Purpose": "shared"}
    assert client.post(route, headers=headers).status_code == 403
    headers["X-Neptune-Purpose"] = "mirror"
    result = client.post(route, headers=headers)
    assert result.status_code == 200
    assert int(result.headers["content-length"]) == len(result.content)
    assert hashlib.sha256(result.content).hexdigest() == result.headers["x-content-sha256"]
    assert all(entry["leases"] == 0 for entry in service.exports.entries.values())
    receipt = {"generation": int(result.headers["x-mastermind-generation"]), "size": len(result.content),
               "sha256": result.headers["x-content-sha256"]}
    assert client.post(route + "/receipt", headers=headers, json={**receipt, "size": 1}).status_code == 409
    assert client.post(route + "/receipt", headers=headers, json=receipt).json()["accepted"]
    assert service.state.setting("mirror_verified_generation") == receipt["generation"]


def test_managed_native_commands_preserve_preconditions_and_activity(api):
    client, service = api
    route = "/internal/bridge/note/create"
    assert client.post(route, json={"path": "Managed.md"}).status_code == 401
    headers = {"Authorization": "Bearer bridge-test-token"}
    response = client.post(route, json={"path": "Managed.md"}, headers=headers)
    assert response.status_code == 200
    assert service.state.one("SELECT COUNT(*) AS n FROM activity WHERE kind='CREATE'")["n"] == 1
    assert client.post(route, json={"path": "Elsewhere/managed.md"}, headers=headers).status_code == 409
    assert client.post("/internal/bridge/note/delete", json={"path": "Managed.md"}, headers=headers).status_code == 428
    assert client.post("/internal/bridge/note/delete", json={"path": "Managed.md", "expected_sha256": "0"*64}, headers=headers).status_code == 409
    assert service.vault.read("Managed.md") == ""
    assert client.post("/internal/bridge/note/delete", json={"path": "Managed.md", "expected_sha256": response.json()["sha256"]}, headers=headers).status_code == 200
    assert not (service.config.vault / "Managed.md").exists()
    assert service.state.one("SELECT display FROM reference_history WHERE name_key='managed'")


def test_owner_routes_nonindexable_and_unauthorized_runtime(api):
    client, _ = api
    for path in ("/api/notes", "/api/graph", "/api/status", "/api/logs", "/runtime/index.html"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
        assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/sitemap.xml").status_code == 404
    with pytest.raises(Exception) as denied, client.websocket_connect("/runtime/websockify"):
        pytest.fail("Unauthenticated websocket was accepted")
    assert denied.value.code == 4401


def test_startup_failure_is_visible_to_owner_without_exposing_diagnostics(api):
    client, service = api
    authenticate(client)
    service.ready = False
    service.failure = "RECOVERY_REQUIRED"
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["status"] == "NOT_READY"
    assert response.json()["failure"] == "RECOVERY_REQUIRED"


def test_owner_cookie_csrf_and_etag_write_workflow(api):
    client, _ = api
    response = authenticate(client)
    cookies = response.headers.get_list("set-cookie")
    assert "HttpOnly" in cookies[0] and "Secure" in cookies[0] and "SameSite=strict" in cookies[0]
    assert OWNER_COOKIE in client.cookies and CSRF_COOKIE in client.cookies
    denied = client.post("/api/notes", json={"path": "A.md", "text": "content"}, headers={"X-CSRF-Token": "bad"})
    assert denied.status_code == 403
    created = client.post("/api/notes", json={"path": "A.md", "text": "First\r\nsecond\r\n"})
    assert created.status_code == 200
    read = client.get("/api/note", params={"path": "A.md"})
    assert read.json()["text"] == "First\r\nsecond\r\n"
    assert read.headers["ETag"] == '"'+created.json()["sha256"]+'"'
    assert client.put("/api/note", json={"path": "A.md", "text": "missing precondition"}).status_code == 428
    payload = {"path": "A.md", "text": "saved", "expected_sha256": created.json()["sha256"]}
    assert client.put("/api/note", json=payload).status_code == 200
    assert client.put("/api/note", json=payload).status_code == 409
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/notes").status_code == 401


def test_login_origin_size_and_error_payload_do_not_echo_secrets(api):
    client, _ = api
    response = client.post("/api/auth/login", json={"access_key": "sensitive-canary"})
    assert response.status_code == 403 and "sensitive-canary" not in response.text
    response = client.post("/api/auth/login", json={"access_key": {"private": "sensitive-canary"}},
                           headers={"Origin": "https://mastermind.test"})
    assert response.status_code == 422 and "sensitive-canary" not in response.text
    response = client.post("/api/auth/login", content=b'{"access_key":"' + b"a"*65536 + b'"}',
                           headers={"Origin": "https://mastermind.test", "Content-Type": "application/json"})
    assert response.status_code == 413


def test_native_reference_dictionary_is_bridge_only_and_contains_no_bodies(api):
    client, service = api
    route = "/internal/bridge/reference-dictionary"
    assert client.get(route).status_code == 401
    authenticate(client)
    assert client.post("/api/notes", json={"path": "Café.md", "text": "private body"}).status_code == 200
    with service.state.transaction() as db:
        db.execute("INSERT OR IGNORE INTO reference_history VALUES('internal','deleted','Deleted')")
        db.execute("INSERT OR IGNORE INTO reference_history VALUES('saturn','root/a.pdf','root/a.pdf')")
    assert client.get(route).status_code == 401
    assert client.get(route, headers={"Authorization": "Bearer neptune-export-test-token"}).status_code == 401
    response = client.get(route, headers={"Authorization": "Bearer bridge-test-token"})
    assert response.status_code == 200
    data = response.json()
    assert data["current"] == {"café": "Café"}
    assert set(data["history"]) == {"Café", "Deleted"}
    assert data["saturn"] == ["root/a.pdf"]
    assert set(data) == {"current", "history", "saturn"}
    assert "private body" not in response.text
    service.ready = False
    assert client.get(route, headers={"Authorization": "Bearer bridge-test-token"}).status_code == 503


def test_bridge_references_and_activity_use_separate_scope(api):
    client, service = api
    authenticate(client)
    client.post("/api/notes", json={"path": "Café.md", "text": "#main\nBody"})
    response = client.post("/internal/bridge/references", json={"text": "😀 @Cafe\u0301"})
    assert response.status_code == 401
    response = client.post("/internal/bridge/references", json={"text": "😀 @Cafe\u0301"},
                           headers={"Authorization": "Bearer bridge-test-token"})
    assert response.status_code == 200
    assert response.json()[0]["start"] == 2
    body = {"events": [{"id": "id-1", "session_id": "edit-1", "path": "Café.md", "kind": "EDIT",
                         "occurred_at": time.time()}], "version": __version__, "epoch": service.activity.epoch}
    for _ in range(2):
        assert client.post("/internal/bridge/events", json=body,
                           headers={"Authorization": "Bearer bridge-test-token"}).status_code == 200
    assert service.state.one("SELECT COUNT(*) AS count FROM activity")["count"] == 1


@pytest.mark.parametrize("version", [None, "0.0.1", "999.0.0", True])
def test_bridge_activity_rejects_incompatible_build_before_persisting(api, version):
    client, service = api
    assert version != __version__
    body = {"version": version, "epoch": service.activity.epoch,
            "events": [{"id": "rejected-event", "kind": "EDIT", "path": "Note.md", "occurred_at": time.time()}]}
    response = client.post("/internal/bridge/events", json=body, headers={"Authorization": "Bearer bridge-test-token"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ACTIVITY"
    assert service.state.one("SELECT COUNT(*) AS count FROM activity")["count"] == 0
