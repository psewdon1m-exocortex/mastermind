from contextlib import contextmanager
from threading import Lock

import httpx

from .deadline import remaining
from .errors import DomainError


class RuntimeClient:
    def __init__(self, config, token_reader=lambda: ""):
        self.config, self.token_reader = config, token_reader
        self.pending_cancellations = set()
        self.cancellation_lock = Lock()

    def request(self, method, route, payload=None, *, timeout=120):
        if not self.config.runtime_url:
            raise DomainError("RUNTIME_UNAVAILABLE", "Runtime supervisor is not configured.", 503)
        if route == "/internal/quiesce":
            timeout = remaining(timeout)
        try:
            with httpx.Client(base_url=self.config.runtime_url, timeout=timeout, trust_env=False) as client:
                response = client.request(method, route, json=payload,
                                          headers={"Authorization": "Bearer " + self.token_reader()})
            if response.status_code >= 400:
                raise DomainError("VAULT_BUSY", "Runtime could not safely complete the operation.", 423)
            return response.json()
        except httpx.HTTPError:
            raise DomainError("RUNTIME_UNAVAILABLE", "Runtime supervisor is unavailable.", 503) from None

    def status(self):
        if self.config.runtime_mode == "offline":
            return {"state": "stopped", "mode": "offline"}
        return self.request("GET", "/internal/status")

    @contextmanager
    def pause(self, operation_id, resume_if=lambda: True):
        if self.config.runtime_mode == "offline":
            yield
            return
        self.reconcile_cancellations()
        try:
            result = self.request("POST", "/internal/quiesce", {"operation_id": operation_id})
            if result.get("state") != "stopped":
                raise DomainError("VAULT_BUSY", "Runtime did not confirm stopped writers.", 423)
        except Exception:
            # No caller mutation has started. A lost acceptance response must
            # not leave a lease permanently orphaned; cancellation also rejects
            # a quiesce request that reaches the supervisor after this request.
            if resume_if():
                try:
                    self.cancel_prepared_pause(operation_id)
                except DomainError:
                    pass  # The observer retries the exact identity after transport recovery.
            raise
        try:
            yield result
        except Exception:
            if resume_if():
                self.release_pause(operation_id)
            raise
        else:
            if resume_if():
                self.release_pause(operation_id)

    def cancel_prepared_pause(self, operation_id):
        with self.cancellation_lock:
            self.pending_cancellations.add(operation_id)
        self.reconcile_cancellations()

    def prepare_native(self, operation_id):
        self.reconcile_cancellations()
        try:
            return self.request("POST", "/internal/native-prepare", {"operation_id": operation_id})
        except Exception:
            try:
                self.cancel_prepared_pause(operation_id)
            except DomainError:
                pass
            raise

    def release_pause(self, operation_id, *, native=False):
        try:
            return self.request("POST", "/internal/native-release" if native else "/internal/resume", {"operation_id": operation_id})
        except DomainError:
            # The caller has already completed/rolled back its safe mutation.
            # An acknowledged cancellation is equivalent to the lost release.
            self.cancel_prepared_pause(operation_id)

    def reconcile_cancellations(self):
        with self.cancellation_lock:
            pending = tuple(self.pending_cancellations)
        for identity in pending:
            result = self.request("POST", "/internal/cancel-quiesce", {"operation_id": identity}, timeout=15)
            if result.get("cancelled") is not True:
                raise DomainError("VAULT_BUSY", "Runtime has not acknowledged a cancelled pause.", 423)
            with self.cancellation_lock:
                self.pending_cancellations.discard(identity)

    def native_rename(self, old_path, new_path, operation_id):
        if self.config.runtime_mode == "offline":
            raise DomainError("RUNTIME_UNAVAILABLE", "Native rename requires official Obsidian.", 503)
        return self.request("POST", "/internal/rename",
                            {"old_path": old_path, "new_path": new_path, "operation_id": operation_id})
