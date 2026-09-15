"""Consistent snapshot coalescing and leased, complete agent artifacts."""
import secrets
import threading
import time
import zipfile

from .errors import DomainError
from .fs import directory_inventory, file_inventory, remove_private_tree, sha_file
from .spool import private_open


class Exports:
    def __init__(self, backup, dirty=None):
        self.backup, self.dirty = backup, dirty
        self.directory = backup.config.home / "exports" / "snapshots"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.entries = {}
        self.current = None

    def reset(self):
        # Called only by the elected Core leader before serving requests. Old clients died with the old Core.
        with self.lock:
            for path in self.directory.iterdir():
                if len(path.name) != 32 or any(c not in "0123456789abcdef" for c in path.name):
                    raise DomainError("RECOVERY_REQUIRED", "An unrecognized export staging entry needs review.", 503)
                remove_private_tree(path, self.directory)
            self.entries.clear()
            self.current = None

    def prune(self):
        with self.lock:
            for identifier, entry in list(self.entries.items()):
                if entry["leases"] == 0:
                    remove_private_tree(self.directory / identifier, self.directory)
                    del self.entries[identifier]
                    if self.current == identifier:
                        self.current = None

    def prepare(self, kind):
        if kind not in ("archive", "mirror", "portable"):
            raise DomainError("EXPORT_INVALID", "The export purpose is invalid.", 422)
        with self.lock:
            self.prune()
            if sum(entry["leases"] for entry in self.entries.values()) >= 4:
                raise DomainError("EXPORT_BUSY", "Export transfer capacity is busy.", 429)
            if kind == "archive":
                self.backup.trust_key()
                self.backup.signing_key()
                self.backup.secrets.read("recovery_recipient")
            # Dirty intents are independent of the main database and close the debounce reuse window.
            generation = int(self.backup.state.one("SELECT value FROM metadata WHERE key='generation'")["value"])
            entry = self.entries.get(self.current)
            if entry and (entry["boundary"]["generation"] != generation
                          or entry["changes"] != self.backup.state.db.total_changes
                          or self.dirty and self.dirty.pending()):
                entry = None
            if entry and kind in entry["artifacts"]:
                entry["leases"] += 1
                return {"snapshot_id": entry["id"], **entry["artifacts"][kind]}
            required = self.backup.estimate() * (5 if kind == "archive" else 3)
            with self.backup.spool.lock.acquire(timeout=0):
                self.backup.spool.reserve(required)
                if entry is None:
                    identifier = secrets.token_hex(16)
                    folder = self.directory / identifier
                    folder.mkdir(mode=0o700)
                    try:
                        with self.backup.coordinator.boundary(), self.backup.state.lock:
                            boundary = self.backup.snapshot(folder, inside_boundary=True)
                            changes = self.backup.state.db.total_changes
                    except BaseException:
                        remove_private_tree(folder, self.directory)
                        raise
                    entry = {"id": identifier, "created": time.monotonic(), "boundary": boundary,
                             "leases": 0, "artifacts": {}, "changes": changes}
                    self.entries[identifier] = entry
                    self.current = identifier
                identifier = entry["id"]
                if kind not in entry["artifacts"]:
                    folder = self.directory / identifier
                    destination = folder / (kind + ".zip")
                    try:
                        if kind == "archive":
                            self.backup.pack(folder, entry["boundary"], destination)
                        elif kind == "portable":
                            from .portable import pack
                            pack(folder, entry["boundary"], destination, self.backup.config)
                        else:
                            with private_open(destination) as raw, zipfile.ZipFile(raw, "w", zipfile.ZIP_STORED) as archive:
                                for relative, path in directory_inventory(folder / "vault"):
                                    archive.write(path, relative + "/")
                                for relative, path in file_inventory(folder / "vault"):
                                    archive.write(path, relative)
                        size = destination.stat().st_size
                        if size > self.backup.config.max_backup_bytes:
                            raise DomainError("SIZE_LIMIT", "The completed export exceeds its limit.", 413)
                        artifact = {"path": destination, "size": size, "sha256": sha_file(destination), **entry["boundary"]}
                        entry["artifacts"][kind] = artifact
                        # Bounded durable receipts survive a Core restart after a remote commit.
                        with self.backup.state.transaction():
                            before = self.backup.state.db.total_changes
                            recent = self.backup.state.setting("agent_export_receipts", [])
                            recent = [record for record in recent if record["created_at"] > time.time() - 30 * 86400]
                            recent.append({"kind": kind, "generation": artifact["generation"], "size": size,
                                           "sha256": artifact["sha256"], "created_at": time.time()})
                            self.backup.state.set_setting("agent_export_receipts", recent[-10_000:])
                            entry["changes"] += self.backup.state.db.total_changes - before
                    except BaseException:
                        # Existing leases can finish. The incomplete snapshot will not be reused.
                        self.current = None
                        self.prune()
                        raise
            entry["leases"] += 1
            self.prune()
            return {"snapshot_id": identifier, **entry["artifacts"][kind]}

    def release(self, identifier):
        with self.lock:
            entry = self.entries.get(identifier)
            if entry:
                entry["leases"] = max(0, entry["leases"] - 1)
            self.prune()

    def receipt(self, kind, data):
        if kind not in ("archive", "mirror") or not isinstance(data, dict) or set(data) != {"generation", "sha256", "size"}:
            raise DomainError("RECEIPT_INVALID", "The export receipt is invalid.", 422)
        if type(data["generation"]) is not int or data["generation"] < 0 or type(data["size"]) is not int \
                or not 0 < data["size"] <= self.backup.config.max_backup_bytes or not isinstance(data["sha256"], str):
            raise DomainError("RECEIPT_INVALID", "The export receipt is invalid.", 422)
        with self.backup.state.transaction():
            known = self.backup.state.setting("agent_export_receipts", [])
            if not any(record["kind"] == kind and all(record[key] == data[key] for key in data) for record in known):
                raise DomainError("RECEIPT_INVALID", "The receipt does not match a completed export.", 409)
            previous = self.backup.state.setting(kind + "_verified_generation", -1)
            self.backup.state.set_setting(kind + "_verified_generation", max(previous, data["generation"]))
            self.backup.state.set_setting(kind + "_last_success_at", time.time())
            confirmed = min(self.backup.state.setting(pipeline+"_verified_generation", -1)
                            for pipeline in ("archive", "mirror"))
            self.backup.state.db.execute("DELETE FROM outbox WHERE generation<=?", (confirmed,))
        return {"accepted": True, "generation": data["generation"]}
