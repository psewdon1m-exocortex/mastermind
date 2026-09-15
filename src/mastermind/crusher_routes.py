import asyncio

from fastapi import Depends, Request

from .errors import DomainError


def install_crusher(app, service, owner, bounded_json):
    def identity(request: Request):
        header = request.headers.get("authorization", "")
        if header.startswith("Bearer "):
            return service.crusher_access.principal(header[7:])["principal"]
        owner(request)
        return "owner"

    identity_dependency = Depends(identity)

    @app.post("/api/v1/crusher/access", dependencies=[Depends(owner)])
    def create_access():
        return service.crusher_access.code()

    @app.post("/api/v1/crusher/sessions")
    async def activate(request: Request):
        data = await bounded_json(request, 4096)
        if set(data) != {"code"}:
            raise DomainError("INVALID_REQUEST", "Provide the Crusher access code.", 422)
        return await asyncio.to_thread(service.crusher_access.activate, data["code"], request.client.host)

    @app.post("/api/v1/crusher/uploads")
    async def reserve_upload(request: Request, principal=identity_dependency):
        data = await bounded_json(request, 4096)
        if set(data) != {"name", "size"}:
            raise DomainError("INVALID_REQUEST", "Provide the source name and size.", 422)
        return await asyncio.to_thread(service.crusher_access.upload, principal, data["name"], data["size"])

    @app.put("/api/v1/crusher/uploads/{identifier}/content")
    async def upload(identifier: str, request: Request, principal=identity_dependency):
        return await service.crusher_access.receive(identifier, principal, request.stream())

    @app.post("/api/v1/crusher/uploads/{identifier}/complete")
    async def complete(identifier: str, request: Request, principal=identity_dependency):
        data = await bounded_json(request, 4096)
        if set(data) != {"sha256"}:
            raise DomainError("INVALID_REQUEST", "Provide the source SHA-256.", 422)
        return await asyncio.to_thread(service.crusher_access.complete_upload, identifier, principal, data["sha256"])

    @app.post("/api/v1/crusher/jobs")
    async def submit(request: Request, principal=identity_dependency):
        data = await bounded_json(request, 1024**2*6 + 4096)
        return await asyncio.to_thread(service.crusher_access.accept, principal,
                                       request.headers.get("idempotency-key"), data)

    @app.get("/api/v1/crusher/jobs")
    def listing(request: Request, limit: int = 100, offset: int = 0, principal=identity_dependency):
        return service.crusher_access.list(principal, limit, offset)

    @app.get("/api/v1/crusher/jobs/{identifier}")
    def status(identifier: str, request: Request):
        ticket = request.headers.get("x-crusher-status-ticket")
        if ticket:
            return service.crusher_access.status(identifier, ticket=ticket)
        return service.crusher_access.status(identifier, principal=identity(request))
