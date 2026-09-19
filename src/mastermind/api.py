import asyncio
import base64
import hmac
import json
import os
import secrets
import ssl
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from . import __version__
from .activity import Activity
from .audit import Audit
from .auth import Auth
from .backup import Backup, checked_json
from .config import Config
from .coordinator import Coordinator
from .crusher import Crusher
from .crusher_access import CrusherAccess
from .errors import DomainError
from .exports import Exports
from .fs import name_key, safe_relative, sha_bytes
from .integrations import Chronos, Neptune, resource_path
from .kernel import Kernel
from .locking import FileMutex
from .native_rename import NativeRename
from .references import excluded_spans, parse
from .restore import Restore
from .runtime_client import RuntimeClient
from .runtime_monitor import RuntimeMonitor
from .secret_store import ShellSecrets, read_credential_file
from .semantic import Semantic
from .shared import Shared, SharedConflict
from .state import State
from .updates import Updates
from .vault import Vault
from .watcher import DirtyJournal

OWNER_COOKIE = "__Host-mastermind_owner"
CSRF_COOKIE = "__Host-mastermind_csrf"


async def bounded_json(request, limit=64*1024):
    data = bytearray()
    try:
        async with asyncio.timeout(15):
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > limit:
                    raise DomainError("SIZE_LIMIT", "Request body exceeds this route's limit.", 413)
        result = checked_json(data)
        if not isinstance(result, dict):
            raise TypeError("Object required")
        return result
    except (ValueError, TypeError, UnicodeError):
        raise DomainError("INVALID_REQUEST", "A valid JSON object is required.", 422) from None
    except TimeoutError:
        raise DomainError("REQUEST_TIMEOUT", "Request body timed out.", 408) from None


def require_text(data, key):
    if not isinstance(data.get(key), str):
        raise DomainError("INVALID_REQUEST", "A text field is missing or invalid.", 422)
    return data[key]


