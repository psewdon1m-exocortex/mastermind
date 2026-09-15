"""Local administrative API, served only on a mode-0600 Unix socket.

This app is never mounted on the browser listener. The private Core data
directory and Unix permissions are its authority boundary; no owner key is
stored or passed through process arguments by the CLI.
"""
import asyncio
import json
import os
import shutil
import socket
import stat
import time
from contextlib import contextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import __version__
from .agent_lifecycle import complete_profile
from .errors import DomainError
from .fs import open_under, sha_file
from .secret_store import SHELL_BINDINGS


def socket_path(config):
    return config.home / "run" / "admin.sock"


def replication_state(service):
    generation = int(service.state.one("SELECT value FROM metadata WHERE key='generation'")["value"])
    backlog = service.state.one("SELECT COUNT(*) AS count,MIN(occurred_at) AS oldest FROM outbox")
    return {"generation": generation, "pending_paths": backlog["count"],
            "oldest_pending_seconds": max(0, time.time()-backlog["oldest"]) if backlog["oldest"] else None,
            **{kind: {"verified_generation": service.state.setting(kind+"_verified_generation"),
                      "last_success_at": service.state.setting(kind+"_last_success_at"),
                      "generation_lag": max(0, generation-service.state.setting(kind+"_verified_generation", -1))}
               for kind in ("archive", "mirror")}}


def local_diagnostics(service):
    checks = {}
    def check(name, function):
        try:
            checks[name] = {"status": "PASS", **(function() or {})}
        except Exception as error:  # noqa: BLE001 — report each diagnostic independently without hiding a failure
            checks[name] = {"status": "FAIL", "code": error.code if isinstance(error, DomainError) else "CHECK_FAILED"}
    def config():
        if service.config.runtime_mode != "supervised" or service.config.secret_backend != "kernel":
            raise DomainError("DEVELOPMENT_PROFILE", "Development configuration is not production readiness.", 503)
    def files():
        paths = (service.config.home, service.config.state, service.config.vault)
        for path in paths:
            info = path.stat()
            if path.is_symlink() or not os.access(path, os.R_OK | os.W_OK | os.X_OK):
                raise OSError("Vault or state permissions are invalid")
            if os.name == "posix" and (info.st_uid != os.geteuid() or info.st_mode & 0o022):
                raise OSError("Vault or state is not private to the production UID")
        return {"effective_uid": os.geteuid() if hasattr(os, "geteuid") else None,
                "mount_devices": {label: path.stat().st_dev for label, path in
                    (("state", service.config.state), ("vault", service.config.vault))}}
    def integrity():
        with service.state.lock:
            deadline = time.monotonic()+15
            service.state.db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            try:
                if service.state.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise OSError("SQLite integrity failed")
            finally:
                service.state.db.set_progress_handler(None, 0)
    def bridge():
        directory = service.config.bridge_artifacts
        if directory is None:
            raise OSError("Bridge release inventory is missing")
        with open_under(directory, "integrity.json") as stream:
            inventory = json.loads(stream.read(4097))
        if set(inventory) != {"main.js", "manifest.json", "styles.css"}:
            raise OSError("Bridge inventory is invalid")
        for name, digest in inventory.items():
            if sha_file(directory / name) != digest or sha_file(service.config.vault / ".obsidian/plugins/mastermind-bridge" / name) != digest:
                raise OSError("Bridge release and installed files differ")
    def writers():
        if not service.maintenance or not service.maintenance.is_alive() or service.dirty.failure or service.index_failure:
            raise OSError("Watcher is unavailable")
        return {"recovery_required": service.coordinator.recovery_required, "restore_active": service.restore.active}
    def capacity():
        free = shutil.disk_usage(service.backup.spool.directory).free
        if free < 64*1024**2:
            raise OSError("Spool free space is below its safety reserve")
        return {"available_bytes": free, "configured_quota_bytes": service.config.spool_quota}
    def jobs():
        count = service.state.one("SELECT COUNT(*) AS count FROM jobs WHERE state NOT IN ('COMPLETED','FAILED','CANCELLED') "
                                  "AND created_at<?", (time.time()-3600,))["count"]
        if count:
            raise DomainError("STALE_CRUSHER_JOBS", "Crusher has jobs beyond its deadline.", 503)
        return {"stale_jobs": count}
    check("config", config)
    check("vault_permissions", files)
    check("unique_basenames", lambda: {"notes": len(service.vault.inventory())})
    check("sqlite_integrity", integrity)
    check("bridge_release", bridge)
    check("watcher", writers)
    check("spool_capacity", capacity)
    check("crusher", jobs)
    return checks


