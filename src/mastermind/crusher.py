"""Single durable Crusher pipeline. Only the Core coordinator can commit a note."""
import asyncio
import json
import re
import secrets
import threading
import time
import unicodedata
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import PurePosixPath

from markdown_it import MarkdownIt

from .crusher_access import PROGRESS, TERMINAL
from .errors import DomainError
from .extractors import scrub
from .fs import WINDOWS_RESERVED, name_key, sha_bytes, sha_file
from .gemini import Gemini, Generated, Understanding
from .hierarchy import Hierarchy
from .integrations import Neptune
from .worker_client import WorkerClient

RETRYABLE = {"PROVIDER_TRANSIENT", "SOURCE_NETWORK", "WORKER_UNAVAILABLE", "WORKER_BUSY",
             "NEPTUNE_UNAVAILABLE", "RESOURCE_BUSY", "KERNEL_UNAVAILABLE", "SOURCE_TIMEOUT"}


class Scheduled(Exception):
    pass


class Stopping(BaseException):
    pass


def filename(title):
    value = unicodedata.normalize("NFC", title)
    value = "".join(c for c in value if c.isprintable() and c not in '\\/:*?"<>|[]#^').strip().rstrip(". ")
    while len(value.encode("utf-8")) > 180:
        value = value[:-1]
    if not value or WINDOWS_RESERVED.match(value):
        value = "Crusher note " + datetime.now(UTC).strftime("%Y%m%d %H%M%S")
    return value


def footer(record, identifier, placement):
    values = {"job_id": identifier, "source_type": record["source"]["type"], "source": record["source_label"],
              "processed_at": datetime.now(UTC).isoformat(), "provider": "Gemini", "model": record["models"]["text"],
              "placement_confidence": placement["confidence"], "suggested_destination": placement["suggested"] or ""}
    lines = [key + ": " + json.dumps(value, ensure_ascii=True).replace(">", "\\u003e").replace("<", "\\u003c")
             for key, value in values.items()]
    return "\n\n<!-- mastermind:crusher\n" + "\n".join(lines) + "\n-->\n"


