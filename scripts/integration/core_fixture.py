"""Explicit local qualification factory. This file never enters production images.

Core, Worker, native Obsidian, Kernel/Volt and Neptune/Saturn remain real services.
Only the paid Google endpoint uses controlled REST responses. Tests therefore
qualify orchestration and boundaries, not real-provider availability or quality.
"""
import asyncio
import json
import secrets
import time

import httpx
from fastapi import Request

from mastermind.api import OWNER_COOKIE
from mastermind.api import create_app as production_app
from mastermind.fs import sha_file
from mastermind.gemini import Gemini

ORIGIN = "https://generativelanguage.googleapis.com"


def response(status, value=None, headers=None):
    return httpx.Response(status, headers=headers, stream=httpx.ByteStream(json.dumps(value or {}).encode()))


def create_app():
    app = production_app()
    service = app.state.service
    retries = set()

    def respond(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "synthetic-integration-provider-key"
        if request.url.path.startswith("/upload/"):
            if request.headers["x-goog-upload-command"] == "start":
                return response(200, headers={"x-goog-upload-url": ORIGIN + "/upload/v1beta/files?upload_id=fixture"})
            assert 0 < len(request.read()) <= 2*1024**2
            return response(200, {"file": {"name": "files/integration-source", "uri": ORIGIN + "/v1beta/files/integration-source", "state": "ACTIVE"}})
        if request.method == "DELETE":
            return response(200)
        data = json.loads(request.read())
        parts = data["contents"][0]["parts"]
        if request.url.path.endswith(":countTokens"):
            return response(200, {"totalTokens": max(1, len(json.dumps(parts, ensure_ascii=False))//3)})
        packet = json.loads(parts[0]["text"])["data"]
        schema = data["generationConfig"]["responseJsonSchema"]["title"]
        if schema == "Understanding":
            source = packet.get("source", "Controlled media facts")
            if "[FAIL_SCHEMA]" in source:
                return response(200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "malformed"}]}}]})
            if "[RETRY_ONCE]" in source and source not in retries:
                retries.add(source)
                return response(429, headers={"Retry-After": "5"})
            value = {"title": "Fixture knowledge", "summary": source[:1000], "topics": ["knowledge", "architecture"],
                     "entities": [], "suggested_links": []}
        elif schema == "Choice":
            value = {"action": "choose", "handle": packet["candidates"][0]["handle"], "confidence": 0.96}
        elif schema == "Generated":
            if "[HOLD_GENERATE]" in packet["understanding"]["summary"]:
                time.sleep(10)
            value = {"title": "Fixture knowledge", "markdown": "# Fixture knowledge\n\nKnowledge architecture organizes facts into meaningful branches."}
        else:
            raise AssertionError("Unexpected provider schema")
        return response(200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(value)}]}}],
                              "usageMetadata": {"candidatesTokenCount": 100}})

    service.crusher.provider.close()
    service.crusher.provider = Gemini(service.kernel, service.secrets,
        client=httpx.Client(base_url=ORIGIN, transport=httpx.MockTransport(respond)))

    @app.post("/qualification/restore")
    async def native_restore(request: Request):
        # Fixed local scenario, protected by the real owner session and CSRF checks.
        session = service.auth.session(request.cookies.get(OWNER_COOKIE))
        service.auth.csrf(session, request.headers.get("x-csrf-token"), request.headers.get("origin"), service.config.public_url)
        def run():
            identifier = secrets.token_hex(8)
            note = "Restore qualification " + identifier + ".md"
            source = service.config.home / "recovery" / ("qualification-" + identifier + ".zip")
            baseline = "Saved before real native restore.\n"
            service.vault.write(note, baseline, None, create=True)
            service.backup.create(source)
            service.vault.write(note, "Changed after snapshot.\n", sha_file(service.config.vault / note))
            started = time.monotonic()
            result = service.restore.apply(source)
            assert service.vault.read(note) == baseline
            assert not service.coordinator.recovery_required
            source.unlink()
            return {"native_restore": "PASS", "state": result["state"], "canonical_text": "RESTORED",
                    "verification_copy_removed": not any(service.config.vault.parent.glob(".verify-*")),
                    "elapsed_seconds": round(time.monotonic()-started, 3)}
        return await asyncio.to_thread(run)
    return app
