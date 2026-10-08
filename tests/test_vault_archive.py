import hashlib
import io
import json
import stat
import struct
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace

import pytest
from test_api import api as api_fixture
from test_api import authenticate
from test_owner_operations import wait

from mastermind.errors import DomainError
from mastermind.fs import atomic_write, file_inventory, sha_file
from mastermind.restore import tree_digest
from mastermind.vault_archive import VaultArchive, directory_budget

api = api_fixture


def archive_at(path, files, compression=zipfile.ZIP_STORED):
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, data in files:
            if isinstance(name, str) and "\\" in name:
                entry = zipfile.ZipInfo(name)
                entry.filename = name  # Write the malicious bytes unchanged on Windows too.
                name = entry
            archive.writestr(name, data)
    return path


def populate(backup):
    files = {"root/root.md": b"#main\r\n[[Birds]]\r\n", "root/Animals/Birds.md": "#key\nПтицы @root".encode(),
             "attachments/Фото.bin": bytes(range(256))*1024,
             ".obsidian/plugins/other/data.json": b'{"opaque":"PLUGIN-DATA-UNCHANGED"}',
             ".obsidian/appearance.json": b'{"cssTheme":"Example"}', ".trash/old.txt": b"old",
             ".obsidian/app.json": b'{"alwaysUpdateLinks":true}'}
    for name, data in files.items():
        atomic_write(backup.config.vault / name, data)
    (backup.config.vault / "empty/nested").mkdir(parents=True)
    atomic_write(backup.config.home / "shell-canary", b"SHELL-SECRET-OUTSIDE-VAULT")
    return files


def test_plain_export_and_restore_preserve_the_complete_obsidian_root(recovery, tmp_path, monkeypatch):
    backup, restore, auth = recovery
    files = populate(backup)
    auth.initialize("current target key")
    backup.state.set_setting("appearance", {"accent": "#102030"})
    backup.state.set_setting("_backup_policy_restore", {"requestId": "already-pending"})
    # Functional backup/restore must work without Kernel, Neptune or recovery keys.
    monkeypatch.setattr(backup.secrets, "read", lambda *_: pytest.fail("Vault ZIP requested a Shell recovery secret"))
    zip_path = tmp_path / "vault.zip"
    artifact = restore.vault_archive.create(zip_path)
    assert artifact == {"size": zip_path.stat().st_size, "sha256": sha_file(zip_path)}
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.testzip() is None
        assert {i.filename: archive.read(i) for i in archive.infolist() if not i.is_dir()} == files
        assert "empty/nested/" in archive.namelist()
        assert not any(name.startswith("vault/") for name in archive.namelist())
    assert b"SHELL-SECRET-OUTSIDE-VAULT" not in zip_path.read_bytes()
    assert not list(backup.spool.directory.iterdir())
    before = tree_digest(backup.config.vault)
    inspection = restore.vault_archive.inspect(zip_path)
    assert inspection["notes"] == 2 and inspection["files"] == len(files)
    assert inspection["root_prefix"] == "" and inspection["shell_settings_preserved"]
    assert tree_digest(backup.config.vault) == before
    session = auth.login("current target key", "test")
    atomic_write(backup.config.vault / "root/root.md", b"modified")
    atomic_write(backup.config.vault / "later.md", b"created after snapshot")
    backup.state.set_setting("appearance", {"accent": "#abcdef"})
    result = restore.apply(zip_path, vault_only=True)
    assert result["state"] == "COMPLETED" and result["notes"] == 2
    assert {p: path.read_bytes() for p, path in file_inventory(backup.config.vault)} == files
    assert (backup.config.vault / "empty/nested").is_dir()
    assert backup.state.setting("appearance") == {"accent": "#abcdef"}
    assert backup.state.setting("_backup_policy_restore") == {"requestId": "already-pending"}
    assert backup.vault.graph()["connectedness"] == 100
    with pytest.raises(DomainError):
        auth.session(session["token"])
    assert auth.login("current target key", "after")
    assert not list(restore.directory.iterdir())
    assert not list(backup.spool.directory.iterdir())


