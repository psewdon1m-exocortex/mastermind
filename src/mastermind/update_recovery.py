"""Offline update operations. The caller stops all three components first."""
import json
import os
import re
import secrets
import shutil
import time

from . import __version__
from .bridge_artifacts import install_bridge_files
from .errors import DomainError
from .fs import atomic_json, durable_tree, sha_file, sync_dir
from .locking import FileMutex
from .restore import tree_digest
from .state import State


def update_record(config, request_id):
    if not re.fullmatch("[a-f0-9]{32}", request_id):
        raise DomainError("UPDATE_INVALID", "The update request identity is invalid.", 422)
    root = config.home / "recovery/updates"
    active = root / "active.json"
    if not active.is_file() or active.is_symlink() or active.stat().st_size > 65536:
        raise DomainError("RECOVERY_REQUIRED", "The update journal is unavailable.", 503)
    value = json.loads(active.read_text("utf-8"))
    if value["request_id"] != request_id:
        raise DomainError("UPDATE_CONFLICT", "The update journal belongs to another request.", 409)
    return root / request_id, value


def save_record(config, folder, value, **changes):
    value.update(changes, updated_at=time.time())
    atomic_json(folder / "update.json", value)
    atomic_json(config.home / "recovery/updates/active.json", value)


def verify_preimage(folder, value):
    snapshot = folder / "snapshot"
    if tree_digest(snapshot / "vault") != value["preimage_vault_sha256"] \
            or sha_file(snapshot / "snapshot.sqlite3") != value["preimage_db_sha256"]:
        raise DomainError("RECOVERY_REQUIRED", "The retained pre-update generation failed integrity.", 503)
    return snapshot


def migrate(config, request_id, version, schema):
    if schema != 1 or version != __version__:
        raise DomainError("SCHEMA_UNSUPPORTED", "This image cannot migrate to the requested release/schema.", 409)
    with FileMutex(config.home / "recovery/service.lock").acquire(timeout=0), \
            FileMutex(config.home / "recovery/mutation.lock").acquire(timeout=0):
        folder, record = update_record(config, request_id)
        if record["phase"] == "MIGRATED" and record["version"] == version:
            return
        if record["phase"] != "APPLY_REQUESTED" or record["version"] != version:
            raise DomainError("UPDATE_CONFLICT", "Migration has no prepared snapshot barrier.", 409)
        verify_preimage(folder, record)
        if tree_digest(config.vault) != record["preimage_vault_sha256"]:
            raise DomainError("RECOVERY_REQUIRED", "Canonical data changed after the update snapshot.", 503)
        save_record(config, folder, record, phase="MIGRATING")
        state = State(config.state / "mastermind.sqlite3")
        try:
            if state.one("PRAGMA integrity_check") != {"integrity_check": "ok"}:
                raise DomainError("RECOVERY_REQUIRED", "The migration database failed integrity.", 503)
            if config.bridge_artifacts:
                install_bridge_files(config.vault, config.bridge_artifacts)
            durable_tree(config.vault)
        finally:
            state.close()
        save_record(config, folder, record, phase="MIGRATED")


