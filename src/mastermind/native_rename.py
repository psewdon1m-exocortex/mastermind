"""Obsidian owns native link propagation; every participating write has a durable intent."""
import hashlib
import json
import secrets
import shutil
import threading
import time
from pathlib import Path, PurePosixPath

from .errors import DomainError
from .fs import (
    atomic_json,
    atomic_stream_under,
    atomic_write,
    atomic_write_under,
    directory_inventory,
    file_inventory,
    name_key,
    open_under,
    resolve,
    sha_bytes,
    sha_under,
)
from .references import parse
from .spool import Spool


class NativeRename:
    def __init__(self, vault):
        self.vault = vault
        self.coordinator, self.state = vault.coordinator, vault.state
        self.runtime = self.coordinator.runtime
        # Bridge write-intent callbacks must not acquire the mutation lock held by rename().
        self.intent_lock = threading.RLock()
        self.active = None
        self.deadline = None
        self.fault = lambda point: None

    def version(self, relative):
        root = self.vault.config.vault
        path = resolve(root, relative)
        if path.is_file():
            return {"kind": "file", "sha256": sha_under(root, relative)}
        if not path.is_dir():
            raise DomainError("NOT_FOUND", "Source path not found.", 404)
        digest = hashlib.sha256(b"mastermind-directory/v1\0")
        for child, _ in directory_inventory(path):
            resolve(root, relative + "/" + child)
            digest.update(b"d\0" + child.encode() + b"\0")
        for child, _ in file_inventory(path):
            resolve(root, relative + "/" + child)
            digest.update(b"f\0" + child.encode() + b"\0" + sha_under(root, relative + "/" + child).encode() + b"\0")
        return {"kind": "directory", "sha256": digest.hexdigest()}

    def intent(self, envelope):
        with self.intent_lock:
            plan = self.active
            if not plan or envelope.get("operation_id") != plan["id"]:
                raise DomainError("INVALID_OPERATION", "No matching native operation is active.", 409)
            if "move" in envelope:
                if envelope["move"] != plan["root_move"] or set(envelope) != {"operation_id", "move"}:
                    raise DomainError("INVALID_OPERATION", "The native move is outside its plan.", 409)
                changes, expected = {}, {}
                for old, new in plan["file_moves"]:
                    changes[old], changes[new] = None, resolve(self.vault.config.vault, old)
                    expected[old], expected[new] = plan["allowed"][old], None
                self._append(plan, changes, expected)
                plan["move_seen"] = True
                atomic_json(self.coordinator.directory / plan["id"] / "journal.json", plan)
                self.fault("intent")
                return {"prepared": True}
            writes = envelope.get("writes")
            expected = envelope.get("expected")
            if not isinstance(writes, list) or not 1 <= len(writes) <= 2 or not isinstance(expected, dict):
                raise DomainError("INVALID_OPERATION", "Native write intent is invalid.", 422)
            changes = {}
            for write in writes:
                if not isinstance(write, dict):
                    raise DomainError("INVALID_OPERATION", "Native write intent is invalid.", 422)
                relative = write.get("path")
                resolve(self.vault.config.vault, relative)
                if relative not in plan["allowed"] or relative in changes:
                    raise DomainError("INVALID_OPERATION", "The write is outside the rename plan.", 409)
                text = write.get("text")
                if text is None and write.get("remove") is True:
                    changes[relative] = None
                elif isinstance(text, str) and len(text.encode("utf-8")) <= self.vault.config.max_note_bytes:
                    changes[relative] = text.encode("utf-8")
                else:
                    raise DomainError("INVALID_OPERATION", "Native note data is invalid.", 422)
            self._append(plan, changes, expected)
            self.fault("intent")
            return {"prepared": True}

    def _append(self, plan, changes, expected):
        folder = self.coordinator.directory / plan["id"]
        indexed = {item["path"]: item for item in plan["changes"]}
        for relative, data in changes.items():
            if self.deadline is not None and time.monotonic() > self.deadline:
                raise DomainError("VAULT_BUSY", "The native operation exceeded its pause deadline.", 423)
            resolve(self.vault.config.vault, relative)
            current = sha_under(self.vault.config.vault, relative)
            known = indexed[relative]["after"] if relative in indexed else plan["allowed"][relative]
            if relative not in expected or current != expected[relative] or current != known:
                raise DomainError("CONFLICT", "A concurrent writer changed a rename participant.", 409)
            item = indexed.get(relative)
            if item is None:
                item = {"path": relative, "before": current, "after": current,
                        "accepted": [current], "index": len(plan["changes"])}
                if current is not None:
                    with open_under(self.vault.config.vault, relative) as source:
                        atomic_stream_under(folder, f"{item['index']}.before", source, current,
                                            self.vault.config.max_backup_bytes, deadline=self.deadline)
                plan["changes"].append(item)
                indexed[relative] = item
            digest = sha_bytes(data) if isinstance(data, bytes) else sha_under(self.vault.config.vault,
                data.relative_to(self.vault.config.vault).as_posix()) if isinstance(data, Path) else None
            if isinstance(data, Path):
                with open_under(self.vault.config.vault, data.relative_to(self.vault.config.vault).as_posix()) as source:
                    atomic_stream_under(folder, f"{item['index']}.after", source, digest,
                                        self.vault.config.max_backup_bytes, deadline=self.deadline)
            elif data is not None:
                atomic_write(folder / f"{item['index']}.after", data)
            item["after"] = digest
            if digest not in item["accepted"]:
                item["accepted"].append(digest)
        atomic_json(folder / "journal.json", plan)

    def rename(self, old_path, new_path, expected):
        if self.vault.config.runtime_mode == "offline":
            raise DomainError("RUNTIME_UNAVAILABLE", "Rename requires the official Obsidian Runtime.", 503)
        if expected is None:
            raise DomainError("PRECONDITION_REQUIRED", "An expected content digest is required.", 428)
        if old_path == new_path:
            raise DomainError("INVALID_OPERATION", "The destination must differ from the source.", 422)
        operation_id = secrets.token_hex(16)
        folder = self.coordinator.directory / operation_id
        with self.coordinator.lock, self.coordinator.process_lock.acquire():
            if self.coordinator.recovery_required:
                raise DomainError("RECOVERY_REQUIRED", "Canonical data requires recovery.", 503)
            resolve(self.vault.config.vault, old_path)
            resolve(self.vault.config.vault, new_path)
            paused, plan = False, None
            try:
                checkpoint = self.runtime.prepare_native(operation_id)
                paused = True
                self.deadline = time.monotonic() + 120
                if checkpoint.get("activity"):
                    self.coordinator.on_native_checkpoint(checkpoint["activity"])
                self.coordinator.on_paused()
                self.vault.index(force=True)
                source_version = self.version(old_path)
                is_directory = source_version["kind"] == "directory"
                if old_path.startswith(new_path + "/") or new_path.startswith(old_path + "/"):
                    raise DomainError("INVALID_OPERATION", "A directory cannot be moved into itself or its ancestor.", 422)
                if not is_directory and old_path.lower().endswith(".md"):
                    self.vault.validate_destination(new_path, exclude=(old_path,))
                elif not is_directory and new_path.lower().endswith(".md"):
                    raise DomainError("INVALID_OPERATION", "An attachment cannot become a Markdown note by renaming.", 422)
                if source_version["sha256"] != expected:
                    raise DomainError("CONFLICT", "The source changed; reload before renaming.", 409)
                if resolve(self.vault.config.vault, new_path).exists():
                    raise DomainError("CONFLICT", "The rename destination already exists.", 409)
                old_name, new_name = PurePosixPath(old_path).stem, PurePosixPath(new_path).stem
                current = {row["name_key"]: row["name"] for row in self.state.rows("SELECT * FROM notes")}
                history = [r["display"] for r in self.state.rows(
                    "SELECT display FROM reference_history WHERE kind='internal'")]
                allowed = {relative: sha_under(self.vault.config.vault, relative)
                    for relative, _ in file_inventory(self.vault.config.vault)
                    if not any(part.startswith(".") for part in relative.split("/"))}
                file_moves = [[relative, new_path + relative[len(old_path):]] for relative in allowed
                              if relative == old_path or is_directory and relative.startswith(old_path + "/")]
                if not is_directory and old_path not in allowed:
                    raise DomainError("NOT_FOUND", "Source note not found.", 404)
                moving = {source for source, _ in file_moves}
                remaining_names = {name_key(relative) for relative in allowed if relative not in moving}
                for _, destination in file_moves:
                    resolve(self.vault.config.vault, destination)
                    if name_key(destination) in remaining_names:
                        raise DomainError("CONFLICT", "The destination has a case or Unicode path collision.", 409)
                allowed.update({destination: None for _, destination in file_moves})
                directories = {relative: path.stat().st_mode & 0o777 for relative, path in directory_inventory(self.vault.config.vault)
                               if not any(part.startswith(".") for part in relative.split("/"))}
                desired = {new_path + relative[len(old_path):] if is_directory and (relative == old_path or relative.startswith(old_path + "/"))
                           else relative for relative in directories}
                parent = PurePosixPath(new_path if is_directory else new_path.rpartition("/")[0])
                while str(parent) != ".":
                    desired.add(str(parent))
                    parent = parent.parent
                plan = {"id": operation_id, "state": "NATIVE_PREPARED", "native": True, "all_files": True, "changes": [],
                        "root_move": [old_path, new_path], "file_moves": file_moves,
                        "directories": directories, "desired_directories": sorted(desired),
                        "allowed": allowed, "created_at": time.time(), "metadata": {
                            "moves": file_moves, "paths": [old_path, new_path], "activities": []}}
                kinds = (["RENAME"] if old_name != new_name and not is_directory else []) + (
                    ["MOVE"] if PurePosixPath(old_path).parent != PurePosixPath(new_path).parent else [])
                plan["metadata"]["activities"] = [{"id": operation_id+"-"+str(index)+"-"+kind, "kind": kind,
                    "path": destination, "occurred_at": time.time()} for index, (source, destination) in enumerate(file_moves)
                    if source.lower().endswith(".md") for kind in (["MOVE"] if is_directory else kinds)]
                total = sum(path.stat().st_size for relative, path in file_inventory(self.vault.config.vault) if relative in allowed)
                if total > self.vault.config.max_expanded_bytes or len(allowed) > self.vault.config.max_archive_entries:
                    raise DomainError("SIZE_LIMIT", "Rename recovery inventory exceeds its limit.", 413)
                Spool(self.vault.config).reserve(total*3 + 16*1024**2)
                folder.mkdir(mode=0o700)
                # A bounded preflight copy also preserves evidence if an unsupported
                # plugin bypasses the adapter and writes directly to the filesystem.
                baseline = folder / "baseline"
                baseline.mkdir(mode=0o700)
                baseline_bytes = 0
                plan["baseline"] = {}
                for index, (relative, digest) in enumerate(allowed.items()):
                    if digest is None:
                        continue
                    path = resolve(self.vault.config.vault, relative)
                    baseline_bytes += path.stat().st_size
                    if baseline_bytes > self.vault.config.max_expanded_bytes \
                            or shutil.disk_usage(folder).free < path.stat().st_size+64*1024**2:
                        raise DomainError("SPOOL_FULL", "Rename recovery storage is exhausted.", 507)
                    with open_under(self.vault.config.vault, relative) as source:
                        atomic_stream_under(baseline, str(index), source, digest,
                                            self.vault.config.max_backup_bytes, deadline=self.deadline)
                    plan["baseline"][relative] = str(index)
                atomic_json(folder / "journal.json", plan)
                with self.state.transaction() as db:
                    db.execute("INSERT INTO operations VALUES(?,?,?,?)", (operation_id, "PREPARED",
                               plan["created_at"], json.dumps(plan["metadata"])))
                self.active = plan
                self.fault("prepared")
                self.runtime.native_rename(old_path, new_path, operation_id)
                checkpoint = self.runtime.request("POST", "/internal/quiesce", {"operation_id": operation_id})
                if checkpoint.get("state") != "stopped":
                    raise DomainError("VAULT_BUSY", "Native writers did not stop.", 423)
                if checkpoint.get("activity"):
                    self.coordinator.on_native_checkpoint(checkpoint["activity"])
                self.fault("native_stopped")
                with self.intent_lock:
                    self.active = None
                    if not (plan["changes"] or is_directory and plan.get("move_seen")) or any(sha_under(self.vault.config.vault, item["path"])
                                                  != item["after"] for item in plan["changes"]):
                        raise DomainError("RECOVERY_REQUIRED", "Native rename differs from its write intents.", 503)
                    self.coordinator.validate_native_inventory(plan)
                    if resolve(self.vault.config.vault, old_path).exists() \
                            or not resolve(self.vault.config.vault, new_path).exists():
                        raise DomainError("RECOVERY_REQUIRED", "Native rename did not reach its destination.", 503)
                    patches, expected_patches = {}, {}
                    for relative, _ in (self.vault.files() if not is_directory and old_path.lower().endswith(".md") else []):
                        text = self.vault.read(relative)
                        refs = [ref for ref in parse(text, current, history) if ref.kind == "internal"
                                and ref.target == name_key(old_name) and text[ref.start] == "@"]
                        if refs and old_name != new_name:
                            modified = text
                            for ref in reversed(refs):
                                modified = modified[:ref.start] + "@" + new_name + modified[ref.end:]
                            patches[relative] = modified.encode("utf-8")
                            expected_patches[relative] = sha_bytes(text.encode("utf-8"))
                    self._append(plan, patches, expected_patches)
                    plan["state"] = "FINAL_PREPARED"
                    atomic_json(folder / "journal.json", plan)
                    self.fault("final_prepared")
                    for relative, data in patches.items():
                        if sha_under(self.vault.config.vault, relative) != expected_patches[relative]:
                            raise DomainError("CONFLICT", "A writer changed a final rename participant.", 409)
                        atomic_write_under(self.vault.config.vault, relative, data)
                        self.fault("patch:" + relative)
                    self.coordinator.finish(plan)
                    plan["state"] = "COMMITTED"
                    atomic_json(folder / "journal.json", plan)
                self.vault.index(force=True)
                shutil.rmtree(folder)
                return {"path": new_path, "sha256": self.version(new_path)["sha256"],
                        "operation_id": operation_id}
            except Exception:
                if plan is not None and (folder / "journal.json").exists():
                    with self.intent_lock:
                        self.active = None
                    try:
                        checkpoint = self.runtime.request("POST", "/internal/quiesce", {"operation_id": operation_id})
                        if checkpoint.get("state") != "stopped":
                            raise DomainError("VAULT_BUSY", "Native writers did not stop.", 423)
                        record = self.state.one("SELECT state FROM operations WHERE id=?", (operation_id,))
                        if not record or record["state"] != "COMMITTED":
                            self.coordinator.validate_native_inventory(plan)
                            self.coordinator.rollback(plan)
                        self.vault.index(force=True)
                        shutil.rmtree(folder)
                    except Exception:  # noqa: BLE001 - preserve all recovery evidence on uncertainty
                        self.coordinator.recovery_required = True
                elif folder.exists():
                    shutil.rmtree(folder)
                raise
            except BaseException:
                self.coordinator.recovery_required = True
                raise
            finally:
                self.active = None
                self.deadline = None
                if paused and not self.coordinator.recovery_required:
                    self.runtime.release_pause(operation_id, native=True)
