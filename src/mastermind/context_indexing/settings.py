"""Owner configuration, bounded idempotency and canonical bootstrap for context-indexing."""
import copy
import re
import time
from pathlib import PurePosixPath

from ..errors import DomainError
from ..fs import resolve, sha_bytes
from .graph import Graph, Scope, digest
from .template import DEFAULT_PATH, DEFAULT_TEMPLATE, parse

DEFAULTS = {"revision": 0, "schema": "context-indexing.settings.v1", "output_dir": "root/crusher",
            "fallback_note": "root/pool.md", "template_path": DEFAULT_PATH, "curator_enabled": False}


class Settings:
    def __init__(self, service):
        self.service, self.state, self.vault = service, service.state, service.vault

    def get(self):
        return {**DEFAULTS, **copy.deepcopy(self.state.setting("context_indexing", {}))}

    def note(self, path):
        resolved = resolve(self.vault.config.vault, path)
        if resolved.suffix.lower() != ".md":
            raise DomainError("CONFIGURATION_PATH", "Select a Markdown note inside Vault.", 422)
        return self.vault.read(path)

    def check_identity(self, configuration, field):
        if self.state.setting("context_indexing_invalid_paths", {}).get(field) == configuration[field]:
            raise DomainError("CONFIGURATION_REBIND_REQUIRED", "The configured note was deleted. Explicitly choose it again.", 422)

    def fallback(self, configuration, graph=None, *, rebind=False):
        graph = graph or Graph(self.vault, Scope("crusher"))
        if not rebind:
            self.check_identity(configuration, "fallback_note")
        path = configuration["fallback_note"]
        try:
            self.note(path)
        except DomainError:
            raise DomainError("FALLBACK_INVALID", "The configured fallback note is unavailable.", 422) from None
        if path == graph.root or not graph.path(path) or path == configuration["template_path"]:
            raise DomainError("FALLBACK_INVALID", "The fallback note must be reachable from the graph root.", 422)
        note = graph.notes[path]
        if any(c in note["name"] for c in "[]#^|"):
            raise DomainError("FALLBACK_INVALID", "The fallback name cannot be represented as an internal link.", 422)
        return {"path": path, "sha256": note["sha"], "name": note["name"]}

    def validate(self, configuration, *, fields=None):
        if fields is None or "template_path" in fields:
            if fields is None:
                self.check_identity(configuration, "template_path")
            parse(self.note(configuration["template_path"]))
        if fields is None or "fallback_note" in fields:
            self.fallback(configuration, rebind=fields is not None)
        return {"valid": True}

    def change(self, data, *, dry_run=False):
        allowed = {"fallback_note", "template_path", "curator_enabled"}
        if not isinstance(data, dict) or set(data)-allowed-{"expected_revision", "operation_id"}:
            raise DomainError("INVALID_SETTINGS", "Use the supported context-indexing settings.", 422)
        changes = {k: v for k, v in data.items() if k in allowed}
        if "curator_enabled" in changes and type(changes["curator_enabled"]) is not bool:
            raise DomainError("INVALID_SETTINGS", "Enable Curator must be a boolean.", 422)
        if any(not isinstance(v, str) for k, v in changes.items() if k != "curator_enabled"):
            raise DomainError("INVALID_SETTINGS", "Note paths must be strings.", 422)
        if not dry_run and (type(data.get("expected_revision")) is not int or
                not isinstance(data.get("operation_id"), str) or
                not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", data["operation_id"])):
            raise DomainError("PRECONDITION_REQUIRED", "Provide the observed revision and a stable operation ID.", 428)
        # Coordinator first, then State: keep lock ordering consistent with canonical writes.
        with self.vault.coordinator.lock:
            current = self.get()
            operations = self.state.setting("context_indexing_operations", [])
            payload = digest(data)
            previous = next((v for v in operations if v["id"] == data.get("operation_id")), None)
            if previous and not dry_run:
                if previous["digest"] != payload:
                    raise DomainError("IDEMPOTENCY_CONFLICT", "Operation ID was used with different settings.", 409)
                return previous["result"]
            if not dry_run and current["revision"] != data["expected_revision"]:
                raise DomainError("SETTINGS_CONFLICT", "Settings changed in another session. Reload and retry.", 409)
            candidate = {**current, **changes}
            self.validate(candidate, fields=set(changes))
            if dry_run:
                return {"valid": True, "revision": current["revision"]}
            candidate["revision"] += 1
            with self.state.transaction():
                self.state.set_setting("context_indexing", candidate)
                invalid = self.state.setting("context_indexing_invalid_paths", {})
                for key in changes:
                    invalid.pop(key, None)
                self.state.set_setting("context_indexing_invalid_paths", invalid)
                operations.append({"id": data["operation_id"], "digest": payload, "result": candidate})
                self.state.set_setting("context_indexing_operations", operations[-32:])
        self.service.audit.emit("context_indexing.settings", actor="owner", context={"fields": sorted(changes)})
        return candidate

    def snapshot(self):
        with self.vault.coordinator.lock:
            configuration = self.get()
            self.check_identity(configuration, "template_path")
            template = parse(self.note(configuration["template_path"]))
            fallback = self.fallback(configuration)
            return {"configuration": configuration, "fallback": fallback, "template": template,
                    "timestamp": time.time(), "timezone": self.state.setting("shell", {}).get(
                        "timezone", self.service.config.timezone)}

    def bootstrap(self):
        """Idempotent canonical initialization; never invent a missing graph root."""
        with self.vault.coordinator.boundary() as operation_id:
            self.vault.index()
            config = self.get()
            for field in ("fallback_note", "template_path"):
                self.check_identity(config, field)
            root = self.state.setting("crusher_root", "root.md")
            original = self.note(root)
            changes, expected = {}, {}
            if self.state.setting("context_indexing") is None:
                existing = self.state.one("SELECT path FROM notes WHERE name_key='pool'")
                if existing:
                    config["fallback_note"] = existing["path"]
            for path, initial in ((config["template_path"], DEFAULT_TEMPLATE),
                                  (config["fallback_note"], "# pool\n\nЗаметки, ожидающие тематического размещения.\n")):
                if not resolve(self.vault.config.vault, path).exists():
                    self.vault.validate_destination(path)
                    changes[path], expected[path] = initial.encode(), None
            template_text = changes.get(config["template_path"])
            parse(template_text.decode() if template_text is not None else self.note(config["template_path"]))
            fallback = config["fallback_note"]
            graph = Graph(self.vault, Scope("crusher"))
            if not graph.path(fallback):
                if fallback not in changes:
                    raise DomainError("FALLBACK_INVALID", "Connect the selected fallback note to root before initialization.", 422)
                name = PurePosixPath(fallback).stem
                if any(c in name for c in "[]#^|"):
                    raise DomainError("FALLBACK_INVALID", "The fallback note name is unsupported.", 422)
                changes[root], expected[root] = (original.rstrip()+"\n\n[["+name+"]]\n").encode(), sha_bytes(original.encode())
            if changes:
                self.vault.coordinator.commit(changes, expected, {"context_indexing_bootstrap": True},
                                             inside_boundary=True, operation_id=operation_id)
                self.vault.index()
            # Empty output directory contains no data and is checked under the same writer boundary.
            resolve(self.vault.config.vault, config["output_dir"]).mkdir(parents=True, exist_ok=True)
            with self.state.transaction():
                if self.state.setting("context_indexing") is None:
                    config["revision"] = 1
                    self.state.set_setting("context_indexing", config)
                self.state.set_setting("context_indexing_schema", 1)
            self.validate(config)
            return self.get()
