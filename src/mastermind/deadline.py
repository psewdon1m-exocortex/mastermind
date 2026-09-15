"""One monotonic budget across the work done while editor writers are paused."""
import time
from contextlib import contextmanager
from contextvars import ContextVar

from .errors import DomainError

SNAPSHOT_SECONDS = 120
_expires = ContextVar("mastermind_snapshot_deadline", default=None)


def remaining(maximum=None):
    expires = _expires.get()
    if expires is None:
        return maximum
    seconds = expires - time.monotonic()
    if seconds <= 0:
        raise DomainError("SNAPSHOT_TIMEOUT", "Snapshot preparation exceeded the editor pause limit.", 408)
    return seconds if maximum is None else min(maximum, seconds)


def check():
    remaining()


@contextmanager
def snapshot_budget(*, started=None):
    # A nested snapshot must not restart the enclosing update's budget.
    previous = _expires.get()
    expires = (time.monotonic() if started is None else started) + SNAPSHOT_SECONDS
    token = _expires.set(min(previous, expires) if previous is not None else expires)
    try:
        check()
        yield
        check()
    finally:
        _expires.reset(token)
