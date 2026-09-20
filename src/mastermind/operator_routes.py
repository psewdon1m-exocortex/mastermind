"""Owned Shell routes; never mounted below a public Share capability."""
import asyncio
import re
import time
from pathlib import Path
from uuid import UUID

from fastapi import Depends, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .agent_lifecycle import AgentLifecycle, complete_profile
from .errors import DomainError
from .fs import open_under
from .operator import Operator
from .owner_operations import OwnerOperations


def install_operator(app, service, owner, bounded_json):
    from .context_indexing.routes import install as install_context_indexing
    from .wyvern_routes import install_wyvern
    install_context_indexing(app, service, owner, bounded_json)
    install_wyvern(app, service, owner, bounded_json)
    service.operator = Operator(service)
    service.owner_operations = OwnerOperations(service)
    service.agent_lifecycle = AgentLifecycle(service)
    web = Path(__file__).parent / "web"
    app.mount("/assets", StaticFiles(directory=web), name="shell-assets")

    def page():
        return FileResponse(web / "index.html", media_type="text/html", headers={"Content-Security-Policy":
            "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; "
            "font-src 'self'; connect-src 'self'; frame-src 'self'; worker-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'"})

    for route in ("/", "/login", "/dashboard", "/vault", "/crusher", "/analytics", "/shared", "/shares", "/settings", "/documentation"):
        app.add_api_route(route, page, methods=["GET"], include_in_schema=False)

    @app.get("/api/owner/documentation", dependencies=[Depends(owner)])
    def documentation():
        from .documentation import articles
        return articles()

    @app.get("/api/appearance")
    def appearance():
        return {"accent": service.operator.preferences()["accent"]}

    @app.get("/api/owner/settings", dependencies=[Depends(owner)])
    def preferences():
        return service.operator.preferences()

    @app.patch("/api/owner/settings", dependencies=[Depends(owner)])
    async def change(request: Request):
        service.data_ready()
        return await asyncio.to_thread(service.operator.change, await bounded_json(request, 8192))

    @app.get("/api/owner/metrics", dependencies=[Depends(owner)])
    def metrics():
        return service.operator.metrics()

    @app.get("/api/owner/connection", dependencies=[Depends(owner)])
    def connection():
        return service.operator.connection()

    @app.get("/api/owner/agents", dependencies=[Depends(owner)])
    async def agents():
        async def neptune():
            base = {"archive_last_success_at": service.state.setting("archive_last_success_at"),
                    "mirror_last_success_at": service.state.setting("mirror_last_success_at"),
                    "archive_generation": service.state.setting("archive_verified_generation"),
                    "mirror_generation": service.state.setting("mirror_verified_generation")}
            try:
                result = await service.neptune.control("status")
                if result.get("product") != "neptune-linux" or not isinstance(result.get("project"), dict):
                    raise DomainError("NEPTUNE_INCOMPATIBLE", "Unexpected Neptune identity.", 503)
                project = result["project"]
                return {**base, "state": "LINKED" if complete_profile(result) else "PARTIAL_CONFIGURATION", "installed": True, "socket_reachable": True,
                        "authenticated": True, "version": result.get("version"), "archive_enabled": project.get("enabled"),
                        "mirror_enabled": (project.get("mirror") or {}).get("enabled"),
                        "reader_configured": project.get("reader") is not None}
            except DomainError as error:
                return {**base, "state": "NOT_CONFIGURED" if error.code == "NEPTUNE_NOT_CONFIGURED" else "UNAVAILABLE",
                        "code": error.code, "installed": None, "socket_reachable": None, "authenticated": False}
        async def updater():
            try:
                result = await asyncio.to_thread(service.updates.updater.call, "GET", "/v1/health")
                return {"state": "AVAILABLE" if result.get("service") == "updater" and result.get("status") == "ok"
                        else "INCOMPATIBLE", "version": result.get("version")}
            except DomainError as error:
                return {"state": "UNAVAILABLE", "code": error.code}
        n, u, lifecycle = await asyncio.gather(neptune(), updater(), service.agent_lifecycle.status())
        return {"version": __version__, "neptune": n, "updater": u, "neptune_initialization": lifecycle}

    @app.get("/api/owner/neptune/policy", dependencies=[Depends(owner)])
    def backup_policy():
        return service.backup_policy.read()

    @app.put("/api/owner/neptune/policy", dependencies=[Depends(owner)])
    async def change_backup_policy(request: Request):
        service.data_ready()
        return await asyncio.to_thread(service.backup_policy.mutate, await bounded_json(request, 4096))

    @app.get("/api/owner/neptune/policy/runs", dependencies=[Depends(owner)])
    def backup_runs():
        return service.backup_policy.runs()

    @app.post("/api/owner/neptune/policy/runs", dependencies=[Depends(owner)])
    async def create_backup_run(request: Request):
        service.data_ready()
        return await asyncio.to_thread(service.backup_policy.runs, "POST", await bounded_json(request, 4096))

    @app.post("/api/owner/agents/neptune/enroll", dependencies=[Depends(owner)])
    async def enroll(request: Request):
        service.data_ready()
        data = await bounded_json(request, 4096)
        return await asyncio.to_thread(service.agent_lifecycle.initialize, data)

    @app.get("/api/owner/agents/neptune/initialization", dependencies=[Depends(owner)])
    async def initialization():
        return await service.agent_lifecycle.status()

    @app.post("/api/owner/updates/check", dependencies=[Depends(owner)])
    async def update_check(request: Request):
        if await bounded_json(request, 4096) != {}:
            raise DomainError("INVALID_REQUEST", "Release discovery takes no supplied source.", 422)
        return await asyncio.to_thread(service.updates.discover)

    @app.post("/api/owner/helper-updates/check", dependencies=[Depends(owner)])
    async def check_helper(request: Request):
        data = await bounded_json(request, 4096)
        if set(data) != {"component"} or data["component"] not in ("updater", "neptune", "wyvern", "gryphon"):
            raise DomainError("INVALID_REQUEST", "Select a helper consumed by this service", 422)
        return await asyncio.to_thread(service.updates.updater.call, "POST", "/v2/check",
            data={"head_id": service.config.updater_head_id, "component": data["component"]})

    @app.post("/api/owner/helper-updates/install/{component}", dependencies=[Depends(owner)])
    async def install_helper(component: str, request: Request):
        data = await bounded_json(request, 4096)
        try:
            UUID(data.get("request_id", ""))
            if component not in ("updater", "neptune", "wyvern", "gryphon") or set(data) - {"version", "request_id", "confirm_shared"} or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", data.get("version", "")):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise DomainError("INVALID_REQUEST", "Select an exact helper release and stable request UUID", 422) from None
        if component in ("wyvern", "gryphon") and data.get("confirm_shared") is not True:
            raise DomainError("CONFIRMATION_REQUIRED", "Confirm the shared gateway update impact", 409)
        return await asyncio.to_thread(service.updates.updater.call, "POST", "/v2/components/" + component + "/updates",
            data={**data, "head_id": service.config.updater_head_id})

    @app.get("/api/owner/helper-updates/jobs", dependencies=[Depends(owner)])
    def helper_jobs():
        return service.updates.updater.call("GET", "/v1/jobs?head_id=" + service.config.updater_head_id)

    @app.get("/api/owner/helper-updates/jobs/{identifier}", dependencies=[Depends(owner)])
    def helper_job(identifier: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier):
            raise DomainError("NOT_FOUND", "Unknown operation", 404)
        job = service.updates.updater.call("GET", "/v1/jobs/" + identifier)
        if job.get("head_id") != service.config.updater_head_id:
            raise DomainError("NOT_FOUND", "Unknown operation", 404)
        return job

    @app.post("/api/owner/connection", dependencies=[Depends(owner)])
    async def change_connection(request: Request):
        service.data_ready()
        return await asyncio.to_thread(service.operator.change_connection, await bounded_json(request, 128*1024+4096))

    @app.get("/api/owner/analytics", dependencies=[Depends(owner)])
    def analytics(first: str | None = None, last: str | None = None):
        service.data_ready()
        return service.operator.analytics(first, last)

    @app.get("/api/owner/operations", dependencies=[Depends(owner)])
    def operations():
        return service.owner_operations.listing()

    @app.post("/api/owner/operations", dependencies=[Depends(owner)])
    async def create_operation(request: Request):
        data = await bounded_json(request, 4096)
        if set(data)-{"kind", "size"}:
            raise DomainError("INVALID_REQUEST", "Maintenance operation fields are invalid.", 422)
        return await asyncio.to_thread(service.owner_operations.create, data.get("kind"), data.get("size"))

    @app.get("/api/owner/operations/{identifier}", dependencies=[Depends(owner)])
    def operation(identifier: str):
        return service.owner_operations.public(service.owner_operations.read(identifier))

    @app.delete("/api/owner/operations/{identifier}", dependencies=[Depends(owner)])
    def remove(identifier: str):
        return service.owner_operations.remove(identifier)

    @app.put("/api/owner/operations/{identifier}/content", dependencies=[Depends(owner)])
    async def content(identifier: str, request: Request):
        return await service.owner_operations.receive(identifier, request.stream())

    @app.post("/api/owner/operations/{identifier}/confirm", dependencies=[Depends(owner)])
    async def confirm(identifier: str, request: Request):
        return await asyncio.to_thread(service.owner_operations.confirm, identifier, await bounded_json(request, 4096))

    class Download(StreamingResponse):
        def __init__(self, record, path):
            self.identifier = record["id"]
            def chunks():
                deadline = time.monotonic()+3600
                with open_under(service.owner_operations.directory, record["id"]+"/download.zip") as source:
                    while block := source.read(1024**2):
                        if time.monotonic() > deadline:
                            raise DomainError("DOWNLOAD_TIMEOUT", "Download exceeded its deadline.", 408)
                        yield block
            super().__init__(chunks(), media_type="application/zip", headers={
                "Content-Length": str(record["size"]), "X-Content-SHA256": record["sha256"],
                "ETag": '"'+record["sha256"]+'"',
                "Content-Disposition": 'attachment; filename="'+record["filename"]+'"'})

        async def __call__(self, scope, receive, send):
            try:
                await super().__call__(scope, receive, send)
            finally:
                service.owner_operations.release(self.identifier)

    @app.get("/api/owner/operations/{identifier}/download", dependencies=[Depends(owner)])
    def download(identifier: str):
        return Download(*service.owner_operations.download(identifier))
