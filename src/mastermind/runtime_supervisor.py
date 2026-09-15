"""Private typed control plane for one pinned Obsidian process and its display."""
import ctypes
import hmac
import json
import os
import re
import secrets
import signal
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import psutil
import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from .bridge_artifacts import install_bridge_files
from .errors import DomainError
from .fs import atomic_json, resolve
from .secret_store import SecretStore


class Supervisor:
    def __init__(self):
        # Adopt double-forked/setsid plugin descendants instead of losing them to PID 1.
        # https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html
        if os.name != "posix" or ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
            raise DomainError("RUNTIME_ISOLATION", "Runtime could not establish descendant supervision.", 503)
        self.home = Path(os.environ.get("MASTERMIND_RUNTIME_HOME", "/home/mastermind"))
        self.vault = Path(os.environ.get("MASTERMIND_RUNTIME_VAULT", "/vault/current"))
        self.artifacts = Path(os.environ.get("MASTERMIND_BRIDGE_ARTIFACTS", "/app/bridge"))
        self.secrets = SecretStore(Path(os.environ.get("MASTERMIND_SECRET_DIRECTORY", "/run/mastermind")))
        self.lock = threading.RLock()
        self.obsidian = None
        self.display = None
        self.window_manager = None
        self.leases = set()
        self.allowed = False
        self.native_operation = None
        self.boot_id = secrets.token_hex(16)
        self.verifying = False

    def bridge(self, route, payload=None):
        try:
            with httpx.Client(timeout=30, trust_env=False) as client:
                response = client.request("POST" if payload is not None else "GET",
                    "http://127.0.0.1:8092" + route, json=payload,
                    headers={"Authorization": "Bearer " + self.secrets.read("bridge_token")})
                if response.status_code != 200:
                    raise DomainError("VAULT_BUSY", "Bridge could not verify the native editor state.", 423)
                return response.json()
        except httpx.HTTPError:
            raise DomainError("BRIDGE_UNAVAILABLE", "The native editor bridge is unavailable.", 503) from None

    def graphical_session(self):
        self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
        password = self.secrets.read("vnc_password")
        subprocess.run(["kasmvncpasswd", "-u", "mastermind", "-r", "-w", str(self.home / ".kasmpasswd")],
                       input=(password + "\n" + password + "\n").encode(), check=True, timeout=15,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.display = subprocess.Popen([
            "Xkasmvnc", ":1", "-geometry", "1440x900", "-depth", "24", "-nolisten", "tcp",
            "-httpd", "/usr/share/kasmvnc/www", "-websocketPort", "8090", "-interface", "0.0.0.0",
            "-KasmPasswordFile", str(self.home / ".kasmpasswd"), "-sslOnly", "0", "-AlwaysShared",
            "-SecurityTypes", "None",
            "-DLP_ClipAcceptMax", "8388608", "-DLP_ClipSendMax", "8388608", "-DLP_Log", "off",
            "-publicIP", "127.0.0.1", "-FrameRate", "30", "-RectThreads", "2",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.display.poll() is not None:
                raise DomainError("DISPLAY_UNAVAILABLE", "The graphical display exited during startup.", 503)
            probe = subprocess.run(["xdpyinfo", "-display", ":1"], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=2, check=False)
            if probe.returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise DomainError("DISPLAY_UNAVAILABLE", "The graphical display did not become ready.", 503)
        namespace = "http://openbox.org/3.4/rc"
        configuration = ET.parse("/etc/xdg/openbox/rc.xml")
        applications = configuration.getroot().find("{"+namespace+"}applications")
        if applications is None:
            applications = ET.SubElement(configuration.getroot(), "{"+namespace+"}applications")
        application = ET.SubElement(applications, "{"+namespace+"}application", {"class": "obsidian"})
        ET.SubElement(application, "{"+namespace+"}maximized").text = "yes"
        managed_config = self.home / "openbox-mastermind.xml"
        configuration.write(managed_config, encoding="utf-8", xml_declaration=True)
        self.window_manager = subprocess.Popen(["openbox", "--config-file", str(managed_config)], stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL, start_new_session=True)

    def install_bridge(self):
        install_bridge_files(self.vault, self.artifacts)
        profile = self.home / ".config/obsidian/obsidian.json"
        settings = json.loads(profile.read_text("utf-8")) if profile.exists() else {}
        settings.update({"vaults": {"mastermind": {"path": str(self.vault), "ts": int(time.time()*1000),
                                                  "open": True}}, "updateDisabled": True})
        atomic_json(profile, settings)

    def running(self):
        return self.obsidian is not None and self.obsidian.poll() is None

    def start(self):
        if self.running() or not self.allowed or self.leases:
            return
        self.verify_no_writers()
        if not self.vault.is_dir():
            raise DomainError("VAULT_UNAVAILABLE", "The canonical Vault is unavailable.", 503)
        self.install_bridge()
        env = {**os.environ, "DISPLAY": ":1", "HOME": str(self.home),
               "MASTERMIND_BRIDGE_TOKEN_FILE": str(self.secrets.directory / "bridge_token"),
               "MASTERMIND_BRIDGE_STATE": str(self.home / "bridge-state.json"),
               "MASTERMIND_START_PAUSED": "1" if self.verifying else "0"}
        # Obsidian community plugins already execute Node code. The Linux container
        # (non-root, no capabilities, no-new-privileges, private mounts/network) is
        # the isolation boundary; a setuid Chromium helper cannot elevate here.
        self.obsidian = subprocess.Popen([
            "/opt/obsidian/obsidian", "--no-sandbox", "--disable-dev-shm-usage",
            "--user-data-dir=" + str(self.home / ".config/obsidian"),
        ], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def wait_bridge(self, timeout=45):
        expected_version = json.loads((self.artifacts / "manifest.json").read_text("utf-8"))["version"]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.running():
                raise DomainError("RUNTIME_EXITED", "The official editor exited during startup.", 503)
            try:
                status = self.bridge("/status")
                if status.get("ready") and status.get("version") == expected_version and status.get("protocol_version") == 1:
                    return status
            except DomainError:
                pass
            time.sleep(0.25)
        raise DomainError("BRIDGE_UNAVAILABLE", "Bridge handshake timed out.", 503)

    def stop_verified(self, operation_id):
        if not self.running():
            if self.obsidian is not None:
                for process in psutil.process_iter(["pid", "status"]):
                    try:
                        if os.getpgid(process.pid) == self.obsidian.pid and process.status() != psutil.STATUS_ZOMBIE:
                            raise DomainError("VAULT_BUSY", "The editor exited with a surviving writer process.", 423)
                    except (ProcessLookupError, psutil.NoSuchProcess):
                        continue
            self.verify_no_writers()
            return
        # A preceding mutation resumes asynchronously. A new barrier must wait for
        # the new Bridge to load before asking it to save native buffers.
        self.wait_bridge()
        result = self.bridge("/quiesce", {"operation_id": operation_id})
        if result.get("buffers_verified") is not True:
            raise DomainError("VAULT_BUSY", "Native buffers were not confirmed saved.", 423)
        children = psutil.Process(self.obsidian.pid).children(recursive=True)
        os.killpg(self.obsidian.pid, signal.SIGTERM)
        try:
            self.obsidian.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(self.obsidian.pid, signal.SIGKILL)
            self.obsidian.wait(timeout=5)
        _, alive = psutil.wait_procs(children, timeout=5)
        for child in alive:
            if child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
                raise DomainError("VAULT_BUSY", "A descendant writer did not stop.", 423)
        self.verify_no_writers()
        return result.get("activity")

    def verify_no_writers(self):
        # Only the exact display and window-manager processes are exempt; their
        # arbitrary children are not. Docker health probes are outside this ancestry.
        trusted = {process.pid for process in (self.display, self.window_manager)
                   if process is not None and process.poll() is None}
        try:
            for process in psutil.Process().children(recursive=True):
                try:
                    if process.pid in trusted:
                        continue
                    if process.status() == psutil.STATUS_ZOMBIE:
                        try:
                            os.waitpid(process.pid, os.WNOHANG)
                        except ChildProcessError:
                            pass
                        continue
                    raise DomainError("VAULT_BUSY", "An adopted descendant writer is still running.", 423)
                except psutil.NoSuchProcess:
                    continue
        except psutil.AccessDenied:
            raise DomainError("VAULT_BUSY", "Runtime cannot verify every descendant writer.", 423) from None

    def status(self):
        status = {"state": "running" if self.running() else "stopped", "startup_allowed": self.allowed,
                  "paused": bool(self.leases), "display_ready": self.display is not None and self.display.poll() is None}
        if self.running():
            try:
                status["bridge"] = self.bridge("/status")
            except DomainError:
                status["bridge"] = {"ready": False}
        return status


def create_app():
    supervisor = Supervisor()

    @asynccontextmanager
    async def lifespan(app):
        supervisor.graphical_session()
        yield
        # Container shutdown never pretends an unverified dirty editor was flushed.
        for process in (supervisor.obsidian, supervisor.window_manager, supervisor.display):
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({"error": {"code": error.code, "message": str(error)}}, status_code=error.status)

    def authorized(request: Request):
        actual = request.headers.get("authorization", "")
        if not hmac.compare_digest(actual, "Bearer " + supervisor.secrets.read("runtime_token")):
            raise DomainError("UNAUTHORIZED", "Runtime authorization required.", 401)

    def operation(payload):
        value = payload.get("operation_id")
        if not isinstance(value, str) or not re.fullmatch("[a-zA-Z0-9_-]{1,64}", value):
            raise DomainError("INVALID_OPERATION", "A valid operation identity is required.", 422)
        return value

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/internal/status", dependencies=[Depends(authorized)])
    def status():
        with supervisor.lock:
            return supervisor.status()

    @app.get("/internal/lifecycle", dependencies=[Depends(authorized)])
    def lifecycle():
        # A health observer must not queue behind a long native quiesce/rename.
        if not supervisor.lock.acquire(blocking=False):
            return {"boot_id": supervisor.boot_id, "busy": True}
        try:
            return {"boot_id": supervisor.boot_id, "busy": False, "startup_allowed": supervisor.allowed,
                    "paused": bool(supervisor.leases) or supervisor.native_operation is not None,
                    "running": supervisor.running()}
        finally:
            supervisor.lock.release()

    @app.post("/internal/begin-recovery", dependencies=[Depends(authorized)])
    def begin_recovery():
        with supervisor.lock:
            activity = supervisor.stop_verified("startup")
            supervisor.allowed = False
            supervisor.leases.clear()
            supervisor.native_operation = None
            return {"state": "stopped", "activity": activity}

    @app.post("/internal/allow-start", dependencies=[Depends(authorized)])
    def allow_start():
        with supervisor.lock:
            supervisor.allowed = True
            supervisor.start()
            return supervisor.wait_bridge()

    @app.post("/internal/quiesce", dependencies=[Depends(authorized)])
    def quiesce(payload: dict):
        with supervisor.lock:
            identity = operation(payload)
            activity = supervisor.stop_verified(identity)
            supervisor.leases.add(identity)
            return {"state": "stopped", "operation_id": identity, "activity": activity}

    @app.post("/internal/resume", dependencies=[Depends(authorized)])
    def resume(payload: dict):
        with supervisor.lock:
            identity = operation(payload)
            supervisor.leases.discard(identity)
            supervisor.start()
            return supervisor.status()

    @app.post("/internal/verify-generation", dependencies=[Depends(authorized)])
    def verify_generation(payload: dict):
        with supervisor.lock:
            identity = operation(payload)
            if identity not in supervisor.leases:
                raise DomainError("VAULT_BUSY", "Generation verification requires the held write barrier.", 423)
            leases = set(supervisor.leases)
            original_vault = supervisor.vault
            try:
                copy = payload.get("vault_copy")
                if copy is not None:
                    if copy != ".verify-" + identity:
                        raise DomainError("INVALID_OPERATION", "Verification copy does not match its operation.", 422)
                    supervisor.vault = resolve(original_vault.parent, copy, internal=True)
                    if not supervisor.vault.is_dir():
                        raise DomainError("VAULT_UNAVAILABLE", "Verification copy is unavailable.", 503)
                supervisor.verifying = True
                supervisor.leases.clear()
                supervisor.allowed = True
                supervisor.start()
                status = supervisor.wait_bridge()
                supervisor.stop_verified(identity)
                return {"verified": True, "bridge_version": status.get("version"),
                        "obsidian_version": status.get("obsidian_version")}
            finally:
                # A failed handshake does not authorize writes beside a surviving editor.
                try:
                    if supervisor.running():
                        supervisor.stop_verified(identity)
                finally:
                    supervisor.vault = original_vault
                    supervisor.verifying = False
                    supervisor.leases = leases

    @app.post("/internal/open", dependencies=[Depends(authorized)])
    def open_note(payload: dict):
        with supervisor.lock:
            path = payload.get("path")
            resolve(supervisor.vault, path)
            supervisor.wait_bridge()
            return supervisor.bridge("/open", {"path": path})

    @app.post("/internal/native-prepare", dependencies=[Depends(authorized)])
    def native_prepare(payload: dict):
        with supervisor.lock:
            identity = operation(payload)
            if not supervisor.running() or supervisor.leases or supervisor.native_operation:
                raise DomainError("VAULT_BUSY", "Native editor is unavailable for a managed rename.", 423)
            checkpoint = supervisor.bridge("/quiesce", {"operation_id": identity})
            if checkpoint.get("buffers_verified") is not True:
                raise DomainError("VAULT_BUSY", "Native editor buffers are not saved.", 423)
            supervisor.native_operation = identity
            return checkpoint

    @app.post("/internal/rename", dependencies=[Depends(authorized)])
    def native_rename(payload: dict):
        with supervisor.lock:
            identity = operation(payload)
            if supervisor.native_operation != identity:
                raise DomainError("VAULT_BUSY", "Native rename has no prepared barrier.", 423)
            resolve(supervisor.vault, payload.get("old_path"))
            resolve(supervisor.vault, payload.get("new_path"))
            return supervisor.bridge("/native-rename", payload)

    @app.post("/internal/native-release", dependencies=[Depends(authorized)])
    def native_release(payload: dict):
        with supervisor.lock:
            identity = operation(payload)
            if supervisor.native_operation not in (identity, None):
                raise DomainError("VAULT_BUSY", "Another native operation holds the barrier.", 423)
            supervisor.native_operation = None
            supervisor.leases.discard(identity)
            if supervisor.running():
                supervisor.bridge("/unfreeze", {})
            supervisor.start()
            return supervisor.status()

    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=8091, access_log=False)