def rollback(config, request_id, archive, *, fault=lambda _: None):
    with FileMutex(config.home / "recovery/service.lock").acquire(timeout=0), \
            FileMutex(config.home / "recovery/mutation.lock").acquire(timeout=0):
        folder, record = update_record(config, request_id)
        if record["previous_version"] != __version__ or record["previous_schema"] != 1:
            raise DomainError("SCHEMA_UNSUPPORTED", "Rollback must use the exact previous Core image.", 409)
        if archive.is_symlink() or not archive.is_file() or archive.stat().st_size != record["size"] or sha_file(archive) != record["sha256"]:
            raise DomainError("UPDATE_INTEGRITY", "The sealed rollback archive failed integrity.", 409)
        snapshot = verify_preimage(folder, record)
        if record["phase"] in {"ROLLBACK_RESTORED", "ROLLED_BACK"} or record.get("rollback_data_restored"):
            return
        if record["phase"] in TERMINAL_PHASES:
            raise DomainError("UPDATE_CONFLICT", "A completed update requires a fresh managed rollback barrier.", 409)
        staged = config.vault.parent / (".update-new-" + request_id)
        previous = config.vault.parent / (".update-old-" + request_id)
        new_db = folder / "rollback.sqlite3"
        database = config.state / "mastermind.sqlite3"
        if record["phase"] != "ROLLBACK_PREPARED":
            if staged.exists() or previous.exists() or new_db.exists():
                raise DomainError("RECOVERY_REQUIRED", "Unjournaled rollback staging needs review.", 503)
            shutil.copytree(snapshot / "vault", staged)
            shutil.copyfile(snapshot / "snapshot.sqlite3", new_db)
            state = State(new_db)
            try:
                with state.transaction() as db:
                    for table in ("sessions", "codes", "uploads", "projections", "edit_sessions"):
                        db.execute(f'DELETE FROM "{table}"')
                    db.execute("UPDATE metadata SET value=? WHERE key='activity_epoch'", (secrets.token_hex(16),))
                    for row in state.rows("SELECT id,record FROM jobs WHERE state NOT IN ('COMPLETED','FAILED','CANCELLED')"):
                        value = json.loads(row["record"])
                        value.pop("source_path", None)
                        value["error"] = {"code": "SOURCE_UNAVAILABLE", "message": "Resubmit the source after rollback."}
                        value["public_error"] = value["error"]
                        value["reserved_bytes"] = 0
                        db.execute("UPDATE jobs SET state='FAILED',stage='FAILED',record=?,leased_by=NULL,lease_expires_at=NULL WHERE id=?",
                                   (json.dumps(value), row["id"]))
            finally:
                state.close()
            durable_tree(staged)
            save_record(config, folder, record, phase="ROLLBACK_PREPARED", rollback_db_sha256=sha_file(new_db),
                        replaced_vault_sha256=tree_digest(config.vault), replaced_db_sha256=sha_file(database))
            fault("prepared")
        if tree_digest(staged) not in (None, record["preimage_vault_sha256"]) or tree_digest(previous) not in (None, record["replaced_vault_sha256"]):
            raise DomainError("RECOVERY_REQUIRED", "Unknown writes changed the rollback generations.", 503)
        current = tree_digest(config.vault)
        if current not in (None, record["preimage_vault_sha256"], record["replaced_vault_sha256"]):
            raise DomainError("RECOVERY_REQUIRED", "Unknown canonical writes prevent rollback.", 503)
        if current != record["preimage_vault_sha256"]:
            if config.vault.exists():
                if previous.exists():
                    raise DomainError("RECOVERY_REQUIRED", "The rollback destination is occupied.", 503)
                os.replace(config.vault, previous)
                sync_dir(config.vault.parent)
                fault("old_vault_moved")
            os.replace(staged, config.vault)
            sync_dir(config.vault.parent)
            fault("vault_restored")
        if sha_file(database) != record["rollback_db_sha256"]:
            if sha_file(database) != record["replaced_db_sha256"] or sha_file(new_db) != record["rollback_db_sha256"]:
                raise DomainError("RECOVERY_REQUIRED", "Unknown database writes prevent rollback.", 503)
            # Preserve even an unsupported new schema and its WAL for explicit repair.
            for suffix in ("", "-wal", "-shm"):
                source = database.with_name(database.name + suffix)
                destination = folder / ("replaced.sqlite3" + suffix)
                if source.exists():
                    if destination.exists():
                        if sha_file(source) != sha_file(destination):
                            raise DomainError("RECOVERY_REQUIRED", "The retained database differs from its rollback source.", 503)
                    else:
                        shutil.copyfile(source, destination)
                    if suffix:
                        source.unlink()
            durable_tree(folder)
            fault("database_retained")
            os.replace(new_db, database)
            sync_dir(database.parent)
            fault("database_restored")
        save_record(config, folder, record, phase="ROLLBACK_RESTORED", rollback_data_restored=True)
        fault("committed")


TERMINAL_PHASES = {"COMPLETED", "ROLLED_BACK", "FAILED"}
