import hashlib
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

import pytest

from mastermind.bridge_artifacts import install_bridge_files
from mastermind.errors import DomainError
from mastermind.exports import Exports
from mastermind.fs import atomic_write, file_inventory, sha_file
from mastermind.portable import HISTORY, MANIFEST
from mastermind.references import parse


def test_portable_export_preserves_bytes_and_only_adds_owned_history(recovery):
    backup, _, _ = recovery
    artifacts = Path(__file__).resolve().parents[1] / "bridge/dist"
    install_bridge_files(backup.config.vault, artifacts)
    backup.vault.write("root.md", "#main\r\n@Deleted [[Café]] @Café\r\n", None, create=True)
    backup.vault.write("Café.md", "#key\n", None, create=True)
    backup.vault.write("Deleted.md", "delete me", None, create=True)
    backup.vault.delete("Deleted.md", sha_file(backup.config.vault / "Deleted.md"))
    with backup.state.transaction() as db:
        db.execute("INSERT INTO reference_history VALUES('saturn','root/my file.pdf','root/my file.pdf')")
    plugin = backup.config.vault / ".obsidian/plugins/opaque/data.json"
    atomic_write(plugin, b'{"opaque":"UNCHANGED-PLUGIN-CANARY"}\r\n')
    atomic_write(backup.config.home / "shell-secrets", b"SHELL-CREDENTIAL-NEVER-EXPORTED")
    atomic_write(backup.config.vault / "attachments/file.bin", bytes(range(256)))
    (backup.config.vault / "Empty/deep").mkdir(parents=True)
    original = {relative: sha_file(path) for relative, path in file_inventory(backup.config.vault)}
    exports = Exports(backup)
    artifact = exports.prepare("portable")
    try:
        with zipfile.ZipFile(artifact["path"]) as archive:
            actual = {item.filename: hashlib.sha256(archive.read(item)).hexdigest()
                      for item in archive.infolist() if not item.is_dir()}
            assert set(actual) == set(original) | {HISTORY, MANIFEST}
            assert all(actual[path] == digest for path, digest in original.items())
            assert "Empty/deep/" in archive.namelist()
            history = json.loads(archive.read(HISTORY))
            assert "Deleted" in history["internal"]
            assert history["saturn"] == ["root/my file.pdf"]
            manifest = json.loads(archive.read(MANIFEST))
            assert manifest["sync_supported"] is False
            assert manifest["generated_files"] == [HISTORY, MANIFEST]
            assert {item["path"]: item["sha256"] for item in manifest["original_files"]} == original
            assert manifest["replaced_bridge_metadata"] == []
            assert all(b"SHELL-CREDENTIAL-NEVER-EXPORTED" not in archive.read(item)
                       for item in archive.infolist() if not item.is_dir())
        assert {relative: sha_file(path) for relative, path in file_inventory(backup.config.vault)} == original
    finally:
        exports.release(artifact["snapshot_id"])
    assert not list(exports.directory.iterdir())


def test_portable_export_refuses_missing_bridge_and_cleans_staging(recovery):
    exports = Exports(recovery[0])
    with pytest.raises(DomainError, match="bundled Bridge"):
        exports.prepare("portable")
    assert not list(exports.directory.iterdir())


def test_portable_conformance_fixture_stays_equal_to_core():
    source = Path(__file__).resolve().parents[1] / "bridge/tests/portable-cases.json"
    if not source.exists():
        pytest.skip("Bridge conformance cases are checked in the Node qualification job")
    for item in json.loads(source.read_text("utf-8")):
        assert [asdict(ref) for ref in parse(item["text"], item["current"], item["history"], item["saturn"])] == item["expected"]
