"""Owner-only adapters. Saturn content is always read through the local Neptune agent."""
import asyncio
import re
import ssl
import threading
import time
from datetime import datetime

import httpx

from .backup import checked_json
from .errors import DomainError
from .kernel import bounded_response
from .secret_store import read_credential_file


def resource_path(value):
    if not isinstance(value, str) or len(value.encode()) > 4096 or len(value.split("/")) > 64 \
            or value.split("/", 1)[0] != "root" or any(part in ("", ".", "..") for part in value.split("/")) \
            or any(ord(char) < 32 or ord(char) == 127 or char in "\\:" for char in value) \
            or re.search(r"%[0-9a-fA-F]{2}", value):
        raise DomainError("RESOURCE_PATH_INVALID", "The resource path is invalid.", 422)
    return value


class Neptune:
    def __init__(self, config, *, client=None):
        self.config = config
        self.client = client or httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=config.neptune_socket or "/run/neptune/not-configured.sock"),
            timeout=httpx.Timeout(60, connect=3, pool=3), base_url="http://neptune",
            follow_redirects=False, trust_env=False, limits=httpx.Limits(max_connections=4))
        self.active = 0
        self.failure = None

    def headers(self, purpose):
        if purpose not in ("owner-reference", "owner-crusher"):
            raise DomainError("FORBIDDEN", "This principal cannot resolve external resources.", 403)
        if not self.config.neptune_socket or not self.config.neptune_token_file:
            raise DomainError("NEPTUNE_NOT_CONFIGURED", "Neptune is not connected.", 503)
        return {"X-Neptune-Token": read_credential_file(self.config.neptune_token_file), "X-Neptune-Purpose": purpose}

    async def close(self):
        await self.client.aclose()

    async def control(self, operation):
        routes = {"status": ("GET", "/v1/projects/mastermind/status"),
                  "archive": ("POST", "/v1/projects/mastermind/runs"),
                  "mirror": ("POST", "/v1/projects/mastermind/mirror/runs")}
        if operation not in routes:
            raise ValueError("Unsupported Neptune owner operation")
        method, route = routes[operation]
        try:
            async with asyncio.timeout(60):
                async with self.client.stream(method, route, headers=self.headers("owner-reference")) as response:
                    if response.status_code not in (200, 201, 202):
                        code = "NEPTUNE_INCOMPATIBLE" if response.status_code == 404 else "NEPTUNE_REJECTED"
                        raise DomainError(code, "The local Neptune agent could not complete this operation.", 503)
                    body = bytearray()
                    async for block in response.aiter_bytes(64*1024):
                        if len(body)+len(block) > 64*1024:
                            raise ValueError
                        body.extend(block)
                    result = checked_json(body)
                    if not isinstance(result, dict):
                        raise TypeError
                    return result
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError):
            raise DomainError("NEPTUNE_UNAVAILABLE", "Neptune returned no complete bounded response.", 503) from None

    async def request(self, operation, path, *, purpose="owner-reference", limit=100, cursor=None, headers=None):
        path = resource_path(path)
        if operation not in ("resources", "resource-metadata", "resource-content") or type(limit) is not int or not 1 <= limit <= 100:
            raise DomainError("INVALID_REQUEST", "The reader request is invalid.", 422)
        if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 2048 or any(ord(c) < 32 for c in cursor)):
            raise DomainError("CURSOR_INVALID", "The reader cursor is invalid.", 422)
        if self.active >= 4:
            raise DomainError("RESOURCE_BUSY", "External resource capacity is busy.", 429)
        supplied = self.headers(purpose)
        for key, value in (headers or {}).items():
            if key not in ("Range", "If-Range") or not isinstance(value, str) or len(value) > 512 \
                    or any(ord(c) < 32 for c in value):
                raise DomainError("INVALID_REQUEST", "Conditional content headers are invalid.", 422)
            supplied[key] = value
        self.active += 1
        response = None
        transferred = False
        try:
            params = {"path": path, "limit": limit, **({"cursor": cursor} if cursor else {})}
            request = self.client.build_request("GET", "/api/v1/projects/mastermind/" + operation, params=params, headers=supplied)
            async with asyncio.timeout(15):
                response = await self.client.send(request, stream=True)
            if response.status_code not in (200, 206):
                code = {404: "RESOURCE_NOT_FOUND", 409: "RESOURCE_CHANGED", 412: "RESOURCE_CHANGED",
                        416: "RANGE_NOT_SATISFIABLE", 429: "RESOURCE_BUSY"}.get(response.status_code, "NEPTUNE_UNAVAILABLE")
                status = response.status_code if response.status_code in (404, 409, 412, 416, 429) else 503
                error_headers = {}
                content_range = response.headers.get("content-range", "")
                if status == 416 and re.fullmatch(r"bytes \*/[0-9]{1,20}", content_range):
                    error_headers["Content-Range"] = content_range
                raise DomainError(code, "Neptune could not provide this resource.", status, error_headers)
            if operation == "resource-content":
                length = response.headers.get("content-length", "")
                if not length.isdigit() or int(length) > 32 * 1024**3 or not response.headers.get("etag") \
                        or response.status_code == 206 and "content-range" not in response.headers:
                    raise DomainError("NEPTUNE_INVALID", "Neptune returned invalid stream headers.", 503)
                self.failure = None
                response.extensions["mastermind_reader_slot"] = True
                transferred = True
                return response  # Ownership transfers to stream(), including the concurrency slot.
            data = bytearray()
            async with asyncio.timeout(15):
                async for chunk in response.aiter_bytes(64 * 1024):
                    if len(data) + len(chunk) > 1024 * 1024:
                        raise ValueError
                    data.extend(chunk)
            result = checked_json(data)
            entries = result["entries"] if operation == "resources" else [result]
            if not isinstance(entries, list) or len(entries) > limit:
                raise ValueError
            for entry in entries:
                item_path = resource_path(entry["path"])
                if operation == "resources":
                    if not item_path.startswith(path + "/") or "/" in item_path[len(path) + 1:]:
                        raise ValueError
                elif item_path != path:
                    raise ValueError
                if entry["type"] not in ("file", "folder") or type(entry["size_bytes"]) is not int \
                        or entry["size_bytes"] < 0 or not isinstance(entry["etag"], str) or len(entry["etag"]) > 512:
                    raise ValueError
            if operation == "resources":
                next_cursor = result.get("next_cursor")
                if next_cursor is not None and (not isinstance(next_cursor, str) or len(next_cursor) > 2048):
                    raise ValueError
            self.failure = None
            return result
        except DomainError as error:
            self.failure = error.code
            raise
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError, UnicodeError):
            self.failure = "NEPTUNE_UNAVAILABLE"
            raise DomainError(self.failure, "Neptune resource reading is unavailable.", 503) from None
        finally:
            if not transferred:
                self.active -= 1
                if response is not None:
                    await response.aclose()

    async def release(self, response):
        if response.extensions.pop("mastermind_reader_slot", False):
            self.active -= 1
            await response.aclose()

    async def stream(self, response):
        transferred = 0
        length = int(response.headers["content-length"])
        try:
            async with asyncio.timeout(3600):
                async for chunk in response.aiter_bytes(256 * 1024):
                    transferred += len(chunk)
                    if transferred > length:
                        raise DomainError("RESOURCE_CHANGED", "The resource changed during transfer.", 409)
                    yield chunk
                if transferred != length:
                    raise DomainError("RESOURCE_CHANGED", "The resource stream ended early.", 409)
        finally:
            await self.release(response)


