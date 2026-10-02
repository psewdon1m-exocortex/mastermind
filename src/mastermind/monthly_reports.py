"""Narrow Chronos report ingress; ordinary Vault notes remain the source of truth."""
import re

import yaml

from .errors import DomainError
from .fs import safe_relative, sha_bytes
from .references import parse

SLOT = re.compile(r"\{\{([^{}\n]+)\}\}")
ALLOWED_SLOTS = {
    "chronos.month", "chronos.month_title", "chronos.timezone", "chronos.period",
    "chronos.total", "chronos.days", "chronos.coverage",
    "chronos.category_chart", "chronos.category_table",
    "chronos.daily_chart", "chronos.daily_table",
}
REQUIRED_SLOTS = {"chronos.month", "chronos.timezone", "chronos.total", "chronos.category_chart", "chronos.daily_chart"}


def _references(service, text):
    current, history, saturn = service.dictionary()
    names = {row["name_key"]: row["path"] for row in service.state.rows("SELECT name_key,path FROM notes")}
    refs = parse(text, current, history, saturn)
    if len(refs) != 1 or refs[0].kind != "internal" or not text[refs[0].start:refs[0].end].startswith("@") \
            or not refs[0].exists or refs[0].target not in names:
        raise DomainError("REPORT_LINK_INVALID", "The template must contain one valid @note reference.", 422)
    return names[refs[0].target]


def template_info(service, path):
    service.data_ready()
    path = safe_relative(path)
    if not path.startswith("root/templates/") or not path.lower().endswith(".md"):
        raise DomainError("REPORT_TEMPLATE_INVALID", "Select a Markdown note under root/templates.", 422)
    service.vault.index()
    text = service.vault.read(path)
    if len(text.encode("utf-8")) > 64 * 1024 or "\0" in text:
        raise DomainError("REPORT_TEMPLATE_INVALID", "The report template exceeds 64 KiB.", 422)
    slots = SLOT.findall(text)
    if len(slots) != len(set(slots)) or not REQUIRED_SLOTS <= set(slots) or set(slots) - ALLOWED_SLOTS \
            or "{{" in SLOT.sub("", text) or "}}" in SLOT.sub("", text):
        raise DomainError("REPORT_TEMPLATE_INVALID", "The report template has unsupported placeholders.", 422)
    front = re.match(r"\A---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|\Z)", text)
    try:
        metadata = yaml.safe_load(front[1]) if front else None
    except yaml.YAMLError:
        metadata = None
    if not isinstance(metadata, dict) or metadata.get("period") != "{{chronos.month}}" \
            or metadata.get("timezone") != "{{chronos.timezone}}":
        raise DomainError("REPORT_TEMPLATE_INVALID", "The template needs period and timezone frontmatter placeholders.", 422)
    anchor = _references(service, text)
    return {"path": path, "text": text, "sha256": sha_bytes(text.encode("utf-8")), "anchor": anchor}


def create_report(service, data):
    if not isinstance(data, dict) or set(data) != {"month", "timezone", "template_path", "template_sha256", "text"}:
        raise DomainError("INVALID_REQUEST", "A complete monthly report is required.", 422)
    month, body = data["month"], data["text"]
    if not isinstance(month, str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month) \
            or not isinstance(body, str) or not body or len(body.encode("utf-8")) > min(service.config.max_note_bytes, 256 * 1024):
        raise DomainError("REPORT_INVALID", "The report month or Markdown body is invalid.", 422)
    path = f"Chronos {month}.md"
    digest = sha_bytes(body.encode("utf-8"))
    with service.coordinator.lock:
        service.data_ready()
        try:
            existing = service.vault.read(path)
        except DomainError as error:
            if error.code != "NOT_FOUND":
                raise
        else:
            if sha_bytes(existing.encode("utf-8")) == digest:
                return {"path": path, "sha256": digest, "created": False}
            raise DomainError("REPORT_EXISTS", "The monthly report already exists with different content.", 409)
        info = template_info(service, data["template_path"])
        if not isinstance(data["template_sha256"], str) or info["sha256"] != data["template_sha256"]:
            raise DomainError("REPORT_TEMPLATE_CHANGED", "The report template changed; fetch it again.", 409)
        front = re.match(r"\A---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|\Z)", body)
        try:
            metadata = yaml.safe_load(front[1]) if front else None
        except yaml.YAMLError:
            metadata = None
        if not isinstance(data["timezone"], str) or not 1 <= len(data["timezone"]) <= 128 \
                or not isinstance(metadata, dict) or metadata.get("period") != month \
                or metadata.get("timezone") != data["timezone"] \
                or SLOT.search(body) or _references(service, body) != info["anchor"]:
            raise DomainError("REPORT_INVALID", "The report does not match its month, timezone or template link.", 422)
        try:
            result = service.vault.write(path, body, None, create=True)
        except DomainError as error:
            if error.code not in {"DUPLICATE_BASENAME", "CONFLICT"}:
                raise
            try:
                existing = service.vault.read(path)
            except DomainError:
                raise error from None
            if sha_bytes(existing.encode("utf-8")) != digest:
                raise error from None
            return {"path": path, "sha256": digest, "created": False}
        service.audit.emit("chronos.report.create", actor="chronos", target=path,
                           context={"month": month, "template": info["path"], "template_sha256": info["sha256"]})
        return {**result, "created": True}
