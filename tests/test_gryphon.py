import copy
import json
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import httpx
import pytest
from test_api import api as api_fixture
from test_api import authenticate

from mastermind.auth import digest
from mastermind.errors import DomainError
from mastermind.gryphon import CATALOG, Gryphon, catalog_matches
from mastermind.state import EPHEMERAL_TABLES, MANDATORY_TABLES

api = api_fixture


@pytest.fixture
def connected(api, tmp_path):
    client, service = api
    credential = tmp_path / "gryphon-client"
    credential.write_text("fixture-" + "g"*48)
    gateway = service.gryphon
    gateway.config = replace(service.config, gryphon_socket="/fixture.sock", gryphon_token_file=credential)
    status = {"schema": "exocortex.gryphon.service-status.v1", "serviceId": "mastermind", "version": "0.1.4",
              "state": "enabled", "connected": True, "connectionId": "connection-1", "commandPrefix": "mastermind",
              "commands": CATALOG, "bot": {"id": "bot-1", "alias": "fixture", "username": "fixture_bot", "state": "ready"},
              "binding": {"telegramUserId": "12345", "chatId": "12345", "linkedAt": "2026-09-19T00:00:00Z"}}
    requests = []
    def handle(request):
        assert request.headers["authorization"] == "Bearer " + credential.read_text()
        requests.append((request.method, request.url.path, request.content))
        if request.url.path == "/v1/service/connection" and request.method == "DELETE":
            status.update(connected=False, connectionId=None, state="unlinked", bot=None, binding=None)
            return httpx.Response(200, json={"disconnected": True})
        if request.url.path == "/v1/service/binding" and request.method == "DELETE":
            status["binding"] = None
            return httpx.Response(200, json={"revoked": True})
        if request.url.path == "/v1/service/command-catalog":
            return httpx.Response(200, json={"serviceId": "mastermind", **json.loads(request.content)})
        return httpx.Response(200, json=status)
    gateway.transport = httpx.MockTransport(handle)
    return client, service, status, requests


def envelope(command="crusher", event="event-1", **changes):
    return {"schema": "exocortex.telegram.command.v1", "serviceId": "mastermind", "eventId": event,
            "correlationId": "correlation-1", "connectionId": "connection-1",
            "actor": {"telegramUserId": "12345", "chatId": "12345", "chatType": "private"},
            "command": command, "arguments": {}, **changes}


def issued(service, event="event-1"):
    result = service.gryphon.command(envelope(event=event))
    return re.search(r"code: ([0-9]{6})", result["actions"][0]["text"])[1], result


def test_machine_auth_and_owner_csrf_are_separate(connected):
    client, service, _, _ = connected
    path = "/internal/gryphon/command"
    assert client.post(path, json=envelope()).status_code == 401
    assert client.post(path, json=envelope(), headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/owner/gryphon").status_code == 401
    authenticate(client)
    assert client.post(path, json=envelope()).status_code == 401
    assert client.get("/api/owner/gryphon").json()["binding"]["telegramUserId"] == "12345"
    assert client.delete("/api/owner/gryphon/binding", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    result = client.post(path, json=envelope(), headers={"Authorization": "Bearer " + service.gryphon.token()})
    assert result.status_code == 200
    assert "code:" in result.json()["actions"][0]["text"]


def test_code_consumed_once_and_guest_cannot_read_owner_data(connected):
    client, service, _, _ = connected
    code, result = issued(service)
    assert "https://mastermind.test/crusher\n" in result["actions"][0]["text"]
    first = client.post("/api/v1/crusher/sessions", json={"code": code})
    assert first.status_code == 200
    token = first.json()["token"]
    assert client.post("/api/v1/crusher/sessions", json={"code": code}).status_code == 401
    assert client.get("/api/v1/crusher/jobs", headers={"Authorization": "Bearer " + token}).status_code == 200
    for route in ("/api/owner/gryphon", "/api/notes", "/api/owner/settings"):
        assert client.get(route, headers={"Authorization": "Bearer " + token}).status_code in (401, 404)


def test_event_replay_atomic_encrypted_and_survives_restart(connected):
    _, service, _, _ = connected
    code, response = issued(service)
    old = service.gryphon
    service.gryphon = Gryphon(service, transport=old.transport)
    service.gryphon.config = old.config
    assert service.gryphon.command(envelope(correlationId="new-correlation")) == response
    assert service.state.one("SELECT COUNT(*) AS n FROM codes")["n"] == 1
    packed = service.state.one("SELECT response FROM gryphon_events")["response"]
    assert code.encode() not in packed and b"send_message" not in packed
    assert code not in json.dumps(service.audit.page())
    assert {"gryphon_events", "gryphon_access"}.issubset(EPHEMERAL_TABLES)
    assert not {"gryphon_events", "gryphon_access"}.intersection(MANDATORY_TABLES)
    with pytest.raises(DomainError, match="already used"):
        service.gryphon.command(envelope("revoke"))


def test_concurrent_redelivery_issues_one_code(connected):
    _, service, _, _ = connected
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: service.gryphon.command(envelope()), range(4)))
    assert all(result == results[0] for result in results)
    assert service.state.one("SELECT COUNT(*) AS n FROM codes")["n"] == 1


@pytest.mark.parametrize("change", [
    {"serviceId": "saturn"}, {"command": "delete_vault"}, {"connectionId": "another"},
    {"actor": {"telegramUserId": "12345", "chatId": "12345", "chatType": "group"}},
    {"actor": {"telegramUserId": "54321", "chatId": "54321", "chatType": "private"}},
    {"actor": {"telegramUserId": "12345", "chatId": "54321", "chatType": "private"}},
    {"arguments": {"source": "forbidden"}}, {"extra": "forbidden"},
])
def test_invalid_or_foreign_command_cannot_issue_code(connected, change):
    _, service, _, _ = connected
    with pytest.raises(DomainError):
        service.gryphon.command(envelope(**change))
    assert service.state.one("SELECT COUNT(*) AS n FROM codes")["n"] == 0


