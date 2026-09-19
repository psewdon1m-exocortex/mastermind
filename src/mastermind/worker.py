"""Private Worker: bounded sources/embeddings, no Vault, SQLite or provider secrets."""
import asyncio
import hashlib
import hmac
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import __version__
from .backup import checked_json
from .curator_runtime import LocalCurator
from .embeddings import Embeddings
from .errors import DomainError
from .fs import atomic_json, open_under, remove_private_tree, sha_file
from .secret_store import read_credential_file
from .worker_fetch import PublicFetch


class Worker:
    def __init__(self, directory, model_directory, inventory, credential_file):
        self.directory, self.credential_file = directory, credential_file
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.embeddings = Embeddings(model_directory, inventory)
        self.curator = LocalCurator(os.environ.get("MASTERMIND_CURATOR_DIRECTORY", "/opt/mastermind/curator"),
                                    os.environ.get("MASTERMIND_CURATOR_INVENTORY", "/app/curator-model.lock.json"))
        self.lock = threading.RLock()
        self.active = None
        self.ready = False
        self.stop = threading.Event()
        self.fetcher = PublicFetch()
        self.readers = {}
        self.housekeeping = None

    def start(self):
        self.cleanup_expired()
        self.embeddings.load()
        self.ready = True
        self.housekeeping = threading.Thread(target=self.maintain, daemon=True, name="worker-cleanup")
        self.housekeeping.start()
        self.start_curator()

    def start_curator(self):
        with self.lock:
            if self.active is not None:
                return
            self.active = "curator-start"
        try:
            self.curator.start()
        finally:
            with self.lock:
                self.active = None

    def cleanup_expired(self):
        with self.lock:
            for folder in self.directory.iterdir():
                if re.fullmatch(r"[a-f0-9]{32}", folder.name) and folder.is_dir() and not folder.is_symlink() \
                        and not folder.is_junction() and folder.name != self.active and not self.readers.get(folder.name) \
                        and folder.stat().st_mtime < time.time()-86400:
                    remove_private_tree(folder, self.directory)

    def maintain(self):
        while not self.stop.wait(60):
            try:
                self.cleanup_expired()
                if self.active is None and not self.curator.status()["ready"]:
                    self.start_curator()
            except (OSError, DomainError):
                pass  # Retry bounded cleanup; never expose source names in logs.

    def folder(self, identifier):
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise DomainError("JOB_INVALID", "Worker job identity is invalid.", 422)
        path = self.directory / identifier
        if path.is_symlink() or path.is_junction():
            raise DomainError("JOB_INVALID", "Worker job storage is unsafe.", 503)
        return path

    def reserve(self, identifier, size):
        if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 2*1024**3:
            raise DomainError("SOURCE_SIZE_INVALID", "Worker source limit is 2 GiB.", 413)
        with self.lock:
            if self.active is not None or self.readers.get(identifier):
                raise DomainError("WORKER_BUSY", "Another source job is using the Worker.", 423)
            path = self.folder(identifier)
            required = size + 8*1024**3
            retained = sum(file.stat().st_size for file in self.directory.rglob("*") if file.is_file())
            if retained + required > 16*1024**3 or shutil.disk_usage(self.directory).free < required+64*1024**2:
                raise DomainError("INSUFFICIENT_SPACE", "Worker space cannot cover this source.", 507)
            path.mkdir(mode=0o700, exist_ok=True)
            self.active = identifier
            return path

    def source(self, identifier):
        folder = self.folder(identifier)
        try:
            with open_under(folder, "source.json") as stream:
                raw = stream.read(16*1024+1)
            if len(raw) > 16*1024:
                raise ValueError
            record = checked_json(raw)
            if not isinstance(record, dict) or not isinstance(record.get("sha256"), str) \
                    or not re.fullmatch(r"[a-f0-9]{64}", record["sha256"]) or type(record.get("size")) is not int \
                    or not 0 <= record["size"] <= 2*1024**3 or not isinstance(record.get("name"), str) \
                    or len(record["name"].encode()) > 512 or not isinstance(record.get("mime"), str) \
                    or not re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", record["mime"]):
                raise ValueError
            with open_under(folder, "source") as stream:
                if os.fstat(stream.fileno()).st_size != record["size"] \
                        or hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
                    raise ValueError
            return folder, record
        except (OSError, ValueError, KeyError, UnicodeError, DomainError):
            raise DomainError("SOURCE_UNAVAILABLE", "The Worker source is absent or failed integrity.", 409) from None

    def acquire(self, identifier, url):
        folder = self.reserve(identifier, 2*1024**3)
        try:
            if (folder / "source.json").exists():
                _, record = self.source(identifier)
                if record.get("source_url") != url:
                    raise DomainError("SOURCE_CONFLICT", "Worker job source is immutable.", 409)
                return record
            temporary = folder / "source.receiving"
            with temporary.open("wb") as output:
                record = self.fetcher.get(url, output)
            temporary.replace(folder / "source")
            record.update(name="source.html" if record["mime"] == "text/html" else "source", source_url=url)
            atomic_json(folder / "source.json", record)
            return record
        finally:
            self.active = None

    async def receive(self, identifier, request):
        try:
            size = int(request.headers.get("content-length", ""))
            expected = request.headers["x-source-sha256"]
            name = request.headers["x-source-name"]
            mime = request.headers.get("content-type", "application/octet-stream")
            if not re.fullmatch(r"[a-f0-9]{64}", expected) or len(name) > 512 or len(mime) > 128:
                raise ValueError
            # Names are UTF-8 in a hex transport field, never filesystem paths.
            name = bytes.fromhex(name).decode("utf-8")
        except (ValueError, KeyError, UnicodeError):
            raise DomainError("SOURCE_INVALID", "Worker source metadata is invalid.", 422) from None
        folder = self.reserve(identifier, size)
        try:
            if (folder / "source.json").exists():
                _, record = await asyncio.to_thread(self.source, identifier)
                if record["sha256"] != expected or record["size"] != size:
                    raise DomainError("SOURCE_CONFLICT", "Worker job source is immutable.", 409)
                return record
            content_hash, total = hashlib.sha256(), 0
            temporary = folder / "source.receiving"
            async with asyncio.timeout(900):
                with temporary.open("wb") as output:
                    iterator = request.stream().__aiter__()
                    while True:
                        try:
                            block = await asyncio.wait_for(iterator.__anext__(), 60)
                        except StopAsyncIteration:
                            break
                        total += len(block)
                        if total > size:
                            raise DomainError("SOURCE_SIZE_INVALID", "Worker source exceeds its reservation.", 413)
                        await asyncio.to_thread(output.write, block)
                        content_hash.update(block)
                    output.flush()
                    os.fsync(output.fileno())
            if total != size or content_hash.hexdigest() != expected:
                raise DomainError("SOURCE_INTEGRITY", "Worker source failed its length or digest check.", 422)
            temporary.replace(folder / "source")
            record = {"size": size, "sha256": expected, "name": name, "mime": mime}
            atomic_json(folder / "source.json", record)
            return record
        except TimeoutError:
            raise DomainError("SOURCE_TIMEOUT", "Worker upload exceeded its deadline.", 408) from None
        finally:
            (folder / "source.receiving").unlink(missing_ok=True)
            self.active = None

    def sandbox(self, folder, *, mode="extract", proxy_port=None):
        environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONPATH": "/app/src",
                       "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(folder), "TMPDIR": str(folder),
                       "LANG": "C.UTF-8", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
        # stderr has a fixed generic wrapper failure; untrusted parser logging is
        # discarded rather than allowed to grow the service log or leak source bytes.
        command = [sys.executable, "-m", "mastermind.worker_sandbox", str(folder), mode]
        if proxy_port:
            command.append(str(proxy_port))
        process = subprocess.Popen(command,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    env=environment, close_fds=True, start_new_session=True)
        deadline = time.monotonic()+(900 if mode == "git" else 1200)
        try:
            while process.poll() is None:
                if self.stop.wait(0.2) or time.monotonic() > deadline:
                    raise DomainError("EXTRACTION_TIMEOUT", "The extraction sandbox exceeded its deadline.", 408)
                if mode == "git":
                    expanded = 0
                    for entries, path in enumerate(folder.rglob("*"), 1):
                        if path.is_file() and not path.is_symlink():
                            expanded += path.stat().st_size
                        if entries > 20000 or expanded > 12*1024**3:
                            raise DomainError("ARCHIVE_LIMIT", "Git work exceeded its file or expansion budget.", 413)
            if process.returncode != 0:
                raise DomainError("EXTRACTION_SANDBOX_FAILED", "The source extractor or its isolation boundary failed.", 422)
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)

    def git(self, identifier, url):
        from .crusher_access import public_url
        from .worker_proxy import public_proxy
        url = public_url(url)
        folder = self.reserve(identifier, 2*1024**3)
        try:
            if (folder / "source.json").exists():
                _, record = self.source(identifier)
                if record.get("source_url") != url:
                    raise DomainError("SOURCE_CONFLICT", "Worker job source is immutable.", 409)
                return record
            repository = folder / "repository"
            if repository.exists():
                remove_private_tree(repository, folder)
            atomic_json(folder / "git-plan.json", {"url": url})
            with public_proxy() as port:
                self.sandbox(folder, mode="git", proxy_port=port)
            (folder / "source.receiving").replace(folder / "source")
            record = {"source_url": url, "name": "repository.zip", "mime": "application/zip",
                      "size": (folder / "source").stat().st_size, "sha256": sha_file(folder / "source")}
            atomic_json(folder / "source.json", record)
            remove_private_tree(repository, folder)
            return record
        finally:
            self.active = None

    def extract(self, identifier):
        folder, record = self.source(identifier)
        with self.lock:
            if self.active is not None or self.readers.get(identifier):
                raise DomainError("WORKER_BUSY", "Another source operation is in progress.", 423)
            self.active = identifier
        try:
            extracted = folder / "extracted.json"
            if not extracted.exists():
                atomic_json(folder / "extraction-plan.json", {"path": str(folder / "source"),
                                                              "name": record["name"], "mime": record["mime"]})
                self.sandbox(folder)
            with open_under(folder, "extracted.json") as source:
                raw = source.read(4*1024**2+1)
            if len(raw) > 4*1024**2:
                raise DomainError("EXTRACTION_LIMIT", "Extractor output exceeded its bound.", 413)
            result = checked_json(raw)
            if "error" in result:
                raise DomainError(result["error"]["code"], result["error"]["message"], 422)
            return result
        except (OSError, ValueError, KeyError):
            raise DomainError("EXTRACTION_FAILED", "The extractor did not produce a valid bounded result.", 422) from None
        finally:
            self.active = None

    def cleanup(self, identifier):
        with self.lock:
            if self.active == identifier or self.readers.get(identifier):
                raise DomainError("WORKER_BUSY", "The active Worker job cannot be removed.", 423)
            folder = self.folder(identifier)
            if folder.exists():
                remove_private_tree(folder, self.directory)
        return {"removed": True}

    def render(self, identifier):
        from .worker_browser import render
        folder, record = self.source(identifier)
        with self.lock:
            if self.active is not None or self.readers.get(identifier):
                raise DomainError("WORKER_BUSY", "Another Worker operation is active.", 423)
            self.active = identifier
        try:
            result = render(folder, record, self.fetcher)
            atomic_json(folder / "rendered.json", result)
            return result
        finally:
            self.active = None


