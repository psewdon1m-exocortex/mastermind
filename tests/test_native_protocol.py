from contextlib import contextmanager
from dataclasses import replace

import pytest

from mastermind.errors import DomainError
from mastermind.fs import atomic_write, sha_file
from mastermind.native_rename import NativeRename


class PowerLoss(BaseException):
    pass


class ProtocolRuntime:
    """Fault-injection peer only. The separate browser suite uses official Obsidian."""
    def __init__(self, vault):
        self.vault = vault
        self.native = None
        self.after_native = lambda: None

    def request(self, method, route, payload=None):
        return {"state": "stopped", "buffers_verified": True}

    @contextmanager
    def pause(self, identity, resume_if=lambda: True):
        yield

    def native_rename(self, old, new, identity):
        root = self.vault.config.vault
        source = root / old
        text = source.read_text("utf-8")
        self.native.intent({"operation_id": identity, "writes": [{"path": old, "remove": True},
            {"path": new, "text": text}], "expected": {old: sha_file(source), new: None}})
        (root / new).parent.mkdir(parents=True, exist_ok=True)
        source.rename(root / new)
        text = (root / "Links.md").read_text("utf-8")
        after = text.replace("[[Old]]", "[[New]]")
        self.native.intent({"operation_id": identity, "writes": [{"path": "Links.md", "text": after}],
                            "expected": {"Links.md": sha_file(root / "Links.md")}})
        atomic_write(root / "Links.md", after.encode())
        self.after_native()
        return {"renamed": True}


@pytest.fixture
def native(service):
    config, _, coordinator, vault = service
    vault.write("Old.md", "#main\nBody\n", None, create=True)
    vault.write("Links.md", "[[Old]] @Old\n`@Old`\n<!-- @Old -->\n", None, create=True)
    vault.config = replace(config, runtime_mode="supervised")
    coordinator.runtime = runtime = ProtocolRuntime(vault)
    native = runtime.native = NativeRename(vault)
    return native, runtime, sha_file(config.vault / "Old.md")


def test_managed_rename_commits_custom_refs_and_two_activity_kinds(native):
    operation, _, digest = native
    result = operation.rename("Old.md", "Branch/New.md", digest)
    assert result["path"] == "Branch/New.md"
    assert operation.vault.read("Links.md") == "[[New]] @New\n`@Old`\n<!-- @Old -->\n"
    assert not (operation.vault.config.vault / "Old.md").exists()
    assert {row["kind"] for row in operation.state.rows("SELECT kind FROM activity")} == {"RENAME", "MOVE"}
    assert operation.state.one("SELECT * FROM reference_history WHERE name_key='old'")
    assert operation.state.one("SELECT * FROM reference_history WHERE name_key='new'")
    assert not list(operation.coordinator.directory.iterdir())


@pytest.mark.parametrize("point", ["prepared", "native_stopped", "patch:Links.md"])
def test_native_crash_recovers_one_complete_generation(native, point):
    operation, _, digest = native
    def fail(current):
        if current == point:
            raise PowerLoss()
    operation.fault = fail
    with pytest.raises(PowerLoss):
        operation.rename("Old.md", "New.md", digest)
    assert operation.coordinator.recovery_required
    operation.coordinator.recover()
    operation.vault.index(force=True)
    if point == "patch:Links.md":
        assert operation.vault.read("Links.md") == "[[New]] @New\n`@Old`\n<!-- @Old -->\n"
        assert (operation.vault.config.vault / "New.md").is_file()
        assert len(operation.state.rows("SELECT * FROM activity")) == 1
    else:
        assert operation.vault.read("Links.md") == "[[Old]] @Old\n`@Old`\n<!-- @Old -->\n"
        assert (operation.vault.config.vault / "Old.md").is_file()
        assert not operation.state.rows("SELECT * FROM activity")
    assert not operation.coordinator.recovery_required


def test_unknown_native_writer_is_preserved_and_blocks_rollback(native):
    operation, runtime, digest = native
    path = operation.vault.config.vault / "Links.md"
    runtime.after_native = lambda: atomic_write(path, b"Unknown plugin data to preserve")
    with pytest.raises(DomainError, match="differs"):
        operation.rename("Old.md", "New.md", digest)
    assert operation.coordinator.recovery_required
    assert path.read_bytes() == b"Unknown plugin data to preserve"
    with pytest.raises(DomainError):
        operation.coordinator.recover()
    assert list(operation.coordinator.directory.glob("*/baseline/*"))


def test_unregistered_native_writer_cannot_be_silently_rolled_back(native):
    operation, runtime, digest = native
    untouched = operation.vault.config.vault / "Unrelated.md"
    atomic_write(untouched, b"Original unrelated content")
    operation.vault.index()
    runtime.after_native = lambda: atomic_write(untouched, b"Unregistered plugin content")
    with pytest.raises(DomainError, match="unregistered"):
        operation.rename("Old.md", "New.md", digest)
    assert operation.coordinator.recovery_required
    assert untouched.read_bytes() == b"Unregistered plugin content"
    assert any(path.read_bytes() == b"Original unrelated content"
               for path in operation.coordinator.directory.glob("*/baseline/*"))