class Service:
    def __init__(self, config):
        # Schema initialization is a write. Acquire leadership before opening
        # SQLite, not later in the asynchronous startup handshake.
        lease = FileMutex(config.home / "recovery" / "service.lock").acquire(timeout=0)
        lease.__enter__()
        try:
            self.initialize(config)
        except BaseException:
            for name in ("state", "kernel", "chronos"):
                value = getattr(self, name, None)
                if value is not None:
                    value.close()
            lease.__exit__(None, None, None)
            raise
        self.leader = lease

    def initialize(self, config):
        self.config = config
        self.state = State(config.state / "mastermind.sqlite3")
        credential_directory = config.credential_directory or config.home / "bootstrap-credentials"
        credential_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.kernel_credential = credential_directory / "kernel_token"
        def kernel_token():
            if self.kernel_credential.exists():
                return read_credential_file(self.kernel_credential)
            if config.kernel_token_file is None:
                raise DomainError("KERNEL_NOT_CONFIGURED", "Kernel identity is not configured.", 503)
            return read_credential_file(config.kernel_token_file)
        self.kernel = Kernel(self.state.setting("kernel_url", config.kernel_url), kernel_token, client=httpx.Client(
            verify=ssl.create_default_context(cafile=config.trust_ca_file), trust_env=False,
            timeout=httpx.Timeout(5, connect=3), follow_redirects=False,
            limits=httpx.Limits(max_connections=4)))
        self.secrets = ShellSecrets(config.secret_directory, self.kernel,
                                    development=config.test_mode or config.secret_backend == "development-files")
        self.neptune = Neptune(config)
        self.chronos = Chronos(self.kernel, self.secrets, ca_file=config.trust_ca_file)
        self.runtime = RuntimeClient(config, lambda: self.secrets.read("runtime_token"))
        self.coordinator = Coordinator(config, self.state, self.runtime)
        self.vault = Vault(config, self.state, self.coordinator)
        self.native = NativeRename(self.vault)
        self.audit = Audit(config, self.state)
        self.activity = Activity(self.state)
        self.coordinator.on_native_checkpoint = self.activity.ingest
        self.auth = Auth(self.state, self.audit)
        self.backup = Backup(config, self.state, self.coordinator, self.vault, self.secrets, self.audit)
        self.restore = Restore(self.backup, self.auth)
        self.dirty = DirtyJournal(config, self.state)
        self.exports = Exports(self.backup, self.dirty)
        self.coordinator.on_paused = self.dirty.flush
        self.stop_event = threading.Event()
        self.maintenance = None
        self.index_failure = None
        self.operation_audit_failure = None
        self.maintenance_failure = None
        self.ready = False
        self.failure = None
        self.started = time.monotonic()
        self.sockets = {}
        self.loop = None
        self.leader = None
        self.auth.revoke_listeners.append(self.close_sockets)
        self.restore.on_begin = lambda: self.close_sockets(None)
        self.updates = Updates(self)
        self.shared = Shared(self.vault, self.auth, self.secrets, self.audit, self.data_ready)
        self.crusher_access = CrusherAccess(config, self.state, self.auth, self.audit, self.data_ready)
        self.crusher = Crusher(self)
        self.semantic = Semantic(self)
        self.runtime_monitor = RuntimeMonitor(self)
        self.downloads = []
        self.download_lock = threading.Lock()

    def start_with_retry(self):
        delay = 1
        while not self.stop_event.is_set():
            try:
                self.start()
            except Exception:  # noqa: BLE001 — never leave an unobserved failed startup task with an empty diagnosis
                self.failure = self.failure or "STARTUP_FAILED"
                return
            if self.ready or self.failure not in {"RUNTIME_UNAVAILABLE", "KERNEL_UNAVAILABLE", "DEPENDENCY_UNAVAILABLE"}:
                return
            if self.stop_event.wait(delay):
                return
            delay = min(delay * 2, 30)

    def start(self):
        try:
            if self.config.runtime_mode != "offline":
                checkpoint = self.runtime.request("POST", "/internal/begin-recovery", {})
                if checkpoint.get("activity"):
                    self.activity.ingest(checkpoint["activity"])
            self.restore.recover()
            self.coordinator.recover()
            self.exports.reset()
            self.activity.expire()
            self.vault.index(force=True)
            self.dirty.flush()
            self.dirty.start()
            if self.state.setting("access_key_verifier") is None and self.secrets.available("bootstrap_access_key"):
                self.auth.initialize(self.secrets.read("bootstrap_access_key"))
            self.ready = self.state.setting("access_key_verifier") is not None
            self.maintenance = threading.Thread(target=self.maintain, name="mastermind-index", daemon=True)
            self.maintenance.start()
            self.failure = None
            self.updates.start()
            self.crusher.start()
            self.semantic.start()
            if self.config.runtime_mode != "offline" and not self.updates.blocks:
                try:
                    self.runtime.request("POST", "/internal/allow-start", {})
                except DomainError as error:
                    self.failure = error.code
                    self.audit.emit("runtime.start", outcome="error", context={"code": self.failure})
        except (DomainError, OSError) as error:
            self.failure = error.code if isinstance(error, DomainError) else "STORAGE_UNAVAILABLE"
            self.audit.emit("startup.check", outcome="error", context={"code": self.failure})

    def maintain(self):
        reconciled = time.monotonic()
        runtime_checked = time.monotonic()
        cleaned = time.monotonic()
        while not self.stop_event.wait(0.1):
            now = time.monotonic()
            due = now-reconciled >= 15*60
            try:
                pending = self.dirty.pending()
                if pending and (now-self.dirty.last_event >= 0.5 or now-self.dirty.first_event >= 5) or due:
                    with self.coordinator.lock:
                        self.dirty.flush()
                        self.vault.index(force=due)
                        self.index_failure = None
                    reconciled = now if due else reconciled
            except Exception as error:  # noqa: BLE001 — latch failure and keep the watcher alive for recovery
                self.index_failure = error.code if isinstance(error, DomainError) else "STORAGE_UNAVAILABLE"
                try:
                    self.dirty.record("*")
                except Exception:  # noqa: BLE001 — failed dirty-journal write must latch NOT_READY
                    self.dirty.failure = "DIRTY_JOURNAL_UNAVAILABLE"
            try:
                if now-cleaned >= 60:
                    self.activity.expire()
                    self.owner_operations.cleanup()
                    self.restore.cleanup()
                    self.updates.cleanup()
                    self.maintenance_failure = None
                    cleaned = now
            except Exception:  # noqa: BLE001 - retention failure must not kill the canonical watcher
                self.maintenance_failure = "MAINTENANCE_UNAVAILABLE"
                cleaned = now
            if now-runtime_checked >= 5:
                try:
                    self.runtime_monitor.check()
                except Exception:  # noqa: BLE001 - a failed observer must not stop the canonical watcher
                    self.runtime_monitor.failure = "RUNTIME_MONITOR_FAILED"
                runtime_checked = time.monotonic()

    def stop(self):
        self.stop_event.set()
        if hasattr(self, "owner_operations"):
            self.owner_operations.close()
        self.crusher.close()
        self.semantic.close()
        self.updates.close()
        if self.maintenance:
            self.maintenance.join(timeout=60)
        self.dirty.close()
        if self.leader:
            self.auth.revoke()
        self.state.close()
        self.kernel.close()
        self.chronos.close()
        if self.leader:
            self.leader.__exit__(None, None, None)
            self.leader = None

    def close_sockets(self, session_hash):
        if self.loop is None:
            return
        async def close():
            for key, sockets in list(self.sockets.items()):
                if session_hash is None or key == session_hash:
                    for socket in list(sockets):
                        try:
                            await socket.close(code=4401)
                        except (RuntimeError, WebSocketDisconnect, OSError):
                            pass  # A concurrently closed socket must not prevent revoking its peers.
        asyncio.run_coroutine_threadsafe(close(), self.loop)

    def data_ready(self):
        if self.updates.blocks:
            raise DomainError("UPDATE_IN_PROGRESS", "An update or rollback holds the data write barrier.", 423)
        if not self.ready or self.coordinator.recovery_required or self.dirty.failure \
                or self.index_failure not in (None, "VAULT_BUSY"):
            raise DomainError("NOT_READY", "Canonical data is not ready for this operation.", 503)

    def dictionary(self):
        current = {row["name_key"]: row["name"] for row in self.state.rows("SELECT name,name_key FROM notes")}
        history = [row["display"] for row in self.state.rows("SELECT display FROM reference_history WHERE kind='internal'")]
        saturn = [row["display"] for row in self.state.rows("SELECT display FROM reference_history WHERE kind='saturn'")]
        return current, history, saturn

    def vnc(self):
        source = urlsplit(self.config.runtime_url or "")
        if source.scheme not in ("http", "https") or not source.hostname:
            raise DomainError("RUNTIME_UNAVAILABLE", "Runtime is not configured.", 503)
        return source.scheme + "://" + source.hostname + ":8090"

    def vnc_headers(self):
        return {"Authorization": "Basic " + base64.b64encode(
            ("mastermind:" + self.secrets.read("vnc_password")).encode()).decode()}