def test_wrapper_is_removed_only_for_an_identifiable_obsidian_vault(recovery, tmp_path):
    backup, restore, _ = recovery
    wrapped = archive_at(tmp_path / "wrapped.zip", [("My Vault/", b""), ("My Vault/.obsidian/app.json", b'{}'),
                                                    ("My Vault/root/Note.md", b"hello")])
    assert restore.vault_archive.inspect(wrapped)["root_prefix"] == "My Vault/"
    restore.apply(wrapped, vault_only=True)
    assert (backup.config.vault / "root/Note.md").read_bytes() == b"hello"
    assert not (backup.config.vault / "My Vault").exists()
    normal = archive_at(tmp_path / "normal.zip", [("root/Note.md", b"hello")])
    assert restore.vault_archive.inspect(normal)["root_prefix"] == ""
    restore.apply(normal, vault_only=True)
    assert (backup.config.vault / "root/Note.md").is_file()


@pytest.mark.parametrize("entries", [
    [("../escape.md", b"no")], [("/absolute.md", b"no")], [("C:/drive.md", b"no")],
    [("folder\\escape.md", b"no")], [("Note.md:stream", b"no")], [("nul.md", b"no")],
    [("a.md", b"a"), ("A.md", b"b")], [("Café.md", b"a"), ("Cafe\u0301.md", b"b")],
    [("folder/a.md", b"a"), ("Folder/b.md", b"b")], [("folder/a.md", b"a"), ("folder", b"b")],
    [("folder", b"b"), ("folder/a.md", b"a")], [("folder/", b"unexpected bytes")],
    [("Branch/Note.md", b"a"), ("Other/Note.md", b"b")], [("Note.md", b"\xff\xfe")],
    [("manifest.json", b"{}"), ("payload.age", b"encrypted service archive")],
])
def test_bad_archive_is_rejected_without_mutating_live_data(recovery, tmp_path, entries):
    backup, restore, _ = recovery
    atomic_write(backup.config.vault / "Existing.md", b"preserve")
    before = tree_digest(backup.config.vault)
    source = archive_at(tmp_path / "invalid.zip", entries)
    with pytest.raises(DomainError):
        restore.vault_archive.inspect(source)
    assert tree_digest(backup.config.vault) == before
    assert not list(backup.spool.directory.iterdir())


@pytest.mark.parametrize("mode", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR])
def test_archive_special_files_are_rejected(recovery, tmp_path, mode):
    entry = zipfile.ZipInfo("link")
    entry.create_system = 3
    entry.external_attr = (mode | 0o777) << 16
    source = archive_at(tmp_path / "special.zip", [(entry, b"../outside")])
    with pytest.raises(DomainError, match="linked"):
        recovery[1].vault_archive.inspect(source)


def test_corrupt_crc_truncated_archive_and_encryption_flags_are_rejected(recovery, tmp_path):
    source = archive_at(tmp_path / "valid.zip", [("Note.md", b"body")])
    original = source.read_bytes()
    offset = 30+len("Note.md")
    corrupted = original[:offset]+bytes([original[offset] ^ 0xff])+original[offset+1:]
    encrypted = bytearray(original)
    encrypted[6] |= 1
    central = original.index(b"PK\x01\x02")
    encrypted[central+8] |= 1
    for name, data in [("crc", corrupted), ("truncated", original[:-15]), ("encrypted", encrypted)]:
        source = tmp_path / (name+".zip")
        source.write_bytes(data)
        with pytest.raises(DomainError):
            recovery[1].vault_archive.inspect(source)


def test_archive_limits_are_checked_before_expansion(recovery, tmp_path):
    backup, _, _ = recovery
    archive = VaultArchive(backup)
    source = archive_at(tmp_path / "limits.zip", [("a/b.md", b"0123456789"), ("c.md", b"1234")])
    for limits in [{"max_backup_bytes": 10}, {"max_expanded_bytes": 13}, {"max_archive_entries": 1},
                   {"max_archive_entries": 2}, {"max_note_bytes": 9}]:
        archive.config = replace(backup.config, **limits)
        with pytest.raises(DomainError):
            archive.inspect(source)
    archive.config = backup.config
    source = archive_at(tmp_path / "bomb.zip", [("bomb.bin", b"0"*(4*1024**2))], zipfile.ZIP_DEFLATED)
    with pytest.raises(DomainError, match="expansion"):
        archive.inspect(source)
    data = bytearray(archive_at(tmp_path / "central.zip", [("a.md", b"x")]).read_bytes())
    struct.pack_into("<L", data, len(data)-22+12, 65*1024**2)
    (tmp_path / "central.zip").write_bytes(data)
    with pytest.raises(DomainError, match="directory exceeds"):
        archive.inspect(tmp_path / "central.zip")


