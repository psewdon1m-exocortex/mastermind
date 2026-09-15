import json

import pytest
from fastapi.testclient import TestClient
from test_api import api, authenticate  # noqa: F401 - reuse the live ASGI fixture

from mastermind.api import OWNER_COOKIE
from mastermind.fs import atomic_write
from mastermind.shared_routes import COOKIE


@pytest.fixture
def shared_api(request):
    owner, service = request.getfixturevalue("api")
    atomic_write(service.config.secret_directory / "share_pepper_v1", b"separate-private-pepper")
    authenticate(owner)
    body = "---\nsecret: PRIVATE_FRONTMATTER\n---\n\nPublic text\n\n@PRIVATE_TARGET\n\nFinal text\n"
    assert owner.post("/api/notes", json={"path": "Share.md", "text": body}).status_code == 200
    issued = owner.post("/api/v1/shares", json={"path": "Share.md", "permission": "edit"})
    assert issued.status_code == 200
    path = "/s/" + issued.json()["url"].rsplit("/", 1)[1]
    visitor = TestClient(owner.app, base_url=service.config.public_url)
    visitor.headers.update({"Origin": service.config.public_url})
    yield owner, visitor, service, path, issued.json()["share_id"]
    visitor.close()


def unlock(visitor, path):
    result = visitor.post(path + "/api/session", json={})
    assert result.status_code == 200
    assert "HttpOnly" in result.headers["set-cookie"] and "Secure" in result.headers["set-cookie"]
    assert "SameSite=strict" in result.headers["set-cookie"]
    visitor.headers["X-CSRF-Token"] = result.json()["csrf"]
    return result


def test_public_scope_and_strict_csp(shared_api):
    owner, visitor, service, path, _ = shared_api
    page = visitor.get(path)
    assert page.status_code == 200 and "default-src 'none'" in page.headers["content-security-policy"]
    assert "unsafe-inline" not in page.headers["content-security-policy"]
    assert page.headers["x-frame-options"] == "DENY" and page.headers["cache-control"] == "no-store"
    assert "noindex" in page.headers["x-robots-tag"]
    assert visitor.get(path + "/api/note").status_code == 401
    unlock(visitor, path)
    result = visitor.get(path + "/api/note")
    assert result.status_code == 200 and "PRIVATE" not in result.text
    assert "Share.md" not in result.text
    # Share cookie or token must never be interpreted as owner authentication.
    for route in ("/api/notes", "/api/graph", "/api/status", "/api/v1/shares", "/runtime/index.html"):
        assert visitor.get(route).status_code == 401
    visitor.cookies.set(OWNER_COOKIE, visitor.cookies.get(COOKIE), domain="mastermind.test", path="/")
    assert visitor.get("/api/notes").status_code == 401
    assert visitor.get(path + "/api/content", params={"path": "Private.md"}).status_code == 404
    # Even an owner opening Shared receives only the public projection.
    unlock(owner, path)
    assert "PRIVATE" not in owner.get(path + "/api/note").text
    assert path not in json.dumps(service.audit.page())


def test_public_http_etag_csrf_injection_and_conflict(shared_api):
    owner, visitor, _, path, _ = shared_api
    unlock(visitor, path)
    response = visitor.get(path + "/api/note")
    view = response.json()
    values = [part["value"] for part in view["segments"] if part["kind"] == "text"]
    body = {"projection_id": view["projection_id"], "values": values}
    assert visitor.put(path + "/api/note", json=body).status_code == 428
    headers = {"If-Match": response.headers["etag"]}
    assert visitor.put(path + "/api/note", json=body, headers={**headers, "Origin": "https://evil.test"}).status_code == 403
    assert visitor.put(path + "/api/note", json=body, headers={**headers, "X-CSRF-Token": "bad"}).status_code == 403
    assert visitor.put(path + "/api/note", json={**body, "fragments": ["forged"]}, headers=headers).status_code == 422
    malicious = values.copy()
    malicious[-1] += "[Open](../Private.md)"
    assert visitor.put(path + "/api/note", json={**body, "values": malicious}, headers=headers).status_code == 422
    values[-1] = values[-1].replace("Final text", "Visitor change")
    saved = visitor.put(path + "/api/note", json=body, headers=headers)
    assert saved.status_code == 200
    original = owner.get("/api/note", params={"path": "Share.md"}).json()
    assert "Visitor change" in original["text"] and "PRIVATE_TARGET" in original["text"]
    stale = visitor.put(path + "/api/note", json=body, headers=headers)
    assert stale.status_code == 409 and stale.json()["projection"]
    assert "PRIVATE" not in stale.text


def test_policy_change_invalidates_open_public_page(shared_api):
    owner, visitor, _, path, identifier = shared_api
    unlock(visitor, path)
    assert visitor.get(path + "/api/note").status_code == 200
    changed = owner.patch("/api/v1/shares/" + identifier, json={"permission": "view"})
    assert changed.status_code == 200
    assert visitor.get(path + "/api/note").status_code == 401
    unlock(visitor, path)
    assert visitor.get(path + "/api/note").json()["permission"] == "view"
    assert owner.patch("/api/v1/shares/" + identifier, json={"revoke": True}).status_code == 200
    assert visitor.get(path).status_code == 404
    assert visitor.get(path + "/api/note").status_code == 404
