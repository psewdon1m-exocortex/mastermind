"""Advisory cross-process locks shared by the HTTP service, CLI and recovery."""
import os
import threading
import time
from contextlib import contextmanager

from .errors import DomainError


class FileMutex:
    def __init__(self, path):
        self.path = path
        self.local = threading.local()

    @contextmanager
    def acquire(self, timeout=30):
        if getattr(self.local, "depth", 0):
            self.local.depth += 1
            try:
                yield
            finally:
                self.local.depth -= 1
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
        stream = os.fdopen(fd, "r+b", buffering=0)
        if os.name == "nt":
            import msvcrt

            def lock():
                stream.seek(0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

            def unlock():
                stream.seek(0)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            def lock():
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            def unlock():
                fcntl.flock(fd, fcntl.LOCK_UN)
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    lock()
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise DomainError("VAULT_BUSY", "Another process owns the mutation gate.", 423) from None
                    time.sleep(0.025)
            self.local.depth = 1
            try:
                yield
            finally:
                self.local.depth = 0
                unlock()
        finally:
            stream.close()
