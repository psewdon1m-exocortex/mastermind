"""Authoritative non-secret Shell preferences, telemetry and owner activity summaries."""
import math
import os
import re
import threading
import time
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psutil

from .errors import DomainError
from .fs import atomic_write
from .kernel import Kernel, checked_origin
from .secret_store import SHELL_BINDINGS

ORDERS = {
    "navigation": ["dashboard", "vault", "crusher", "analytics", "shares", "settings"],
    "dashboard": ["cpu", "ram", "disk", "uptime", "operations"],
    "analytics": ["heatmap", "connectedness", "notes", "edges", "broken"],
    "settings": ["appearance", "security", "backup", "updates", "logs"],
}


def accent(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise DomainError("INVALID_SETTINGS", "Use a six-digit accent color.", 422)
    channels = [int(value[i:i+2], 16)/255 for i in (1, 3, 5)]
    linear = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in channels]
    luminance = sum(a*b for a, b in zip(linear, (.2126, .7152, .0722)))
    if (luminance+.05)/.05 < 4.5:
        raise DomainError("ACCENT_CONTRAST", "The accent needs at least 4.5:1 contrast on black.", 422)
    return value.upper()


class Operator:
    def __init__(self, service):
        self.service, self.state = service, service.state
        self.metrics_lock = threading.Lock()
        self.cpu_sample = None
        self.metric_cache = None
        self.connection_lock = threading.Lock()
        self.connection_verified = False

    def connection(self):
        return {"url": self.service.kernel.origin, "state": "NOT_CONFIGURED" if not self.service.kernel.origin else
                "UNAVAILABLE" if self.service.kernel.failure else "VERIFIED" if self.connection_verified else "NOT_VERIFIED",
                "failure": self.service.kernel.failure,
                "verified_at": self.state.setting("kernel_verified_at"), "token_write_only": True}

    def change_connection(self, data):
        if set(data) not in ({"url"}, {"token"}, {"check"}) or data.get("check", True) is not True:
            raise DomainError("INVALID_CONNECTION", "Change the Kernel URL or replace its token in a separate action.", 422)
        with self.connection_lock, self.service.kernel.lock:
            origin = checked_origin(data["url"]) if "url" in data else self.service.kernel.origin
            if origin is None:
                raise DomainError("KERNEL_NOT_CONFIGURED", "Configure the Kernel URL first.", 409)
            token = data.get("token") if "token" in data else self.service.kernel.token()
            if not isinstance(token, str) or not token or len(token.encode()) > 128*1024 \
                    or any(ord(c) < 32 or ord(c) == 127 for c in token):
                raise DomainError("INVALID_CONNECTION", "The replacement service token is invalid.", 422)
            candidate = Kernel(origin, lambda: token, client=self.service.kernel.client)
            # A signed-shape Register snapshot alone does not prove Volt resolution.
            candidate.resolve([SHELL_BINDINGS["share_pepper_v1"]], fresh=True)
            if "token" in data:
                # Bootstrap credential exception: outside Vault, backup, SQLite and every public endpoint.
                # The protected parent is mounted as a directory so atomic rotation is immediately visible.
                atomic_write(self.service.kernel_credential, token.encode())
                self.service.auth.revoke()
            if "url" in data:
                self.state.set_setting("kernel_url", origin)
            self.service.kernel.origin = origin
            self.service.kernel.invalidate()
            self.service.kernel.failure = None
            self.connection_verified = True
            self.state.set_setting("kernel_verified_at", time.time())
            self.service.audit.emit("kernel.verify" if "check" in data else "kernel.rotate" if "token" in data else
                                    "kernel.configure", actor="owner", target="kernel")
            return {**self.connection(), "state": "VERIFIED"}

    def preferences(self):
        stored = self.state.setting("shell", {})
        return {"revision": stored.get("revision", 0), "accent": stored.get("accent", "#00A8FF"),
                "sidebar": stored.get("sidebar", "fixed"),
                "timezone": stored.get("timezone", self.service.config.timezone),
                "orders": {key: stored.get("orders", {}).get(key, values) for key, values in ORDERS.items()}}

    def change(self, data):
        if set(data) - {"revision", "accent", "sidebar", "timezone", "orders"} or type(data.get("revision")) is not int:
            raise DomainError("INVALID_SETTINGS", "Provide the current settings revision and supported fields.", 422)
        with self.state.transaction():
            current = self.preferences()
            if current["revision"] != data["revision"]:
                raise DomainError("SETTINGS_CONFLICT", "Settings changed in another session. Reload and retry.", 409)
            if "accent" in data:
                current["accent"] = accent(data["accent"])
            if "sidebar" in data:
                if data["sidebar"] not in ("fixed", "auto"):
                    raise DomainError("INVALID_SETTINGS", "Select a supported sidebar mode.", 422)
                current["sidebar"] = data["sidebar"]
            if "timezone" in data:
                try:
                    if not isinstance(data["timezone"], str) or len(data["timezone"]) > 128:
                        raise ValueError
                    ZoneInfo(data["timezone"])
                except (ValueError, ZoneInfoNotFoundError):
                    raise DomainError("INVALID_SETTINGS", "Use an installed IANA timezone.", 422) from None
                current["timezone"] = data["timezone"]
            if "orders" in data:
                if not isinstance(data["orders"], dict) or set(data["orders"]) - ORDERS.keys():
                    raise DomainError("INVALID_SETTINGS", "Unknown reorder collection.", 422)
                for key, values in data["orders"].items():
                    if not isinstance(values, list) or any(not isinstance(v, str) for v in values) \
                            or len(values) != len(ORDERS[key]) or set(values) != set(ORDERS[key]):
                        raise DomainError("INVALID_SETTINGS", "Include every collection item exactly once.", 422)
                    current["orders"][key] = values
            current["revision"] += 1
            self.state.set_setting("shell", current)
        self.service.audit.emit("settings.change", actor="owner", context={"fields": sorted(set(data)-{"revision"})})
        return current

    def metrics(self):
        with self.metrics_lock:
            now = time.monotonic()
            if self.metric_cache and now-self.metric_cache[0] < 2:
                return {**self.metric_cache[1], "uptime_seconds": now-self.service.started}
            result = {"sampled_at": time.time(), "cpu": None, "ram": None, "disk": None,
                      "uptime_seconds": now-self.service.started}
            try:
                cpu = psutil.cpu_times()
                # guest time is already included in user/nice on Linux.
                total = sum(cpu)-getattr(cpu, "guest", 0)-getattr(cpu, "guest_nice", 0)
                idle = cpu.idle + getattr(cpu, "iowait", 0)
                percent = None
                if self.cpu_sample:
                    delta = total-self.cpu_sample[0]
                    if delta > 0:
                        percent = min(100, max(0, 100*(1-(idle-self.cpu_sample[1])/delta)))
                self.cpu_sample = total, idle
                result["cpu"] = {"percent": percent, "cores": psutil.cpu_count(), "scope": "server"}
            except (OSError, psutil.Error):
                pass
            try:
                memory = psutil.virtual_memory()
                result["ram"] = {"total": memory.total, "available": memory.available,
                                 "used": memory.total-memory.available, "percent": memory.percent, "scope": "server"}
            except (OSError, psutil.Error):
                pass
            try:
                disk = os.statvfs(self.service.config.vault)
                total, available = disk.f_blocks*disk.f_frsize, disk.f_bavail*disk.f_frsize
                result["disk"] = {"total": total, "available": available, "used": total-available,
                                  "percent": 100*(total-available)/total if total else None,
                                  "scope": "canonical_vault_filesystem"}
            except (AttributeError, OSError):
                pass  # Linux statvfs is authoritative; unsupported hosts report unknown.
            self.metric_cache = now, result
            return result

    def analytics(self, first=None, last=None):
        zone = ZoneInfo(self.preferences()["timezone"])
        try:
            end = date.fromisoformat(last) if last else datetime.now(zone).date()
            start = date.fromisoformat(first) if first else end-timedelta(days=364)
            if not 0 <= (end-start).days <= 730:
                raise ValueError
        except (ValueError, TypeError):
            raise DomainError("INVALID_PERIOD", "Choose a calendar period of at most 731 days.", 422) from None
        lower = datetime.combine(start, datetime.min.time(), zone).timestamp()
        upper = datetime.combine(end+timedelta(days=1), datetime.min.time(), zone).timestamp()
        def local_day(stamp):
            return datetime.fromtimestamp(stamp, UTC).astimezone(zone).date().isoformat()
        # Aggregation runs in SQLite, retaining only the bounded displayed dates.
        with self.state.lock:
            self.state.db.create_function("mastermind_local_day", 1, local_day)
            rows = self.state.rows("SELECT mastermind_local_day(occurred_at) AS day,kind,COUNT(*) AS count "
                                   "FROM activity WHERE occurred_at>=? AND occurred_at<? "
                                   "GROUP BY day,kind", (lower, upper))
        days = {(start+timedelta(days=i)).isoformat(): {"count": 0, "kinds": {}}
                for i in range((end-start).days+1)}
        for row in rows:
            if row["day"] in days:
                days[row["day"]]["count"] += row["count"]
                days[row["day"]]["kinds"][row["kind"]] = row["count"]
        maximum = max(item["count"] for item in days.values())
        graph = self.service.vault.graph()
        return {"timezone": str(zone), "first": start.isoformat(), "last": end.isoformat(),
                "notes": len(graph["nodes"]), "edges": len(graph["edges"]), "broken": graph["broken"],
                "connectedness": graph["connectedness"], "max_activity": maximum,
                "days": [{"date": day, **item, "level": math.ceil(item["count"]/maximum*4) if maximum else 0}
                         for day, item in days.items()]}