@pytest.mark.parametrize("empty_folder", [False, True])
def test_empty_vault_export_can_be_restored(recovery, tmp_path, empty_folder):
    backup, restore, _ = recovery
    if empty_folder:
        (backup.config.vault / "empty/nested").mkdir(parents=True)
    source = tmp_path / "empty.zip"
    restore.vault_archive.create(source)
    assert restore.vault_archive.inspect(source)["files"] == 0
    atomic_write(backup.config.vault / "Later.md", b"not in snapshot")
    assert restore.apply(source, vault_only=True)["notes"] == 0
    assert list(file_inventory(backup.config.vault)) == []
    assert (backup.config.vault / "empty/nested").is_dir() == empty_folder


@pytest.mark.parametrize("sentinels", [True, False])
def test_zip64_directory_is_validated_without_large_payloads(recovery, tmp_path, sentinels):
    source = archive_at(tmp_path / "zip64.zip", [("Note.md", b"content")])
    data = source.read_bytes()
    offset = len(data)-22
    record = bytearray(data[-22:])
    central_size, central_offset = struct.unpack_from("<LL", record, 12)
    if sentinels:
        struct.pack_into("<HHLL", record, 8, 65535, 65535, 0xffffffff, 0xffffffff)
    zip64 = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, 1, 1, central_size, central_offset)
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, offset, 1)
    source.write_bytes(data[:offset]+zip64+locator+record)
    assert recovery[1].vault_archive.inspect(source)["notes"] == 1
    bad = bytearray(source.read_bytes())
    struct.pack_into("<Q", bad, offset+24, 100001)
    struct.pack_into("<Q", bad, offset+32, 100001)
    source.write_bytes(bad)
    with pytest.raises(DomainError, match="directory exceeds"):
        recovery[1].vault_archive.inspect(source)


def test_classic_zip_count_at_sentinel_does_not_require_zip64(recovery, tmp_path):
    # Header-only preallocation check: the classic counter can equal 0xffff.
    source = archive_at(tmp_path / "count.zip", [("Note.md", b"content")])
    data = bytearray(source.read_bytes())
    struct.pack_into("<HH", data, len(data)-22+8, 65535, 65535)
    source.write_bytes(data)
    directory_budget(source, recovery[0].config)
    with pytest.raises(DomainError, match="directory exceeds"):
        directory_budget(source, replace(recovery[0].config, max_archive_entries=65534))


def test_export_output_limit_releases_boundary_and_staging(recovery, tmp_path):
    backup, restore, _ = recovery
    populate(backup)
    before = tree_digest(backup.config.vault)
    restore.vault_archive.config = replace(backup.config, max_backup_bytes=32)
    with pytest.raises(DomainError):
        restore.vault_archive.create(tmp_path / "limited.zip")
    assert tree_digest(backup.config.vault) == before
    assert not list(backup.spool.directory.iterdir())
    with backup.coordinator.boundary():
        pass


@pytest.mark.parametrize("operation", ["create", "inspect", "restore"])
def test_vault_operation_without_disk_reservation_keeps_current_data(recovery, tmp_path, operation):
    backup, restore, _ = recovery
    atomic_write(backup.config.vault / "Current.md", b"keep")
    source = archive_at(tmp_path / "new.zip", [("New.md", b"new")])
    backup.spool.config = replace(backup.config, spool_quota=1)
    with pytest.raises(DomainError, match="reserve enough"):
        if operation == "restore":
            restore.apply(source, vault_only=True)
        elif operation == "create":
            restore.vault_archive.create(tmp_path / "export.zip")
        else:
            restore.vault_archive.inspect(source)
    assert (backup.config.vault / "Current.md").read_bytes() == b"keep"
    assert not (backup.config.vault / "New.md").exists()
    assert not list(backup.spool.directory.iterdir())
    assert not restore.active and not backup.coordinator.recovery_required


