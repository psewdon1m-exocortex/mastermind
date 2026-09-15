"""Administrative commands use the running Core's private Unix socket."""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

from .admin import socket_path
from .backup import checked_json
from .config import Config
from .errors import DomainError
from .update_recovery import migrate, rollback


@contextmanager
def regular_source(path, maximum):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum or info.st_nlink != 1:
            raise DomainError("INVALID_ARCHIVE", "Choose one regular recovery archive within the 8 GiB limit.", 422)
        yield source, info.st_size


class AdminClient:
    def __init__(self, config, *, client=None):
        self.config = config
        self.client = client or httpx.Client(transport=httpx.HTTPTransport(uds=str(socket_path(config))),
            base_url="http://mastermind-admin", timeout=httpx.Timeout(120, connect=3, write=60),
            trust_env=False, follow_redirects=False)

    def close(self):
        self.client.close()

    def call(self, method, route, *, data=None, content=None, size=None):
        headers = {"Content-Length": str(size), "Content-Type": "application/zip"} if content is not None else {}
        with self.client.stream(method, "/v1"+route, headers=headers, json=data, content=content) as response:
            body = bytearray()
            for block in response.iter_bytes(64*1024):
                body.extend(block)
                if len(body) > 1024**2:
                    raise DomainError("ADMIN_PROTOCOL", "Administrative response exceeds its metadata limit.", 503)
            value = checked_json(body)
            if response.status_code != 200:
                code = value.get("error", "ADMIN_REJECTED") if isinstance(value, dict) else "ADMIN_REJECTED"
                raise DomainError(code if isinstance(code, str) and re.fullmatch(r"[A-Z_]{1,64}", code) else "ADMIN_REJECTED",
                                  "Core could not complete this operation.", response.status_code)
            return value

    def wait(self, identifier, desired, seconds=900):
        deadline, previous = time.monotonic()+seconds, None
        while True:
            value = self.call("GET", "/operations/"+identifier)
            if value["state"] != previous:
                print(json.dumps({"operation_id": identifier, "state": value["state"], "stage": value["stage"]}), file=sys.stderr)
                previous = value["state"]
            if value["state"] == desired:
                return value
            if value["state"] in {"FAILED", "INTERRUPTED"}:
                raise DomainError(value.get("error", "OPERATION_INTERRUPTED"), "Maintenance operation failed; inspect its persisted status.", 503)
            if time.monotonic() > deadline:
                raise DomainError("OPERATION_PENDING", "The operation continues in Core; inspect its persisted status.", 503)
            time.sleep(.5)

    def backup(self, output=None):
        record = self.call("POST", "/operations", data={"kind": "backup"})
        record = self.wait(record["id"], "COMPLETED")
        if output is None:
            return {**record, "archive": str(self.config.home / "exports/owner" / record["id"] / "download.zip")}
        digest, size = hashlib.sha256(), 0
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as target:
                with self.client.stream("GET", "/v1/operations/"+record["id"]+"/download") as response:
                    if response.status_code != 200:
                        raise DomainError("DOWNLOAD_UNAVAILABLE", "Staged archive is unavailable.", 503)
                    for block in response.iter_bytes(1024**2):
                        size += len(block)
                        if size > record["size"]:
                            raise DomainError("BACKUP_INTEGRITY", "Archive size changed.", 503)
                        target.write(block)
                        digest.update(block)
                target.flush()
                os.fsync(target.fileno())
            if size != record["size"] or digest.hexdigest() != record["sha256"]:
                raise DomainError("BACKUP_INTEGRITY", "Downloaded archive failed its integrity check.", 503)
        except BaseException:
            output.unlink(missing_ok=True)
            raise
        self.call("DELETE", "/operations/"+record["id"])
        return {"completed": True, "archive": str(output.absolute()), "size": size, "sha256": digest.hexdigest()}

    def restore(self, source_path, *, apply=False, yes=False):
        with regular_source(source_path, self.config.max_backup_bytes) as (source, size):
            digest = hashlib.file_digest(source, "sha256").hexdigest()
            source.seek(0)
            record = self.call("POST", "/operations", data={"kind": "restore", "size": size})
            identifier = record["id"]
            uploaded = self.call("PUT", "/operations/"+identifier+"/content", content=source, size=size)
        if uploaded.get("sha256") != digest:
            raise DomainError("RESTORE_INTEGRITY", "Recovery upload changed during transfer.", 409)
        self.call("POST", "/operations/"+identifier+"/confirm", data={"action": "inspect", "sha256": digest})
        inspected = self.wait(identifier, "AWAITING_CONFIRMATION")
        if not apply:
            self.call("DELETE", "/operations/"+identifier)
            return {"verified": True, "sha256": digest, "inspection": inspected["inspection"]}
        if not yes:
            print(json.dumps({"inspection": inspected["inspection"], "sha256": digest}, ensure_ascii=False), file=sys.stderr)
            if not sys.stdin.isatty() or input("Replace the current Vault and state? Type RESTORE: ") != "RESTORE":
                self.call("DELETE", "/operations/"+identifier)
                raise DomainError("CONFIRMATION_REQUIRED", "Restore was not applied. Use --yes for an intentional unattended restore.", 409)
        self.call("POST", "/operations/"+identifier+"/confirm", data={"action": "restore", "sha256": digest})
        return self.wait(identifier, "COMPLETED")