def test_revocation_only_removes_telegram_access(connected):
    client, service, _, _ = connected
    owner_code = service.crusher_access.code()["code"]
    code, _ = issued(service)
    guest = service.crusher_access.activate(code, "127.0.0.1")["token"]
    pending_code, _ = issued(service, "event-2")
    result = service.gryphon.command(envelope("revoke", "event-3"))
    assert "1 session(s)" in result["actions"][0]["text"]
    assert client.get("/api/v1/crusher/jobs", headers={"Authorization": "Bearer " + guest}).status_code == 401
    assert client.post("/api/v1/crusher/sessions", json={"code": pending_code}).status_code == 401
    assert client.post("/api/v1/crusher/sessions", json={"code": owner_code}).status_code == 200


@pytest.mark.parametrize("path", ["binding", "connection"])
def test_owner_unlink_or_revoke_invalidates_access_and_old_events(connected, path):
    client, service, _, _ = connected
    code, _ = issued(service)
    token = service.crusher_access.activate(code, "127.0.0.1")["token"]
    authenticate(client)
    assert client.delete("/api/owner/gryphon/" + path).status_code == 200
    with pytest.raises(DomainError):
        service.crusher_access.principal(token)
    with pytest.raises(DomainError):
        service.gryphon.command(envelope())


def test_expiry_and_atomic_single_activation(connected):
    _, service, _, _ = connected
    code, _ = issued(service)
    def activate(_):
        try:
            service.crusher_access.activate(code, "127.0.0.1")
            return True
        except DomainError:
            return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(activate, range(2))) == 1
    expired, _ = issued(service, "expired")
    with service.state.transaction() as db:
        db.execute("UPDATE codes SET expires_at=? WHERE code_hash=?", (time.time()-1, digest(expired)))
    with pytest.raises(DomainError):
        service.crusher_access.activate(expired, "127.0.0.1")


def test_old_or_unavailable_gateway_fails_closed_and_retains_last_status(connected):
    _, service, status, _ = connected
    assert service.gryphon.status()["reachable"]
    binding = copy.deepcopy(status["binding"])
    del status["binding"]["telegramUserId"]
    failed = service.gryphon.status()
    assert not failed["reachable"] and failed["last_known"] and failed["binding"] == binding
    with pytest.raises(DomainError):
        service.gryphon.command(envelope())


def test_initialize_and_update_are_scoped_to_current_head(connected, monkeypatch):
    client, service, _, _ = connected
    authenticate(client)
    calls = []
    monkeypatch.setattr(service.updates.updater, "call", lambda *args, **kwargs: calls.append((args, kwargs)) or {"state": "REQUESTED"})
    request = {"request_id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}
    assert client.post("/api/owner/gryphon/initialize", json=request).status_code == 200
    assert calls[-1][1]["data"] == {**request, "head_id": "mastermind"}
    assert client.post("/api/owner/gryphon/initialize", json={**request, "head_id": "saturn"}).status_code == 422
    assert client.post("/api/owner/helper-updates/check", json={"component": "gryphon"}).status_code == 200
    assert calls[-1][1]["data"]["head_id"] == "mastermind"
    assert client.post("/api/owner/helper-updates/install/gryphon", json={**request, "version": "0.1.5"}).status_code == 409


def test_gateway_catalog_order_is_not_significant():
    assert catalog_matches(list(reversed(CATALOG)))
    assert not catalog_matches([CATALOG[0]]*3)
    assert not catalog_matches(None)


def test_receipt_failure_rolls_back_code_and_mapping(connected):
    _, service, _, _ = connected
    # Simulate failure after code allocation, before the durable reply is committed.
    with service.state.transaction() as db:
        db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON gryphon_events BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="fixture failure"):
        issued(service)
    assert service.state.one("SELECT COUNT(*) AS n FROM codes")["n"] == 0
    assert service.state.one("SELECT COUNT(*) AS n FROM gryphon_access")["n"] == 0
    with service.state.transaction() as db:
        db.execute("DROP TRIGGER fail_receipt")
    issued(service)
    assert service.state.one("SELECT COUNT(*) AS n FROM codes")["n"] == 1


def test_periodic_cleanup_expires_receipts_without_a_command(connected):
    _, service, _, _ = connected
    issued(service)
    with service.state.transaction() as db:
        db.execute("UPDATE gryphon_events SET created_at=?", (time.time()-8*86400,))
        db.execute("UPDATE gryphon_access SET expires_at=?", (time.time()-1,))
    service.gryphon.next_reconcile = 0
    service.gryphon.reconcile()
    assert service.state.one("SELECT COUNT(*) AS n FROM gryphon_events")["n"] == 0
    assert service.state.one("SELECT COUNT(*) AS n FROM gryphon_access")["n"] == 0


def test_rotated_credential_cannot_reissue_an_old_event(connected):
    _, service, _, _ = connected
    issued(service)
    service.gryphon.config.gryphon_token_file.write_text("rotated-" + "r"*48)
    with pytest.raises(DomainError, match="cannot be replayed"):
        issued(service)
    assert service.state.one("SELECT COUNT(*) AS n FROM codes")["n"] == 1


def test_unlinked_gateway_with_stray_binding_is_rejected(connected):
    _, service, status, _ = connected
    status.update(connected=False, bot="invalid", binding="invalid")
    assert service.gryphon.status()["code"] == "GRYPHON_PROTOCOL"
