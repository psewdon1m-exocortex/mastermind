import io
import secrets
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from mastermind import deadline
from mastermind.errors import DomainError
from mastermind.fs import sha_file, stream_digest
from mastermind.spool import copy_bounded
from mastermind.updates import Updates


@pytest.fixture
def clock(monkeypatch):
    value = [0.0]
    monkeypatch.setattr(deadline, "time", SimpleNamespace(monotonic=lambda: value[0]))
    monkeypatch.setattr("mastermind.updates.time", SimpleNamespace(monotonic=lambda: value[0], time=time.time))
    return value


def test_nested_budget_cannot_extend_pause_and_is_cleared_after_failure(clock):
    with pytest.raises(DomainError, match="pause limit"), deadline.snapshot_budget():
        clock[0] = 110
        with deadline.snapshot_budget():
            clock[0] = 121
            deadline.check()
    assert deadline.remaining(3600) == 3600


@pytest.mark.parametrize("operation", ["copy", "hash"])
def test_large_single_file_checks_deadline_between_chunks(clock, operation):
    class SlowInput(io.BytesIO):
        def read(self, size=-1):
            data = super().read(size)
            clock[0] += 61
            return data
    source = SlowInput(b"x" * (3 * 1024**2))
    target = io.BytesIO()
    with pytest.raises(DomainError) as error, deadline.snapshot_budget():
        if operation == "copy":
            copy_bounded(source, target, 4 * 1024**2)
        else:
            stream_digest(source)
    assert error.value.code == "SNAPSHOT_TIMEOUT"
    assert source.tell() == 2 * 1024**2
    assert len(target.getvalue()) <= 1024**2


def test_snapshot_timeout_resumes_editor_cleans_spool_and_preserves_live_data(recovery, clock, monkeypatch, tmp_path):
    backup, _, _ = recovery
    backup.vault.write("root.md", "unchanged", None, create=True)
    original = sha_file(backup.config.vault / "root.md")
    events = []
    @contextmanager
    def pause(*args, **kwargs):
        events.append("stopped")
        try:
            yield
        finally:
            events.append("resumed")
    monkeypatch.setattr(backup.coordinator.runtime, "pause", pause)
    original_index = backup.vault.index
    def slow_index(**kwargs):
        result = original_index(**kwargs)
        clock[0] = 121
        return result
    monkeypatch.setattr(backup.vault, "index", slow_index)
    destination = tmp_path / "never-offered.zip"
    with pytest.raises(DomainError) as error:
        backup.create(destination)
    assert error.value.code == "SNAPSHOT_TIMEOUT"
    assert events == ["stopped", "resumed"]
    assert not destination.exists() and not list(backup.spool.directory.iterdir())
    assert sha_file(backup.config.vault / "root.md") == original
    monkeypatch.setattr(backup.vault, "index", original_index)
    backup.vault.write("after.md", "writes are available", None, create=True)


@pytest.mark.parametrize("stage", ["snapshot", "pack", "seal"])
def test_update_timeout_never_submits_apply_and_releases_safe_barrier(recovery, clock, monkeypatch, stage):
    backup, _, _ = recovery
    backup.vault.write("root.md", "before update", None, create=True)
    service = SimpleNamespace(config=backup.config, state=backup.state, coordinator=backup.coordinator,
                              backup=backup, stop_event=threading.Event())
    updates = Updates(service)
    updates.record = {"request_id": secrets.token_hex(16), "version": "0.0.9", "phase": "PREPARING"}
    updates.save()
    calls, resumed = [], []
    @contextmanager
    def pause(operation_id, resume_if):
        try:
            yield
        finally:
            resumed.append(resume_if())
    monkeypatch.setattr(backup.coordinator.runtime, "pause", pause)
    def call(method, route, **kwargs):
        calls.append((method, route))
        if route.endswith("/preparations"):
            return {"state": "COMPLETED", "version": "0.0.9", "id": "prepared"}
        if route.endswith("/backup-spools"):
            return {"spool_id": "owned"}
        if route.endswith("/content"):
            for _ in kwargs["source"]:
                pass
            return {}
        if route.endswith("/seal"):
            clock[0] = 121
            return {"state": "SEALED", "size": updates.record["size"], "sha256": updates.record["sha256"]}
        raise AssertionError("Unexpected privileged request")
    monkeypatch.setattr(updates.updater, "call", call)
    if stage in {"snapshot", "pack"}:
        original = getattr(backup, stage)
        def expire(*args, **kwargs):
            result = original(*args, **kwargs)
            clock[0] = 121
            return result
        monkeypatch.setattr(backup, stage, expire)
    try:
        updates.run()
        assert updates.record["phase"] == "FAILED"
        assert updates.record["error"] == "SNAPSHOT_TIMEOUT"
        assert not updates.blocks and resumed == [True]
        assert not any(route == "/v1/updates" for _, route in calls)
        assert (backup.config.vault / "root.md").read_text("utf-8") == "before update"
    finally:
        updates.close()