def test_native_preflight_conflict_does_not_write(native):
    operation, _, _ = native
    with pytest.raises(DomainError, match="source changed"):
        operation.rename("Old.md", "New.md", "0"*64)
    assert operation.vault.read("Old.md") == "#main\nBody\n"
    assert not operation.coordinator.recovery_required


def test_offline_rename_does_not_fall_back_to_filesystem(service):
    native = NativeRename(service[3])
    with pytest.raises(DomainError) as error:
        native.rename("Old.md", "New.md", "0"*64)
    assert error.value.code == "RUNTIME_UNAVAILABLE"


class PathRuntime(ProtocolRuntime):
    def native_rename(self, old, new, identity):
        root = self.vault.config.vault
        self.native.intent({"operation_id": identity, "move": [old, new]})
        (root / new).parent.mkdir(parents=True, exist_ok=True)
        (root / old).rename(root / new)
        before = self.vault.read("Links.md")
        # The peer represents native Obsidian propagation; live tests exercise FileManager itself.
        after = before.replace(old, new)
        self.native.intent({"operation_id": identity, "writes": [{"path": "Links.md", "text": after}],
                            "expected": {"Links.md": sha_file(root / "Links.md")}})
        atomic_write(root / "Links.md", after.encode())
        self.after_native()


@pytest.mark.parametrize("is_directory", [False, True])
@pytest.mark.parametrize("crash", [None, "prepared", "intent", "native_stopped", "final_prepared"])
def test_attachment_and_folder_moves_recover_bytes_empty_directories_and_share_paths(service, is_directory, crash, monkeypatch):
    from pathlib import Path
    config, state, coordinator, vault = service
    vault.config = replace(config, runtime_mode="supervised")
    coordinator.runtime = runtime = PathRuntime(vault)
    operation = runtime.native = NativeRename(vault)
    old = "Branch" if is_directory else "picture.bin"
    new = "Moved" if is_directory else "new-picture.bin"
    binary = "Branch/picture.bin" if is_directory else old
    atomic_write(config.vault / binary, bytes(range(256))*4096)
    digest = sha_file(config.vault / binary)
    (config.vault / "Branch/Empty/deep").mkdir(parents=True)
    # Use offline Core writes to populate the isolated fixture, then restore its protocol peer.
    vault.config = config
    vault.write("Links.md", "![[" + binary + "]]\n@Topic\n", None, create=True)
    vault.write("Branch/Topic.md", "#key\n", None, create=True)
    vault.config = replace(config, runtime_mode="supervised")
    with state.transaction() as db:
        db.execute("INSERT INTO shares VALUES('test-share','hash','v1','Branch/Topic.md','view',NULL,0,0,NULL,NULL,1)")
    before = operation.version(old)["sha256"]
    original_read = Path.read_bytes
    def no_binary_buffer(path):
        if path.suffix in (".bin", ".before", ".after"):
            raise AssertionError("A binary recovery file was read wholly into RAM")
        return original_read(path)
    monkeypatch.setattr(Path, "read_bytes", no_binary_buffer)
    if crash:
        operation.fault = lambda point: (_ for _ in ()).throw(PowerLoss()) if point == crash else None
        with pytest.raises(PowerLoss):
            operation.rename(old, new, before)
        coordinator.recover()
    else:
        operation.rename(old, new, before)
    committed = crash in (None, "final_prepared")
    destination = binary.replace(old, new, 1) if committed else binary
    assert sha_file(config.vault / destination) == digest
    assert vault.read("Links.md") == "![[" + destination + "]]\n@Topic\n"
    folder = "Moved" if is_directory and committed else "Branch"
    assert (config.vault / folder / "Empty/deep").is_dir()
    assert state.one("SELECT path FROM shares WHERE id='test-share'")["path"] == folder + "/Topic.md"
    assert len(state.rows("SELECT * FROM activity WHERE kind='MOVE'")) == int(is_directory and committed)
    assert not list(coordinator.directory.iterdir())
    assert not coordinator.recovery_required


def test_empty_folder_move_and_recovery(service):
    config, _, coordinator, vault = service
    vault.write("Links.md", "No references\n", None, create=True)
    (config.vault / "Empty/deep").mkdir(parents=True)
    vault.config = replace(config, runtime_mode="supervised")
    coordinator.runtime = runtime = PathRuntime(vault)
    operation = runtime.native = NativeRename(vault)
    operation.rename("Empty", "Elsewhere", operation.version("Empty")["sha256"])
    assert (config.vault / "Elsewhere/deep").is_dir()
    assert not (config.vault / "Empty").exists()