async def doctor(service):
    checks = await asyncio.to_thread(local_diagnostics, service)
    dependencies = {}
    async def probe(name, function):
        try:
            value = await asyncio.to_thread(function)
            dependencies[name] = {"status": "PASS", **(value or {})}
        except Exception as error:  # noqa: BLE001 — one failed dependency must not suppress other diagnostic results
            dependencies[name] = {"status": "FAIL", "code": error.code if isinstance(error, DomainError) else "DEPENDENCY_UNAVAILABLE"}
    def kernel():
        service.kernel.resolve([SHELL_BINDINGS["share_pepper_v1"]], fresh=True)
    def chronos():
        try:
            service.chronos.card("t-00000000")
        except DomainError as error:
            if error.code != "RESOURCE_NOT_FOUND":
                raise
        return {"authenticated_capability": True}
    def runtime():
        result = service.runtime.status()
        if not result.get("bridge", {}).get("ready") or not result.get("startup_allowed"):
            if result.get("owner_setup_required") and result.get("display_ready") and result.get("state") == "running":
                return {"status": "PENDING", "code": "NATIVE_OWNER_SETUP_REQUIRED"}
            raise DomainError("RUNTIME_NOT_READY", "Native Runtime is not ready.", 503)
        return {"obsidian": "RUNNING", "bridge": "READY"}
    def vnc():
        import httpx
        with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client, \
                client.stream("GET", service.vnc()+"/", headers=service.vnc_headers()) as response:
            if response.status_code != 200:
                raise OSError("Native display gateway is not reachable")
    def updater():
        result = service.updates.updater.call("GET", "/v1/health", timeout=5)
        if result.get("service") != "updater" or result.get("status") != "ok" or not {
                "mastermind.components.v1", "mastermind.spool.v1", "mastermind.enrollment.v1"}.issubset(result.get("capabilities", [])):
            raise DomainError("UPDATER_INCOMPATIBLE", "Host Updater does not support the qualified Mastermind profile.", 503)
        heads = service.updates.updater.call("GET", "/v1/services?head_id="+service.config.updater_head_id, timeout=5)
        if heads.get("services") != [{"id": service.config.updater_head_id}]:
            raise DomainError("UPDATER_SCOPE_INVALID", "The authenticated own head is unavailable.", 503)
        return {"version": result["version"], "own_head": True, "typed_profile": True}
    def worker():
        from .worker_client import WorkerClient
        client = WorkerClient(service.config, service.secrets)
        try:
            result = client.request("GET", "/healthz", limit=16384, timeout=5)
            if result.get("ready") is not True:
                raise DomainError("WORKER_NOT_READY", "The private Worker is not ready.", 503)
            return {"ready": True}
        finally:
            client.close()
    await asyncio.gather(probe("register", kernel), probe("chronos", chronos),
                         probe("runtime", runtime), probe("kasmvnc", vnc), probe("updater", updater), probe("worker", worker))
    try:
        status = await service.neptune.control("status")
        if not complete_profile(status):
            raise DomainError("NEPTUNE_PARTIAL_CONFIGURATION", "Typed profile is incomplete.", 503)
        await service.neptune.request("resources", "root", limit=1)
        dependencies["neptune"] = {"status": "PASS", "typed_profile": True, "reader": "READY"}
    except DomainError as error:
        dependencies["neptune"] = {"status": "FAIL", "code": error.code}
    try:
        service.data_ready()
        ready = True
    except DomainError:
        ready = False
    return {"service": "mastermind", "version": __version__, "status": "READY" if ready and
            all(v["status"] == "PASS" for v in [*checks.values(), *dependencies.values()]) else "NOT_READY",
            "live": True, "canonical_ready": ready, "checks": checks, "dependencies": dependencies,
            "replication": replication_state(service),
            "edge_verification": {"status": "UNKNOWN", "reason": "An external vantage is required; local CLI cannot certify the public edge."}}


