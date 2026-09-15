"""Retained snapshot barrier and restart-safe handoff to the own Updater head."""
import json
import re
import secrets
import threading
import time
from contextlib import ExitStack

import httpx

from . import __version__
from .deadline import check, remaining, snapshot_budget
from .errors import DomainError
from .fs import atomic_json, durable_tree, remove_private_tree, sha_file
from .restore import tree_digest
from .secret_store import read_credential_file

TERMINAL = {"COMPLETED", "ROLLED_BACK", "FAILED"}


class Updater:
    def __init__(self, config):
        self.config = config
        self.client = httpx.Client(base_url="http://updater.local", transport=httpx.HTTPTransport(uds=config.updater_socket),
                                   trust_env=False, follow_redirects=False, timeout=httpx.Timeout(60, connect=5)) \
            if config.updater_socket else None

    def call(self, method, route, *, data=None, source=None, size=None, timeout=60):
        if self.client is None or self.config.updater_token_file is None:
            raise DomainError("UPDATER_UNAVAILABLE", "Updater is not configured.", 503)
        headers = {"X-Updater-Token": read_credential_file(self.config.updater_token_file)}
        if source is not None:
            headers.update({"Content-Length": str(size), "Content-Type": "application/zip"})
        try:
            timeout = remaining(timeout)
            deadline = time.monotonic() + timeout
            with self.client.stream(method, route, headers=headers, json=data if source is None else None,
                                    content=source, timeout=httpx.Timeout(timeout, connect=min(5, timeout),
                                        read=timeout if route.endswith("/preparations") else min(60, timeout), write=min(60, timeout))) as response:
                body = bytearray()
                for block in response.iter_bytes():
                    check()
                    if time.monotonic() > deadline:
                        raise DomainError("UPDATER_TIMEOUT", "Updater exceeded the operation deadline.", 503)
                    if len(body) + len(block) > 1024 * 1024:
                        raise DomainError("UPDATER_PROTOCOL", "Updater metadata exceeded its limit.", 503)
                    body.extend(block)
                check()
                if response.status_code >= 400:
                    raise DomainError("UPDATER_REJECTED", "Updater rejected this operation.", response.status_code)
                return json.loads(body) if body else None
        except (httpx.HTTPError, ValueError):
            raise DomainError("UPDATER_UNAVAILABLE", "Updater did not return a complete response.", 503) from None

    def close(self):
        if self.client:
            self.client.close()


