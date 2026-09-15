"""Core-side private Worker adapter. Only bounded source/chunk data crosses this API."""
import hashlib
import time
from contextlib import contextmanager

import httpx

from .backup import checked_json
from .errors import DomainError
from .fs import open_under


class WorkerClient:
    def __init__(self, config, secrets_store, *, client=None):
        self.origin, self.secrets = config.worker_url, secrets_store
        self.client = client or httpx.Client(base_url=self.origin or "http://worker.invalid", trust_env=False,
            follow_redirects=False, timeout=httpx.Timeout(1260, connect=5, write=60, pool=5),
            limits=httpx.Limits(max_connections=4))

    def close(self):
        self.client.close()

    def headers(self):
        if not self.origin:
            raise DomainError("WORKER_UNAVAILABLE", "The private Worker is not configured.", 503)
        return {"Authorization": "Bearer " + self.secrets.read("worker_token"), "Accept-Encoding": "identity"}

    def request(self, method, route, data=None, *, content=None, headers=None, limit=4*1024**2, timeout=None):
        try:
            arguments = {"json": data} if data is not None else {"content": content} if content is not None else {}
            if timeout is not None:
                arguments["timeout"] = timeout
            with self.client.stream(method, route, headers={**self.headers(), **(headers or {})}, **arguments) as response:
                raw, deadline = bytearray(), time.monotonic()+(float(timeout) if isinstance(timeout, (int, float)) else 1260)
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise ValueError
                for block in response.iter_bytes(64*1024):
                    if len(raw)+len(block) > limit or time.monotonic() > deadline:
                        raise ValueError
                    raw.extend(block)
                value = checked_json(raw)
                if not isinstance(value, dict):
                    raise TypeError
                if response.status_code != 200:
                    code = value.get("error", {}).get("code", "WORKER_UNAVAILABLE")
                    if code not in {"WORKER_BUSY", "SOURCE_UNAVAILABLE", "SOURCE_INTEGRITY", "SOURCE_NETWORK",
                                    "SOURCE_SIZE_INVALID", "SOURCE_TIMEOUT", "SSRF_REJECTED", "SOURCE_URL_INVALID",
                                    "SOURCE_REDIRECT_LIMIT", "SOURCE_ENCODING", "SOURCE_HEADERS_INVALID", "INSUFFICIENT_SPACE",
                                    "EXTRACTION_FAILED", "EXTRACTION_SANDBOX_FAILED", "EXTRACTION_TIMEOUT", "SOURCE_ENCRYPTED",
                                    "ARCHIVE_UNSAFE", "ARCHIVE_LIMIT", "EXTRACTION_LIMIT", "SOURCE_EMPTY", "EMBEDDINGS_UNAVAILABLE"}:
                        code = "WORKER_UNAVAILABLE"
                    raise DomainError(code, "The private Worker could not complete this source operation.",
                                      response.status_code if response.status_code in (408, 409, 413, 422, 423, 429, 503, 507) else 503)
                return value
        except (httpx.HTTPError, OSError, ValueError, TypeError, UnicodeError):
            raise DomainError("WORKER_UNAVAILABLE", "The private Worker connection or response failed.", 503) from None

    def transfer(self, identifier, directory, name, *, expected, size, source_name):
        def chunks():
            total, content_hash, deadline = 0, hashlib.sha256(), time.monotonic()+900
            with open_under(directory, name) as source:
                while block := source.read(1024**2):
                    total += len(block)
                    if total > size or time.monotonic() > deadline:
                        raise DomainError("SOURCE_INTEGRITY", "The accepted source changed or exceeded its deadline.", 409)
                    content_hash.update(block)
                    yield block
            if total != size or content_hash.hexdigest() != expected:
                raise DomainError("SOURCE_INTEGRITY", "The accepted source failed its integrity check.", 409)
        result = self.request("PUT", "/jobs/" + identifier + "/source", content=chunks(), headers={
            "Content-Length": str(size), "Content-Type": "application/octet-stream", "X-Source-Sha256": expected,
            "X-Source-Name": source_name.encode("utf-8").hex()})
        if result.get("sha256") != expected or result.get("size") != size:
            raise DomainError("SOURCE_INTEGRITY", "Worker source receipt did not match the accepted bytes.", 503)
        return result

    def acquire(self, identifier, url):
        return self.request("POST", "/jobs/" + identifier + "/acquire", {"url": url})

    def extract(self, identifier):
        value = self.request("POST", "/jobs/" + identifier + "/extract")
        if value.get("schema") != "mastermind.extraction.v1" or not isinstance(value.get("text"), str) \
                or len(value["text"].encode("utf-8")) > 512*1024 or type(value.get("needs_media")) is not bool \
                or type(value.get("needs_browser")) is not bool:
            raise DomainError("EXTRACTION_FAILED", "The Worker extraction result is invalid.", 503)
        return value

    def embed(self, texts, *, query=False):
        import math
        value = self.request("POST", "/embeddings", {"texts": texts, "query": query})
        vectors = value.get("vectors")
        if not isinstance(vectors, list) or len(vectors) != len(texts) or any(
            not isinstance(vector, list) or len(vector) != 384 or any(type(number) not in (int, float)
                or not math.isfinite(number) or abs(number) > 1.001 for number in vector) for vector in vectors
        ):
            raise DomainError("EMBEDDINGS_INVALID", "The Worker returned invalid semantic vectors.", 503)
        return value

    def cleanup(self, identifier):
        return self.request("DELETE", "/jobs/" + identifier)

    @contextmanager
    def media(self, identifier):
        with self.client.stream("GET", "/jobs/" + identifier + "/source", headers=self.headers(), timeout=60) as response:
            length = response.headers.get("content-length", "")
            sha = response.headers.get("x-source-sha256", "")
            if response.status_code != 200 or not length.isdigit() or not 0 < int(length) <= 2*1024**3 or len(sha) != 64:
                raise DomainError("SOURCE_INTEGRITY", "Worker media stream headers are invalid.", 503)
            def blocks():
                total, content_hash, deadline = 0, hashlib.sha256(), time.monotonic()+300
                for block in response.iter_raw():
                    total += len(block)
                    if total > int(length) or time.monotonic() > deadline:
                        raise DomainError("SOURCE_INTEGRITY", "Worker media exceeded its transfer budget.", 503)
                    content_hash.update(block)
                    yield block
                if total != int(length) or content_hash.hexdigest() != sha:
                    raise DomainError("SOURCE_INTEGRITY", "Worker media failed its content receipt.", 503)
            yield {"size": int(length), "sha256": sha, "blocks": blocks()}
