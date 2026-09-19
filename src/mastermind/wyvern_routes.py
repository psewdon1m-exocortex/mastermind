"""Own-client Settings operations; shared Adapter administration stays in Updater."""
import asyncio
import secrets

from fastapi import Depends, Request

from .errors import DomainError
from .wyvern import Wyvern


def install_wyvern(app, service, owner, bounded_json):
    gateway = Wyvern(service.config.wyvern_link_file)

    @app.get("/api/owner/wyvern", dependencies=[Depends(owner)])
    def status():
        return gateway.status()

    @app.post("/api/owner/wyvern/bindings", dependencies=[Depends(owner)])
    async def bindings(request: Request):
        service.data_ready()
        data = await bounded_json(request, 8192)
        if set(data) != {"bindings", "expected_revision", "request_id"}:
            raise DomainError("INVALID_REQUEST", "Provide function bindings and the current revision.", 422)
        return await asyncio.to_thread(gateway.call, "POST", "/v1/bindings", data=data)

    @app.post("/api/owner/wyvern/connect", dependencies=[Depends(owner)])
    async def connect(request: Request):
        service.data_ready()
        if await bounded_json(request, 1024) != {}:
            raise DomainError("INVALID_REQUEST", "Connection uses this service's registered host identity.", 422)
        return await asyncio.to_thread(service.updates.updater.call, "POST", "/v1/lifecycle/wyvern-installation",
            data={"head_id": service.config.updater_head_id, "request_id": "wyvern-" + secrets.token_hex(16)})