def create_app():
    worker = Worker(Path(os.environ.get("MASTERMIND_WORK_DIRECTORY", "/work")),
                    Path(os.environ.get("MASTERMIND_MODEL_DIRECTORY", "/opt/mastermind/model")),
                    Path(os.environ.get("MASTERMIND_MODEL_INVENTORY", "/app/embedding-model.lock.json")),
                    Path(os.environ.get("MASTERMIND_WORKER_TOKEN_FILE", "/run/mastermind/worker_token")))

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(asyncio.to_thread(worker.start))
        yield
        worker.stop.set()
        await task
        await asyncio.to_thread(worker.curator.close)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.worker = worker

    @app.exception_handler(DomainError)
    def error(request, value):
        return JSONResponse({"error": {"code": value.code, "message": str(value)}}, status_code=value.status)

    def private(request: Request):
        if not hmac.compare_digest(request.headers.get("authorization", ""),
                                   "Bearer " + read_credential_file(worker.credential_file)):
            raise DomainError("UNAUTHORIZED", "Private Worker authorization is required.", 401)

    async def body(request, limit=1024**2):
        raw = bytearray()
        async with asyncio.timeout(15):
            async for part in request.stream():
                if len(raw)+len(part) > limit:
                    raise DomainError("SIZE_LIMIT", "The Worker request exceeds its bound.", 413)
                raw.extend(part)
        try:
            value = checked_json(raw)
            if not isinstance(value, dict):
                raise TypeError
            return value
        except (ValueError, TypeError, UnicodeError):
            raise DomainError("INVALID_REQUEST", "A valid Worker request object is required.", 422) from None

    @app.get("/healthz", dependencies=[Depends(private)])
    def health():
        return {"ready": worker.ready, "version": __version__, "embeddings_ready": worker.embeddings.session is not None,
                "model_sha256": worker.embeddings.model_sha, "active": worker.active is not None}

    @app.post("/embeddings", dependencies=[Depends(private)])
    async def embeddings(request: Request):
        value = await body(request, 16*64*1024+4096)
        if set(value) - {"texts", "query"} or not isinstance(value.get("query", False), bool):
            raise DomainError("INVALID_REQUEST", "Embedding fields are invalid.", 422)
        with worker.lock:
            if worker.active is not None:
                raise DomainError("WORKER_BUSY", "Another Worker operation is active.", 423)
            worker.active = "embeddings"
        try:
            return await asyncio.to_thread(worker.embeddings.embed, value.get("texts"), query=value.get("query", False))
        finally:
            with worker.lock:
                worker.active = None

    @app.get("/curator/status", dependencies=[Depends(private)])
    def curator_status():
        return worker.curator.status()

    @app.post("/curator/assist", dependencies=[Depends(private)])
    async def curator_assist(request: Request):
        value = await body(request, 16*1024)
        with worker.lock:
            if worker.active is not None:
                raise DomainError("WORKER_BUSY", "Another Worker operation is active.", 423)
            worker.active = "curator"
        try:
            return await asyncio.to_thread(worker.curator.assist, value)
        finally:
            with worker.lock:
                worker.active = None

    @app.post("/chunks", dependencies=[Depends(private)])
    async def chunks(request: Request):
        value = await body(request, 8*1024**2*6+4096)
        if set(value) != {"text"} or not isinstance(value["text"], str) or len(value["text"].encode()) > 8*1024**2:
            raise DomainError("SIZE_LIMIT", "Chunking input exceeds one supported note.", 413)
        return {"chunks": await asyncio.to_thread(worker.embeddings.chunks, value["text"]),
                "model_sha256": worker.embeddings.model_sha}

    @app.post("/jobs/{identifier}/acquire", dependencies=[Depends(private)])
    async def acquire(identifier: str, request: Request):
        value = await body(request, 16*1024)
        if set(value) != {"url"} or not isinstance(value["url"], str):
            raise DomainError("INVALID_REQUEST", "Provide one public source URL.", 422)
        return await asyncio.to_thread(worker.acquire, identifier, value["url"])

    @app.post("/jobs/{identifier}/git", dependencies=[Depends(private)])
    async def git(identifier: str, request: Request):
        value = await body(request, 16*1024)
        if set(value) != {"url"} or not isinstance(value["url"], str):
            raise DomainError("INVALID_REQUEST", "Provide one public Git URL.", 422)
        return await asyncio.to_thread(worker.git, identifier, value["url"])

    @app.put("/jobs/{identifier}/source", dependencies=[Depends(private)])
    async def source(identifier: str, request: Request):
        return await worker.receive(identifier, request)

    @app.get("/jobs/{identifier}/source", dependencies=[Depends(private)])
    def media(identifier: str):
        with worker.lock:
            if worker.active == identifier:
                raise DomainError("WORKER_BUSY", "The selected source is being processed.", 423)
            folder, record = worker.source(identifier)
            worker.readers[identifier] = worker.readers.get(identifier, 0)+1
        def release():
            with worker.lock:
                worker.readers[identifier] -= 1
                if not worker.readers[identifier]:
                    del worker.readers[identifier]

        class LeasedStream(StreamingResponse):
            async def __call__(self, scope, receive, send):
                try:
                    await super().__call__(scope, receive, send)
                finally:
                    release()

        def blocks():
            with open_under(folder, "source") as stream:
                while block := stream.read(256*1024):
                    yield block
        return LeasedStream(blocks(), media_type=record["mime"], headers={"Content-Length": str(record["size"]),
                                                                              "X-Source-Sha256": record["sha256"]})

    @app.post("/jobs/{identifier}/extract", dependencies=[Depends(private)])
    def extract(identifier: str):
        return worker.extract(identifier)

    @app.post("/jobs/{identifier}/render", dependencies=[Depends(private)])
    def render(identifier: str):
        return worker.render(identifier)

    @app.delete("/jobs/{identifier}", dependencies=[Depends(private)])
    def remove(identifier: str):
        return worker.cleanup(identifier)

    return app
