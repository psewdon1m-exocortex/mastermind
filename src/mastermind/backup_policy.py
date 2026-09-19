"""Restorable scheduling intent, with a durable hold until explicit verification."""
from __future__ import annotations

import threading
import time
from copy import deepcopy
from uuid import UUID, uuid4

import httpx

from .errors import DomainError
from .secret_store import read_credential_file


class NeptuneError(DomainError):
    def __init__(self, message, status=503):
        super().__init__("BACKUP_POLICY_UNAVAILABLE", message, status)


JOURNAL_KEY = "_backup_policy_restore"


def validate_intent(value):
    if value is None:
        return None
    def interval(item, name, maximum):
        return isinstance(item, dict) and type(item.get("enabled")) is bool and type(item.get(name)) is int and 1 <= item[name] <= maximum
    if not isinstance(value, dict) or value.get("schema") != "exocortex.backup.intent.v1" or not interval(value.get("archive"), "intervalHours", 8760) or (
        value.get("mirror") is not None and not interval(value.get("mirror"), "intervalMinutes", 10080)
    ):
        raise ValueError("Invalid automatic-backup recovery policy")
    return {"schema": "exocortex.backup.intent.v1",
            "archive": {k: value["archive"][k] for k in ("enabled", "intervalHours")},
            "mirror": None if value.get("mirror") is None else {k: value["mirror"][k] for k in ("enabled", "intervalMinutes")},
            "sourceRevision": value.get("sourceRevision") if type(value.get("sourceRevision")) is int else None}


def restored_record(value):
    intent = validate_intent(value)
    return {"intent": intent, "requestId": str(uuid4()), "expectedRevision": None, "resume": None} if intent else None


class BackupPolicy:
    def __init__(self, client, store, configured):
        self.client, self.store, self.configured = client, store, configured
        self.lock = threading.Lock()

    def assert_export_ready(self):
        if self.store.backup_policy_pending():
            raise NeptuneError("Restored backup policy awaits verification; automatic export is paused", 409)

    def export_intent(self):
        pending = deepcopy(self.store.backup_policy_pending())
        if pending:
            return validate_intent(pending["intent"])
        if not self.configured():
            return None
        policy = self.client.policy()
        if policy.get("schema") != "exocortex.backup.policy.v1":
            raise NeptuneError("Upgrade Neptune and Saturn to the service policy protocol", 409)
        return validate_intent({"schema": "exocortex.backup.intent.v1", "archive": policy["archive"],
                                "mirror": policy.get("mirror"), "sourceRevision": policy["revision"]})

    def read(self):
        pending = deepcopy(self.store.backup_policy_pending())
        try:
            current = self.client.policy()
        except NeptuneError:
            if not pending:
                raise
            current = {"schema": "exocortex.backup.policy.v1", "revision": 0, "appliedRevision": 0, "observed": {}}
        if pending:
            current.update(archive=deepcopy(pending["intent"]["archive"]), mirror=deepcopy(pending["intent"]["mirror"]),
                           paused=True, restoredPending=True)
        return current

    def save_pending(self, pending, value):
        if not self.store.set_backup_policy_pending(value, expected_request_id=pending["requestId"]):
            raise NeptuneError("A newer restore changed the policy; review it before resuming", 409)

    def mutate(self, body):
        pending = deepcopy(self.store.backup_policy_pending())
        if not pending:
            return self.client.policy("PUT", body)
        try:
            UUID(body.get("requestId", ""))
            valid = body.get("kind") == "resume" and not set(body) - {"kind", "requestId", "expectedRevision"}
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise NeptuneError("Review and verify the restored policy before editing it", 409)
        if self.lock.locked():
            raise NeptuneError("Policy verification is already active", 409)
        with self.lock:
            current = self.client.policy()
            if pending["expectedRevision"] is None:
                pending["expectedRevision"] = current["revision"]
                self.save_pending(pending, pending)
            try:
                restored = self.client.policy("PUT", {"kind": "restore", "requestId": pending["requestId"],
                    "expectedRevision": pending["expectedRevision"], "archive": pending["intent"]["archive"], "mirror": pending["intent"]["mirror"]})
            except NeptuneError as error:
                if error.status == 409:
                    self.save_pending(pending, {**pending, "expectedRevision": None, "requestId": str(uuid4()), "resume": None})
                raise
            if pending["resume"] is None:
                pending["resume"] = {"kind": "resume", "requestId": body["requestId"], "expectedRevision": restored["revision"]}
            self.save_pending(pending, pending)
            verified = self.client.policy("PUT", pending["resume"])
            if verified.get("paused") or verified.get("revision") != verified.get("appliedRevision"):
                raise NeptuneError("Restored policy is not yet verified and applied", 409)
            self.save_pending(pending, None)
            return verified

    def runs(self, method="GET", body=None):
        if method != "GET":
            self.assert_export_ready()
        return self.client.policy(method, body, "/runs")


class PolicyTransport:
    def __init__(self, config):
        self.config = config

    def policy(self, method="GET", body=None, suffix=""):
        if suffix not in ("", "/runs") or method not in ("GET", "PUT", "POST"):
            raise ValueError("Unsupported policy operation")
        if not self.config.neptune_socket or not self.config.neptune_token_file:
            raise NeptuneError("Neptune is not configured")
        try:
            with httpx.Client(transport=httpx.HTTPTransport(uds=self.config.neptune_socket),
                    base_url="http://neptune", trust_env=False, follow_redirects=False,
                    timeout=httpx.Timeout(60, connect=3)) as client:
                headers = {"X-Neptune-Token": read_credential_file(self.config.neptune_token_file)}
                with client.stream(method, "/v1/projects/mastermind/policy" + suffix,
                        headers=headers, **({"json": body} if body is not None else {})) as response:
                    if response.status_code >= 400:
                        raise NeptuneError("Neptune rejected the policy operation; refresh its status before retrying", response.status_code)
                    data, deadline = bytearray(), time.monotonic() + 60
                    for block in response.iter_bytes(65536):
                        if len(data) + len(block) > 262144 or time.monotonic() > deadline:
                            raise ValueError("Unbounded policy response")
                        data.extend(block)
                    import json
                    result = json.loads(data)
                    if not isinstance(result, dict):
                        raise TypeError("Invalid policy response")
                    return result
        except (httpx.HTTPError, ValueError, TypeError, OSError):
            raise NeptuneError("Neptune returned no complete policy response") from None
