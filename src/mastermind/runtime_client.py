from contextlib import contextmanager

import httpx

from .errors import DomainError


class RuntimeClient:
    def __init__(self, config, token_reader=lambda: ""):
        self.config, self.token_reader = config, token_reader

    def request(self, method, route, payload=None, *, timeout=120):
        if not self.config.runtime_url:
            raise DomainError("RUNTIME_UNAVAILABLE", "Runtime supervisor is not configured.", 503)
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
        result = self.request("POST", "/internal/quiesce", {"operation_id": operation_id})
        if result.get("state") != "stopped":
            raise DomainError("VAULT_BUSY", "Runtime did not confirm stopped writers.", 423)
        try:
            yield result
        except Exception:
            if resume_if():
                self.request("POST", "/internal/resume", {"operation_id": operation_id})
            raise
        else:
            if resume_if():
                self.request("POST", "/internal/resume", {"operation_id": operation_id})

    def native_rename(self, old_path, new_path, operation_id):
        if self.config.runtime_mode == "offline":
            raise DomainError("RUNTIME_UNAVAILABLE", "Native rename requires official Obsidian.", 503)
        return self.request("POST", "/internal/rename",
                            {"old_path": old_path, "new_path": new_path, "operation_id": operation_id})