class Chronos:
    def __init__(self, kernel, secrets, *, client=None, clock=time.monotonic, ca_file=None):
        self.kernel, self.secrets = kernel, secrets
        self.client = client or httpx.Client(timeout=5, trust_env=False, follow_redirects=False,
                                            verify=ssl.create_default_context(cafile=ca_file))
        self.clock, self.cache = clock, {}
        self.lock = threading.Lock()

    def close(self):
        self.cache.clear()
        self.client.close()

    def card(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._~-]{0,127}", identifier):
            raise DomainError("REFERENCE_INVALID", "The Chronos reference is invalid.", 422)
        with self.lock:
            now = self.clock()
            self.cache = {key: item for key, item in self.cache.items() if item[0] > now}
            if identifier in self.cache:
                return self.cache[identifier][1]
            origin = self.kernel.origin_for("chronos")
            token = self.secrets.read("chronos_service_token")
            try:
                with self.client.stream("GET", origin + "/api/v1/internal/mastermind/events/" + identifier,
                    headers={"Authorization": "Bearer " + token, "X-Mastermind-Purpose": "owner-reference", "Accept-Encoding": "identity"}) as response:
                    if response.status_code == 404:
                        raise DomainError("RESOURCE_NOT_FOUND", "The Chronos event is unavailable.", 404)
                    data = bounded_response(response, 8192)
                if data.get("schema") != "chronos.mastermind-event.v1" or data.get("audience") != "mastermind" \
                        or data.get("id") != identifier:
                    raise ValueError
                for name in ("started_at", "ended_at"):
                    stamp = data.get(name)
                    if name == "ended_at" and stamp is None:
                        continue
                    if not isinstance(stamp, str) or len(stamp) > 50 or datetime.fromisoformat(stamp).tzinfo is None:
                        raise ValueError
                card = {"kind": "chronos", "id": identifier, "started_at": data["started_at"], "ended_at": data["ended_at"]}
                if len(self.cache) >= 1000:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[identifier] = (self.clock() + 30, card)
                return card
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                raise DomainError("CHRONOS_UNAVAILABLE", "Chronos is unavailable.", 503) from None
