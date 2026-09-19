"""Own-client Settings operations; shared Adapter administration stays in Updater."""
import asyncio
from uuid import UUID

from fastapi import Depends, Request

from . import wyvern_intent
from .errors import DomainError
from .wyvern import Wyvern


def install_wyvern(app, service, owner, bounded_json):
    gateway = Wyvern(service.config.wyvern_link_file, intent_state=service.state)

    @app.get("/api/owner/wyvern", dependencies=[Depends(owner)])
    def status():
        return gateway.status()

    @app.post("/api/owner/wyvern/bindings", dependencies=[Depends(owner)])
    async def bindings(request: Request):
        service.data_ready()
        data = await bounded_json(request, 8192)
        if set(data) != {"bindings", "expected_revision", "request_id"}:
            raise DomainError("INVALID_REQUEST", "Provide function bindings and the current revision.", 422)
        result = await asyncio.to_thread(gateway.call, "POST", "/v1/bindings", data=data)
        wyvern_intent.save(service.state, wyvern_intent.from_status(result))
        return result

    @app.post("/api/owner/wyvern/connect", dependencies=[Depends(owner)])
    async def connect(request: Request):
        service.data_ready()
        data = await bounded_json(request, 1024)
        try:
            UUID(data.get("request_id", ""))
            if set(data) != {"request_id"}:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise DomainError("INVALID_REQUEST", "Provide a stable request UUID", 422) from None
        return await asyncio.to_thread(service.updates.updater.call, "POST", "/v1/lifecycle/wyvern-installation",
            data={"head_id": service.config.updater_head_id, "request_id": data["request_id"]})

    @app.get("/api/owner/wyvern/management", dependencies=[Depends(owner)])
    def management():
        return {"url": service.kernel.management_url("wyvern")}
