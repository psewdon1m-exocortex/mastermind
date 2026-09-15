"""Recoverable Vault/SQLite generation switch; recovery runs before normal startup."""
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from dataclasses import replace

from .backup import canonical
from .bridge_artifacts import install_bridge_files
from .coordinator import Coordinator
from .errors import DomainError
from .fs import (
    atomic_json,
    directory_inventory,
    durable_tree,
    file_inventory,
    remove_private_tree,
    sha_file,
    sync_dir,
)
from .runtime_client import RuntimeClient
from .state import MANDATORY_TABLES, State
from .vault import Vault


def tree_digest(directory):
    digest = hashlib.sha256()
    if not directory.is_dir() or directory.is_symlink():
        return None
    for relative, path in file_inventory(directory):
        digest.update(canonical([relative, sha_file(path)]))
    for relative, _ in directory_inventory(directory):
        digest.update(canonical([relative, "directory"]))
    return digest.hexdigest()


def database_digest(path):
    if not path.is_file() or path.is_symlink():
        return None
    digest = hashlib.sha256()
    # Read-only SQLite includes WAL state without executing imported SQL/schema code.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        for table in MANDATORY_TABLES:
            for row in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
                digest.update(canonical([table, dict(row)]))
    return digest.hexdigest()


class Restore:
    def __init__(self, backup, auth):
        self.backup, self.auth = backup, auth
        self.config, self.state, self.coordinator = backup.config, backup.state, backup.coordinator
        self.directory = self.config.home / "recovery" / "restores"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.fault = lambda point: None
        self.active = False
        self.operation_lock = threading.Lock()
        self.on_begin = lambda: None
        self.last_warning = None

    def locations(self, operation_id):
        if not re.fullmatch("[a-f0-9]{32}", operation_id):
            raise DomainError("RECOVERY_REQUIRED", "Restore identity is invalid.", 503)
        folder = self.directory / operation_id
        return folder, self.config.vault.parent / (".old-"+operation_id), \
            self.config.vault.parent / (".new-"+operation_id)

    def prepare(self, tree, folder):
        staged_config = replace(self.config, home=folder / "generation", runtime_mode="offline", test_mode=True)
        staged_config.vault.parent.mkdir(mode=0o700, parents=True)
        shutil.move(tree / "vault", staged_config.vault)
        if self.config.bridge_artifacts:
            install_bridge_files(staged_config.vault, self.config.bridge_artifacts)
        staged_config.state.mkdir(mode=0o700, parents=True)
        database = staged_config.state / "mastermind.sqlite3"
        shutil.move(tree / "restored.sqlite3", database)
        staged = State(database)
        try:
            with staged.transaction() as db:
                db.execute("UPDATE metadata SET value=? WHERE key='activity_epoch'", (secrets.token_hex(16),))
                # Restored tokens remain path-bound. Known later revocations are monotonic.
                for share in self.state.rows("SELECT token_hmac,revoked_at FROM shares WHERE revoked_at IS NOT NULL"):
                    db.execute("UPDATE shares SET revoked_at=CASE WHEN revoked_at IS NULL THEN ? "
                               "ELSE MIN(revoked_at,?) END WHERE token_hmac=?",
                               (share["revoked_at"], share["revoked_at"], share["token_hmac"]))
                for row in staged.rows("SELECT id,record FROM jobs WHERE state NOT IN ('COMPLETED','FAILED','CANCELLED')"):
                    record = json.loads(row["record"])
                    record.pop("source_path", None)
                    record["error"] = {"code": "SOURCE_UNAVAILABLE", "message": "Resubmit the source after restore."}
                    record["public_error"] = record["error"]
                    record["reserved_bytes"] = 0
                    db.execute("UPDATE jobs SET state='FAILED',stage='FAILED',record=?,leased_by=NULL,"
                               "lease_expires_at=NULL,updated_at=? WHERE id=?",
                               (json.dumps(record), time.time(), row["id"]))
            coordinator = Coordinator(staged_config, staged, RuntimeClient(staged_config))
            vault = Vault(staged_config, staged, coordinator)
            vault.index(force=True)
            with staged.transaction() as db:
                old_generation = int(self.state.one("SELECT value FROM metadata WHERE key='generation'")["value"])
                restored_generation = int(staged.one("SELECT value FROM metadata WHERE key='generation'")["value"])
                generation = max(old_generation, restored_generation) + 1
                db.execute("UPDATE metadata SET value=? WHERE key='generation'", (str(generation),))
                db.execute("DELETE FROM outbox")
                db.execute("INSERT INTO outbox VALUES('*',?,?)", (generation, time.time()))
            return staged_config, len(vault.graph()["nodes"])
        finally:
            staged.close()

    def apply(self, source, *, create_safety_backup=True):
        if not self.operation_lock.acquire(blocking=False):
            raise DomainError("VAULT_BUSY", "A restore is already running.", 423)
        self.active = True
        try:
            self.on_begin()
            return self._apply(source, create_safety_backup=create_safety_backup)
        finally:
            self.active = False
            self.operation_lock.release()

    def _apply(self, source, *, create_safety_backup=True):
        self.last_warning = None
        manifest = self.backup.verify_wrapper(source)
        operation_id = secrets.token_hex(16)
        folder, old_vault, new_vault = self.locations(operation_id)
        folder.mkdir(mode=0o700)
        safety = folder / "pre-restore.zip"
        journal = None
        warnings = []
        @contextmanager
        def preserve_committed_outcome():
            try:
                yield
            except Exception:
                if not journal or journal["phase"] != "COMMITTED":
                    raise
                # The verified generation is already durable. A failed Runtime
                # resume requires recovery before further writes, not a claim
                # that the previous Vault is still active.
                self.coordinator.recovery_required = True
                warnings.append("POST_RESTORE_RECOVERY_REQUIRED")
        verification_vault = self.config.vault.parent / (".verify-" + operation_id)
        # A restore retains its write barrier through safety snapshot and generation switch.
        with preserve_committed_outcome(), self.coordinator.boundary(operation_id), self.state.lock:
            if create_safety_backup:
                self.backup.create(safety, inside_boundary=True)
            required = manifest["expanded_bytes"]*4 + source.stat().st_size*2 + self.backup.estimate()*2
            with self.backup.spool.operation(required) as work:
                tree, _ = self.backup.unpack(source, work)
                prepared, note_count = self.prepare(tree, work)
                # Copy to the destination volumes before the journal can reach PREPARED.
                shutil.copytree(prepared.vault, new_vault)
                if self.config.runtime_mode != "offline":
                    # Native startup can modify workspace/plugin files. Verify a private
                    # copy so interrupted verification never invalidates rollback hashes.
                    shutil.copytree(prepared.vault, verification_vault)
                new_db = folder / "new.sqlite3"
                shutil.copyfile(prepared.state / "mastermind.sqlite3", new_db)
                self.state.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                with closing(sqlite3.connect(folder / "old.sqlite3")) as old:
                    self.state.db.backup(old, pages=256)
                durable_tree(new_vault)
                durable_tree(folder)
                journal = {"id": operation_id, "phase": "PREPARED", "created_at": time.time(),
                           "old_vault": tree_digest(self.config.vault), "new_vault": tree_digest(new_vault),
                           "old_db": database_digest(folder / "old.sqlite3"), "new_db": database_digest(new_db),
                           "notes": note_count}
                atomic_json(folder / "journal.json", journal)
                try:
                    self.fault("prepared")
                    self.state.close()
                    os.replace(self.config.vault, old_vault)
                    sync_dir(self.config.vault.parent)
                    self.mark(folder, journal, "OLD_VAULT_MOVED")
                    self.fault("old_vault_moved")
                    os.replace(new_vault, self.config.vault)
                    sync_dir(self.config.vault.parent)
                    self.mark(folder, journal, "NEW_VAULT_MOVED")
                    self.fault("new_vault_moved")
                    os.replace(new_db, self.state.path)
                    sync_dir(self.state.path.parent)
                    self.mark(folder, journal, "NEW_DB_MOVED")
                    self.fault("new_db_moved")
                    self.state.reopen()
                    self.validate(journal)
                    if self.config.runtime_mode != "offline":
                        result = self.coordinator.runtime.request("POST", "/internal/verify-generation",
                            {"operation_id": operation_id, "vault_copy": verification_vault.name})
                        if result.get("verified") is not True:
                            raise DomainError("RUNTIME_UNAVAILABLE", "Runtime rejected the restored generation.", 503)
                        self.validate(journal)
                    self.fault("verified")
                    self.mark(folder, journal, "COMMITTED")
                    self.fault("committed")
                except Exception:
                    if journal["phase"] != "COMMITTED":
                        self.coordinator.recovery_required = True
                        if self.config.runtime_mode != "offline":
                            stopped = self.coordinator.runtime.request("POST", "/internal/quiesce", {"operation_id": operation_id})
                            if stopped.get("state") != "stopped":
                                raise DomainError("VAULT_BUSY", "Writers must stop before restore rollback.", 423)
                        self.rollback(journal)
                        self.coordinator.recovery_required = False
                    raise
                except BaseException:
                    self.coordinator.recovery_required = True
                    raise
            self.auth.revoke()
        try:
            if verification_vault.exists():
                remove_private_tree(verification_vault, verification_vault.parent)
        except (DomainError, OSError):
            warnings.append("RESTORE_CLEANUP_REQUIRED")
        try:
            self.backup.audit.emit("restore.apply", actor="owner", target=operation_id,
                                   context={"notes": note_count, "backup_boundary": manifest["boundary"]})
        except Exception:  # noqa: BLE001 — diagnostics cannot undo an already verified committed generation
            warnings.append("AUDIT_UNAVAILABLE")
        self.last_warning = warnings[0] if warnings else None
        return {"id": operation_id, "state": "COMPLETED", "notes": note_count,
                **({"warnings": warnings} if warnings else {})}

    def mark(self, folder, journal, phase):
        journal["phase"] = phase
        atomic_json(folder / "journal.json", journal)

    def validate(self, journal):
        if tree_digest(self.config.vault) != journal["new_vault"] \
                or database_digest(self.state.path) != journal["new_db"]:
            raise DomainError("RECOVERY_REQUIRED", "Restored generation verification failed.", 503)
        if self.state.one("PRAGMA integrity_check") != {"integrity_check": "ok"}:
            raise DomainError("RECOVERY_REQUIRED", "Restored database integrity failed.", 503)

    def rollback(self, journal):
        folder, old_vault, new_vault = self.locations(journal["id"])
        # Inspect every affected generation before the first rollback mutation.
        if tree_digest(self.config.vault) not in (None, journal["old_vault"], journal["new_vault"]) \
                or tree_digest(old_vault) not in (None, journal["old_vault"]) \
                or tree_digest(new_vault) not in (None, journal["new_vault"]) \
                or database_digest(self.state.path) not in (journal["old_db"], journal["new_db"]) \
                or database_digest(folder / "old.sqlite3") != journal["old_db"]:
            raise DomainError("RECOVERY_REQUIRED", "Unknown changes prevent automatic restore rollback.", 503)
        try:
            self.state.close()
        except sqlite3.ProgrammingError:
            pass  # A crash can happen after closing the previous connection.
        if old_vault.exists():
            if self.config.vault.exists():
                if new_vault.exists():
                    remove_private_tree(new_vault, new_vault.parent)
                os.replace(self.config.vault, new_vault)
            os.replace(old_vault, self.config.vault)
            sync_dir(self.config.vault.parent)
        staged = folder / "rollback.sqlite3"
        shutil.copyfile(folder / "old.sqlite3", staged)
        os.replace(staged, self.state.path)
        sync_dir(self.state.path.parent)
        self.state.reopen()
        self.mark(folder, journal, "ROLLED_BACK")

    def recover(self):
        # Must be called before watcher/indexing/API writers and Runtime start permission.
        with self.coordinator.lock, self.coordinator.process_lock.acquire(), self.coordinator.runtime.pause(
            "restore-recovery", resume_if=lambda: not self.coordinator.recovery_required
        ), self.state.lock:
            self.coordinator.recovery_required = True
            for folder in sorted(self.directory.iterdir()):
                if not folder.is_dir() or folder.is_symlink() or not (folder / "journal.json").is_file():
                    continue
                journal = json.loads((folder / "journal.json").read_text("utf-8"))
                if journal["id"] != folder.name:
                    raise DomainError("RECOVERY_REQUIRED", "Restore journal identity mismatch.", 503)
                if journal["phase"] not in ("COMMITTED", "ROLLED_BACK"):
                    self.rollback(journal)
            self.coordinator.recovery_required = False

    def cleanup(self, *, now=None):
        now = now or time.time()
        for folder in self.directory.iterdir():
            if folder.is_symlink() or not folder.is_dir() or not re.fullmatch("[a-f0-9]{32}", folder.name):
                continue
            file = folder / "journal.json"
            if not file.is_file():
                # A failed preflight contains no live generation; retained safety backups expire after 24 h.
                if folder.stat().st_mtime < now - 86400:
                    _, old, new = self.locations(folder.name)
                    verification = self.config.vault.parent / (".verify-" + folder.name)
                    # No generation switch occurs before journal publication.
                    if old.exists():
                        continue
                    for path in (new, verification):
                        if path.exists():
                            remove_private_tree(path, path.parent)
                    remove_private_tree(folder, self.directory)
                continue
            journal = json.loads(file.read_text("utf-8"))
            if journal["phase"] not in ("COMMITTED", "ROLLED_BACK") or journal["created_at"] >= now - 86400:
                continue
            _, old, new = self.locations(folder.name)
            verification = self.config.vault.parent / (".verify-" + folder.name)
            if tree_digest(old) not in (None, journal["old_vault"]) \
                    or tree_digest(new) not in (None, journal["new_vault"]):
                self.backup.audit.emit("restore.cleanup", outcome="error", target=folder.name,
                                       context={"reason": "retained_generation_changed"})
                continue
            for path in (old, new, verification):
                if path.exists():
                    remove_private_tree(path, path.parent)
            remove_private_tree(folder, self.directory)
