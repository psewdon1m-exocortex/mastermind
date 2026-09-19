"""Scoped Wyvern transport. Provider credentials never enter Core."""
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import wyvern_intent
from .backup import checked_json
from .errors import DomainError
from .fs import open_under


class Wyvern:
    def __init__(self, link_file=None, *, client=None, intent_state=None):
        self.link_file = Path(link_file or os.environ.get("MASTERMIND_WYVERN_LINK_FILE", "/run/wyvern-link/link.json"))
        self.client = client
        self.intent_state = intent_state
        self.last_status = None

    def link(self):
        try:
            with open_under(self.link_file.parent, self.link_file.name) as stream:
                raw = stream.read(4097)
            if len(raw) > 4096:
                raise ValueError
            value = checked_json(raw)
            if value.get("schema") != "exocortex.wyvern.link.v1" or not re.fullmatch(r"[a-f0-9]{64}", value.get("token", "")):
                raise ValueError
            for key in ("client_id", "instance_id"):
                if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value.get(key, "")):
                    raise ValueError
            if value.get("mode") == "local":
                if value.get("socket") != "/run/wyvern/client.sock" or value.get("url"):
                    raise ValueError
            elif value.get("mode") == "remote":
                origin = urlsplit(value.get("url", ""))
                if origin.scheme != "https" or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment or ".." in origin.path or value.get("socket"):
                    raise ValueError
            else:
                raise ValueError
            return value
        except (OSError, ValueError, TypeError, AttributeError):
            raise DomainError("WYVERN_NOT_CONFIGURED", "Connect this service to Wyvern in Settings.", 503) from None

    def call(self, method, route, *, data=None, content=None, headers=None, timeout=300):
        link = self.link()
        intent = wyvern_intent.read(self.intent_state)
        if intent and intent["state"] == "pending_verification" and route in ("/v1/generate", "/v1/count-tokens", "/v1/media"):
            observed = self.call("GET", "/v1/client", timeout=8)
            if not wyvern_intent.matches(intent, observed):
                raise DomainError("WYVERN_RESTORE_PENDING", "Confirm this service's restored Adapter bindings before LLM use.", 409)
        client = self.client or httpx.Client(
            base_url=link.get("url", "http://wyvern.local").rstrip("/") + "/",
            transport=httpx.HTTPTransport(uds=link["socket"]) if link["mode"] == "local" else None,
            trust_env=False, follow_redirects=False, timeout=httpx.Timeout(timeout, connect=5, pool=5))
        try:
            options = {"json": data} if data is not None else {"content": content} if content is not None else {}
            with client.stream(method, route.lstrip("/"), headers={**(headers or {}), "Authorization": "Bearer " + link["token"], "Accept-Encoding": "identity"}, **options) as response:
                if response.status_code == 410:
                    raise DomainError("WYVERN_MEDIA_EXPIRED", "The source media handle expired; upload it again.", 410)
                if response.status_code == 429 or response.status_code >= 500:
                    raise DomainError("PROVIDER_TRANSIENT", "Wyvern or its Adapter is temporarily unavailable.", 503)
                if response.status_code >= 400 or response.status_code < 200 or response.status_code >= 300:
                    raise DomainError("PROVIDER_REJECTED", "Wyvern rejected the request or its selected Adapter.", response.status_code if response.status_code in (401, 403, 409, 422) else 422)
                if response.headers.get("content-encoding", "identity") not in ("identity", ""):
                    raise ValueError
                raw, deadline = bytearray(), time.monotonic() + timeout
                for block in response.iter_bytes(65536):
                    if len(raw) + len(block) > 2*1024**2 or time.monotonic() > deadline:
                        raise ValueError
                    raw.extend(block)
                result = checked_json(raw)
                if not isinstance(result, dict):
                    raise TypeError
                return result
        except (httpx.HTTPError, OSError):
            raise DomainError("PROVIDER_TRANSIENT", "Wyvern connection failed or timed out.", 503) from None
        except (ValueError, TypeError, UnicodeError):
            raise DomainError("PROVIDER_RESPONSE_INVALID", "Wyvern returned an invalid bounded response.", 422) from None
        finally:
            if self.client is None:
                client.close()

    def status(self):
        try:
            link = self.link()
            status = self.call("GET", "/v1/client", timeout=8)
            if status.get("schema") != "exocortex.wyvern.client.v1" or status.get("client_id") != link["client_id"] or status.get("instance_id") != link["instance_id"]:
                raise DomainError("WYVERN_INCOMPATIBLE", "Wyvern returned another client identity.", 503)
            intent = wyvern_intent.read(self.intent_state)
            pending = bool(intent and intent["state"] == "pending_verification" and not wyvern_intent.matches(intent, status))
            self.last_status = {**status, "mode": link["mode"], "link_configured": True, "last_verified_at": datetime.now(UTC).isoformat(), "stale": False,
                    **({"llm_ready": False, "code": "WYVERN_RESTORE_PENDING", "recovery_intent": intent} if pending else {})}
            return self.last_status
        except DomainError as error:
            return {**(self.last_status or {}), "stale": True, "reachable": False, "client_linked": False, "llm_ready": False, "link_configured": error.code != "WYVERN_NOT_CONFIGURED", "code": error.code}

    def export_intent(self):
        retained = wyvern_intent.read(self.intent_state)
        if retained and retained["state"] == "pending_verification":
            return retained
        if not os.path.lexists(self.link_file):
            if retained and retained["state"] != "unconfigured":
                raise DomainError("WYVERN_BACKUP_UNAVAILABLE", "Wyvern is required to capture current function bindings.", 503)
            return {"schema": wyvern_intent.SCHEMA, "state": "unconfigured", "instance_id": None, "client_id": None, "revision": None, "bindings": {}}
        link = self.link()
        status = self.call("GET", "/v1/client", timeout=8)
        if status.get("schema") != "exocortex.wyvern.client.v1" or any(status.get(k) != link[k] for k in ("instance_id", "client_id")):
            raise DomainError("WYVERN_INCOMPATIBLE", "Wyvern returned another client identity.", 503)
        return wyvern_intent.from_status(status)

    def close(self):
        if self.client:
            self.client.close()
