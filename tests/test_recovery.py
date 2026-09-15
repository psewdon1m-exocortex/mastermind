import base64
import json
import sqlite3
import time
import zipfile
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from mastermind.audit import Audit, redact
from mastermind.auth import Auth, digest
from mastermind.backup import Backup, zip_members
from mastermind.config import Config
from mastermind.coordinator import Coordinator
from mastermind.errors import DomainError
from mastermind.fs import atomic_write, file_inventory, sha_file
from mastermind.restore import Restore
from mastermind.runtime_client import RuntimeClient
from mastermind.state import State
from mastermind.vault import Vault


@pytest.mark.parametrize("value", ["", " x ", "\t\n", "🔐ключ", "Cafe\u0301", "A"*10240])
def test_access_key_exact_value_roundtrip(recovery, value):
    backup, _, auth = recovery
    auth.initialize(value)
    session = auth.login(value, "127.0.0.1")
    assert auth.session(session["token"])["principal"] == "owner"
    with pytest.raises(DomainError, match="not accepted"):
        auth.login(value + " ", "127.0.0.1")
    assert value not in json.dumps(backup.state.rows("SELECT * FROM sessions")) if value else True
    assert backup.state.setting("access_key_verifier").startswith("$argon2id$")


def test_rotation_revokes_sessions_and_csrf_rejects_foreign_origin(recovery):
    backup, _, auth = recovery
    auth.initialize(" before ")
    first, second = auth.login(" before ", "one"), auth.login(" before ", "two")
    current = auth.session(first["token"])
    auth.csrf(current, first["csrf"], backup.config.public_url, backup.config.public_url)
    with pytest.raises(DomainError, match="origin"):
        auth.csrf(current, first["csrf"], "https://elsewhere.invalid", backup.config.public_url)
    new = auth.rotate(" before ", " after ", first["token"])
    for session in (first, second):
        with pytest.raises(DomainError):
            auth.session(session["token"])
    assert auth.session(new["token"])
    assert auth.login(" after ", "three")


def test_login_abuse_is_bounded(recovery):
    _, _, auth = recovery
    auth.initialize("test")
    for _ in range(5):
        with pytest.raises(DomainError) as denied:
            auth.login("wrong", "same-ip")
        assert denied.value.status == 401
    with pytest.raises(DomainError) as limited:
        auth.login("test", "same-ip")
    assert limited.value.status == 429


def test_recursive_redaction_before_any_sink(recovery, tmp_path):
    backup, _, _ = recovery
    context = {"nested": [{"Authorization": "Bearer secret-canary", "password": "password-canary"}],
               "message": "Failure https://user:pass@example.invalid/s/tokenvalue?secret=value",
               "error": "Failed /s/secretshare and token=some-secret-value"}
    backup.audit.emit("security.test", context=context)
    backup.audit.export(tmp_path / "logs.zip")
    with zipfile.ZipFile(tmp_path / "logs.zip") as archive:
        data = b"".join(archive.read(name) for name in archive.namelist())
        assert set(archive.namelist()) == {"events.jsonl", "errors.json", "manifest.json", "README.txt"}
    for canary in (b"secret-canary", b"password-canary", b"user:pass", b"tokenvalue", b"secretshare",
                   b"some-secret-value"):
        assert canary not in data
        assert canary not in (backup.audit.directory / "events.jsonl").read_bytes()
    assert redact({"body": [{"apiKey": "test"}]})["body"][0]["apiKey"] == "[REDACTED]"