class Updates:
    def __init__(self, service):
        self.service, self.config = service, service.config
        self.directory = self.config.home / "recovery" / "updates"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / "active.json"
        self.lock = threading.RLock()
        self.record = self.read()
        self.thread = None
        self.updater = Updater(self.config)

    def read(self):
        if not self.path.exists():
            return None
        if self.path.is_symlink() or self.path.stat().st_size > 65536:
            raise DomainError("RECOVERY_REQUIRED", "Update journal requires recovery.", 503)
        record = json.loads(self.path.read_text("utf-8"))
        if not re.fullmatch("[a-f0-9]{32}", record.get("request_id", "")):
            raise DomainError("RECOVERY_REQUIRED", "Update journal identity is invalid.", 503)
        return record

    def save(self, **changes):
        with self.lock:
            self.record = {**(self.record or {}), **changes, "updated_at": time.time()}
            atomic_json(self.path, self.record)
            folder = self.directory / self.record["request_id"]
            folder.mkdir(mode=0o700, exist_ok=True)
            atomic_json(folder / "update.json", self.record)

    @property
    def blocks(self):
        return self.record is not None and self.record["phase"] not in TERMINAL | {"PREPARING"}

    def public(self):
        if self.record is None:
            return {"state": "idle"}
        return {key: self.record[key] for key in ("request_id", "phase", "version", "updated_at", "error", "job_id", "operation")
                if key in self.record}

    def discover(self):
        result = self.updater.call("POST", "/v1/releases/check", data={"head_id": self.config.updater_head_id})
        if not isinstance(result, dict) or result.get("installed_version") != __version__ \
                or not isinstance(result.get("available_version"), str) \
                or not re.fullmatch(r"\d+\.\d+\.\d+", result["available_version"]) \
                or type(result.get("update_available")) is not bool:
            raise DomainError("UPDATER_PROTOCOL", "Updater release discovery did not match this installed head.", 503)
        compatible = result.get("profile") == "mastermind" and result.get("compatible") is True \
            and result.get("components") == ["core", "runtime", "worker"]
        return {"installed_version": __version__, "available_version": result["available_version"],
                "update_available": result["update_available"], "compatible": compatible,
                "checked_at": time.time()}

    def rollback_target(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", job_id):
            raise DomainError("UPDATE_INVALID", "Select an own-head completed update.", 422)
        job = self.updater.call("GET", "/v1/jobs/" + job_id)
        if job.get("head_id") != self.config.updater_head_id or job.get("service") != "mastermind" \
                or job.get("state") != "COMPLETED" or job.get("version") != __version__ \
                or job.get("rollback_available") is not True or not job.get("previous_manifest_sha256") \
                or not isinstance(job.get("previous_version"), str) \
                or not re.fullmatch(r"\d+\.\d+\.\d+", job["previous_version"]):
            raise DomainError("ROLLBACK_UNAVAILABLE", "This update has no verified previous version for the installed service.", 409)
        return job

    def rollback_options(self):
        listing = self.updater.call("GET", "/v1/jobs?head_id=" + self.config.updater_head_id)
        jobs = [job for job in listing.get("jobs", []) if job.get("service") == "mastermind" and
                job.get("head_id") == self.config.updater_head_id and job.get("state") == "COMPLETED" and
                job.get("version") == __version__ and job.get("rollback_available") is True and job.get("previous_manifest_sha256")]
        if not jobs:
            return {"available": False}
        job = max(jobs, key=lambda item: item.get("created_at", ""))
        target = self.rollback_target(job["id"])
        return {"available": True, "job_id": job["id"], "version": target["previous_version"], "preserves_current_data": True}

    def submit_rollback(self, job_id):
        target = self.rollback_target(job_id)
        return self.submit(target["previous_version"], rollback_of=job_id)

    def submit(self, version, *, rollback_of=None):
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise DomainError("VERSION_INVALID", "Select an exact stable release version.", 422)
        with self.lock:
            if self.record and self.record["phase"] not in TERMINAL or self.thread and self.thread.is_alive():
                raise DomainError("UPDATE_BUSY", "An update is already pending.", 409)
            self.record = {"request_id": secrets.token_hex(16), "version": version, "phase": "PREPARING", "created_at": time.time(),
                           "operation": "rollback" if rollback_of else "update"}
            if rollback_of:
                self.record["rollback_of"] = rollback_of
            self.save()
            self.thread = threading.Thread(target=self.run, name="mastermind-update", daemon=True)
            self.thread.start()
            return self.public()

    def start(self):
        if not self.record or self.record["phase"] in TERMINAL:
            return
        if self.record["phase"] == "PREPARING":
            self.save(phase="FAILED", error="PREPARATION_INTERRUPTED")
            return
        # Before a sealed handoff, no privileged mutation could have started.
        if self.record["phase"] in {"QUIESCING", "SNAPSHOT", "SPOOLING"}:
            self.save(phase="FAILED", error="HANDOFF_INTERRUPTED")
            return
        self.thread = threading.Thread(target=self.monitor, name="mastermind-update-recovery", daemon=True)
        self.thread.start()

    def run(self):
        request_id, version = self.record["request_id"], self.record["version"]
        root = f"/v1/heads/{self.config.updater_head_id}"
        try:
            preparation = {"request_id": request_id, "version": version}
            if self.record.get("rollback_of"):
                preparation["rollback_of"] = self.record["rollback_of"]
            prepared = self.updater.call("POST", root + "/preparations", data=preparation, timeout=3600)
            if prepared.get("state") != "COMPLETED" or prepared.get("version") != version:
                raise DomainError("UPDATE_INCOMPATIBLE", "Release preparation was not completed.", 409)
            self.save(preparation_id=prepared["id"])
            backup = self.service.backup
            backup.trust_key()
            backup.signing_key()
            backup.secrets.read("recovery_recipient")
            backup.secrets.read("recovery_identity")  # automatic rollback must already be recoverable
            with backup.spool.lock.acquire(timeout=0):
                backup.spool.reserve(backup.estimate() * 8)
                folder = self.directory / request_id
                self.save(phase="QUIESCING")
                with ExitStack() as retained:
                    with snapshot_budget():
                        retained.enter_context(self.service.coordinator.boundary(request_id, resume_if=lambda: self.record["phase"] in
                            TERMINAL | {"QUIESCING", "SNAPSHOT", "SPOOLING"}))
                        spool_id = self.prepare_snapshot(backup, folder, root, request_id)
                    self.save(phase="APPLY_REQUESTED", spool_id=spool_id)
                    # This marker precedes the request: loss of its response must keep writers blocked.
                    try:
                        job = self.updater.call("POST", "/v1/updates", data={"request_id": request_id,
                            "head_id": self.config.updater_head_id, "service": "mastermind", "version": version,
                            "preparation_id": prepared["id"], "backup": {"spool_id": spool_id}})
                        self.save(job_id=job["id"])
                    except DomainError as error:
                        if error.status < 500:
                            self.save(phase="FAILED", error=error.code)
                            raise
                        self.save(error="HANDOFF_RESPONSE_UNCERTAIN")
                    self.monitor(owns_boundary=True)
        except (DomainError, OSError, ValueError, KeyError) as error:
            if self.record["phase"] not in {"APPLY_REQUESTED", "MIGRATED", "FUNCTIONAL_PASSED", "ROLLBACK_PREPARED", "ROLLBACK_RESTORED"}:
                self.save(phase="FAILED", error=error.code if isinstance(error, DomainError) else "UPDATE_PREPARATION_FAILED")
            else:
                self.save(error="UPDATE_RECOVERY_REQUIRED")

    def prepare_snapshot(self, backup, folder, root, request_id):
        self.save(phase="SNAPSHOT")
        snapshot = folder / "snapshot"
        snapshot.mkdir(mode=0o700)
        with self.service.state.lock:
            boundary = backup.snapshot(snapshot, inside_boundary=True)
        durable_tree(snapshot)
        self.save(preimage_vault_sha256=tree_digest(snapshot / "vault"),
                  preimage_db_sha256=sha_file(snapshot / "snapshot.sqlite3"), generation=boundary["generation"],
                  previous_version=__version__, previous_schema=1)
        archive = folder / "mastermind-backup.zip"
        backup.pack(snapshot, boundary, archive)
        size, digest = archive.stat().st_size, sha_file(archive)
        self.save(phase="SPOOLING", size=size, sha256=digest)
        spool = self.updater.call("POST", root + "/backup-spools", data={"request_id": request_id,
            "filename": "mastermind-backup.zip", "size": size, "sha256": digest})
        route = root + "/backup-spools/" + spool["spool_id"]
        def chunks():
            with archive.open("rb") as source:
                check()
                while block := source.read(1024 * 1024):
                    check()
                    yield block
                check()
        self.updater.call("PUT", route + "/content", source=chunks(), size=size, timeout=3600)
        sealed = self.updater.call("POST", route + "/seal")
        if sealed.get("state") != "SEALED" or sealed.get("sha256") != digest or sealed.get("size") != size:
            raise DomainError("UPDATE_INTEGRITY", "Updater did not seal the exact snapshot.", 409)
        check()
        return spool["spool_id"]

    def monitor(self, owns_boundary=False):
        while not self.service.stop_event.wait(1):
            try:
                if self.record.get("job_id"):
                    job = self.updater.call("GET", "/v1/jobs/" + self.record["job_id"])
                else:
                    result = self.updater.call("GET", "/v1/jobs?head_id=" + self.config.updater_head_id)
                    job = next((job for job in result["jobs"] if job["request_id"] == self.record["request_id"]), None)
                    if job is None:
                        if self.record["phase"] == "APPLY_REQUESTED":
                            try:
                                job = self.updater.call("POST", "/v1/updates", data={"request_id": self.record["request_id"],
                                    "head_id": self.config.updater_head_id, "service": "mastermind", "version": self.record["version"],
                                    "preparation_id": self.record["preparation_id"], "backup": {"spool_id": self.record["spool_id"]}})
                                self.save(job_id=job["id"])
                            except DomainError as error:
                                if error.status < 500:
                                    self.save(phase="FAILED", error=error.code)
                                    if not owns_boundary and self.config.runtime_mode != "offline":
                                        self.release_runtime()
                                    return
                        else:
                            self.save(error="APPLY_NOT_CONFIRMED")
                        continue
                    self.save(job_id=job["id"])
                if job.get("head_id") != self.config.updater_head_id or job.get("request_id") != self.record["request_id"]:
                    raise DomainError("UPDATE_INTEGRITY", "Updater job identity mismatch.", 503)
                state = job["state"]
                if state in {"COMPLETED", "ROLLED_BACK"} or state == "FAILED" and not job.get("mutation_started"):
                    self.save(phase=state, error=None)
                    if not owns_boundary and self.config.runtime_mode != "offline":
                        self.release_runtime()
                    return
                if state in {"ROLLBACK_FAILED", "FAILED"}:
                    self.save(error="UPDATE_RECOVERY_REQUIRED")
            except (DomainError, KeyError, ValueError):
                pass  # A dependency outage never implicitly releases the update barrier.

    def release_runtime(self):
        self.service.runtime.request("POST", "/internal/resume", {"operation_id": self.record["request_id"]})
        self.service.runtime.request("POST", "/internal/allow-start", {})

    def cleanup(self, *, now=None):
        now = time.time() if now is None else now
        with self.lock:
            for folder in self.directory.iterdir():
                if not re.fullmatch(r"[a-f0-9]{32}", folder.name):
                    continue
                if folder.is_symlink() or not folder.is_dir():
                    raise DomainError("RECOVERY_REQUIRED", "Update retention found an unexpected private path.", 503)
                journal = folder / "update.json"
                if journal.is_symlink() or not journal.is_file() or journal.stat().st_size > 65536:
                    raise DomainError("RECOVERY_REQUIRED", "Update retention requires a complete journal.", 503)
                record = json.loads(journal.read_text("utf-8"))
                if record.get("request_id") != folder.name:
                    raise DomainError("RECOVERY_REQUIRED", "Update retention journal identity changed.", 503)
                if record.get("phase") in TERMINAL and record.get("updated_at", now) < now - 24 * 3600:
                    remove_private_tree(folder, self.directory)

    def confirm(self, data):
        record = self.record
        if not self.blocks or record["phase"] != "APPLY_REQUESTED" or any(data.get(key) != record.get(key)
            for key in ("request_id", "version", "sha256", "size")):
            raise DomainError("UPDATE_CONFLICT", "The retained snapshot does not match this update.", 409)
        status = self.service.runtime.status()
        if status.get("state") != "stopped" or self.config.runtime_mode != "offline" and not status.get("paused"):
            raise DomainError("VAULT_BUSY", "The native writer barrier is not held.", 423)
        return {"held": True, "request_id": record["request_id"], "schema": 1}

    def close(self):
        # Stop waits only for the current bounded polling request, never for the
        # privileged operation that is itself waiting for this Core to stop.
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.updater.close()