@pytest.mark.parametrize("accepted", [True, False])
def test_vault_runtime_verifies_private_copy_and_rejection_rolls_back(recovery, tmp_path, accepted):
    backup, restore, _ = recovery
    atomic_write(backup.config.vault / "Old.md", b"original")
    source = archive_at(tmp_path / "incoming.zip", [("New.md", b"imported")])
    requests = []
    class RuntimePeer:
        @contextmanager
        def pause(self, *args, **kwargs):
            yield
        def request(self, method, route, payload):
            requests.append(route)
            if route == "/internal/verify-generation":
                assert payload["vault_copy"] == ".verify-"+payload["operation_id"]
                candidate = backup.config.vault.parent / payload["vault_copy"]
                atomic_write(candidate / "New.md", b"native startup only touches private copy")
                return {"verified": accepted}
            assert route == "/internal/quiesce"
            return {"state": "stopped"}
    restore.config = replace(backup.config, runtime_mode="supervised")
    backup.coordinator.runtime = RuntimePeer()
    if accepted:
        restore.apply(source, vault_only=True)
        assert (backup.config.vault / "New.md").read_bytes() == b"imported"
    else:
        with pytest.raises(DomainError, match="Runtime rejected"):
            restore.apply(source, vault_only=True)
        assert (backup.config.vault / "Old.md").read_bytes() == b"original"
        assert not (backup.config.vault / "New.md").exists()
        assert "/internal/quiesce" in requests
    assert "/internal/verify-generation" in requests
    assert not list(backup.config.vault.parent.glob(".verify-*"))
    assert not backup.coordinator.recovery_required


def test_managed_bridge_is_reinstalled_without_replacing_plugin_data(recovery, tmp_path):
    backup, restore, _ = recovery
    artifacts = tmp_path / "bridge-release"
    owned = {"main.js": b"release bridge", "styles.css": b"release styles", "manifest.json": b'{}'}
    for name, content in owned.items():
        atomic_write(artifacts / name, content)
    atomic_write(artifacts / "integrity.json", json.dumps({n: hashlib.sha256(v).hexdigest() for n, v in owned.items()}).encode())
    prefix = ".obsidian/plugins/mastermind-bridge/"
    source = archive_at(tmp_path / "bridge.zip", [(prefix+"main.js", b"old bridge"),
        (prefix+"data.json", b'{"opaque":"keep"}'), (".obsidian/plugins/other/data.json", b"opaque plugin data"),
        (".obsidian/community-plugins.json", b'["other"]'), ("Note.md", b"note")])
    restore.config = replace(backup.config, bridge_artifacts=artifacts)
    restore.apply(source, vault_only=True)
    for name, content in owned.items():
        assert (backup.config.vault / (prefix+name)).read_bytes() == content
    assert (backup.config.vault / (prefix+"data.json")).read_bytes() == b'{"opaque":"keep"}'
    assert (backup.config.vault / ".obsidian/plugins/other/data.json").read_bytes() == b"opaque plugin data"
    assert json.loads((backup.config.vault / ".obsidian/community-plugins.json").read_bytes()) == ["other", "mastermind-bridge"]


@pytest.mark.parametrize("point", ["prepared", "old_vault_moved", "new_vault_moved", "new_db_moved", "verified"])
def test_vault_restore_rolls_back_on_failure_at_every_switch_phase(recovery, tmp_path, point):
    backup, restore, _ = recovery
    atomic_write(backup.config.vault / "Old.md", b"old")
    backup.state.set_setting("appearance", {"accent": "#123456"})
    source = archive_at(tmp_path / "new.zip", [("New.md", b"new")])
    before = tree_digest(backup.config.vault)
    def fail(phase):
        if phase == point:
            raise OSError("injected switch failure")
    restore.fault = fail
    with pytest.raises(OSError, match="injected"):
        restore.apply(source, vault_only=True)
    assert tree_digest(backup.config.vault) == before
    assert backup.state.setting("appearance") == {"accent": "#123456"}
    assert not restore.active and not backup.coordinator.recovery_required


def test_interrupted_vault_restore_recovers_pair_after_restart(recovery, tmp_path):
    backup, restore, _ = recovery
    atomic_write(backup.config.vault / "Old.md", b"old")
    source = archive_at(tmp_path / "new.zip", [("New.md", b"new")])
    class Crash(BaseException):
        pass
    def crash(phase):
        if phase == "new_db_moved":
            raise Crash()
    restore.fault = crash
    with pytest.raises(Crash):
        restore.apply(source, vault_only=True)
    assert backup.coordinator.recovery_required
    restore.recover()
    restore.cleanup()
    assert (backup.config.vault / "Old.md").read_bytes() == b"old"
    assert not (backup.config.vault / "New.md").exists()
    assert not backup.coordinator.recovery_required