def populate(backup, auth):
    auth.initialize(" exact\nkey ")
    backup.vault.write("root.md", "#main\r\n[[Topic]] @Topic\r\n", None, create=True)
    backup.vault.write("Branch/Topic.md", "#key\nPrivate note", None, create=True)
    plugin = backup.config.vault / ".obsidian/plugins/existing/data.json"
    atomic_write(plugin, b'{"api_key":"USER-PLUGIN-OPAQUE-CANARY", "value": 123}\r\n')
    atomic_write(backup.config.vault / "attachments/binary.dat", bytes(range(256))*4)
    (backup.config.vault / "Empty folder/deep empty").mkdir(parents=True)
    atomic_write(backup.config.home / ".env", b"SHELL_SECRET=NEVER-IN-ARCHIVE")
    with backup.state.transaction() as db:
        db.execute("INSERT INTO activity VALUES('activity-1','edit-1','EDIT','root.md',?)", (time.time(),))
        db.execute("INSERT INTO shares VALUES('share-1',?,'v1','root.md','edit',NULL,?,?,NULL,NULL,1)",
                   (digest("share-token"), time.time(), time.time()))
        db.execute("INSERT INTO jobs VALUES('job-1','owner','once','source-digest','RUNNING','EXTRACTING',10,"
                   "?,?,?,NULL,NULL)", (time.time(), time.time(), json.dumps({"source_path": "temporary-file"})))
    backup.state.set_setting("appearance", {"accent": "#00A8FF"})
    return {rel: sha_file(path) for rel, path in file_inventory(backup.config.vault)}


def test_complete_encrypted_roundtrip_and_restore_policy(recovery, tmp_path):
    backup, restore, auth = recovery
    original = populate(backup, auth)
    before = auth.login(" exact\nkey ", "one")
    archive = tmp_path / "complete.zip"
    manifest = backup.create(archive)
    with zipfile.ZipFile(archive) as outer:
        assert outer.namelist() == ["manifest.json", "payload.age"]
        assert b"root.md" not in outer.read("manifest.json")
    assert b"USER-PLUGIN-OPAQUE-CANARY" not in archive.read_bytes()
    inspected = backup.inspect(archive)
    assert inspected["notes"] == 2
    assert inspected["manifest"]["generation"] == manifest["generation"]
    backup.vault.write("root.md", "different", sha_file(backup.config.vault / "root.md"))
    backup.vault.write("New.md", "new file", None, create=True)
    with backup.state.transaction() as db:
        db.execute("UPDATE shares SET revoked_at=? WHERE id='share-1'", (time.time(),))
    result = restore.apply(archive)
    assert result["state"] == "COMPLETED"
    assert original == {rel: sha_file(path) for rel, path in file_inventory(backup.config.vault)}
    assert (backup.config.vault / "Empty folder/deep empty").is_dir()
    assert backup.state.one("SELECT * FROM activity")["id"] == "activity-1"
    assert backup.state.one("SELECT revoked_at FROM shares")["revoked_at"] is not None
    assert backup.state.one("SELECT state FROM jobs")["state"] == "FAILED"
    assert "SOURCE_UNAVAILABLE" in backup.state.one("SELECT record FROM jobs")["record"]
    assert backup.state.setting("appearance") == {"accent": "#00A8FF"}
    with pytest.raises(DomainError):
        auth.session(before["token"])
    assert auth.login(" exact\nkey ", "after-restore")
    assert backup.vault.list("Private")[0]["path"] == "Branch/Topic.md"
    assert backup.vault.graph()["connectedness"] == 100
    assert list(restore.directory.glob("*/pre-restore.zip"))
    assert not list(backup.spool.directory.iterdir())


def test_clean_restore_to_separate_home_with_external_keys(recovery, tmp_path):
    backup, _, auth = recovery
    original = populate(backup, auth)
    archive = tmp_path / "original.zip"
    backup.create(archive)
    config = replace(backup.config, home=tmp_path / "clean-install")
    state = State(config.state / "mastermind.sqlite3")
    coordinator = Coordinator(config, state, RuntimeClient(config))
    vault = Vault(config, state, coordinator)
    audit = Audit(config, state)
    second = Backup(config, state, coordinator, vault, backup.secrets, audit)
    try:
        Restore(second, Auth(state, audit)).apply(archive)
        assert original == {rel: sha_file(path) for rel, path in file_inventory(config.vault)}
        assert second.state.setting("access_key_verifier") == backup.state.setting("access_key_verifier")
    finally:
        state.close()


class Crash(BaseException):
    pass


