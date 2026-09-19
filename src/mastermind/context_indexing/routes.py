"""Owner-only configuration; generic graph retrieval remains an internal contract."""
import asyncio

from fastapi import Depends, Request

from ..errors import DomainError


def representation(value):
    return {"schema": value["schema"], "revision": value["revision"],
            "crusher": {k: value[k] for k in ("output_dir", "fallback_note", "template_path")},
            "retrieval": {"curator_enabled": value["curator_enabled"]},
            **{k: value[k] for k in ("graph_root", "readiness") if k in value}}


def changes(data):
    if not isinstance(data, dict) or set(data)-{"crusher", "retrieval", "operation_id", "expected_revision"}:
        raise DomainError("INVALID_SETTINGS", "Unsupported context-indexing settings.", 422)
    result = {k: data[k] for k in ("operation_id", "expected_revision") if k in data}
    for name, allowed in (("crusher", {"fallback_note", "template_path"}), ("retrieval", {"curator_enabled"})):
        fields = data.get(name, {})
        if not isinstance(fields, dict) or set(fields)-allowed:
            raise DomainError("INVALID_SETTINGS", "Unsupported context-indexing settings field.", 422)
        result.update(fields)
    return result


def install(app, service, owner, bounded_json):
    @app.get("/api/owner/context-indexing/settings", dependencies=[Depends(owner)])
    def settings():
        service.data_ready()
        return representation(service.context_indexing.status())

    @app.patch("/api/owner/context-indexing/settings", dependencies=[Depends(owner)])
    async def change(request: Request):
        service.data_ready()
        data = changes(await bounded_json(request, 8192))
        return representation(await asyncio.to_thread(service.context_indexing.settings.change, data))

    @app.post("/api/owner/context-indexing/validate", dependencies=[Depends(owner)])
    async def validate(request: Request):
        service.data_ready()
        return await asyncio.to_thread(service.context_indexing.settings.change,
                                       changes(await bounded_json(request, 8192)), dry_run=True)

    @app.post("/api/owner/context-indexing/initialize", dependencies=[Depends(owner)])
    async def initialize(request: Request):
        service.data_ready()
        if await bounded_json(request, 1024) != {}:
            raise DomainError("INVALID_REQUEST", "Initialization takes no supplied content.", 422)
        return representation(await asyncio.to_thread(service.context_indexing.settings.bootstrap))

    @app.get("/api/owner/context-indexing/waiting", dependencies=[Depends(owner)])
    def waiting():
        service.data_ready()
        return service.crusher.waiting()

    @app.post("/api/owner/context-indexing/jobs/{identifier}/resume", dependencies=[Depends(owner)])
    async def resume(identifier: str, request: Request):
        service.data_ready()
        return await asyncio.to_thread(service.crusher.resume, identifier, await bounded_json(request, 1024))
