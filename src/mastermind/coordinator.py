"""Recoverable multi-file transactions. The operation journal is private temporary state."""
import json
import os
import secrets
import shutil
import threading
import time
from contextlib import contextmanager

from .errors import DomainError
from .fs import (
    atomic_json,
    atomic_stream_under,
    atomic_write,
    atomic_write_under,
    directory_inventory,
    file_inventory,
    open_under,
    resolve,
    sha_bytes,
    sha_file,
    sha_under,
    unlink_under,
)
from .locking import FileMutex


class Coordinator:
    def __init__(self, config, state, runtime):
        self.config, self.state, self.runtime = config, state, runtime
        self.directory = config.home / "recovery" / "operations"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.process_lock = FileMutex(config.home / "recovery" / "mutation.lock")
        self.recovery_required = False
        self.fault = lambda point: None
        self.on_native_checkpoint = lambda checkpoint: None
        self.on_paused = lambda: None
        self.on_configuration_change = lambda fields: None

    @contextmanager
    def boundary(self, operation_id=None, *, resume_if=lambda: True):
        operation_id = operation_id or secrets.token_hex(16)
        with self.lock, self.process_lock.acquire():
            if self.recovery_required:
                raise DomainError("RECOVERY_REQUIRED", "An interrupted operation requires recovery.", 503)
            with self.runtime.pause(operation_id, resume_if=lambda: not self.recovery_required and resume_if()) as snapshot:
                if snapshot and snapshot.get("activity"):
                    self.on_native_checkpoint(snapshot["activity"])
                self.on_paused()
                yield operation_id

    def commit(self, changes: dict[str, bytes | None], expected: dict[str, str | None], metadata=None,
               *, inside_boundary=False, operation_id=None):
        metadata = metadata or {}
        operation_id = operation_id or secrets.token_hex(16)
        if not inside_boundary:
            with self.boundary(operation_id):
                return self.commit(changes, expected, metadata, inside_boundary=True, operation_id=operation_id)
        plan = {"id": operation_id, "state": "PREPARED", "changes": [], "metadata": metadata,
                "created_at": time.time()}
        folder = self.directory / operation_id
        folder.mkdir(mode=0o700)
        try:
            for index, (relative, data) in enumerate(changes.items()):
                path = resolve(self.config.vault, relative)
                before = sha_under(self.config.vault, relative)
                if relative not in expected or before != expected[relative]:
                    raise DomainError("CONFLICT", "The note changed; reload before saving.", 409)
                if path.exists() and not path.is_file():
                    raise DomainError("CONFLICT", "The destination is not a regular file.", 409)
                if before is not None:
                    with open_under(self.config.vault, relative) as source, (folder / f"{index}.before").open("wb") as output:
                        shutil.copyfileobj(source, output, 1024*1024)
                    with (folder / f"{index}.before").open("r+b") as stream:
                        os.fsync(stream.fileno())
                if data is not None:
                    atomic_write(folder / f"{index}.after", data)
                plan["changes"].append({"path": relative, "before": before,
                                        "after": sha_bytes(data) if data is not None else None, "index": index})
            atomic_json(folder / "journal.json", plan)
            with self.state.transaction() as db:
                db.execute("INSERT INTO operations VALUES(?,?,?,?)",
                           (operation_id, "PREPARED", plan["created_at"], json.dumps(metadata)))
            self.fault("prepared")
            for item in plan["changes"]:
                path = resolve(self.config.vault, item["path"])
                if sha_under(self.config.vault, item["path"]) != item["before"]:
                    raise DomainError("CONFLICT", "A concurrent writer changed the note.", 409)
                if item["after"] is None:
                    if item["before"] is not None:
                        unlink_under(self.config.vault, item["path"])
                else:
                    data = (folder / f"{item['index']}.after").read_bytes()
                    if sha_bytes(data) != item["after"]:
                        raise DomainError("RECOVERY_REQUIRED", "Operation payload failed integrity.", 503)
                    atomic_write_under(self.config.vault, item["path"], data, create=item["before"] is None)
                self.fault("file:" + str(item["index"]))
            self.finish(plan)
            self.fault("committed")
            plan["state"] = "COMMITTED"
            atomic_json(folder / "journal.json", plan)
            shutil.rmtree(folder)
            return operation_id
        except Exception:
            committed = self.state.one("SELECT state FROM operations WHERE id=?", (operation_id,))
            if committed and committed["state"] == "COMMITTED":
                # Cleanup failure must never roll files back after metadata committed.
                raise
            if (folder / "journal.json").exists():
                try:
                    self.rollback(plan)
                    shutil.rmtree(folder)
                except Exception:  # noqa: BLE001 - keep the original failure and latch the recovery barrier
                    self.recovery_required = True
            else:
                shutil.rmtree(folder)
            raise

    def finish(self, plan):
        from .context_indexing.identity import canonical_change
        with self.state.transaction() as db:
            record = db.execute("SELECT state FROM operations WHERE id=?", (plan["id"],)).fetchone()
            if record and record["state"] == "COMMITTED":
                return
            generation = int(db.execute("SELECT value FROM metadata WHERE key='generation'").fetchone()[0])+1
            db.execute("UPDATE metadata SET value=? WHERE key='generation'", (str(generation),))
            for path in {item["path"] for item in plan["changes"]} | set(plan["metadata"].get("paths", [])):
                db.execute("INSERT INTO outbox VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET "
                           "generation=excluded.generation,occurred_at=excluded.occurred_at",
                           (path, generation, time.time()))
            if db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] > 100_000:
                db.execute("DELETE FROM outbox")
                db.execute("INSERT INTO outbox VALUES('*',?,?)", (generation, time.time()))
            metadata = plan["metadata"]
            configuration_fields = canonical_change(self.state, metadata, plan["changes"])
            for old_path, new_path in metadata.get("moves", []):
                db.execute("UPDATE shares SET path=?,updated_at=? WHERE path=?",
                           (new_path, time.time(), old_path))
                db.execute("UPDATE edit_sessions SET path=? WHERE path=?", (new_path, old_path))
            for a in metadata.get("activities", [metadata["activity"]] if metadata.get("activity") else []):
                db.execute("INSERT OR IGNORE INTO activity VALUES(?,?,?,?,?)",
                           (a["id"], a.get("session_id"), a["kind"], a["path"], a["occurred_at"]))
            if metadata.get("job_id"):
                row = db.execute("SELECT record FROM jobs WHERE id=?", (metadata["job_id"],)).fetchone()
                if row:
                    value = json.loads(row[0])
                    value["committed_path"] = metadata["committed_path"]
                    if metadata.get("committed_sha"):
                        value["committed_sha"] = metadata["committed_sha"]
                    value.setdefault("transitions", []).append({"state": "COMPLETED", "at": time.time()})
                    db.execute("UPDATE jobs SET state='COMPLETED',stage='COMPLETED',progress=100,"
                               "updated_at=?,record=? WHERE id=?",
                               (time.time(), json.dumps(value), metadata["job_id"]))
            db.execute("UPDATE operations SET state='COMMITTED' WHERE id=?", (plan["id"],))
        if configuration_fields:
            self.on_configuration_change(configuration_fields)

    def rollback(self, plan):
        folder = self.directory / plan["id"]
        # Validate the complete rollback before modifying any file.
        for item in plan["changes"]:
            current = sha_under(self.config.vault, item["path"])
            if current not in item.get("accepted", (item["before"], item["after"])):
                raise DomainError("RECOVERY_REQUIRED", "An unknown writer changed recovery data.", 503)
            if item["before"] is not None and current != item["before"]:
                preimage = folder / f"{item['index']}.before"
                if preimage.stat().st_size > self.config.max_backup_bytes or sha_file(preimage) != item["before"]:
                    raise DomainError("RECOVERY_REQUIRED", "Recovery preimage failed integrity.", 503)
        for item in reversed(plan["changes"]):
            if sha_under(self.config.vault, item["path"]) == item["before"]:
                continue
            if item["before"] is None:
                if sha_under(self.config.vault, item["path"]) is not None:
                    unlink_under(self.config.vault, item["path"])
            else:
                with (folder / f"{item['index']}.before").open("rb") as source:
                    atomic_stream_under(self.config.vault, item["path"], source, item["before"], self.config.max_backup_bytes)
        if "directories" in plan:
            before = plan["directories"]
            for relative in sorted(plan["desired_directories"], key=lambda path: (-path.count("/"), path)):
                if relative not in before:
                    directory = resolve(self.config.vault, relative)
                    if directory.exists():
                        try:
                            directory.rmdir()
                        except OSError:
                            raise DomainError("RECOVERY_REQUIRED", "An unknown file prevents directory rollback.", 503) from None
            for relative, mode in sorted(before.items()):
                directory = resolve(self.config.vault, relative)
                directory.mkdir(mode=mode, parents=True, exist_ok=True)
                if os.name == "posix":
                    os.chmod(directory, mode)
        with self.state.transaction() as db:
            db.execute("UPDATE operations SET state='ROLLED_BACK' WHERE id=?", (plan["id"],))

    def validate_native_inventory(self, plan):
        if not plan.get("native"):
            return
        participants = {item["path"] for item in plan["changes"]}
        for relative, digest in plan["allowed"].items():
            if relative not in participants and sha_under(self.config.vault, relative) != digest:
                raise DomainError("RECOVERY_REQUIRED", "An unregistered writer changed a native rename participant.", 503)
        for relative, _ in file_inventory(self.config.vault):
            if (plan.get("all_files") or relative.lower().endswith(".md")) and not any(p.startswith(".") for p in relative.split("/")) \
                    and relative not in plan["allowed"]:
                raise DomainError("RECOVERY_REQUIRED", "An unregistered writer created a note during rename.", 503)
        if "directories" in plan:
            allowed = set(plan["directories"]) | set(plan["desired_directories"])
            current = set()
            for relative, _ in directory_inventory(self.config.vault):
                if any(part.startswith(".") for part in relative.split("/")):
                    continue
                current.add(relative)
                if relative not in allowed:
                    raise DomainError("RECOVERY_REQUIRED", "An unregistered writer created a directory during rename.", 503)
            if not (set(plan["directories"]) & set(plan["desired_directories"])).issubset(current):
                raise DomainError("RECOVERY_REQUIRED", "An unregistered writer removed a directory during rename.", 503)

    def recover(self):
        with self.lock, self.process_lock.acquire(), self.runtime.pause(
            "recovery", resume_if=lambda: not self.recovery_required
        ):
            self.recovery_required = True
            for folder in sorted(self.directory.iterdir()):
                if not folder.is_dir() or folder.is_symlink():
                    continue
                journal = folder / "journal.json"
                if not journal.exists():
                    shutil.rmtree(folder)
                    continue
                plan = json.loads(journal.read_text("utf-8"))
                if plan["id"] != folder.name:
                    self.recovery_required = True
                    raise DomainError("RECOVERY_REQUIRED", "Recovery identity mismatch.", 503)
                self.validate_native_inventory(plan)
                complete = all(sha_under(self.config.vault, item["path"]) == item["after"]
                               for item in plan["changes"])
                if complete and (not plan.get("native") or plan["state"] in ("FINAL_PREPARED", "COMMITTED")):
                    self.finish(plan)
                else:
                    self.rollback(plan)
                shutil.rmtree(folder)
            self.recovery_required = False
