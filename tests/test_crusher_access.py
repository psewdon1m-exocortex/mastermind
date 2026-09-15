import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from mastermind.crusher_access import CrusherAccess
from mastermind.errors import DomainError
from mastermind.fs import sha_bytes
from mastermind.state import State


@pytest.fixture
def crusher(recovery):
    backup, _, auth = recovery
    return CrusherAccess(backup.config, backup.state, auth, backup.audit)


def activated(crusher):
    code = crusher.code()["code"]
    access = crusher.activate(code, "192.0.2.1")
    return crusher.principal(access["token"])["principal"], access


def test_one_use_code_is_atomic_and_never_owner_scope(crusher):
    code = crusher.code()["code"]
    assert len(code) == 6 and code.isascii() and code.isdigit()

    def attempt(_):
        try:
            return crusher.activate(code, "192.0.2.1")
        except DomainError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(attempt, range(4)))
    assert sum(isinstance(result, dict) for result in results) == 1
    credential = next(result["token"] for result in results if isinstance(result, dict))
    assert len(credential) == 43
    assert credential not in json.dumps(crusher.state.rows("SELECT * FROM sessions"))
    with pytest.raises(DomainError):
        crusher.auth.session(credential)


def test_activation_rate_limits(crusher):
    for _ in range(10):
        with pytest.raises(DomainError) as wrong:
            crusher.activate("bad", "192.0.2.2")
        assert wrong.value.status == 401
    with pytest.raises(DomainError) as blocked:
        crusher.activate(crusher.code()["code"], "192.0.2.2")
    assert blocked.value.status == 429


def test_acceptance_idempotency_persists_across_reopen_and_hides_source(crusher):
    principal, access = activated(crusher)
    source = {"type": "text", "text": "Private source. Never return it in status."}
    first = crusher.accept(principal, "stable-key-123456", source)
    second = crusher.accept(principal, "stable-key-123456", source)
    assert first["job_id"] == second["job_id"]
    with pytest.raises(DomainError) as conflict:
        crusher.accept(principal, "stable-key-123456", {"type": "text", "text": "different"})
    assert conflict.value.status == 409
    other = State(crusher.state.path)
    try:
        assert other.one("SELECT COUNT(*) AS n FROM jobs")["n"] == 1
        record = json.loads(other.one("SELECT record FROM jobs")["record"])
        assert (crusher.directory / record["local_source"]).read_text() == source["text"]
        assert "text" not in record["source"]
    finally:
        other.close()
    assert source["text"] not in json.dumps(first)
    assert set(first) == {"job_id", "source_label", "state", "stage", "progress_percent", "created_at",
                          "updated_at", "error", "status_ticket", "ticket_expires_at"}
    with crusher.state.transaction() as db:
        db.execute("UPDATE sessions SET expires_at=? WHERE kind='crusher'", (time.time()-1,))
    with pytest.raises(DomainError):
        crusher.principal(access["token"])
    assert crusher.status(first["job_id"], ticket=first["status_ticket"])["state"] == "QUEUED"
    with pytest.raises(DomainError):
        crusher.accept(principal, "stable-key-123456", source)


def test_ticket_is_single_job_read_only_and_public_session_has_no_saturn(crusher):
    principal, _ = activated(crusher)
    other, _ = activated(crusher)
    first = crusher.accept(principal, "first-key-1234567", {"type": "text", "text": "One"})
    second = crusher.accept(other, "second-key-123456", {"type": "text", "text": "Two"})
    with pytest.raises(DomainError):
        crusher.status(second["job_id"], ticket=first["status_ticket"])
    with pytest.raises(DomainError):
        crusher.principal(first["status_ticket"])
    assert len(crusher.list(principal)) == 1
    assert crusher.status(second["job_id"], principal="owner")["job_id"] == second["job_id"]
    with pytest.raises(DomainError) as denied:
        crusher.accept(principal, "saturn-key-123456", {"type": "saturn", "path": "/private.txt"})
    assert denied.value.status == 403


async def chunks(data):
    for offset in range(0, len(data), 17):
        yield data[offset:offset+17]


@pytest.mark.asyncio
async def test_stream_complete_accept_and_expiration_do_not_delete_accepted_source(crusher):
    principal, _ = activated(crusher)
    content = ("A generated document\n"*100).encode()
    upload = crusher.upload(principal, "paper.txt", len(content))
    identifier = upload["upload_id"]
    with pytest.raises(DomainError):
        crusher.accept(principal, "upload-key-12345", {"type": "upload", "upload_id": identifier})
    await crusher.receive(identifier, principal, chunks(content))
    with pytest.raises(DomainError):
        crusher.complete_upload(identifier, principal, "0"*64)
    crusher.complete_upload(identifier, principal, sha_bytes(content))
    result = crusher.accept(principal, "upload-key-12345", {"type": "upload", "upload_id": identifier})
    assert result["source_label"] == "paper.txt"
    with crusher.state.transaction() as db:
        db.execute("UPDATE uploads SET expires_at=?", (time.time()-1,))
        db.execute("UPDATE sessions SET expires_at=? WHERE kind='crusher'", (time.time()-1,))
    crusher.cleanup()
    assert (crusher.directory / identifier).read_bytes() == content


@pytest.mark.asyncio
async def test_interrupted_or_oversized_upload_releases_reservation(crusher):
    upload = crusher.upload("owner", "document.txt", 100)

    async def interrupted():
        yield b"a"*40
        raise ConnectionError("synthetic disconnect")

    with pytest.raises(ConnectionError):
        await crusher.receive(upload["upload_id"], "owner", interrupted())
    assert crusher.reserved() == 0 and not list(crusher.directory.iterdir())
    upload = crusher.upload("owner", "document.txt", 100)
    with pytest.raises(DomainError) as excessive:
        await crusher.receive(upload["upload_id"], "owner", chunks(b"a"*101))
    assert excessive.value.status == 413
    assert crusher.reserved() == 0
    assert crusher.upload_slots.acquire(blocking=False) and crusher.upload_slots.acquire(blocking=False)
    crusher.upload_slots.release()
    crusher.upload_slots.release()


def test_queue_and_upload_reservations_are_bounded(crusher):
    principal, _ = activated(crusher)
    for index in range(20):
        crusher.accept(principal, f"same-session-{index:04}", {"type": "text", "text": "short"})
    with pytest.raises(DomainError) as queue:
        crusher.accept(principal, "same-session-9999", {"type": "text", "text": "short"})
    assert queue.value.status == 429
    crusher.upload(principal, "one.txt", 100)
    crusher.upload(principal, "two.txt", 100)
    with pytest.raises(DomainError) as upload:
        crusher.upload(principal, "three.txt", 100)
    assert upload.value.status == 429


@pytest.mark.parametrize("source", [
    {"type": "url", "url": "file:///secret"}, {"type": "url", "url": "https://user:secret@host.test"},
    {"type": "text", "text": "a"*(1024**2+1)}, {"type": "text", "text": "ok", "path": "other.md"},
    {"type": "upload", "upload_id": "../secret"},
])
def test_source_shape_size_and_credentials_rejected(crusher, source):
    with pytest.raises(DomainError):
        crusher.accept("owner", "invalid-key-12345", source)
    assert crusher.state.one("SELECT COUNT(*) AS n FROM jobs")["n"] == 0