@pytest.mark.parametrize("point", ["prepared", "old_vault_moved", "new_vault_moved", "new_db_moved", "verified", "committed"])
def test_crash_during_generation_switch_recovers_pair(recovery, tmp_path, point):
    backup, restore, auth = recovery
    original = populate(backup, auth)
    archive = tmp_path / "base.zip"
    backup.create(archive)
    backup.vault.write("root.md", "Latest live content", sha_file(backup.config.vault / "root.md"))
    backup.state.set_setting("generation_marker", "latest")
    latest = {rel: sha_file(path) for rel, path in file_inventory(backup.config.vault)}
    def fail(stage):
        if stage == point:
            raise Crash()
    restore.fault = fail
    with pytest.raises(Crash):
        restore.apply(archive)
    try:
        backup.state.close()
    except sqlite3.ProgrammingError:
        pass
    backup.state.reopen()
    restore.recover()
    assert not backup.coordinator.recovery_required
    assert {rel: sha_file(path) for rel, path in file_inventory(backup.config.vault)} == \
        (original if point == "committed" else latest)
    assert backup.state.setting("generation_marker") == (None if point == "committed" else "latest")
    restore.recover()


@pytest.mark.parametrize("filename", ["../escape", "vault/../escape", "/escape", "vault/A\\B", "vault/C:bad"])
def test_archive_paths_rejected_before_extraction(tmp_path, filename):
    archive = tmp_path / "hostile.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr(filename, "malicious")
    if "\\" in filename:
        archive.write_bytes(archive.read_bytes().replace(filename.replace("\\", "/").encode(), filename.encode()))
    with zipfile.ZipFile(archive) as source, pytest.raises(DomainError):
        zip_members(source, Config(home=tmp_path))


def test_corruption_wrong_trust_and_size_leave_live_state_unchanged(recovery, tmp_path):
    backup, restore, auth = recovery
    original = populate(backup, auth)
    archive = tmp_path / "base.zip"
    backup.create(archive)
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(tmp_path / "corrupt.zip", "w") as dst:
        dst.writestr("manifest.json", src.read("manifest.json"))
        dst.writestr("payload.age", src.read("payload.age") + b"corrupted")
    with pytest.raises(DomainError):
        restore.apply(tmp_path / "corrupt.zip")
    atomic_write(backup.secrets.directory / "backup_signing_public", base64.b64encode(
        Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)))
    with pytest.raises(DomainError, match="signature"):
        backup.inspect(archive)
    assert original == {rel: sha_file(path) for rel, path in file_inventory(backup.config.vault)}


def test_empty_vault_can_be_backed_up_and_restored(recovery, tmp_path):
    backup, restore, _ = recovery
    archive = tmp_path / "empty.zip"
    backup.create(archive)
    assert backup.inspect(archive)["notes"] == 0
    backup.vault.write("A.md", "after snapshot", None, create=True)
    restore.apply(archive)
    assert backup.vault.list() == []


@pytest.mark.parametrize("crash", [False, True])
def test_native_restore_verification_writes_only_private_copy_and_keeps_rollback_valid(recovery, tmp_path, crash):
    from contextlib import contextmanager
    backup, restore, auth = recovery
    populate(backup, auth)
    archive = tmp_path / "native-verification.zip"
    backup.create(archive)
    backup.vault.write("root.md", "Latest canonical text", sha_file(backup.config.vault / "root.md"))
    class VerificationPeer:
        @contextmanager
        def pause(self, *args, **kwargs):
            yield
        def request(self, method, route, payload):
            if route == "/internal/verify-generation":
                assert payload["vault_copy"] == ".verify-" + payload["operation_id"]
                candidate = backup.config.vault.parent / payload["vault_copy"]
                atomic_write(candidate / ".obsidian/workspace.json", b'{"native_startup":"changed"}')
                atomic_write(candidate / "root.md", b"Verification plugin changed only the copy")
                return {"verified": True}
            assert route == "/internal/quiesce"
            return {"state": "stopped"}
    restore.config = replace(backup.config, runtime_mode="supervised")
    backup.coordinator.runtime = VerificationPeer()
    if crash:
        restore.fault = lambda point: (_ for _ in ()).throw(Crash()) if point == "verified" else None
        with pytest.raises(Crash):
            restore.apply(archive)
        restore.recover()
        assert backup.vault.read("root.md") == "Latest canonical text"
        candidate = next(backup.config.vault.parent.glob(".verify-*"))
        assert (candidate / "root.md").read_bytes() == b"Verification plugin changed only the copy"
    else:
        restore.apply(archive)
        assert "Latest canonical text" != backup.vault.read("root.md")
        assert "Verification plugin" not in backup.vault.read("root.md")
        assert not list(backup.config.vault.parent.glob(".verify-*"))
    assert not restore.active and not backup.coordinator.recovery_required


