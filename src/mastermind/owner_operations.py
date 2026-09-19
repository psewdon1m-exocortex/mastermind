"""Bounded, durable owner export/restore jobs. Credentials and Vault text are never status data."""
import asyncio
import hashlib
import json
import os
import re
import secrets
import threading
import time

from .backup import checked_json
from .errors import DomainError
from .fs import atomic_write_under, open_under, remove_private_tree, sha_file
from .spool import copy_bounded, private_open

TERMINAL = {"COMPLETED", "FAILED", "INTERRUPTED"}


class OwnerOperations:
    def __init__(self, service):
        self.service = service
        self.directory = service.config.home / "exports" / "owner"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.busy = None
        self.thread = None
        self.leases = {}
        self.receiving = set()
        self.stopping = False
        for folder in self.directory.iterdir():
            record = self.read(folder.name, include_expired=True)
            if record["state"] in {"RUNNING", "RECEIVING"}:
                self.save(record, state="INTERRUPTED", stage="INTERRUPTED", error="OPERATION_INTERRUPTED")
            if record["kind"] != "restore":
                (folder / "download.zip").unlink(missing_ok=True)
                self.save(record, stage="TRANSFER_ENDED", download_consumed=True)
        self.cleanup()

    def read(self, identifier, *, include_expired=False):
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise DomainError("NOT_FOUND", "Operation not found.", 404)
        try:
            with open_under(self.directory, identifier + "/operation.json") as source:
                content = source.read(64*1024+1)
        except FileNotFoundError:
            raise DomainError("NOT_FOUND", "Operation not found.", 404) from None
        if len(content) > 64*1024:
            raise DomainError("NOT_FOUND", "Operation not found.", 404)
        record = checked_json(content)
        if record.get("id") != identifier:
            raise DomainError("RECOVERY_REQUIRED", "Owner operation identity is invalid.", 503)
        if not include_expired and record["expires_at"] <= time.time() and record["state"] not in {"RUNNING", "RECEIVING"}:
            raise DomainError("NOT_FOUND", "The staged operation has expired.", 404)
        return record

    def save(self, record, **values):
        if values.get("state") == "COMPLETED" and record.get("state") != "COMPLETED":
            values["expires_at"] = time.time() + 15*60
        record.update(values, updated_at=time.time())
        atomic_write_under(self.directory, record["id"] + "/operation.json",
                           json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode())
        return self.public(record)

    @staticmethod
    def public(record):
        return {key: value for key, value in record.items() if key in {
            "id", "kind", "state", "stage", "created_at", "updated_at", "expires_at", "error", "inspection",
            "size", "sha256", "result", "filename", "progress", "download_consumed"}}

    def cleanup(self):
        with self.lock:
            for folder in self.directory.iterdir():
                record = self.read(folder.name, include_expired=True)
                if record["expires_at"] <= time.time() and folder.name != self.busy \
                        and folder.name not in self.receiving and not self.leases.get(folder.name):
                    remove_private_tree(folder, self.directory)

    def listing(self):
        with self.lock:
            self.cleanup()
            return sorted((self.public(record) for folder in self.directory.iterdir()
                           if (record := self.read(folder.name, include_expired=True))["expires_at"] > time.time()
                           or record["state"] in {"RUNNING", "RECEIVING"}),
                          key=lambda record: record["created_at"], reverse=True)

    def create(self, kind, size=None):
        self.service.data_ready()
        if kind not in ("backup", "portable", "logs", "restore"):
            raise DomainError("INVALID_OPERATION", "Choose a supported maintenance operation.", 422)
        if kind == "restore" and (type(size) is not int or not 0 < size <= self.service.config.max_backup_bytes):
            raise DomainError("SIZE_LIMIT", "Choose a recovery ZIP of at most 8 GiB.", 413)
        with self.lock:
            self.cleanup()
            if len(list(self.directory.iterdir())) >= 16 or self.busy or self.stopping:
                raise DomainError("OPERATION_BUSY", "Maintenance capacity is busy. Finish or remove an earlier operation.", 429)
            with self.service.backup.spool.lock.acquire(timeout=0):
                reserved = sum(self.read(p.name).get("size", 0) for p in self.directory.iterdir()
                               if self.read(p.name)["state"] in {"WAITING_UPLOAD", "RECEIVING"})
                self.service.backup.spool.reserve(reserved + (size if kind == "restore" else 1024**2))
                identifier, now = secrets.token_hex(16), time.time()
                folder = self.directory / identifier
                folder.mkdir(mode=0o700)
                record = {"id": identifier, "kind": kind, "state": "WAITING_UPLOAD" if kind == "restore" else "RUNNING",
                          "stage": "UPLOAD" if kind == "restore" else "PREPARING", "created_at": now,
                          "expires_at": now+15*60, "progress": 0, **({"size": size} if kind == "restore" else {})}
                self.save(record)
            if kind != "restore":
                self.launch(record)
            return self.public(record)

    def launch(self, record, action=None):
        with self.lock:
            if self.busy or self.stopping:
                raise DomainError("OPERATION_BUSY", "Another maintenance operation is running.", 429)
            self.busy = record["id"]
            self.save(record, state="RUNNING", stage=action or "PREPARING")
            self.thread = threading.Thread(target=self.run, args=(record, action), name="mastermind-owner-operation", daemon=True)
            self.thread.start()

    def run(self, record, action):
        folder = self.directory / record["id"]
        try:
            if record["kind"] in ("backup", "portable"):
                artifact = self.service.exports.prepare("archive" if record["kind"] == "backup" else "portable")
                try:
                    with self.service.backup.spool.lock.acquire(timeout=0):
                        self.service.backup.spool.reserve(artifact["size"])
                        with artifact["path"].open("rb") as source, private_open(folder / "download.zip") as destination:
                            size, digest = copy_bounded(source, destination, self.service.config.max_backup_bytes)
                            destination.flush()
                            os.fsync(destination.fileno())
                    if digest != artifact["sha256"] or size != artifact["size"]:
                        raise DomainError("EXPORT_INTEGRITY", "The prepared download failed its integrity check.", 503)
                finally:
                    self.service.exports.release(artifact["snapshot_id"])
                filename = "mastermind-" + ("backup-" if record["kind"] == "backup" else "vault-") + record["id"][:8]+".zip"
                self.save(record, state="COMPLETED", stage="READY_TO_DOWNLOAD", size=size, sha256=digest,
                          filename=filename, progress=100)
            elif record["kind"] == "logs":
                self.service.audit.export(folder / "download.zip")
                self.save(record, state="COMPLETED", stage="READY_TO_DOWNLOAD", progress=100,
                          size=(folder / "download.zip").stat().st_size, sha256=sha_file(folder / "download.zip"),
                          filename="mastermind-logs-"+time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())+".zip")
            elif action == "INSPECTING":
                inspection = self.service.backup.inspect(folder / "upload.zip")
                self.save(record, state="AWAITING_CONFIRMATION", stage="INSPECTED", inspection=inspection, progress=50)
            elif action == "RESTORING":
                if sha_file(folder / "upload.zip") != record["sha256"]:
                    raise DomainError("RESTORE_INTEGRITY", "The inspected archive changed.", 409)
                result = self.service.restore.apply(folder / "upload.zip")
                self.save(record, state="COMPLETED", stage="RESTORED", result=result, progress=100)
        except Exception as error:  # noqa: BLE001 - persist a sanitized terminal result from the job boundary
            code = error.code if isinstance(error, DomainError) else "OPERATION_FAILED"
            self.save(record, state="FAILED", stage="FAILED", error=code)
        finally:
            if record["state"] in {"FAILED", "INTERRUPTED"} or record["kind"] == "restore" and record["state"] == "COMPLETED":
                for name in ("download.zip", "upload.zip"):
                    (folder / name).unlink(missing_ok=True)
            try:
                self.service.audit.emit("owner."+record["kind"], actor="owner", target=record["id"],
                                        outcome="error" if record["state"] == "FAILED" else "success",
                                        context={"stage": record["stage"], **({"code": record["error"]} if record.get("error") else {})})
            except Exception:  # noqa: BLE001 - audit failure cannot turn a committed restore into a failed restore
                self.service.operation_audit_failure = "AUDIT_UNAVAILABLE"
            with self.lock:
                self.busy = None

    async def receive(self, identifier, stream):
        with self.lock:
            record = self.read(identifier)
            if record["kind"] != "restore" or record["state"] != "WAITING_UPLOAD" or self.receiving:
                raise DomainError("UPLOAD_BUSY", "This recovery upload is not available.", 409)
            self.receiving.add(identifier)
            self.save(record, state="RECEIVING")
        target = self.directory / identifier / "upload.zip"
        async def write_complete(function, *args):
            # Cancellation must not close the file while its thread is still writing.
            task = asyncio.create_task(asyncio.to_thread(function, *args))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise
        try:
            size, digest = 0, hashlib.sha256()
            with private_open(target) as destination:
                async with asyncio.timeout(3600):
                    iterator = stream.__aiter__()
                    while True:
                        try:
                            block = await asyncio.wait_for(anext(iterator), 60)
                        except StopAsyncIteration:
                            break
                        size += len(block)
                        if size > record["size"]:
                            raise DomainError("SIZE_LIMIT", "The archive exceeds its reserved size.", 413)
                        # ASGI chunks are consumed one at a time; no whole-file accumulation.
                        await write_complete(destination.write, block)
                        digest.update(block)
                    if size != record["size"]:
                        raise DomainError("UPLOAD_INCOMPLETE", "The recovery upload ended early.", 422)
                    await write_complete(destination.flush)
                    await write_complete(os.fsync, destination.fileno())
            return self.save(record, state="UPLOADED", stage="READY_TO_INSPECT", sha256=digest.hexdigest(), progress=25)
        except BaseException as error:
            target.unlink(missing_ok=True)
            self.save(record, state="FAILED", stage="FAILED", error="UPLOAD_INCOMPLETE")
            if isinstance(error, TimeoutError):
                raise DomainError("UPLOAD_TIMEOUT", "Recovery upload exceeded its transfer deadline.", 408) from None
            raise
        finally:
            with self.lock:
                self.receiving.discard(identifier)

    def confirm(self, identifier, data):
        self.service.data_ready()
        with self.lock:
            record = self.read(identifier)
            if data.get("sha256") != record.get("sha256") or set(data) != {"action", "sha256"}:
                raise DomainError("RESTORE_CONFLICT", "Confirm the exact inspected recovery archive.", 409)
            if data["action"] == "inspect" and record["state"] == "UPLOADED":
                self.launch(record, "INSPECTING")
            elif data["action"] == "restore" and record["state"] == "AWAITING_CONFIRMATION":
                self.launch(record, "RESTORING")
            else:
                raise DomainError("RESTORE_CONFLICT", "The recovery operation is not ready for this action.", 409)
            return self.public(record)

    def remove(self, identifier):
        with self.lock:
            self.read(identifier)
            if identifier == self.busy or identifier in self.receiving or self.leases.get(identifier):
                raise DomainError("OPERATION_BUSY", "A running operation or download cannot be removed.", 409)
            remove_private_tree(self.directory / identifier, self.directory)
            return {"removed": True}

    def download(self, identifier):
        with self.lock:
            record = self.read(identifier)
            if record["state"] != "COMPLETED" or record["kind"] == "restore" or record.get("download_consumed"):
                raise DomainError("DOWNLOAD_UNAVAILABLE", "This operation has no completed download.", 409)
            if sum(self.leases.values()) >= 4:
                raise DomainError("DOWNLOAD_BUSY", "Download capacity is busy.", 429)
            self.leases[identifier] = self.leases.get(identifier, 0)+1
            return record, self.directory / identifier / "download.zip"

    def release(self, identifier):
        with self.lock:
            self.leases[identifier] = max(0, self.leases.get(identifier, 0)-1)
            if self.leases[identifier] == 0:
                (self.directory / identifier / "download.zip").unlink(missing_ok=True)
                record = self.read(identifier, include_expired=True)
                self.save(record, stage="TRANSFER_ENDED", download_consumed=True)

    def close(self):
        self.stopping = True
        if self.thread:
            # Never close SQLite beneath an active commit. The container's stop
            # deadline may kill the process; durable recovery handles that case.
            self.thread.join()
