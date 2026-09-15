import multiprocessing
import time

import pytest

from mastermind.errors import DomainError
from mastermind.fs import sha_file
from mastermind.locking import FileMutex


def hold_lock(path, ready, release):
    with FileMutex(path).acquire():
        ready.set()
        release.wait(5)


def test_another_process_cannot_enter_mutation_gate(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready, release = context.Event(), context.Event()
    path = tmp_path / "mutation.lock"
    child = context.Process(target=hold_lock, args=(path, ready, release))
    child.start()
    try:
        assert ready.wait(5)
        with pytest.raises(DomainError, match="Another process"), FileMutex(path).acquire(timeout=0.1):
            pytest.fail("Cross-process lock was bypassed")
    finally:
        release.set()
        child.join(5)
    assert child.exitcode == 0
    with FileMutex(path).acquire(timeout=0.1):
        pass


def test_crlf_bytes_and_external_edit_are_indexed_exactly(service):
    config, state, _, vault = service
    (config.vault / "A.md").write_bytes(b"first\r\nsecond\r\n")
    vault.index()
    before = state.one("SELECT * FROM notes")
    assert before["sha"] == sha_file(config.vault / "A.md")
    assert vault.read("A.md") == "first\r\nsecond\r\n"
    (config.vault / "A.md").write_bytes(b"changed\r\n")
    vault.index()
    assert state.one("SELECT * FROM outbox")["generation"] >= 2
    assert vault.list("changed")


def test_representative_1650_note_index_and_incremental_update(service, record_property):
    config, _, _, vault = service
    for i in range(1650):
        (config.vault / f"Note {i:04}.md").write_text(
            f"#key\n@Note {(i + 1) % 1650:04}\n[[Note {(i + 2) % 1650:04}]]\n" + "Useful text. " * 50,
            encoding="utf-8",
        )
    started = time.monotonic()
    assert vault.index()["notes"] == 1650
    elapsed = time.monotonic() - started
    record_property("full_index_seconds", elapsed)
    assert elapsed < 30
    assert len(vault.graph()["edges"]) == 3300
    started = time.monotonic()
    (config.vault / "Note 0000.md").write_text("A new subject", encoding="utf-8")
    assert vault.index()["indexed"] == 1
    record_property("incremental_seconds", time.monotonic() - started)
    assert time.monotonic() - started < 5
