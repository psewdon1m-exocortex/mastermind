"""Bounded Register consumer. Resolved values never enter persistent state."""
import hashlib
import hmac
import ipaddress
import json
import re
import threading
import time
from urllib.parse import urlsplit

import httpx

from .backup import checked_json
from .errors import DomainError

REFERENCE = re.compile(r"volt://[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/[1-5]", re.IGNORECASE)
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*")
MAX_RESPONSE = 1024 * 1024


def checked_origin(value, *, loopback=True):
    try:
        url = urlsplit(value)
        port = url.port
        local = url.hostname == "localhost"
        try:
            local = local or ipaddress.ip_address(url.hostname or "").is_loopback
        except ValueError:
            pass
        if not url.hostname or url.username is not None or url.password is not None \
                or url.path not in ("", "/") or url.query or url.fragment \
                or url.scheme != "https" and not (loopback and local and url.scheme == "http") \
                or port is not None and not 1 <= port <= 65535 \
                or any(character.isspace() or ord(character) < 32 for character in value):
            raise ValueError
        return value.rstrip("/")
    except (ValueError, TypeError, AttributeError):
        raise DomainError("CONNECTION_INVALID", "Use an HTTPS origin or a local loopback HTTP origin.", 422) from None


def bounded_response(response, limit=MAX_RESPONSE):
    if response.status_code != 200:
        raise DomainError("DEPENDENCY_UNAVAILABLE", "The configured service could not complete this request.", 503)
    if response.headers.get("content-encoding", "identity") != "identity":
        raise DomainError("DEPENDENCY_INVALID", "The configured service returned an unsupported encoding.", 503)
    result = bytearray()
    deadline = time.monotonic() + 10
    for block in response.iter_bytes():
        if time.monotonic() > deadline:
            raise DomainError("DEPENDENCY_UNAVAILABLE", "The configured service exceeded its response deadline.", 503)
        if len(result) + len(block) > limit:
            raise DomainError("DEPENDENCY_INVALID", "The configured service exceeded its response bound.", 503)
        result.extend(block)
    try:
        return checked_json(result)
    except (ValueError, UnicodeError, RecursionError):
        raise DomainError("DEPENDENCY_INVALID", "The configured service returned invalid data.", 503) from None


class Kernel:
    def __init__(self, origin, token, *, client=None, clock=time.monotonic, ttl=60):
        self.origin = checked_origin(origin) if origin else None
        self.token = token
        self.clock, self.ttl = clock, min(300, max(1, ttl))
        self.client = client or httpx.Client(timeout=httpx.Timeout(5, connect=3), follow_redirects=False,
                                            trust_env=False, limits=httpx.Limits(max_connections=4))
        self.cache = {}
        self.lock = threading.RLock()
        self.failure = None

    def close(self):
        with self.lock:
            self.cache.clear()
            self.client.close()

    def invalidate(self):
        with self.lock:
            self.cache.clear()

    def _json(self, method, route, token, body=None):
        with self.client.stream(method, self.origin + route, headers={"Authorization": "Bearer " + token, "Accept-Encoding": "identity"},
                                **({"json": body} if body is not None else {})) as response:
            return bounded_response(response)

    @staticmethod
    def validate_snapshot(snapshot):
        if not isinstance(snapshot, dict) or snapshot.get("schema") != "exocortex.register.snapshot.v1" \
                or not isinstance(snapshot.get("values"), dict) or not isinstance(snapshot.get("checksum"), str):
            raise ValueError
        # Register keys are ASCII; Python's sort matches the producer's UTF-16 ordering for this schema.
        leaves = {}

        def walk(node, prefix="", depth=0):
            if depth > 20 or len(leaves) > 10000:
                raise ValueError
            for name, value in node.items():
                if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                    raise ValueError
                key = prefix + name
                if isinstance(value, dict):
                    walk(value, key + ".", depth + 1)
                elif isinstance(value, str) and REFERENCE.fullmatch(value):
                    leaves[key] = value
                else:
                    raise ValueError
        walk(snapshot["values"])
        canonical = json.dumps({"values": snapshot["values"]}, ensure_ascii=False,
                               separators=(",", ":"), sort_keys=True).encode()
        checksum = "sha256:" + hashlib.sha256(canonical).hexdigest()
        if not hmac.compare_digest(snapshot["checksum"], checksum):
            raise ValueError
        return leaves

    def resolve(self, keys, *, fresh=False):
        keys = tuple(dict.fromkeys(keys))
        if not 1 <= len(keys) <= 20 or any(not isinstance(key, str) or len(key) > 128 or not KEY.fullmatch(key) for key in keys):
            raise DomainError("REGISTER_KEYS_INVALID", "The requested configuration keys are invalid.", 422)
        with self.lock:
            now = self.clock()
            self.cache = {key: item for key, item in self.cache.items() if item[0] > now}
            if not fresh and all(key in self.cache and self.cache[key][0] > now for key in keys):
                return {key: self.cache[key][1] for key in keys}
            try:
                if not self.origin:
                    raise DomainError("KERNEL_NOT_CONFIGURED", "Kernel is not configured.", 503)
                token = self.token()
                references = self.validate_snapshot(self._json("GET", "/api/v1/register/snapshot", token))
                if any(key not in references for key in keys):
                    raise DomainError("REGISTER_KEY_MISSING", "A required shell configuration binding is missing.", 503)
                data = self._json("POST", "/api/v1/register/resolve", token, {"keys": keys})
                if not isinstance(data, dict) or data.get("schema") != "exocortex.register.resolution.v1":
                    raise ValueError
                values = data["values"]
                selected = {}
                for key in keys:
                    item = values[key]
                    value = item["value"]
                    if not isinstance(value, str) or len(value.encode()) > 128 * 1024 \
                            or type(item.get("secret")) is not bool or type(item.get("volt_revision")) is not int:
                        raise ValueError
                    selected[key] = value
                expires = self.clock() + self.ttl
                self.cache.update({key: (expires, value) for key, value in selected.items()})
                self.failure = None
                return selected
            except DomainError as error:
                self.failure = error.code
                raise
            except (httpx.HTTPError, ValueError, KeyError, TypeError, OSError, RecursionError):
                self.failure = "KERNEL_UNAVAILABLE"
                raise DomainError(self.failure, "Kernel could not resolve the required configuration.", 503) from None

    def origin_for(self, service):
        if service not in ("chronos", "saturn", "updater", "neptune"):
            raise ValueError("Unsupported discovery service")
        prefix = "services." + service
        values = self.resolve([prefix + ".sni", prefix + ".port"])
        host, port = values[prefix + ".sni"], values[prefix + ".port"]
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", host) \
                or not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= 65535:
            raise DomainError("REGISTER_ROUTE_INVALID", "The registered service route is invalid.", 503)
        return checked_origin("https://" + host + ":" + port, loopback=False)
