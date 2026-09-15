"""Age's Rust implementation streams files in an isolated, deadline-bounded process."""
import multiprocessing
import os

import pyrage

from .deadline import check, remaining
from .errors import DomainError


def _transform(mode, source, destination, key):
    os.close(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    try:
        if mode == "encrypt":
            recipient = pyrage.x25519.Recipient.from_str(key)
            pyrage.encrypt_file(str(source), str(destination), [recipient])
        elif mode == "decrypt":
            identity = pyrage.x25519.Identity.from_str(key)
            pyrage.decrypt_file(str(source), str(destination), [identity])
        else:
            os._exit(3)
    except Exception:  # noqa: BLE001 - never let a library exception disclose identity material on stderr
        # Library exceptions can contain identity data. Never forward them to stderr.
        os._exit(2)


def transform(mode, source, destination, secret_store, limit, deadline=3600):
    if source.stat().st_size + (4096 + source.stat().st_size // 4096 if mode == "encrypt" else 0) > limit:
        raise DomainError("SIZE_LIMIT", "The encrypted stream exceeds its resource budget.", 413)
    # multiprocessing transfers this through its private pipe, never a command-line argument or disk file.
    key = secret_store.read("recovery_recipient" if mode == "encrypt" else "recovery_identity")
    worker = multiprocessing.get_context("spawn").Process(
        target=_transform, args=(mode, source, destination, key)
    )
    check()
    worker.start()
    try:
        worker.join(remaining(deadline))
    except BaseException:
        worker.kill()
        worker.join()
        destination.unlink(missing_ok=True)
        raise
    if worker.is_alive():
        worker.terminate()
        worker.join(1)
        if worker.is_alive():
            worker.kill()
            worker.join()
        destination.unlink(missing_ok=True)
        check()
        raise DomainError("DEADLINE_EXCEEDED", "Encryption exceeded its deadline.", 408)
    if worker.exitcode != 0:
        destination.unlink(missing_ok=True)
        raise DomainError("RECOVERY_KEY_MISMATCH" if mode == "decrypt" else "ENCRYPTION_FAILED",
                          "The protected recovery key could not complete the operation.", 422)
    if destination.stat().st_size > limit:
        destination.unlink()
        raise DomainError("SIZE_LIMIT", "The encrypted stream exceeded its resource budget.", 413)
    check()
