"""Owner controls and the separately authenticated Gryphon command adapter."""
import asyncio
from uuid import UUID

from fastapi import Depends, Request

from .errors import DomainError


def install_gryphon(app, service, owner, bounded_json):
    gateway = service.gryphon

    @app.get("/api/owner/gryphon", dependencies=[Depends(owner)])
    def status():
        return gateway.status()

    @app.get("/api/owner/gryphon/bots", dependencies=[Depends(owner)])
    def bots():
        return gateway.bots()

    @app.get("/api/owner/gryphon/management", dependencies=[Depends(owner)])
    def management():
        return {"url": service.kernel.management_url("gryphon")}

    @app.post("/api/owner/gryphon/initialize", dependencies=[Depends(owner)])
    async def initialize(request: Request):
        data = await bounded_json(request, 1024)
        try:
            UUID(data.get("request_id", ""))
            if set(data) != {"request_id"}:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise DomainError("INVALID_REQUEST", "Provide a stable request UUID.", 422) from None
        service.data_ready()
        return await asyncio.to_thread(service.updates.updater.call, "POST", "/v1/lifecycle/gryphon-initialization",
            data={"head_id": service.config.updater_head_id, "request_id": data["request_id"]})

    @app.put("/api/owner/gryphon/connection", dependencies=[Depends(owner)])
    async def connect(request: Request):
        data = await bounded_json(request, 1024)
        if set(data) != {"botId"} or not isinstance(data["botId"], str) or not 1 <= len(data["botId"]) <= 200:
            raise DomainError("INVALID_REQUEST", "Select a registered Gryphon bot.", 422)
        service.data_ready()
        def apply():
            origin = "http://mastermind:18390" if service.config.secret_backend == "development-files" else service.kernel.origin_for("mastermind")
            current = gateway.observed()
            if current["connected"]:
                if current["bot"]["id"] != data["botId"]:
                    raise DomainError("GRYPHON_ALREADY_CONNECTED", "Unlink the current function before selecting another bot.", 409)
            else:
                gateway.call("PUT", "/v1/service/connection", {"botId": data["botId"], "commandPrefix": "mastermind",
                             "adapterUrl": origin.rstrip("/")+"/internal/gryphon/command"})
            gateway.sync_catalog()
            observed = gateway.observed()
            if not observed["connected"] or observed["bot"]["id"] != data["botId"]:
                raise DomainError("GRYPHON_NOT_VERIFIED", "The function connection is not yet verified.", 503)
            service.audit.emit("gryphon.connect", actor="owner", target="mastermind")
            return observed
        return await asyncio.to_thread(apply)

    @app.delete("/api/owner/gryphon/connection", dependencies=[Depends(owner)])
    async def disconnect():
        service.data_ready()
        def apply():
            # Never hold command_lock across the gateway callback made during revocation.
            result = gateway.call("DELETE", "/v1/service/connection")
            with gateway.command_lock:
                service.crusher_access.revoke_telegram()
            observed = gateway.observed()
            if observed["connected"]:
                raise DomainError("GRYPHON_NOT_VERIFIED", "The function unlink is not yet verified.", 503)
            service.audit.emit("gryphon.disconnect", actor="owner", target="mastermind")
            return result
        return await asyncio.to_thread(apply)

    @app.post("/api/owner/gryphon/link-challenge", dependencies=[Depends(owner)])
    def challenge():
        service.data_ready()
        result = gateway.call("POST", "/v1/service/link-challenges")
        if not all(isinstance(result.get(key), str) for key in ("code", "command", "expiresAt")):
            raise DomainError("GRYPHON_PROTOCOL", "The Telegram link challenge is invalid.", 503)
        service.audit.emit("gryphon.challenge", actor="owner", target="mastermind")
        return {key: result.get(key) for key in ("code", "command", "expiresAt", "botUsername")}

    @app.delete("/api/owner/gryphon/link-challenge", dependencies=[Depends(owner)])
    def cancel_challenge():
        service.data_ready()
        return gateway.call("DELETE", "/v1/service/link-challenges")

    @app.delete("/api/owner/gryphon/binding", dependencies=[Depends(owner)])
    async def revoke_binding():
        service.data_ready()
        def apply():
            result = gateway.call("DELETE", "/v1/service/binding")
            with gateway.command_lock:
                service.crusher_access.revoke_telegram()
            if gateway.observed()["binding"] is not None:
                raise DomainError("GRYPHON_NOT_VERIFIED", "Telegram binding revocation is not yet verified.", 503)
            service.audit.emit("gryphon.binding.revoke", actor="owner", target="mastermind")
            return result
        return await asyncio.to_thread(apply)

    def machine(request: Request):
        gateway.authenticate(request.headers.get("authorization", ""))

    @app.post("/internal/gryphon/command", dependencies=[Depends(machine)])
    async def command(request: Request):
        data = await bounded_json(request, 8192)
        return await asyncio.to_thread(gateway.command, data)
