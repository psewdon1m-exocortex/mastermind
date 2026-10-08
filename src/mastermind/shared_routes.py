"""Shared routes deliberately ignore owner credentials and own all public rendering."""
import asyncio
import secrets
from pathlib import Path

from fastapi import Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .errors import DomainError

COOKIE = "__Secure-mastermind_share"


def install_shared(app, service, owner, bounded_json):
    def origin(request):
        if request.headers.get("origin") != service.config.public_url.rstrip("/"):
            raise DomainError("CSRF_REJECTED", "The request origin was not accepted.", 403)

    @app.get("/api/v1/shares", dependencies=[Depends(owner)])
    def listing(limit: int = 100, offset: int = 0):
        return service.shared.list(limit, offset)

    @app.post("/api/v1/shares", dependencies=[Depends(owner)])
    async def create(request: Request):
        data = await bounded_json(request)
        if not isinstance(data.get("path"), str) or set(data) - {"path", "permission", "password", "expires_at"}:
            raise DomainError("INVALID_REQUEST", "Share fields are invalid.", 422)
        return await asyncio.to_thread(service.shared.create, **data)

    @app.patch("/api/v1/shares/{identifier}", dependencies=[Depends(owner)])
    async def policy(identifier: str, request: Request):
        return await asyncio.to_thread(service.shared.change, identifier, await bounded_json(request))

    @app.get("/api/v1/shares/{identifier}/link", dependencies=[Depends(owner)])
    def copy_link(identifier: str):
        return service.shared.copy_link(identifier)

    @app.get("/s/{token}")
    def page(token: str, request: Request):
        unavailable = False
        try:
            service.shared.describe(token)
        except DomainError as error:
            if error.status != 404:
                raise
            unavailable = True
        nonce = secrets.token_urlsafe(24)
        # Assets are fixed and nonce-authorized. The capability remains only in
        # the current URL; no local/session storage, resolver, or owner API calls.
        from .shared_ui import page_html
        # Rejected tokens never enter HTML or asset CSP sources.
        safe_token = "" if unavailable else token
        asset = service.config.public_url.rstrip("/") + "/s/" + safe_token
        return HTMLResponse(page_html(nonce, service.operator.preferences()["accent"], safe_token,
                                     legacy=request.query_params.get("legacy") == "1", unavailable=unavailable),
            status_code=404 if unavailable else 200, headers={"Content-Security-Policy":
            "default-src 'none'; script-src 'nonce-" + nonce + "'; style-src 'nonce-" + nonce + "'; "
            + ("" if unavailable else "font-src " + asset + "/font.woff2 " + asset + "/font-regular.woff2; "
               "img-src " + asset + "/brand.png; connect-src " + asset + "/api/; ") +
            "frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'none'",
            "X-Frame-Options": "DENY"})

    @app.get("/s/{token}/font.woff2")
    def font(token: str):
        service.shared.describe(token)
        return FileResponse(Path(__file__).parent / "web/fonts/SpaceGrotesk-Bold.woff2", media_type="font/woff2")

    @app.get("/s/{token}/font-regular.woff2")
    def regular_font(token: str):
        service.shared.describe(token)
        return FileResponse(Path(__file__).parent / "web/fonts/SpaceGrotesk-Regular.woff2", media_type="font/woff2")

    @app.get("/s/{token}/brand.png")
    def brand(token: str):
        service.shared.describe(token)
        return FileResponse(Path(__file__).parent / "web/brand-mark.png", media_type="image/png")

    @app.get("/s/{token}/api/policy")
    def describe(token: str):
        return {**service.shared.describe(token), "accent": service.operator.preferences()["accent"]}

    @app.post("/s/{token}/api/session")
    async def unlock(token: str, request: Request):
        origin(request)
        data = await bounded_json(request, 32*1024)
        if set(data) - {"password"}:
            raise DomainError("INVALID_REQUEST", "Unlock fields are invalid.", 422)
        session = await asyncio.to_thread(service.shared.unlock, token, data.get("password"), request.client.host)
        response = JSONResponse({"csrf": session["csrf"], "expires_at": session["expires_at"]})
        response.set_cookie(COOKIE, session["token"], max_age=1800, secure=True, httponly=True,
                            samesite="strict", path="/s/" + token)
        return response

    @app.get("/s/{token}/api/note")
    def note(token: str, request: Request):
        value = service.shared.project(token, request.cookies.get(COOKIE))
        return JSONResponse(value, headers={"ETag": '"' + value["sha256"] + '"'})

    @app.put("/s/{token}/api/note")
    async def save(token: str, request: Request):
        credential = request.cookies.get(COOKIE)
        _, session = await asyncio.to_thread(service.shared.authorize, token, credential, edit=True)
        service.auth.csrf(session, request.headers.get("x-csrf-token"), request.headers.get("origin"),
                          service.config.public_url)
        data = await bounded_json(request, service.config.max_share_bytes*6 + 4096)
        if set(data) != {"projection_id", "values"} or not isinstance(data["projection_id"], str):
            raise DomainError("INVALID_REQUEST", "Only the projection identifier and editable values are accepted.", 422)
        expected = request.headers.get("if-match")
        if expected:
            import re
            if not re.fullmatch(r'"[a-f0-9]{64}"', expected):
                raise DomainError("INVALID_PRECONDITION", "If-Match must contain one strong note ETag.", 422)
            expected = expected[1:-1]
        value = await asyncio.to_thread(service.shared.save, token, credential, data["projection_id"],
                                         data["values"], expected)
        return JSONResponse(value, headers={"ETag": '"' + value["sha256"] + '"'})
