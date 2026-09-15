"""Adopt a restarted supervisor only after Core repeats its recovery handshake."""
from .errors import DomainError


class RuntimeMonitor:
    def __init__(self, service):
        self.service = service
        self.boot = None
        self.failure = None

    def check(self):
        service = self.service
        if service.config.runtime_mode == "offline" or not service.ready or service.updates.blocks:
            return
        # Never interfere with an in-progress mutation, retained update barrier
        # or recovery. A later tick retries without changing the current lease.
        if not service.coordinator.lock.acquire(blocking=False):
            return
        try:
            service.data_ready()
            lifecycle = service.runtime.request("GET", "/internal/lifecycle", timeout=5)
            if lifecycle.get("busy") or lifecycle.get("paused"):
                return
            if not lifecycle.get("startup_allowed") or not lifecycle.get("running"):
                checkpoint = service.runtime.request("POST", "/internal/begin-recovery", {})
                if checkpoint.get("activity"):
                    service.activity.ingest(checkpoint["activity"])
                service.coordinator.recover()
                service.vault.index(force=True)
                service.dirty.flush()
                service.runtime.request("POST", "/internal/allow-start", {})
                service.audit.emit("runtime.reconnect", context={"new_supervisor": self.boot != lifecycle.get("boot_id")})
            self.boot = lifecycle.get("boot_id")
            self.failure = None
        except DomainError as error:
            if error.code not in ("NOT_READY", "UPDATE_IN_PROGRESS", "RECOVERY_REQUIRED"):
                self.failure = error.code
        finally:
            service.coordinator.lock.release()
