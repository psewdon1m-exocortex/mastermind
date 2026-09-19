import json
import secrets
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from mastermind import __version__
from mastermind.errors import DomainError
from mastermind.fs import atomic_json, atomic_write, remove_private_tree, sha_file
from mastermind.restore import database_digest, tree_digest
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
              "previous_version": __version__, "previous_schema": 2, "size": archive.stat().st_size,
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
@pytest.mark.parametrize("saved_copy", [False, True])
def test_update_rollback_recovers_after_each_durable_boundary(recovery, point, saved_copy):
    config, request_id, archive = prepared(recovery)
    if saved_copy:
        config = replace(config, secret_directory=recovery[0].secrets.directory)
        folder, record = update_record(config, request_id)
        record.update(saved_copy_protocol=2, preimage_db_logical_sha256=database_digest(folder / "snapshot/snapshot.sqlite3"))
        atomic_json(folder / "update.json", record)
        atomic_json(folder.parent / "active.json", record)
        remove_private_tree(folder / "snapshot", folder)
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
    if saved_copy:
        assert not (archive.parent / "snapshot").exists()
        assert not (archive.parent / "unpack").exists()


def test_migration_requires_exact_image_and_unchanged_preimage(recovery):
    config, request_id, _ = prepared(recovery)
    with pytest.raises(DomainError):
        migrate(config, request_id, "99.0.0", 1)
    with pytest.raises(DomainError):
        migrate(config, request_id, __version__, 3)
    atomic_write(config.vault / "root.md", b"unexpected writer")
    with pytest.raises(DomainError) as conflict:
        migrate(config, request_id, __version__, 2)
    assert conflict.value.code == "RECOVERY_REQUIRED"


def test_valid_migration_is_idempotent_and_keeps_barrier(recovery):
    config, request_id, _ = prepared(recovery)
    migrate(config, request_id, __version__, 2)
    migrate(config, request_id, __version__, 2)
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


def test_version_rollback_only_selects_verified_current_own_head_update(service):
    config, _, _, _ = service
    context = SimpleNamespace(config=config, stop_event=threading.Event())
    updates = Updates(context)
    job = {"id": "spool-owned", "service": "mastermind", "head_id": config.updater_head_id,
           "state": "COMPLETED", "version": __version__, "previous_version": "0.0.0", "rollback_available": True,
           "previous_manifest_sha256": "b" * 64, "created_at": "2026-09-15T09:00:00Z"}
    calls = []
    def call(method, route):
        calls.append((method, route))
        return {"jobs": [job, {**job, "id": "foreign", "head_id": "foreign", "created_at": "2099"}]} if "?" in route else job
    updates.updater.call = call
    submitted = []
    updates.submit = lambda version, **kwargs: submitted.append((version, kwargs))
    try:
        assert updates.rollback_options() == {"available": True, "job_id": "spool-owned", "version": "0.0.0", "preserves_current_data": True}
        updates.submit_rollback("spool-owned")
        assert submitted == [("0.0.0", {"rollback_of": "spool-owned"})]
        for key, invalid in (("head_id", "foreign"), ("state", "FAILED"), ("version", "99.0.0"), ("previous_manifest_sha256", ""), ("rollback_available", False)):
            old, job[key] = job[key], invalid
            with pytest.raises(DomainError):
                updates.submit_rollback("spool-owned")
            job[key] = old
        with pytest.raises(DomainError):
            updates.submit_rollback("../foreign")
        assert len(submitted) == 1 and all("../" not in route for _, route in calls)
    finally:
        updates.close()


def test_update_cleanup_removes_terminal_preimages_immediately_but_preserves_unresolved_recovery(service):
    config, _, _, _ = service
    updates = Updates(SimpleNamespace(config=config, stop_event=threading.Event()))
    now = 1000000
    try:
        for index, (phase, age) in enumerate((("COMPLETED", 90000), ("ROLLED_BACK", 90000), ("FAILED", 90000),
                                             ("COMPLETED", 10), ("APPLY_REQUESTED", 90000), ("ROLLBACK_FAILED", 90000))):
            identifier = f"{index:032x}"
            folder = updates.directory / identifier
            folder.mkdir()
            (folder / "retained-bytes").write_bytes(b"synthetic recovery preimage")
            atomic_json(folder / "update.json", {"request_id": identifier, "phase": phase, "updated_at": now - age})
        (updates.directory / "operator-unmanaged.txt").write_text("preserve")
        updates.cleanup(now=now)
        assert {path.name for path in updates.directory.iterdir()} == {f"{index:032x}" for index in (4, 5)} | {"operator-unmanaged.txt"}
    finally:
        updates.close()