def create_app(config=None, service=None):
    context = service or Service(config or Config.environment())

    @asynccontextmanager
    async def lifespan(app):
        context.loop = asyncio.get_running_loop()
        task = asyncio.create_task(asyncio.to_thread(context.start_with_retry))
        admin = None
        try:
            if os.name == "posix" and not context.config.test_mode:
                from .admin import start_admin
                admin = await start_admin(context)
            yield
        finally:
            context.stop_event.set()
            if admin:
                from .admin import stop_admin
                await stop_admin(context, admin)
            await task
            await context.neptune.close()
            await asyncio.to_thread(context.stop)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = context

    @app.middleware("http")
    async def headers(request, next_handler):
        response = await next_handler(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers.setdefault("X-Frame-Options", "DENY" if request.url.path.startswith("/s/") else "SAMEORIGIN")
        if request.url.path == "/assets/hash-worker.js":
            # A worker has its own response CSP. Firefox applies it to the
            # static sha256.js import; the default deny-all policy blocks it.
            # Permit same-origin modules only, retaining denied network/eval.
            response.headers.setdefault("Content-Security-Policy",
                "default-src 'none'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
        response.headers.setdefault("Content-Security-Policy", (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
        ) if not request.url.path.startswith("/runtime/") else (
            "default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; "
            "connect-src 'self' data:; worker-src 'self' blob:; frame-ancestors 'self'; base-uri 'none'; object-src 'none'"
        ))
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        extra = {"projection": error.projection} if isinstance(error, SharedConflict) else {}
        return JSONResponse({"error": {"code": error.code, "message": str(error)}, **extra}, status_code=error.status,
                            headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # FastAPI's default errors may echo supplied credentials or complete note bodies.
        return JSONResponse({"error": {"code": "INVALID_REQUEST", "message": "Request validation failed."}}, status_code=422)

    def owner(request: Request):
        session = context.auth.session(request.cookies.get(OWNER_COOKIE))
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            context.auth.csrf(session, request.headers.get("x-csrf-token"), request.headers.get("origin"),
                              context.config.public_url)
        return session

    def bridge(request: Request):
        if not hmac.compare_digest(request.headers.get("authorization", ""),
                                   "Bearer " + context.secrets.read("bridge_token")):
            raise DomainError("UNAUTHORIZED", "Bridge authorization required.", 401)

    owner_dependency = Depends(owner)

    from .shared_routes import install_shared
    install_shared(app, context, owner, bounded_json)
    from .crusher_routes import install_crusher
    install_crusher(app, context, owner, bounded_json)
    from .operator_routes import install_operator
    install_operator(app, context, owner, bounded_json)

    def agent_export(request: Request):
        configured = context.config.neptune_export_token_file
        if configured is None or not hmac.compare_digest(request.headers.get("authorization", ""),
                                                         "Bearer " + read_credential_file(configured)):
            raise DomainError("UNAUTHORIZED", "Neptune export authorization is required.", 401)
        context.data_ready()

    def updater_agent(request: Request):
        configured = context.config.updater_token_file
        if configured is None or not hmac.compare_digest(request.headers.get("authorization", ""),
                                                         "Bearer " + read_credential_file(configured)):
            raise DomainError("UNAUTHORIZED", "Updater authorization is required.", 401)

    def cookies(response, session):
        response.set_cookie(OWNER_COOKIE, session["token"], max_age=12*3600, secure=True, httponly=True,
                            samesite="strict", path="/")
        response.set_cookie(CSRF_COOKIE, session["csrf"], max_age=12*3600, secure=True, httponly=False,
                            samesite="strict", path="/")
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        ok = context.ready and not context.coordinator.recovery_required and not context.dirty.failure \
            and context.index_failure in (None, "VAULT_BUSY")
        return JSONResponse({"status": "ready" if ok else "not_ready"}, status_code=200 if ok else 503)

    @app.get("/robots.txt")
    def robots():
        return Response("User-agent: *\nDisallow: /\n", media_type="text/plain")

    @app.post("/api/auth/login")
    async def login(request: Request):
        if request.headers.get("origin") != context.config.public_url.rstrip("/"):
            raise DomainError("CSRF_REJECTED", "The login origin was not accepted.", 403)
        data = await bounded_json(request)
        session = await asyncio.to_thread(context.auth.login, data.get("access_key"), request.client.host)
        return cookies(JSONResponse({"authenticated": True, "csrf": session["csrf"],
                                     "expires_at": session["expires_at"]}), session)

    @app.get("/api/auth/session")
    def session(request: Request, current=owner_dependency):
        return {"authenticated": True, "expires_at": current["expires_at"], "csrf": request.cookies.get(CSRF_COOKIE)}

    @app.post("/api/auth/logout")
    def logout(request: Request, current=owner_dependency):
        context.auth.revoke(request.cookies.get(OWNER_COOKIE))
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(OWNER_COOKIE, secure=True, httponly=True, samesite="strict")
        response.delete_cookie(CSRF_COOKIE, secure=True, samesite="strict")
        return response

    @app.post("/api/auth/rotate")
    async def rotate(request: Request, current=owner_dependency):
        data = await bounded_json(request)
        if not isinstance(data.get("new_access_key"), str) or data.get("confirm_access_key") != data["new_access_key"]:
            raise DomainError("CONFIRMATION_MISMATCH", "Both new Access Key values must match exactly.", 422)
        session = await asyncio.to_thread(context.auth.rotate, data.get("current_access_key"),
                                           data.get("new_access_key"), request.cookies.get(OWNER_COOKIE))
        return cookies(JSONResponse({"authenticated": True, "csrf": session["csrf"]}), session)

    @app.get("/api/status", dependencies=[Depends(owner)])
    def status():
        try:
            runtime = context.runtime.status()
        except DomainError as error:
            runtime = {"state": "unavailable", "code": error.code}
        ok = context.ready and not context.coordinator.recovery_required and not context.index_failure \
            and not context.dirty.failure
        state = "NOT_READY" if not ok else "HEALTHY" if runtime.get("bridge", {}).get("ready") \
            and not context.maintenance_failure and not context.operation_audit_failure and not context.restore.last_warning else "DEGRADED"
        return {"status": state, "runtime": runtime, "failure": context.failure or context.index_failure or context.dirty.failure,
                "conflicts": context.vault.conflicts, "uptime_seconds": time.monotonic()-context.started,
                "semantic_index": context.semantic.status(), "runtime_failure": context.runtime_monitor.failure,
                "maintenance_failure": context.maintenance_failure, "audit_failure": context.operation_audit_failure,
                "restore_warning": context.restore.last_warning}

    @app.get("/api/search/semantic", dependencies=[Depends(owner)])
    def semantic_search(query: str, limit: int = 20):
        return context.semantic.search(query, limit)

    @app.get("/api/index/semantic", dependencies=[Depends(owner)])
    def semantic_status():
        return context.semantic.status()

    @app.post("/api/index/semantic/rebuild", dependencies=[Depends(owner)])
    async def semantic_rebuild(request: Request):
        data = await bounded_json(request)
        return await asyncio.to_thread(context.semantic.reindex, require_text(data, "model_sha256"))

    @app.get("/api/notes", dependencies=[Depends(owner)])
    def notes(query: str = "", limit: int = 100, offset: int = 0):
        context.data_ready()
        return context.vault.list(query, limit, offset)

    @app.get("/api/note", dependencies=[Depends(owner)])
    def note(path: str):
        context.data_ready()
        text = context.vault.read(path)
        digest = sha_bytes(text.encode("utf-8"))
        return JSONResponse({"path": path, "text": text, "sha256": digest}, headers={"ETag": '"'+digest+'"'})

    @app.post("/api/notes", dependencies=[Depends(owner)])
    async def create_note(request: Request):
        context.data_ready()
        data = await bounded_json(request, context.config.max_note_bytes + 64*1024)
        result = await asyncio.to_thread(context.vault.write, require_text(data, "path"), require_text(data, "text"),
                                          None, create=True)
        context.audit.emit("note.create", actor="owner", target=result["path"])
        return result

    @app.put("/api/note", dependencies=[Depends(owner)])
    async def edit_note(request: Request):
        context.data_ready()
        data = await bounded_json(request, context.config.max_note_bytes + 64*1024)
        result = await asyncio.to_thread(context.vault.write, require_text(data, "path"), require_text(data, "text"),
                                          data.get("expected_sha256"))
        context.audit.emit("note.edit", actor="owner", target=result["path"])
        return result

    @app.delete("/api/note", dependencies=[Depends(owner)])
    async def delete_note(request: Request):
        context.data_ready()
        data = await bounded_json(request)
        path = require_text(data, "path")
        await asyncio.to_thread(context.vault.delete, path, data.get("expected_sha256"))
        context.audit.emit("note.delete", actor="owner", target=path)
        return {"deleted": True}

    @app.get("/api/graph", dependencies=[Depends(owner)])
    def graph():
        context.data_ready()
        return context.vault.graph()

    @app.post("/api/note/rename", dependencies=[Depends(owner)])
    async def rename_note(request: Request):
        context.data_ready()
        data = await bounded_json(request)
        result = await asyncio.to_thread(context.native.rename, require_text(data, "old_path"),
                                          require_text(data, "new_path"), data.get("expected_sha256"))
        await asyncio.to_thread(context.audit.emit, "note.rename", actor="owner", target=result["path"])
        return result

    @app.post("/internal/bridge/rename", dependencies=[Depends(bridge)])
    async def bridge_rename(request: Request):
        return await rename_note(request)

    @app.post("/internal/bridge/path-version", dependencies=[Depends(bridge)])
    async def bridge_path_version(request: Request):
        context.data_ready()
        data = await bounded_json(request)
        return await asyncio.to_thread(context.native.version, require_text(data, "path"))

    @app.post("/internal/bridge/note/create", dependencies=[Depends(bridge)])
    async def bridge_create_note(request: Request):
        context.data_ready()
        data = await bounded_json(request)
        path = require_text(data, "path")
        result = await asyncio.to_thread(context.vault.write, path, "", None, create=True, metadata={"activity": {
            "id": secrets.token_hex(16), "kind": "CREATE", "path": path, "occurred_at": time.time()}})
        context.audit.emit("note.create", actor="owner", target=path)
        if context.config.runtime_mode != "offline":
            await asyncio.to_thread(context.runtime.request, "POST", "/internal/open", {"path": path})
        return result

    @app.post("/internal/bridge/note/delete", dependencies=[Depends(bridge)])
    async def bridge_delete_note(request: Request):
        return await delete_note(request)

    @app.post("/internal/bridge/native-intent", dependencies=[Depends(bridge)])
    async def native_intent(request: Request):
        data = await bounded_json(request, context.config.max_note_bytes*6+64*1024)
        return await asyncio.to_thread(context.native.intent, data)

    @app.get("/internal/bridge/graph", dependencies=[Depends(bridge)])
    def bridge_graph():
        context.data_ready()
        return {**context.vault.graph_projection(), "presentation": context.state.setting("graph_presentation", {})}

    @app.post("/internal/bridge/links", dependencies=[Depends(bridge)])
    async def bridge_links(request: Request):
        context.data_ready()
        data = await bounded_json(request)
        return await asyncio.to_thread(context.vault.links, require_text(data, "path"),
                                          "backlinks" if data.get("direction") == "backlinks" else "outgoing")

    @app.post("/internal/bridge/graph-presentation", dependencies=[Depends(bridge)])
    async def graph_presentation(request: Request):
        import math
        data = await bounded_json(request, 256*1024)
        value = {}
        for key in ("x", "y", "zoom"):
            number = data.get(key, 1 if key == "zoom" else 0)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) \
                    or (not 0.1 <= number <= 10 if key == "zoom" else abs(number) > 100000):
                raise DomainError("INVALID_SETTINGS", "Graph presentation is outside its supported range.", 422)
            value[key] = number
        for key in ("internal", "external"):
            if not isinstance(data.get(key, True), bool):
                raise DomainError("INVALID_SETTINGS", "Graph filters must be booleans.", 422)
            value[key] = data.get(key, True)
        positions = data.get("positions", {})
        if not isinstance(positions, dict) or len(positions) > 2000:
            raise DomainError("INVALID_SETTINGS", "Graph position limit exceeded.", 422)
        for path, pair in positions.items():
            safe_relative(path)
            if not isinstance(pair, list) or len(pair) != 2 or any(isinstance(v, bool)
                    or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 100000 for v in pair):
                raise DomainError("INVALID_SETTINGS", "Graph position is invalid.", 422)
        value["positions"] = positions
        await asyncio.to_thread(context.state.set_setting, "graph_presentation", value)
        return value

    @app.get("/api/logs", dependencies=[Depends(owner)])
    def logs(after: int | None = None, limit: int = 200):
        return context.audit.page(after, limit)

    @app.get("/internal/bridge/reference-dictionary", dependencies=[Depends(bridge)])
    async def reference_dictionary():
        context.data_ready()
        current, history, saturn = await asyncio.to_thread(context.dictionary)
        return {"current": current, "history": history, "saturn": saturn}

    @app.post("/internal/bridge/references", dependencies=[Depends(bridge)])
    async def references(request: Request):
        data = await bounded_json(request, context.config.max_note_bytes+64*1024)
        current, history, saturn = await asyncio.to_thread(context.dictionary)
        return [asdict(ref) for ref in await asyncio.to_thread(parse, require_text(data, "text"), current, history, saturn)]

    @app.post("/internal/bridge/suggest", dependencies=[Depends(bridge)])
    async def suggest(request: Request):
        data = await bounded_json(request, context.config.max_note_bytes+64*1024)
        text, query = require_text(data, "text"), require_text(data, "query")
        offset = data.get("offset", 0)
        if not isinstance(offset, int) or offset < 0:
            raise DomainError("INVALID_REQUEST", "Suggestion offset is invalid.", 422)
        # Editor offsets are UTF-16; parser offsets are Unicode code points.
        prefix = text.encode("utf-16-le")[:offset*2].decode("utf-16-le", errors="ignore")
        if any(start <= len(prefix) < end for start, end in excluded_spans(text)):
            return []
        if query.startswith("saturn:"):
            typed = query[7:].lstrip()
            if not typed or "root".startswith(typed):
                return [{"name": "saturn: root", "path": "root"}]
            if not typed.startswith("root/"):
                return []
            parent, _, beginning = typed.rpartition("/")
            result = await resources(resource_path(parent), limit=100)
            return [{"name": "saturn: " + entry["path"], "path": entry["path"]} for entry in result["entries"]
                    if name_key(entry["path"].rsplit("/", 1)[-1]).startswith(name_key(beginning))][:25]
        if query.startswith("chronos:"):
            identifier = query[8:].strip()
            if not identifier:
                return []
            try:
                card = await asyncio.to_thread(context.chronos.card, identifier)
                return [{"name": "chronos: " + identifier, "path": "Chronos · " + card["started_at"]}]
            except DomainError:
                return []
        if ":" in query:
            return []
        key = name_key(query)
        def rank(row):
            name = name_key(row["name"])
            if name.startswith(key):
                return 0
            if any(word.startswith(key) for word in name.split()):
                return 1
            if key in name:
                return 2
            iterator = iter(name)
            return 3 if all(character in iterator for character in key) else 4
        rows = await asyncio.to_thread(context.state.rows, "SELECT name,path FROM notes ORDER BY name_key")
        ranked = sorted(((rank(row), row) for row in rows), key=lambda pair: (pair[0], pair[1]["name"]))
        return [row for score, row in ranked if score < 4][:25]

    @app.post("/internal/bridge/events", dependencies=[Depends(bridge)])
    async def events(request: Request):
        data = await bounded_json(request, 128*1024)
        batch = data.get("events")
        if data.get("version") != __version__ or not isinstance(batch, list) or len(batch) > 100:
            raise DomainError("INVALID_ACTIVITY", "Bridge event envelope is invalid.", 422)
        return await asyncio.to_thread(context.activity.ingest, data)

    async def external_metadata(kind, target):
        context.data_ready()
        if kind == "chronos":
            return await asyncio.to_thread(context.chronos.card, target)
        if kind != "saturn":
            raise DomainError("REFERENCE_INVALID", "The external reference kind is invalid.", 422)
        metadata = await context.neptune.request("resource-metadata", resource_path(target))
        with context.state.transaction() as db:
            db.execute("INSERT OR IGNORE INTO reference_history VALUES('saturn',?,?)", (name_key(target), target))
        return {"kind": "saturn", **metadata}

    @app.get("/api/owner/external", dependencies=[owner_dependency])
    async def owner_external(kind: str, target: str):
        return await external_metadata(kind, target)

    @app.get("/api/owner/updates", dependencies=[owner_dependency])
    def update_status():
        return context.updates.public()

    @app.post("/api/owner/updates", dependencies=[owner_dependency])
    async def update_apply(request: Request):
        data = await bounded_json(request)
        return await asyncio.to_thread(context.updates.submit, require_text(data, "version"))

    @app.post("/api/internal/updater/confirm", dependencies=[Depends(updater_agent)])
    async def update_confirm(request: Request):
        return await asyncio.to_thread(context.updates.confirm, await bounded_json(request))

    @app.get("/api/owner/updates/rollback", dependencies=[owner_dependency])
    async def rollback_options():
        return await asyncio.to_thread(context.updates.rollback_options)

    @app.post("/api/owner/updates/rollback", dependencies=[owner_dependency])
    async def rollback_apply(request: Request):
        data = await bounded_json(request, 4096)
        return await asyncio.to_thread(context.updates.submit_rollback, require_text(data, "job_id"))

    @app.post("/api/internal/updater/functional", dependencies=[Depends(updater_agent)])
    async def update_functional(request: Request):
        data = await bounded_json(request)
        if not context.updates.blocks or data.get("request_id") != context.updates.record["request_id"]:
            raise DomainError("UPDATE_CONFLICT", "This update does not own the data barrier.", 409)
        def verify():
            identity = data["request_id"]
            context.runtime.request("POST", "/internal/quiesce", {"operation_id": identity})
            result = context.runtime.request("POST", "/internal/verify-generation", {"operation_id": identity})
            if result.get("verified") is not True:
                raise DomainError("RUNTIME_UNAVAILABLE", "Runtime failed functional verification.", 503)
            context.vault.index(force=True)
            if not context.config.worker_url:
                raise DomainError("WORKER_UNAVAILABLE", "Worker is not configured.", 503)
            with httpx.Client(base_url=context.config.worker_url, timeout=10, trust_env=False, follow_redirects=False) as worker, \
                    worker.stream("GET", "/healthz", headers={"Authorization": "Bearer " + context.secrets.read("worker_token")}) as response:
                payload = bytearray()
                for chunk in response.iter_bytes():
                    if response.status_code != 200 or len(payload) + len(chunk) > 65536:
                        raise DomainError("WORKER_UNAVAILABLE", "Worker failed functional verification.", 503)
                    payload.extend(chunk)
                health = json.loads(payload)
            if health.get("ready") is not True or health.get("version") != __version__:
                raise DomainError("WORKER_UNAVAILABLE", "Worker/model handshake did not match Core.", 503)
            context.updates.save(phase="FUNCTIONAL_PASSED")
            return {"verified": True, "version": __version__, "schema": 1, "vault": True, "worker": True,
                    "bridge_version": result.get("bridge_version"), "obsidian_version": result.get("obsidian_version"),
                    "model_sha256": health.get("model_sha256")}
        return await asyncio.to_thread(verify)

    class ExportResponse(StreamingResponse):
        def __init__(self, artifact, filename="mastermind-backup.zip"):
            self.artifact = artifact
            def chunks():
                deadline = time.monotonic() + 3600
                with artifact["path"].open("rb") as source:
                    while block := source.read(1024 * 1024):
                        if time.monotonic() > deadline:
                            raise DomainError("EXPORT_TIMEOUT", "The export transfer exceeded its deadline.", 408)
                        yield block
            super().__init__(chunks(), media_type="application/zip", headers={
                "Content-Length": str(artifact["size"]), "ETag": '"' + artifact["sha256"] + '"',
                "X-Mastermind-Generation": str(artifact["generation"]), "X-Content-SHA256": artifact["sha256"],
                "Content-Disposition": 'attachment; filename="' + filename + '"'})

        async def __call__(self, scope, receive, send):
            try:
                await super().__call__(scope, receive, send)
            finally:
                await asyncio.shield(asyncio.to_thread(context.exports.release, self.artifact["snapshot_id"]))

    @app.post("/api/exports/portable", dependencies=[Depends(owner)])
    async def portable_export():
        context.data_ready()
        preparation = asyncio.create_task(asyncio.to_thread(context.exports.prepare, "portable"))
        try:
            artifact = await asyncio.shield(preparation)
        except asyncio.CancelledError:
            def release(task):
                if not task.cancelled() and task.exception() is None:
                    context.exports.release(task.result()["snapshot_id"])
            preparation.add_done_callback(release)
            raise
        context.audit.emit("vault.export", target="portable_copy", context={"generation": artifact["generation"]})
        return ExportResponse(artifact, "mastermind-vault.zip")

    @app.post("/api/internal/neptune/{kind}", dependencies=[Depends(agent_export)])
    async def neptune_export(kind: str, request: Request):
        kind = "archive" if kind == "backup" else kind
        if kind not in ("archive", "mirror"):
            raise DomainError("EXPORT_INVALID", "The Neptune export purpose is invalid.", 422)
        if request.headers.get("x-neptune-purpose") != kind:
            raise DomainError("FORBIDDEN", "The Neptune export purpose was not accepted.", 403)
        preparation = asyncio.create_task(asyncio.to_thread(context.exports.prepare, kind))
        try:
            artifact = await asyncio.shield(preparation)
        except asyncio.CancelledError:
            def abandoned(task):
                if not task.cancelled() and task.exception() is None:
                    asyncio.create_task(asyncio.to_thread(context.exports.release, task.result()["snapshot_id"]))
            preparation.add_done_callback(abandoned)
            raise
        return ExportResponse(artifact)

    @app.post("/api/internal/neptune/{kind}/receipt", dependencies=[Depends(agent_export)])
    async def neptune_receipt(kind: str, request: Request):
        kind = "archive" if kind == "backup" else kind
        if request.headers.get("x-neptune-purpose") != kind:
            raise DomainError("FORBIDDEN", "The Neptune receipt purpose was not accepted.", 403)
        data = await bounded_json(request)
        return await asyncio.to_thread(context.exports.receipt, kind, data)

    @app.post("/internal/bridge/external/open", dependencies=[Depends(bridge)])
    async def bridge_external(request: Request):
        data = await bounded_json(request)
        return await external_metadata(require_text(data, "kind"), require_text(data, "target"))

    @app.post("/internal/bridge/external/download", dependencies=[Depends(bridge)])
    async def bridge_download(request: Request):
        import secrets
        data = await bounded_json(request)
        target = resource_path(require_text(data, "target"))
        metadata = await external_metadata("saturn", target)
        if metadata["type"] != "file":
            raise DomainError("RESOURCE_INVALID", "Select one file to download.", 422)
        with context.download_lock:
            context.downloads = [item for item in context.downloads if item["expires_at"] > time.time()]
            if len(context.downloads) >= 20:
                raise DomainError("RESOURCE_BUSY", "Download preparation queue is full.", 429)
            context.downloads.append({"id": secrets.token_hex(16), "path": target, "expires_at": time.time()+300})
        return {"prepared": True}

    @app.get("/api/runtime/downloads", dependencies=[owner_dependency])
    def runtime_downloads():
        with context.download_lock:
            context.downloads = [item for item in context.downloads if item["expires_at"] > time.time()]
            return list(context.downloads)

    @app.get("/api/owner/resources", dependencies=[owner_dependency])
    @app.get("/internal/bridge/resources", dependencies=[Depends(bridge)])
    async def resources(path: str = "root", limit: int = 100, cursor: str | None = None):
        context.data_ready()
        result = await context.neptune.request("resources", path, limit=limit, cursor=cursor)
        with context.state.transaction() as db:
            for entry in result["entries"]:
                db.execute("INSERT OR IGNORE INTO reference_history VALUES('saturn',?,?)", (name_key(entry["path"]), entry["path"]))
        return result

    class ResourceResponse(StreamingResponse):
        def __init__(self, upstream):
            self.upstream = upstream
            headers = {key: value for key, value in upstream.headers.items()
                       if key.lower() in ("content-length", "etag", "accept-ranges", "content-range", "last-modified")}
            headers["Content-Disposition"] = "attachment"
            super().__init__(context.neptune.stream(upstream), status_code=upstream.status_code,
                             media_type=upstream.headers.get("content-type", "application/octet-stream"), headers=headers)

        async def __call__(self, scope, receive, send):
            try:
                await super().__call__(scope, receive, send)
            finally:
                await asyncio.shield(context.neptune.release(self.upstream))

    @app.get("/api/owner/resources/content", dependencies=[owner_dependency])
    @app.get("/internal/bridge/resources/content", dependencies=[Depends(bridge)])
    async def resource_content(request: Request, path: str):
        context.data_ready()
        headers = {}
        for name in ("Range", "If-Range"):
            values = request.headers.getlist(name)
            if len(values) > 1:
                raise DomainError("INVALID_REQUEST", "Repeated conditional headers are invalid.", 422)
            if values:
                headers[name] = values[0]
        upstream = await context.neptune.request("resource-content", path, headers=headers)
        return ResourceResponse(upstream)

    @app.get("/runtime/{path:path}", dependencies=[Depends(owner)])
    async def runtime_http(path: str):
        context.data_ready()
        if context.restore.active:
            raise DomainError("RESTORE_IN_PROGRESS", "The Vault is being restored.", 423)
        safe_relative(path)
        if path != "index.html" and not path.startswith("assets/"):
            raise DomainError("NOT_FOUND", "Runtime resource not found.", 404)
        client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5), trust_env=False)
        try:
            request = client.build_request("GET", context.vnc()+"/"+path, headers=context.vnc_headers())
            upstream = await client.send(request, stream=True)
            if upstream.status_code != 200:
                await upstream.aclose()
                raise DomainError("RUNTIME_UNAVAILABLE", "Runtime resource is unavailable.", 503)
        except (httpx.HTTPError, DomainError):
            await client.aclose()
            raise DomainError("RUNTIME_UNAVAILABLE", "Runtime resource is unavailable.", 503) from None
        async def chunks():
            try:
                async for chunk in upstream.aiter_bytes(256*1024):
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()
        return StreamingResponse(chunks(), media_type=upstream.headers.get("content-type", "application/octet-stream"))

    @app.websocket("/runtime/websockify")
    async def runtime_websocket(socket: WebSocket):
        try:
            session = await asyncio.to_thread(context.auth.session, socket.cookies.get(OWNER_COOKIE))
            context.data_ready()
            if context.restore.active:
                raise DomainError("RESTORE_IN_PROGRESS", "The Vault is being restored.", 423)
            if socket.headers.get("origin") != context.config.public_url.rstrip("/"):
                raise DomainError("UNAUTHORIZED", "Runtime origin rejected.", 403)
            key = session["token_hash"]
            if sum(map(len, context.sockets.values())) >= 4:
                raise DomainError("RATE_LIMITED", "Runtime connection limit reached.", 429)
            # Reserve before the upstream handshake yields control to another connection.
            context.sockets.setdefault(key, set()).add(socket)
        except DomainError:
            await socket.close(code=4401)
            return
        protocols = [p.strip() for p in socket.headers.get("sec-websocket-protocol", "").split(",") if p.strip()]
        protocols = [p for p in protocols if p in ("binary", "base64")]
        try:
            async with connect(context.vnc().replace("http", "ws", 1)+"/websockify", subprotocols=protocols,
                               additional_headers=context.vnc_headers(), origin=context.config.public_url,
                               proxy=None, max_size=16*1024**2, ping_interval=None,
                               max_queue=2, compression=None) as upstream:
                # Pinned Xkasmvnc does not implement WebSocket Pong. A transport
                # keepalive would disconnect a healthy VNC stream after 40 seconds.
                # Browser-side WebSocket keepalive and the session guard remain active.
                try:
                    await asyncio.to_thread(context.auth.session, socket.cookies.get(OWNER_COOKIE))
                except DomainError:
                    await socket.close(code=4401)
                    return
                await socket.accept(subprotocol=upstream.subprotocol)
                async def incoming():
                    while True:
                        message = await socket.receive()
                        if message["type"] == "websocket.disconnect":
                            return
                        await upstream.send(message.get("bytes") if message.get("bytes") is not None else message["text"])
                async def outgoing():
                    async for message in upstream:
                        if isinstance(message, bytes):
                            await socket.send_bytes(message)
                        else:
                            await socket.send_text(message)
                async def session_guard():
                    while True:
                        await asyncio.sleep(1)
                        try:
                            await asyncio.to_thread(context.auth.session, socket.cookies.get(OWNER_COOKIE))
                        except DomainError:
                            await socket.close(code=4401)
                            return
                tasks = [asyncio.create_task(fn()) for fn in (incoming, outgoing, session_guard)]
                try:
                    completed, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in completed:
                        if not task.cancelled() and task.exception() is not None:
                            failure = task.exception()
                            context.audit.emit("runtime.connection.closed", context={
                                "category": type(failure).__name__,
                                "received_code": getattr(getattr(failure, "rcvd", None), "code", None),
                                "sent_code": getattr(getattr(failure, "sent", None), "code", None)})
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except (WebSocketException, WebSocketDisconnect, httpx.HTTPError, OSError) as error:
            context.audit.emit("runtime.connection.failed", outcome="error", context={"category": type(error).__name__})
        finally:
            context.sockets.get(key, set()).discard(socket)
            try:
                await socket.close()
            except (RuntimeError, WebSocketDisconnect, OSError):
                pass

    return app
