import json
from dataclasses import replace

import httpx
import pytest

from mastermind import wyvern_intent as intent
from mastermind.audit import Audit
from mastermind.auth import Auth
from mastermind.backup import Backup
from mastermind.coordinator import Coordinator
from mastermind.errors import DomainError
from mastermind.restore import Restore
from mastermind.runtime_client import RuntimeClient
from mastermind.state import State
from mastermind.vault import Vault
from mastermind.wyvern import Wyvern


def selected(adapter="google"):
    return {"schema": intent.SCHEMA, "state": "observed", "instance_id": "source-host", "client_id": "mastermind",
            "revision": 7, "bindings": {"text": {"adapter_id": adapter, "profile": "default"}}}


def test_own_intent_roundtrip_clean_restore_stays_pending_without_mutating_gateway(recovery, tmp_path, monkeypatch):
    backup, _, auth = recovery
    auth.initialize("test-access")
    monkeypatch.setattr(Wyvern, "export_intent", lambda self: selected())
    archive = tmp_path / "with-intent.zip"
    backup.create(archive)
    config = replace(backup.config, home=tmp_path / "clean")
    state = State(config.state / "mastermind.sqlite3")
    try:
        audit = Audit(config, state)
        coordinator = Coordinator(config, state, RuntimeClient(config))
        second = Backup(config, state, coordinator, Vault(config, state, coordinator), backup.secrets, audit)
        monkeypatch.setattr(Wyvern, "call", lambda *args, **kwargs: pytest.fail("Restore must not write to shared Wyvern"))
        Restore(second, Auth(state, audit)).apply(archive)
        assert intent.read(state) == {**selected(), "state": "pending_verification"}
        with pytest.raises(DomainError):
            intent.validate({**selected(), "api_key": "must-not-be-exported"})
    finally:
        state.close()


def test_pending_intent_blocks_wrong_adapter_and_survives_reexport(service, tmp_path):
    _, state, _, _ = service
    intent.save(state, {**selected(), "state": "pending_verification"})
    link = tmp_path / "link.json"
    link.write_text(json.dumps({"schema": "exocortex.wyvern.link.v1", "mode": "remote", "url": "https://gateway.test",
                               "instance_id": "source-host", "client_id": "mastermind", "token": "a" * 64}), encoding="utf-8")
    calls = []
    def serve(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"schema": "exocortex.wyvern.client.v1", **{k: v for k, v in selected("other").items() if k != "schema"},
                                        "binding_revision": 8, "llm_ready": True})
    with httpx.Client(base_url="https://gateway.test", transport=httpx.MockTransport(serve)) as client:
        gateway = Wyvern(link, client=client, intent_state=state)
        assert gateway.status()["code"] == "WYVERN_RESTORE_PENDING"
        with pytest.raises(DomainError, match="restored Adapter"):
            gateway.call("POST", "/v1/generate", data={})
        assert "/v1/generate" not in calls
        assert gateway.export_intent() == intent.read(state)


def test_configured_gateway_failure_cannot_silently_omit_backup_intent(service, tmp_path):
    _, state, _, _ = service
    link = tmp_path / "missing.json"
    gateway = Wyvern(link, intent_state=state)
    assert gateway.export_intent()["state"] == "unconfigured"
    intent.save(state, selected())
    with pytest.raises(DomainError, match="capture current"):
        gateway.export_intent()
    link.write_text("invalid", encoding="utf-8")
    with pytest.raises(DomainError):
        gateway.export_intent()
