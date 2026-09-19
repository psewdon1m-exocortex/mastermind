"""Own-head Neptune initialization through the host Updater; setup codes stay in memory."""
import asyncio
import re
import secrets
import threading
import time
from uuid import UUID

from .backup import checked_json
from .errors import DomainError
from .fs import atomic_json, open_under

STATES = {"REQUESTED", "INSTALLING", "ENROLLING", "COMPLETED", "FAILED"}


def complete_profile(result):
    project = result.get("project", {})
    mirror, reader = project.get("mirror") or {}, project.get("reader") or {}
    return result.get("product") == "neptune-linux" and project.get("projectId") == "mastermind" \
        and type(project.get("enabled")) is bool and mirror.get("root") == "mastermind" \
        and mirror.get("mode") == "zip-tree" and reader.get("root") == "root" \
        and reader.get("capability") == "neptune.resource-reader.v1" and reader.get("credential_ready") is True


class AgentLifecycle:
    def __init__(self, service):
        self.service = service
        self.directory = service.config.home / "agent-lifecycle"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.record = None
        try:
            with open_under(self.directory, "neptune.json") as source:
                content = source.read(65537)
            if len(content) > 65536:
                raise DomainError("RECOVERY_REQUIRED", "Agent lifecycle journal is too large.", 503)
            self.record = checked_json(content)
            if self.record.get("state") not in STATES or not re.fullmatch(r"(?:[a-f0-9]{32}|[a-f0-9-]{36})", self.record.get("request_id", "")):
                raise DomainError("RECOVERY_REQUIRED", "Agent lifecycle identity is invalid.", 503)
        except FileNotFoundError:
            pass

    def save(self, **changes):
        with self.lock:
            self.record = {**(self.record or {}), **changes, "updated_at": time.time()}
            atomic_json(self.directory / "neptune.json", self.record)
            return dict(self.record)

    def accept(self, job):
        if not isinstance(job, dict) or job.get("head_id") != self.service.config.updater_head_id \
                or job.get("request_id") != self.record["request_id"] or job.get("service") != "neptune-initialization" \
                or job.get("state") not in STATES or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job.get("id", "")):
            raise DomainError("UPDATER_PROTOCOL", "Initialization result does not match this service request.", 503)
        # Updater diagnostics can contain host paths. Only stable states and our
        # sanitized codes cross the browser boundary.
        return self.save(job_id=job["id"], state="ENROLLING" if job["state"] == "COMPLETED" else job["state"],
                         updater_state=job["state"], error="INITIALIZATION_FAILED" if job["state"] == "FAILED" else None)

    def initialize(self, data):
        if set(data) - {"code", "request_id"} or "code" not in data or not isinstance(data["code"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{32}", data["code"]):
            raise DomainError("INVALID_ENROLLMENT", "Use the 32-character Mastermind setup code from Saturn.", 422)
        request_id = data.get("request_id", secrets.token_hex(16))
        try:
            UUID(request_id)
        except (ValueError, TypeError, AttributeError):
            raise DomainError("INVALID_ENROLLMENT", "Use a stable request UUID", 422) from None
        if not self.service.config.updater_socket or not self.service.config.updater_token_file:
            raise DomainError("UPDATER_UNAVAILABLE", "The local Updater must be installed and registered first.", 503)
        with self.lock:
            if self.record and self.record["request_id"] == request_id:
                return dict(self.record)
            if self.record and self.record["state"] not in {"COMPLETED", "FAILED"}:
                raise DomainError("INITIALIZATION_BUSY", "Neptune initialization is already pending.", 409)
            self.record = {"request_id": request_id, "state": "REQUESTED", "created_at": time.time()}
            self.save()
            try:
                job = self.service.updates.updater.call("POST", "/v1/components/neptune-linux/initialize", data={
                    "head_id": self.service.config.updater_head_id, "request_id": self.record["request_id"],
                    "project_id": "mastermind", "export_url": self.service.config.neptune_export_url,
                    "enrollment_code": data["code"]})
                return self.accept(job)
            except DomainError as error:
                # A lost response may follow accepted work. Keep the request ID
                # and recover it from the authenticated job list before retrying.
                self.save(state="FAILED" if 400 <= error.status < 500 else "REQUESTED", error=error.code)
                raise

    async def status(self):
        with self.lock:
            record = dict(self.record) if self.record else None
        if record is None:
            return {"state": "IDLE"}
        if record["state"] in {"FAILED", "COMPLETED"}:
            return record
        try:
            if record.get("job_id"):
                job = await asyncio.to_thread(self.service.updates.updater.call, "GET",
                    "/v1/components/neptune-linux/initializations/"+record["job_id"]+"?head_id="+self.service.config.updater_head_id)
            else:
                listing = await asyncio.to_thread(self.service.updates.updater.call, "GET",
                    "/v1/jobs?head_id="+self.service.config.updater_head_id)
                jobs = listing.get("jobs") if isinstance(listing, dict) else None
                if not isinstance(jobs, list) or len(jobs) > 1000:
                    raise DomainError("UPDATER_PROTOCOL", "Initialization lookup is invalid.", 503)
                job = next((j for j in jobs if j.get("request_id") == record["request_id"]), None)
                if job is None:
                    if time.time()-record["created_at"] > 600:
                        return self.save(state="FAILED", error="INITIALIZATION_NOT_CONFIRMED")
                    return record
            with self.lock:
                if self.record["request_id"] != record["request_id"]:
                    return dict(self.record)
                result = self.accept(job)
            if job["state"] == "COMPLETED":
                observed = await self.service.neptune.control("status")
                if complete_profile(observed):
                    await self.service.neptune.request("resources", "root", limit=1)
                    result = self.save(state="COMPLETED", error=None, capabilities=["archive", "mirror", "reader"])
                    self.service.audit.emit("neptune.initialize", actor="owner", target="mastermind")
                else:
                    result = self.save(state="FAILED", error="NEPTUNE_PARTIAL_CONFIGURATION")
            return result
        except DomainError as error:
            return {**record, "connection_error": error.code}
