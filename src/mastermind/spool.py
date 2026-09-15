import hashlib
import os
import secrets
import shutil
import time
from contextlib import contextmanager

from .deadline import check
from .errors import DomainError
from .fs import file_inventory, remove_private_tree
from .locking import FileMutex

CHUNK = 1024 * 1024


def copy_bounded(source, destination, limit, *, deadline=None):
    deadline = deadline or time.monotonic() + 3600
    size, digest = 0, hashlib.sha256()
    check()
    while data := source.read(CHUNK):
        check()
        size += len(data)
        if size > limit:
            raise DomainError("SIZE_LIMIT", "The stream exceeds its declared limit.", 413)
        if time.monotonic() > deadline:
            raise DomainError("DEADLINE_EXCEEDED", "The operation exceeded its deadline.", 408)
        destination.write(data)
        digest.update(data)
    check()
    return size, digest.hexdigest()


def private_open(path, mode="wb"):
    if mode != "wb":
        raise ValueError("Only private output files are supported")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb")


class BoundedWriter:
    def __init__(self, stream, limit, deadline=None):
        self.stream, self.limit = stream, limit
        self.deadline = deadline or time.monotonic() + 3600
        self.size = 0

    def write(self, data):
        self.size += len(data)
        if self.size > self.limit:
            raise DomainError("SIZE_LIMIT", "The stream exceeds its declared limit.", 413)
        if time.monotonic() > self.deadline:
            raise DomainError("DEADLINE_EXCEEDED", "The operation exceeded its deadline.", 408)
        return self.stream.write(data)

    def flush(self):
        self.stream.flush()


class Spool:
    def __init__(self, config):
        self.config = config
        self.directory = config.home / "spool"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = FileMutex(config.home / "recovery" / "spool.lock")

    def reserve(self, required):
        used = sum(path.stat().st_size for _, path in file_inventory(self.directory))
        for root in (self.config.home / "recovery" / "restores", self.config.home / "recovery" / "operations",
                     self.config.home / "recovery" / "updates",
                     self.config.home / "exports"):
            if root.exists():
                used += sum(path.stat().st_size for _, path in file_inventory(root))
        for root in self.config.vault.parent.glob(".*-*"):
            if root.is_dir():
                used += sum(path.stat().st_size for _, path in file_inventory(root))
        free = shutil.disk_usage(self.directory).free
        if required < 0 or required + used > self.config.spool_quota or required + 64*1024**2 > free:
            raise DomainError("INSUFFICIENT_SPACE", "The recovery operation cannot reserve enough disk space.", 507)

    @contextmanager
    def operation(self, required):
        with self.lock.acquire(timeout=0):
            self.reserve(required)
            directory = self.directory / secrets.token_hex(16)
            directory.mkdir(mode=0o700)
            try:
                yield directory
            finally:
                # Only this generated direct child is eligible for recursive cleanup.
                if directory.parent.resolve() != self.directory.resolve() or directory.is_symlink():
                    raise DomainError("UNSAFE_PATH", "Spool cleanup target changed.", 503)
                remove_private_tree(directory, self.directory)