def create_admin_app(service):
    from .api import bounded_json
    app = FastAPI(docs_url=None, openapi_url=None, redoc_url=None)

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({"error": error.code, "message": error.message}, status_code=error.status)

    @app.exception_handler(Exception)
    async def unexpected(request, error):
        return JSONResponse({"error": "ADMIN_OPERATION_FAILED"}, status_code=500)

    @app.get("/v1/doctor")
    async def diagnostics():
        return await doctor(service)

    @app.get("/v1/vault/validate")
    def validate():
        with service.coordinator.lock:
            inventory = service.vault.inventory()
            for relative in inventory:
                service.vault._read(relative)
            return {"valid": True, "notes": len(inventory)}

    @app.get("/v1/updates")
    def update_status():
        return service.updates.public()

    @app.post("/v1/updates/check")
    def update_check():
        return service.updates.discover()

    @app.get("/v1/updates/rollback")
    def update_rollback_options():
        return service.updates.rollback_options()

    @app.post("/v1/updates")
    async def update_apply(request: Request):
        from .api import bounded_json, require_text
        data = await bounded_json(request, 4096)
        return await asyncio.to_thread(service.updates.submit, require_text(data, "version"))

    @app.post("/v1/updates/rollback")
    async def update_rollback(request: Request):
        from .api import bounded_json, require_text
        data = await bounded_json(request, 4096)
        return await asyncio.to_thread(service.updates.submit_rollback, require_text(data, "job_id"))

    @app.post("/v1/reindex")
    def reindex():
        service.data_ready()
        with service.coordinator.boundary():
            service.vault.index(force=True)
            service.dirty.flush()
        service.audit.emit("admin.reindex", actor="local_admin")
        return {"completed": True, "notes": service.state.one("SELECT COUNT(*) AS count FROM notes")["count"]}

    @app.get("/v1/replication/status")
    async def replication():
        return {**replication_state(service), "agent": await service.neptune.control("status")}

    @app.post("/v1/replication/reconcile")
    async def reconcile():
        service.data_ready()
        accepted = {}
        for kind in ("archive", "mirror"):
            try:
                await service.neptune.control(kind)
                accepted[kind] = {"accepted": True}
            except DomainError as error:
                accepted[kind] = {"accepted": False, "code": error.code}
        service.audit.emit("admin.replication", actor="local_admin", context={"accepted": accepted})
        return accepted

    @app.post("/v1/operations")
    async def create(request: Request):
        data = await bounded_json(request, 4096)
        if set(data)-{"kind", "size"}:
            raise DomainError("INVALID_REQUEST", "Unsupported maintenance fields.", 422)
        return await asyncio.to_thread(service.owner_operations.create, data.get("kind"), data.get("size"))

    @app.get("/v1/operations/{identifier}")
    def operation(identifier: str):
        return service.owner_operations.public(service.owner_operations.read(identifier))

    @app.put("/v1/operations/{identifier}/content")
    async def upload(identifier: str, request: Request):
        return await service.owner_operations.receive(identifier, request.stream())

    @app.post("/v1/operations/{identifier}/confirm")
    async def confirm(identifier: str, request: Request):
        return await asyncio.to_thread(service.owner_operations.confirm, identifier, await bounded_json(request, 4096))

    @app.delete("/v1/operations/{identifier}")
    def remove(identifier: str):
        return service.owner_operations.remove(identifier)

    @app.get("/v1/operations/{identifier}/download")
    def download(identifier: str):
        record, _ = service.owner_operations.download(identifier)
        def stream():
            with open_under(service.owner_operations.directory, identifier+"/download.zip") as source:
                while block := source.read(1024**2):
                    yield block
        class Download(StreamingResponse):
            async def __call__(self, scope, receive, send):
                try:
                    await super().__call__(scope, receive, send)
                finally:
                    service.owner_operations.release(identifier)
        return Download(stream(), headers={"Content-Length": str(record["size"]), "ETag": '"'+record["sha256"]+'"'},
                        media_type="application/zip")
    return app


class LocalServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        yield  # The main browser server owns process signals.


async def start_admin(service):
    target = socket_path(service.config)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = target.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise OSError("Administrative socket directory must be private to Core")
    if target.exists() or target.is_symlink():
        previous = target.lstat()
        if not stat.S_ISSOCK(previous.st_mode) or previous.st_uid != os.geteuid():
            raise OSError("Unsafe administrative socket entry")
        target.unlink()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(str(target))
        os.chmod(target, 0o600)
        listener.listen(16)
        server = LocalServer(uvicorn.Config(create_admin_app(service), lifespan="off", access_log=False,
                            log_level="critical", limit_concurrency=8, timeout_keep_alive=5, timeout_graceful_shutdown=10))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        deadline = time.monotonic()+5
        while not server.started:
            if task.done():
                await task
                raise OSError("Administrative listener failed to start")
            if time.monotonic() > deadline:
                server.should_exit = True
                await task
                raise OSError("Administrative listener startup timed out")
            await asyncio.sleep(.01)
        return server, task, listener
    except BaseException:
        listener.close()
        target.unlink(missing_ok=True)
        raise


async def stop_admin(service, running):
    server, task, listener = running
    server.should_exit = True
    await task
    listener.close()
    socket_path(service.config).unlink(missing_ok=True)