def test_owner_vault_download_inspect_restore_exact_digest_and_revoked_capabilities(api):
    client, service = api
    assert client.post('/api/owner/operations', json={"kind": "vault"}).status_code == 401
    authenticate(client)
    files = populate(service.backup)
    assert client.post('/api/owner/operations', json={"kind": "vault"}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    identifier = client.post('/api/owner/operations', json={"kind": "vault"}).json()["id"]
    assert wait(service, identifier)["state"] == "COMPLETED"
    download = client.get('/api/owner/operations/'+identifier+'/download')
    assert download.status_code == 200 and download.headers['content-type'] == 'application/zip'
    assert download.headers['content-disposition'] == 'attachment; filename="vault.zip"'
    digest = hashlib.sha256(download.content).hexdigest()
    assert download.headers['x-content-sha256'] == digest
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert {i.filename: archive.read(i) for i in archive.infolist() if not i.is_dir()} == files
    assert not (service.owner_operations.directory / identifier / "download.zip").exists()
    service.state.set_setting("appearance", {"accent": "#789abc"})
    service.state.db.execute("INSERT INTO shares VALUES('s','token','v1','root/root.md','read',NULL,1,1,NULL,NULL,1)")
    service.state.db.execute("INSERT INTO codes VALUES('code',1,9999999999,NULL)")
    service.state.db.execute("INSERT INTO semantic_text VALUES('removed.md','sha','old corpus')")
    service.state.db.execute("INSERT INTO jobs VALUES('job','owner','once','sha','RUNNING','EXTRACTING',0,1,1,?,NULL,NULL)",
                            (json.dumps({"source_path": "old-file"}),))
    identifier = client.post('/api/owner/operations', json={"kind": "vault_restore", "size": len(download.content)}).json()["id"]
    route = '/api/owner/operations/'+identifier
    assert client.put(route+'/content', content=download.content).json()["sha256"] == digest
    assert client.post(route+'/confirm', json={"action": "restore", "sha256": digest}).status_code == 409
    assert client.post(route+'/confirm', json={"action": "inspect", "sha256": "0"*64}).status_code == 409
    assert client.post(route+'/confirm', json={"action": "inspect", "sha256": digest}).status_code == 200
    assert wait(service, identifier)["inspection"]["notes"] == 2
    atomic_write(service.config.vault / "Added.md", b"later")
    assert client.post(route+'/confirm', json={"action": "restore", "sha256": digest}).status_code == 200
    assert wait(service, identifier)["state"] == "COMPLETED"
    assert client.get('/api/auth/session').status_code == 401
    authenticate(client)
    assert client.get(route+'/download').status_code == 409
    assert service.state.setting("appearance") == {"accent": "#789abc"}
    assert service.state.one("SELECT revoked_at FROM shares WHERE id='s'")["revoked_at"] is not None
    assert service.state.rows("SELECT * FROM codes") == []
    assert service.state.rows("SELECT * FROM semantic_text") == []
    assert service.state.one("SELECT state FROM jobs WHERE id='job'")["state"] == "FAILED"
    assert not (service.config.vault / "Added.md").exists()
    assert not (service.owner_operations.directory / identifier / "upload.zip").exists()


def test_staged_vault_archive_cannot_change_after_inspection(api, tmp_path):
    client, service = api
    authenticate(client)
    source = archive_at(tmp_path / "new.zip", [("New.md", b"new")]).read_bytes()
    identifier = client.post('/api/owner/operations', json={"kind": "vault_restore", "size": len(source)}).json()["id"]
    route = '/api/owner/operations/'+identifier
    digest = client.put(route+'/content', content=source).json()["sha256"]
    client.post(route+'/confirm', json={"action": "inspect", "sha256": digest})
    assert wait(service, identifier)["state"] == "AWAITING_CONFIRMATION"
    (service.owner_operations.directory / identifier / "upload.zip").write_bytes(source+b"changed")
    client.post(route+'/confirm', json={"action": "restore", "sha256": digest})
    assert wait(service, identifier)["error"] == "RESTORE_INTEGRITY"
    assert not (service.config.vault / "New.md").exists()


def test_status_polling_during_progress_updates_keeps_operation_readable(api):
    _, service = api
    operations = service.owner_operations
    record = operations.create("vault_restore", size=100)
    def poll():
        for _ in range(100):
            assert operations.read(record["id"])["state"] == "WAITING_UPLOAD"
    def advance():
        for progress in range(100):
            operations.save(record, progress=progress)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(poll), pool.submit(poll), pool.submit(advance)]
        for future in futures:
            future.result(timeout=10)
    assert operations.read(record["id"])["progress"] == 99