def parser():
    result = argparse.ArgumentParser(prog="mastermind", description="Local administration of the running Mastermind Core.")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Read-only live/readiness/dependency diagnostics; never certifies the public edge")
    commands.add_parser("reindex", help="Rebuild canonical Markdown, full-text and graph indexes")
    graph = commands.add_parser("graph").add_subparsers(dest="action", required=True)
    graph.add_parser("rebuild")
    vault = commands.add_parser("vault").add_subparsers(dest="action", required=True)
    vault.add_parser("validate")
    replication = commands.add_parser("replication").add_subparsers(dest="action", required=True)
    replication.add_parser("status")
    replication.add_parser("reconcile", help="Start both independent Neptune pipelines and wait for their results")
    backup = commands.add_parser("backup").add_subparsers(dest="action", required=True).add_parser("create")
    backup.add_argument("--output", type=Path, help="Optional exclusive destination; otherwise return a staged archive retained for 24 hours")
    restore = commands.add_parser("restore").add_subparsers(dest="action", required=True)
    for name in ("verify", "apply"):
        command = restore.add_parser(name)
        command.add_argument("source", type=Path)
        if name == "apply":
            command.add_argument("--yes", action="store_true", help="Explicitly confirm replacing current Vault and state")
    commands.add_parser("operation").add_argument("id", help="Inspect a persisted owner or CLI maintenance operation")
    update = commands.add_parser("update").add_subparsers(dest="action", required=True)
    for action in ("status", "check", "previous"):
        update.add_parser(action)
    apply_update = update.add_parser("apply")
    apply_update.add_argument("version")
    version_rollback = update.add_parser("rollback", help="Return to a verified previous version with a fresh backup, preserving compatible current data")
    version_rollback.add_argument("--job", required=True)
    version_rollback.add_argument("--yes", action="store_true")
    migration = commands.add_parser("update-migrate", help="Offline typed Updater entry point")
    migration.add_argument("--request", required=True)
    migration.add_argument("--version", required=True)
    migration.add_argument("--schema", required=True, type=int)
    rollback_parser = commands.add_parser("update-rollback", help="Offline typed Updater entry point")
    rollback_parser.add_argument("--request", required=True)
    rollback_parser.add_argument("--archive", required=True, type=Path)
    return result


def execute(args, config, client):
    if args.command == "update":
        if args.action == "status":
            return client.call("GET", "/updates"), 0
        if args.action == "check":
            return client.call("POST", "/updates/check", data={}), 0
        if args.action == "previous":
            return client.call("GET", "/updates/rollback"), 0
        if args.action == "apply":
            return client.call("POST", "/updates", data={"version": args.version}), 0
        if not args.yes:
            raise DomainError("CONFIRMATION_REQUIRED", "Use --yes to confirm the version rollback and brief service interruption.", 409)
        return client.call("POST", "/updates/rollback", data={"job_id": args.job}), 0
    if args.command == "doctor":
        report = client.call("GET", "/doctor")
        return report, 0 if report["status"] == "READY" else 1
    if args.command in {"reindex", "graph"}:
        return client.call("POST", "/reindex", data={}), 0
    if args.command == "vault":
        return client.call("GET", "/vault/validate"), 0
    if args.command == "backup":
        return client.backup(args.output), 0
    if args.command == "restore":
        return client.restore(args.source, apply=args.action == "apply", yes=getattr(args, "yes", False)), 0
    if args.command == "operation":
        if not re.fullmatch(r"[a-f0-9]{32}", args.id):
            raise DomainError("INVALID_REQUEST", "Invalid operation ID.", 422)
        return client.call("GET", "/operations/"+args.id), 0
    if args.action == "status":
        return client.call("GET", "/replication/status"), 0
    accepted = client.call("POST", "/replication/reconcile", data={})
    print(json.dumps({"accepted": accepted}), file=sys.stderr)
    deadline = time.monotonic()+900
    while True:
        report = client.call("GET", "/replication/status")
        agent = report["agent"]
        if not agent["active"] and not agent["mirror_active"]:
            success = all(item["accepted"] for item in accepted.values()) and agent["latest_run_state"] == agent["mirror"]["state"] == "complete"
            return {**report, "accepted": accepted, "completed": success}, 0 if success else 1
        if time.monotonic() > deadline:
            raise DomainError("OPERATION_PENDING", "Replication continues in Neptune; inspect replication status.", 503)
        time.sleep(1)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        config = Config.environment()
        if args.command == "update-migrate":
            migrate(config, args.request, args.version, args.schema)
            value, code = {"completed": True, "operation": args.command}, 0
        elif args.command == "update-rollback":
            rollback(config, args.request, args.archive)
            value, code = {"completed": True, "operation": args.command}, 0
        else:
            client = AdminClient(config)
            try:
                value, code = execute(args, config, client)
            finally:
                client.close()
        print(json.dumps(value, ensure_ascii=False))
        return code
    except (DomainError, OSError, ValueError, httpx.HTTPError) as error:
        print(json.dumps({"completed": False, "error": error.code if isinstance(error, DomainError) else "ADMIN_UNAVAILABLE"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
