import json
import secrets
import threading
from types import SimpleNamespace

import pytest

from mastermind import __version__
from mastermind.errors import DomainError
from mastermind.fs import atomic_json, atomic_write, sha_file
from mastermind.restore import tree_digest
from mastermind.state import State
from mastermind.update_recovery import migrate, rollback, update_record
from mastermind.updates import Updates


def prepared(recovery):
    backup, _, _ = recovery
    backup.vault.write("root.md", "before update\n", None, create=True)
    request_id = secrets.token_hex(16)
    folder = backup.config.home / "recovery/updates" / request_id
    snapshot = folder / "snapshot"
    snapshot.mkdir(parents=True)
    boundary = backup.snapshot(snapshot)
    archive = folder / "mastermind-backup.zip"
    backup.pack(snapshot, boundary, archive)
    record = {"request_id": request_id, "phase": "APPLY_REQUESTED", "version": __version__,
              "previous_version": __version__, "previous_schema": 1, "size": archive.stat().st_size,
              "sha256": sha_file(archive), "preimage_vault_sha256": tree_digest(snapshot / "vault"),
              "preimage_db_sha256": sha_file(snapshot / "snapshot.sqlite3")}
    atomic_json(folder.parent / "active.json", record)
    atomic_json(folder / "update.json", record)
    backup.state.close()
    canonical = backup.config.state / "mastermind.sqlite3"
    if backup.state.path != canonical:
        backup.state.path.replace(canonical)
        backup.state.path = canonical
    return backup.config, request_id, archive


@pytest.mark.parametrize("point", ["prepared", "old_vault_moved", "vault_restored", "database_retained", "database_restored", "committed"])
def test_update_rollback_recovers_after_each_durable_boundary(recovery, point):
    config, request_id, archive = prepared(recovery)
    atomic_write(config.vault / "root.md", b"new candidate data\n")
    changed = State(config.state / "mastermind.sqlite3")
    changed.set_setting("candidate_only", True)
    changed.close()
    class PowerLoss(BaseException):
        pass
    def fail(current):
        if current == point:
            raise PowerLoss
    with pytest.raises(PowerLoss):
        rollback(config, request_id, archive, fault=fail)
    rollback(config, request_id, archive)
    assert (config.vault / "root.md").read_text() == "before update\n"
    restored = State(config.state / "mastermind.sqlite3")
    try:
        assert restored.setting("candidate_only") is None
        assert restored.rows("SELECT * FROM sessions") == []
    finally:
        restored.close()
    assert update_record(config, request_id)[1]["rollback_data_restored"]


def test_migration_requires_exact_image_and_unchanged_preimage(recovery):
    config, request_id, _ = prepared(recovery)
    with pytest.raises(DomainError):
        migrate(config, request_id, "99.0.0", 1)
    with pytest.raises(DomainError):
        migrate(config, request_id, __version__, 2)
    atomic_write(config.vault / "root.md", b"unexpected writer")
    with pytest.raises(DomainError) as conflict:
        migrate(config, request_id, __version__, 1)
    assert conflict.value.code == "RECOVERY_REQUIRED"


def test_valid_migration_is_idempotent_and_keeps_barrier(recovery):
    config, request_id, _ = prepared(recovery)
    migrate(config, request_id, __version__, 1)
    migrate(config, request_id, __version__, 1)
    assert update_record(config, request_id)[1]["phase"] == "MIGRATED"


def test_update_rollback_rejects_tampering_and_foreign_requests(recovery):
    config, request_id, archive = prepared(recovery)
    with pytest.raises(DomainError):
        rollback(config, secrets.token_hex(16), archive)
    archive.write_bytes(b"corrupt")
    with pytest.raises(DomainError):
        rollback(config, request_id, archive)
    assert (config.vault / "root.md").read_text() == "before update\n"


def test_old_core_rejects_future_schema_before_any_schema_write(tmp_path):
    path = tmp_path / "state.sqlite3"
    state = State(path)
    state.db.execute("UPDATE metadata SET value='999' WHERE key='schema'")
    state.close()
    original = sha_file(path)
    with pytest.raises(DomainError):
        State(path)
    assert sha_file(path) == original


def test_update_restart_does_not_release_an_uncertain_handoff(recovery):
    config, request_id, _ = prepared(recovery)
    service = SimpleNamespace(config=config, stop_event=threading.Event())
    updates = Updates(service)
    assert updates.blocks
    updates.save(error="HANDOFF_RESPONSE_UNCERTAIN")
    restarted = Updates(service)
    assert restarted.blocks and restarted.record["request_id"] == request_id
    assert "preimage_vault_sha256" not in json.dumps(restarted.public())
    restarted.close()
    updates.close()