class Crusher:
    def __init__(self, service, *, worker=None, provider=None):
        self.service, self.state = service, service.state
        self.access = service.crusher_access
        self.worker = worker or WorkerClient(service.config, service.secrets)
        self.provider = provider or Gemini(service.kernel, service.secrets)
        engine = self

        class PlacementProvider:
            def token_count(self, model, text):
                return engine.provider.token_count(model, text)

            def generate(self, model, task, packet, schema):
                return engine.remote("placement", model, task, packet, schema)

        self.hierarchy = Hierarchy(service.vault, self.worker, PlacementProvider())
        self.stop_event = threading.Event()
        self.thread = None
        self.identity = secrets.token_hex(16)
        self.row = self.record = None
        self.fault = lambda point: None

    def start(self):
        if not self.service.config.worker_url:
            return
        # Service.start already acquired the exclusive process leader and finished
        # coordinator recovery. No earlier Core may still write canonical data.
        with self.state.transaction() as db:
            db.execute("UPDATE jobs SET leased_by=NULL,lease_expires_at=NULL WHERE state NOT IN ('COMPLETED','FAILED')")
        self.thread = threading.Thread(target=self.run, name="mastermind-crusher", daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        self.worker.close()
        self.provider.close()
        if self.thread:
            self.thread.join(timeout=2)

    def save(self, *, state=None, stage=None):
        with self.service.coordinator.lock:
            if self.stop_event.is_set() or self.state.closed:
                raise Stopping
            now = time.time()
            if state and self.row["state"] != state:
                self.record["transitions"].append({"state": state, "at": now})
            self.row["state"] = state or self.row["state"]
            self.row["stage"] = stage or self.row["stage"]
            self.row["updated_at"] = now
            self.row["progress"] = max(self.row["progress"], PROGRESS.get(self.row["state"], 0))
            with self.state.transaction() as db:
                db.execute("UPDATE jobs SET state=?,stage=?,progress=?,updated_at=?,record=?,leased_by=?,lease_expires_at=? WHERE id=?",
                    (self.row["state"], self.row["stage"], self.row["progress"], now, json.dumps(self.record, ensure_ascii=False),
                     None if self.row["state"] in TERMINAL else self.identity,
                     None if self.row["state"] in TERMINAL else now+60, self.row["id"]))

    def checkpoint(self, key, action, *, persist_only=False):
        if self.stop_event.is_set():
            raise Stopping
        self.service.data_ready()
        if time.time() >= self.record["deadline"]:
            raise DomainError("JOB_DEADLINE", "The accepted job exceeded its 60-minute deadline.", 408)
        if persist_only:
            self.save()
            return None
        if key in self.record["results"]:
            return self.record["results"][key]
        if key in ("placement", "acquire", "understand-media"):
            # Composite steps consist of separately counted durable external calls.
            result = action()
            self.record["results"][key] = result
            self.save()
            return result
        attempts = self.record["attempts"].get(key, 0)
        if attempts >= 3:
            raise DomainError("RETRY_EXHAUSTED", "The interrupted stage exhausted its three attempts.", 422)
        self.record["attempts"][key] = attempts+1
        self.record["active_step"] = key
        self.save()
        self.fault("before:" + key)
        try:
            result = action()
        except DomainError as error:
            if error.code in RETRYABLE and attempts < 2:
                delay = (5, 30)[attempts]
                retry = error.headers.get("Retry-After")
                if retry:
                    try:
                        supplied = int(retry) if retry.isascii() and retry.isdigit() else parsedate_to_datetime(retry).timestamp()-time.time()
                        if not 0 <= supplied <= 120:
                            raise ValueError
                        delay = max(delay, supplied)
                    except (ValueError, TypeError, OverflowError):
                        raise DomainError("RETRY_POLICY", "The upstream retry delay exceeds the bounded job policy.", 422) from None
                if time.time()+delay >= self.record["deadline"]:
                    raise DomainError("JOB_DEADLINE", "No retry fits within the job deadline.", 408) from None
                self.record["next_attempt_at"] = time.time()+delay
                self.save()
                self.service.audit.emit("crusher.retry", target=self.row["id"], context={"stage": self.row["stage"], "attempt": attempts+1,
                    "code": error.code, "upstream_outcome": "unknown" if key in ("understand", "generate") or key.endswith("_choice") else "retryable"})
                raise Scheduled from None
            raise
        self.fault("after-external:" + key)
        self.record["results"][key] = result
        self.record.pop("next_attempt_at", None)
        self.save()
        self.fault("after:" + key)
        return result

    def stage(self, name):
        if PROGRESS[name] > self.row["progress"]:
            self.save(state=name, stage=name)

    def fetch_saturn(self):
        # A separate adapter has its own event loop/lease. Credentials never cross
        # into Worker; only the verified selected file bytes do.
        async def transfer():
            reader = Neptune(self.service.config)
            try:
                path = self.record["source"]["path"]
                metadata = await reader.request("resource-metadata", path, purpose="owner-crusher")
                if metadata["type"] != "file" or metadata["size_bytes"] > self.service.config.max_upload_bytes:
                    raise DomainError("SOURCE_SIZE_INVALID", "Select one Saturn file within the 2 GiB source limit.", 413)
                response = await reader.request("resource-content", path, purpose="owner-crusher")
                if response.headers["etag"] != metadata["etag"] or int(response.headers["content-length"]) != metadata["size_bytes"]:
                    await reader.release(response)
                    raise DomainError("SOURCE_INTEGRITY", "The selected Saturn resource changed before transfer.", 409)
                destination = self.access.directory / self.row["id"]
                with destination.open("wb") as output:
                    async for chunk in reader.stream(response):
                        output.write(chunk)
                    output.flush()
                    import os
                    os.fsync(output.fileno())
                return {"local_source": destination.name, "local_sha": sha_file(destination),
                        "source_name": PurePosixPath(path).name, "size": metadata["size_bytes"]}
            finally:
                await reader.close()
        return asyncio.run(transfer())

    def acquire(self):
        identifier, source = self.row["id"], self.record["source"]
        if source["type"] == "saturn" and not self.record.get("local_source"):
            result = self.checkpoint("saturn-source", self.fetch_saturn)
            self.record.update(result)
            self.save()
        if source["type"] in ("text", "upload", "saturn"):
            local = self.record.get("local_source")
            path = self.access.directory / (local or "missing")
            if not local or not path.is_file() or sha_file(path) != self.record["local_sha"]:
                raise DomainError("SOURCE_UNAVAILABLE", "The accepted source is no longer available; submit it again.", 422)
            return self.checkpoint("worker-transfer", lambda: self.worker.transfer(identifier, self.access.directory, local,
                expected=self.record["local_sha"], size=path.stat().st_size, source_name=self.record["source_name"]))
        if source["type"] == "youtube":
            return {"youtube": source["url"]}
        if source["type"] == "git":
            return self.checkpoint("git-clone", lambda: self.worker.request("POST", "/jobs/" + identifier + "/git", {"url": source["url"]}))
        return self.checkpoint("worker-acquire", lambda: self.worker.acquire(identifier, source["url"]))

    def extract(self):
        if self.record["source"]["type"] == "youtube":
            return {"needs_media": True, "needs_browser": False, "text": "", "type": "youtube",
                    "youtube": self.record["source"]["url"]}
        result = self.worker.extract(self.row["id"])
        if result["needs_browser"]:
            result = self.worker.request("POST", "/jobs/" + self.row["id"] + "/render")
        return result

    def remote(self, key, model, task, packet, schema):
        budget = self.record["budget"]
        # Cards are accounted independently by Hierarchy. Charge source-derived
        # fields across actual generation requests before each paid attempt.
        source = json.dumps({key: value for key, value in packet.items() if key not in ("candidates", "breadcrumb")}, ensure_ascii=False)
        count = self.provider.token_count(model, source)
        if budget["source_transmitted"]+count > 32000:
            raise DomainError("SOURCE_TOKEN_LIMIT", "The job exhausted its fixed source input budget.", 422)
        budget["source_transmitted"] += count
        self.save()
        return self.provider.generate(model, task, packet, schema)

    def validate(self, generated):
        title, text = filename(generated["title"]), generated["markdown"]
        # AI prose has no resource authority. Existing code/literal examples are
        # retained; Core appends the sole verified branch link after revalidation.
        tokens = MarkdownIt("commonmark", {"html": True}).parse(text)
        pending, prose = list(tokens), []
        while pending:
            token = pending.pop()
            if token.type in ("html_block", "html_inline", "link_open", "image"):
                raise DomainError("GENERATED_REFERENCE_INVALID", "The generated note contains unapproved markup or resources.", 422)
            if token.type == "text":
                prose.append(token.content)
            pending.extend(token.children or [])
        plain = "\n".join(prose)
        if re.search(r"\[\[|(?<![\w.\-])@[^\s]|(?:https?://|www\.)", plain, re.IGNORECASE):
            raise DomainError("GENERATED_REFERENCE_INVALID", "The generated note contains unapproved resource references.", 422)
        if "mastermind:crusher" in text or text.startswith("---\n") or "\0" in text \
                or scrub(text) != text or scrub(generated["title"]) != generated["title"] \
                or len(text.encode("utf-8")) > self.service.config.max_note_bytes-8192:
            raise DomainError("GENERATED_NOTE_INVALID", "The generated note violates the output policy.", 422)
        return {"title": title, "markdown": text}

    def commit(self, validated, placement):
        vault = self.service.vault
        if time.time() >= self.record["deadline"]:
            raise DomainError("JOB_DEADLINE", "No commit may start after the accepted job deadline.", 408)
        with self.service.coordinator.boundary() as operation_id:
            self.service.data_ready()
            current = self.state.one("SELECT * FROM jobs WHERE id=?", (self.row["id"],))
            if current["state"] == "COMPLETED":
                return
            placement = self.hierarchy.revalidate(placement)
            anchor = placement["anchor"]
            if anchor and any(c in PurePosixPath(anchor).stem for c in "[]#^|"):
                placement = self.hierarchy.inbox("ANCHOR_NAME_UNSUPPORTED", suggested=anchor)
                anchor = None
            directory = str(PurePosixPath(anchor).parent) if anchor else "Inbox/Crusher"
            names = {row["name_key"] for row in self.state.rows("SELECT name_key FROM notes")}
            title = validated["title"]
            candidate = title
            for number in range(2, 100002):
                if name_key(candidate) not in names:
                    break
                candidate = f"{title} ({number})"
            else:
                raise DomainError("FILENAME_LIMIT", "A unique filename could not be allocated.", 409)
            relative = str(PurePosixPath(directory) / (candidate+".md"))
            vault.validate_destination(relative)
            body = validated["markdown"].rstrip()
            if anchor:
                body += "\n\n[[" + PurePosixPath(anchor).stem + "]]"
            body += footer(self.record, self.row["id"], placement)
            data = body.encode("utf-8")
            self.record["commit"] = {"path": relative, "sha256": sha_bytes(data), "placement": placement}
            self.save()
            self.fault("before-commit")
            self.service.coordinator.commit({relative: data}, {relative: None},
                {"job_id": self.row["id"], "committed_path": relative, "committed_sha": sha_bytes(data)},
                inside_boundary=True, operation_id=operation_id)
            self.fault("after-commit")
            vault.index()
            self.row = self.state.one("SELECT * FROM jobs WHERE id=?", (self.row["id"],))
            self.record = json.loads(self.row["record"])
            self.service.audit.emit("crusher.commit", target=self.row["id"], context={"outcome": "durable"})

    def process(self):
        self.record.setdefault("budget", {"unique": {}, "transmitted": 0, "source_transmitted": 0})
        self.record["models"] = self.checkpoint("models", self.provider.models)
        self.stage("ACQUIRING")
        self.checkpoint("acquire", self.acquire)
        self.stage("NORMALIZING")
        self.checkpoint("normalize", lambda: {"source_verified": True})
        self.stage("EXTRACTING")
        extracted = self.checkpoint("extract", self.extract)
        model = self.record["models"]["text"]
        if extracted["needs_media"]:
            self.stage("UNDERSTANDING")
            understanding = self.checkpoint("understand-media", lambda: self.provider.understand_media(
                self.record["models"]["video"], self.row["id"], extracted, self.worker, self.checkpoint,
                self.record["budget"], self.save))
        else:
            self.stage("UNDERSTANDING")
            # Leave room for placement topics and generation from the structured
            # understanding within the total 32k source-transmission budget.
            normalized = self.checkpoint("source-tokens", lambda: self.provider.bound_source(model, extracted["text"], limit=16000))
            understanding = self.checkpoint("understand", lambda: self.remote("understand", model,
                "Understand the source. Capture the essential facts and uncertainties in the summary; suggest topics and entities.",
                {"source": normalized["text"], "source_truncated": extracted.get("truncated", False)
                    or len(normalized["text"]) < len(extracted["text"])}, Understanding))
        self.stage("PLACING")
        placement = self.checkpoint("placement", lambda: self.hierarchy.place(understanding, model,
            checkpoint=self.checkpoint, budget=self.record["budget"]))
        self.stage("GENERATING")
        generated = self.checkpoint("generate", lambda: self.remote("generate", model,
            "Write a self-contained, well-structured note from this source understanding. Preserve facts and uncertainty. Core will add the verified branch link.",
            {"understanding": understanding}, Generated))
        self.stage("VALIDATING")
        validated = self.checkpoint("validate", lambda: self.validate(generated))
        self.stage("COMMITTING")
        self.commit(validated, placement)

    def cleanup_current(self):
        if self.record.get("results", {}).get("media-upload"):
            self.provider.cleanup_media(self.record)
        self.worker.cleanup(self.row["id"])
        local = self.record.get("local_source")
        if local and re.fullmatch(r"[a-f0-9]{32}", local):
            (self.access.directory / local).unlink(missing_ok=True)
        self.record["results"] = {}
        self.record["reserved_bytes"] = 0
        self.record["cleaned"] = True
        self.save()

    def cleanup_terminal(self):
        for row in self.state.rows("SELECT * FROM jobs WHERE state IN ('COMPLETED','FAILED') "
                                   "AND json_extract(record,'$.cleaned') IS NOT 1 ORDER BY updated_at LIMIT 10"):
            self.row, self.record = row, json.loads(row["record"])
            try:
                self.cleanup_current()
            except DomainError:
                # Retry cleanup without changing the already durable job outcome.
                break
        self.access.cleanup()

    def once(self):
        if self.stop_event.is_set():
            return False
        try:
            self.service.data_ready()
        except DomainError:
            return False
        self.row = self.state.one("SELECT * FROM jobs WHERE state NOT IN ('COMPLETED','FAILED') ORDER BY created_at LIMIT 1")
        if not self.row:
            return False
        self.record = json.loads(self.row["record"])
        if self.record.get("next_attempt_at", 0) > time.time():
            return False
        try:
            self.process()
            self.cleanup_current()
        except Scheduled:
            pass
        except DomainError as error:
            current = self.state.one("SELECT * FROM jobs WHERE id=?", (self.row["id"],))
            if current["state"] == "COMPLETED":
                # A cleanup/index error cannot erase a committed note or turn
                # the durable 100% outcome into FAILED.
                return True
            if error.code in ("UPDATE_IN_PROGRESS", "NOT_READY", "RECOVERY_REQUIRED"):
                return False
            self.record["public_error"] = {"code": error.code, "message": "Source processing failed. The job did not commit a note."}
            self.save(state="FAILED", stage="FAILED")
            self.service.audit.emit("crusher.failed", outcome="error", target=self.row["id"], context={"code": error.code})
            try:
                self.cleanup_current()
            except DomainError:
                pass
        return True

    def run(self):
        cleanup_at = 0
        while not self.stop_event.wait(0.2):
            try:
                if time.monotonic() >= cleanup_at:
                    self.service.data_ready()
                    self.cleanup_terminal()
                    cleanup_at = time.monotonic()+60
                self.once()
            except Stopping:
                return
            except DomainError:
                self.stop_event.wait(1)
            except Exception:  # noqa: BLE001 - preserve durable state, never log provider/source exceptions
                if self.stop_event.is_set() or self.state.closed:
                    return
                self.service.audit.emit("crusher.worker_loop", outcome="error", context={"code": "PIPELINE_INTERNAL_ERROR"})
                if self.row:
                    current = self.state.one("SELECT state FROM jobs WHERE id=?", (self.row["id"],))
                    if current and current["state"] not in TERMINAL:
                        self.record["public_error"] = {"code": "PIPELINE_INTERNAL_ERROR", "message": "Source processing failed before note commit."}
                        self.save(state="FAILED", stage="FAILED")
                self.stop_event.wait(5)