def test_archive_output_does_not_clobber_existing_file(recovery, tmp_path):
    backup, _, _ = recovery
    archive = tmp_path / "already-exists.zip"
    archive.write_bytes(b"must survive")
    with pytest.raises(FileExistsError):
        backup.create(archive)
    assert archive.read_bytes() == b"must survive"


@pytest.mark.parametrize("attack", ["symlink", "case-collision", "nul", "ratio", "count"])
def test_archive_member_and_expansion_attacks(tmp_path, attack):
    archive = tmp_path / "attack.zip"
    config = Config(home=tmp_path, max_archive_entries=2)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as out:
        if attack == "symlink":
            info = zipfile.ZipInfo("vault/link")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            out.writestr(info, "/etc/passwd")
        elif attack == "case-collision":
            out.writestr("vault/A", "a")
            out.writestr("vault/a", "b")
        elif attack == "nul":
            out.writestr("vault/A!evil", "a")
        elif attack == "ratio":
            out.writestr("vault/bomb", bytes(2*1024**2))
        else:
            for i in range(3):
                out.writestr(f"vault/{i}", "a")
    if attack == "nul":
        archive.write_bytes(archive.read_bytes().replace(b"A!evil", b"A\0evil"))
    with zipfile.ZipFile(archive) as source, pytest.raises(DomainError):
        zip_members(source, config)


def test_restore_unknown_writer_preserves_changed_file_and_blocks_writes(recovery, tmp_path):
    backup, restore, auth = recovery
    populate(backup, auth)
    archive = tmp_path / "base.zip"
    backup.create(archive)
    def fail(point):
        if point == "new_vault_moved":
            raise Crash()
    restore.fault = fail
    with pytest.raises(Crash):
        restore.apply(archive)
    backup.state.reopen()
    changed = backup.config.vault / "root.md"
    changed.write_bytes(b"independent saved content")
    with pytest.raises(DomainError, match="Unknown changes"):
        restore.recover()
    assert backup.coordinator.recovery_required
    assert changed.read_bytes() == b"independent saved content"
    with pytest.raises(DomainError, match="requires recovery"):
        backup.vault.write("New.md", "must not write", None, create=True)


def test_retained_restore_generations_expire_after_24_hours(recovery, tmp_path):
    backup, restore, auth = recovery
    populate(backup, auth)
    archive = tmp_path / "base.zip"
    backup.create(archive)
    restore.apply(archive)
    restore.cleanup(now=time.time()+3600)
    assert list(restore.directory.iterdir())
    restore.cleanup(now=time.time()+86401)
    assert not list(restore.directory.iterdir())
    assert not list(backup.config.vault.parent.glob(".old-*"))
    assert backup.vault.list()


def test_recovery_spool_budget_includes_retained_backups(recovery):
    backup, restore, _ = recovery
    retained = restore.directory / "retained.bin"
    retained.write_bytes(bytes(1024))
    backup.spool.config = replace(backup.config, spool_quota=1000)
    with pytest.raises(DomainError) as error:
        backup.spool.reserve(1)
    assert error.value.code == "INSUFFICIENT_SPACE"


def test_backup_inspection_counts_uppercase_markdown(recovery, tmp_path):
    backup, _, _ = recovery
    backup.vault.write("Uppercase.MD", "#key\nCase-insensitive note extension", None, create=True)
    destination = tmp_path / "uppercase.zip"
    backup.create(destination)
    assert backup.inspect(destination)["notes"] == 1
