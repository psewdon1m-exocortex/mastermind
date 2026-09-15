import asyncio
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from test_api import api as api_fixture, authenticate
from test_owner_operations import keys

from mastermind.admin import create_admin_app, socket_path, start_admin, stop_admin
from mastermind.cli import AdminClient, execute, parser, regular_source
from mastermind.config import Config
from mastermind.errors import DomainError

api = api_fixture


def test_private_admin_routes_are_absent_from_browser_listener(api):
    browser, service = api
    for method, path in (("get", "/v1/doctor"), ("post", "/v1/reindex"), ("post", "/v1/operations")):
        assert getattr(browser, method)(path).status_code == 404
    authenticate(browser)
    assert browser.get("/v1/doctor").status_code == 404
    with TestClient(create_admin_app(service)) as local:
        assert local.get("/v1/vault/validate").json()["valid"]
        assert local.post("/v1/operations", json={"kind": "backup", "command": "whoami"}).status_code == 422


def test_doctor_is_read_only_and_never_claims_unknown_dependencies_or_edge_pass(api):
    _, service = api
    service.vault.write("Private name.md", "private sentinel note body", None, create=True)
    before = service.state.db.total_changes
    with TestClient(create_admin_app(service)) as local:
        report = local.get("/v1/doctor").json()
    assert service.state.db.total_changes == before
    assert report["status"] == "NOT_READY" and report["canonical_ready"]
    assert report["edge_verification"]["status"] == "UNKNOWN"
    assert report["dependencies"]["neptune"]["status"] == "FAIL"
    assert "private sentinel" not in json.dumps(report) and "Private name" not in json.dumps(report)
    assert report["checks"]["sqlite_integrity"]["status"] == "PASS"


def test_cli_real_backup_verify_restore_retains_bytes_and_revokes_browser_session(api, tmp_path):
    browser, service = api
    keys(service)
    authenticate(browser)
    service.vault.write("Local restore.md", "before", None, create=True)
    destination = tmp_path / "cli.zip"
    with TestClient(create_admin_app(service), base_url="http://mastermind-admin") as local:
        client = AdminClient(service.config, client=local)
        result = client.backup(destination)
        assert result["sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()
        assert sum(service.owner_operations.leases.values()) == 0
        assert client.restore(destination)["verified"]
        service.vault.write("Local restore.md", "after", hashlib.sha256(b"before").hexdigest())
        restored = client.restore(destination, apply=True, yes=True)
        assert restored["state"] == "COMPLETED"
        assert service.vault.read("Local restore.md") == "before"
        assert browser.get("/api/status").status_code == 401


def test_cli_requires_apply_confirmation_and_preserves_existing_output(api, tmp_path, monkeypatch):
    _, service = api
    keys(service)
    source = tmp_path / "valid.zip"
    with TestClient(create_admin_app(service), base_url="http://mastermind-admin") as local:
        client = AdminClient(service.config, client=local)
        client.backup(source)
        before = source.read_bytes()
        with pytest.raises(FileExistsError):
            client.backup(source)
        assert source.read_bytes() == before
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        with pytest.raises(DomainError, match="not applied"):
            client.restore(source, apply=True)
        assert all(item["kind"] != "restore" for item in service.owner_operations.listing())


def test_cli_reports_not_ready_with_failure_exit_and_rejects_path_shaped_operation_id():
    class Client:
        def call(self, method, route):
            return {"status": "NOT_READY"}
    config = Config(Path("/unused"), runtime_mode="offline", test_mode=True)
    assert execute(parser().parse_args(["doctor"]), config, Client())[1] == 1
    with pytest.raises(DomainError):
        execute(parser().parse_args(["operation", "../doctor"]), config, Client())


@pytest.mark.skipif(os.name != "posix", reason="Production Unix filesystem boundary")
@pytest.mark.asyncio
async def test_actual_unix_socket_permissions_listener_and_cleanup():
    with tempfile.TemporaryDirectory(prefix="mm-admin-") as directory:
        service = SimpleNamespace(config=Config(Path(directory), runtime_mode="offline", test_mode=True))
        running = await start_admin(service)
        target = socket_path(service.config)
        try:
            assert stat.S_IMODE(target.stat().st_mode) == 0o600
            assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
            async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds=str(target)), base_url="http://local") as client:
                assert (await client.get("/unknown")).status_code == 404
        finally:
            await stop_admin(service, running)
        assert not target.exists()


@pytest.mark.skipif(os.name != "posix", reason="Production Unix filesystem boundary")
def test_cli_never_opens_fifo_symlink_or_hardlink_as_recovery_source(tmp_path):
    target = tmp_path / "fifo"
    os.mkfifo(target)
    with pytest.raises(DomainError):
        with regular_source(target, 10):
            pass
    target.unlink()
    original = tmp_path / "original"
    original.write_bytes(b"abc")
    target.symlink_to(original)
    with pytest.raises(OSError):
        with regular_source(target, 10):
            pass
    target.unlink()
    os.link(original, target)
    with pytest.raises(DomainError):
        with regular_source(target, 10):
            pass
