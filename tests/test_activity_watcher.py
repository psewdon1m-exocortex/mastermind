import threading
import time

import pytest

from mastermind.activity import Activity
from mastermind.errors import DomainError
from mastermind.watcher import DirtyJournal


def test_idle_session_restart_checkpoint_and_replay(service):
    _, state, _, _ = service
    activity = Activity(state)
    when = time.time()
    session = {"id": "stable-edit", "path": "Note.md", "last_activity_at": when}
    assert activity.ingest({"epoch": None})["reset"] is True
    envelope = {"epoch": activity.epoch, "sessions": [session]}
    assert activity.ingest(envelope)["reset"] is False
    Activity(state).expire(now=when+299)
    assert not state.rows("SELECT * FROM activity")
    Activity(state).expire(now=when+300)
    event = {"id": session["id"], "session_id": session["id"], "path": session["path"],
             "kind": "EDIT", "occurred_at": when}
    activity.ingest({"epoch": activity.epoch, "events": [event], "sessions": [session]})
    assert len(state.rows("SELECT * FROM activity")) == 1
    assert not state.rows("SELECT * FROM edit_sessions")


def test_long_offline_queue_does_not_discard_owner_history(service):
    activity = Activity(service[1])
    when = time.time()-400*86400
    activity.ingest({"epoch": activity.epoch, "events": [{"id": "long-offline-edit", "kind": "EDIT",
        "session_id": "old-stable-session", "path": "Note.md", "occurred_at": when}]})
    assert service[1].one("SELECT occurred_at FROM activity WHERE id='long-offline-edit'")["occurred_at"] == when


def test_activity_restore_keeps_checkpoint_and_resets_obsolete_runtime(recovery, tmp_path):
    backup, restore, _ = recovery
    activity = Activity(backup.state)
    before = activity.epoch
    when = time.time()
    activity.ingest({"epoch": before, "sessions": [{"id": "before-backup", "path": "Note.md",
                                                    "last_activity_at": when}]})
    archive = tmp_path / "checkpoint.zip"
    backup.create(archive)
    activity.ingest({"epoch": before, "events": [{"id": "after-backup", "path": "Other.md",
                                                 "kind": "CREATE", "occurred_at": when}]})
    restore.apply(archive)
    assert activity.epoch != before
    assert activity.ingest({"epoch": before, "events": [{"id": "after-backup"}]})["reset"] is True
    activity.expire(now=when+301)
    assert [row["id"] for row in backup.state.rows("SELECT * FROM activity")] == ["before-backup"]


@pytest.mark.parametrize("record", [
    {"id": "x", "path": "A.md", "last_activity_at": True},
    {"id": "x", "path": "A.md", "last_activity_at": float("nan")},
    {"id": "x", "path": "A.md", "occurred_at": 1},
    {"id": "x", "path": "../A.md", "last_activity_at": 1},
])
def test_invalid_session_never_partially_commits(service, record):
    activity = Activity(service[1])
    good = {"id": "valid", "path": "A.md", "kind": "CREATE", "occurred_at": time.time()}
    with pytest.raises(DomainError):
        activity.ingest({"epoch": activity.epoch, "events": [good], "sessions": [record]})
    assert not service[1].rows("SELECT * FROM activity")


def test_dirty_intent_is_durable_while_main_index_holds_database_lock(service):
    config, state, _, _ = service
    journal = DirtyJournal(config, state)
    try:
        completed = threading.Event()
        with state.transaction():
            worker = threading.Thread(target=lambda: (journal.record("Native.md"), completed.set()))
            started = time.monotonic()
            worker.start()
            assert completed.wait(1), "A native intent waited for the main index transaction"
            assert time.monotonic()-started < 1
        worker.join()
        journal.close()
        journal = DirtyJournal(config, state)
        assert journal.pending() == 1
        assert journal.flush() == 1
        assert state.one("SELECT * FROM outbox WHERE path='Native.md'")
        assert journal.pending() == 0
    finally:
        journal.close()


def test_observer_captures_opaque_plugin_change_and_generation_switch(service):
    config, state, _, _ = service
    journal = DirtyJournal(config, state)
    journal.start()
    try:
        plugin = config.vault / ".obsidian/plugins/opaque-plugin"
        plugin.mkdir(parents=True)
        (plugin / "data.json").write_bytes(b'opaque private plugin bytes')
        deadline = time.monotonic()+3
        while journal.pending() == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert journal.pending()
        old = config.vault.with_name(".old-test")
        config.vault.rename(old)
        config.vault.mkdir()
        (config.vault / "New generation.md").write_text("New generation", encoding="utf-8")
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            journal.flush()
            if state.one("SELECT * FROM outbox WHERE path='New generation.md'"):
                break
            time.sleep(0.01)
        assert state.one("SELECT * FROM outbox WHERE path='New generation.md'")
        assert not state.rows("SELECT * FROM activity")
    finally:
        journal.close()
