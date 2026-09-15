import os
from dataclasses import replace

import pytest

from mastermind.bridge_artifacts import install_bridge_files
from mastermind.errors import DomainError
from mastermind.fs import atomic_write_under, open_under, remove_private_tree, sha_under


def test_descriptor_file_operations_preserve_bytes_and_no_clobber(tmp_path):
    atomic_write_under(tmp_path, "Folder/Note.md", b"bytes\r\n", create=True)
    assert sha_under(tmp_path, "Folder/Note.md")
    with open_under(tmp_path, "Folder/Note.md") as stream:
        assert stream.read() == b"bytes\r\n"
    with pytest.raises(FileExistsError):
        atomic_write_under(tmp_path, "Folder/Note.md", b"unwanted", create=True)
    assert (tmp_path / "Folder/Note.md").read_bytes() == b"bytes\r\n"
    assert not list((tmp_path / "Folder").glob(".mastermind-*"))


@pytest.mark.skipif(os.name != "posix", reason="Production Linux descriptor and permissions boundary")
@pytest.mark.parametrize("operation", ["read", "write"])
def test_directory_swap_never_follows_symlink_outside_root(tmp_path, monkeypatch, operation):
    root, outside = tmp_path / "vault", tmp_path / "outside"
    (root / "child").mkdir(parents=True)
    outside.mkdir()
    (outside / "secret.md").write_bytes(b"outside-sentinel")
    (root / "child/secret.md").write_bytes(b"inside")
    original = os.open
    def swapped(path, flags, *args, **kwargs):
        if path == "child" and not (root / "child").is_symlink():
            (root / "child").rename(root / "original-child")
            (root / "child").symlink_to(outside, target_is_directory=True)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", swapped)
    with pytest.raises(DomainError):
        if operation == "read":
            with open_under(root, "child/secret.md"):
                pytest.fail("Outside content became readable")
        else:
            atomic_write_under(root, "child/secret.md", b"replacement")
    assert (outside / "secret.md").read_bytes() == b"outside-sentinel"


@pytest.mark.skipif(os.name != "posix", reason="Production Linux descriptor and permissions boundary")
def test_symlink_and_hardlink_leaf_are_rejected(tmp_path):
    (tmp_path / "original.md").write_bytes(b"original")
    os.link(tmp_path / "original.md", tmp_path / "hard.md")
    (tmp_path / "symbolic.md").symlink_to(tmp_path / "original.md")
    for path in ("hard.md", "symbolic.md"):
        with pytest.raises(DomainError), open_under(tmp_path, path):
            pytest.fail("Linked file became readable")


@pytest.mark.skipif(os.name != "posix", reason="Production Linux executable and read-only plugin data")
def test_full_restore_preserves_opaque_plugin_modes(recovery, tmp_path):
    backup, restore, _ = recovery
    plugin = backup.config.vault / ".obsidian/plugins/opaque"
    plugin.mkdir(parents=True)
    binary, readonly = plugin / "native-helper", plugin / "read-only.conf"
    binary.write_bytes(b"#!/bin/sh\nprintf 'opaque executable'\n")
    readonly.write_bytes(b"opaque-private-plugin-data")
    binary.chmod(0o750)
    readonly.chmod(0o440)
    plugin.chmod(0o550)
    archive = tmp_path / "permissions.zip"
    backup.create(archive)
    restore.apply(archive)
    assert binary.stat().st_mode & 0o777 == 0o750
    assert readonly.stat().st_mode & 0o777 == 0o440
    assert plugin.stat().st_mode & 0o777 == 0o550
    assert readonly.read_bytes() == b"opaque-private-plugin-data"
    # Private cleanup must work without weakening permissions in the live Vault.
    stage = tmp_path / "private-cleanup"
    stage.mkdir()
    child = stage / "read-only"
    child.mkdir()
    (child / "file").write_bytes(b"cleanup")
    (child / "file").chmod(0o400)
    child.chmod(0o500)
    remove_private_tree(stage, tmp_path)
    assert not stage.exists()
    assert readonly.stat().st_mode & 0o777 == 0o440


def test_restore_installs_trusted_bridge_before_generation_digest(recovery, tmp_path):
    import json

    from mastermind.fs import sha_bytes
    backup, restore, _ = recovery
    artifact = tmp_path / "trusted-release"
    artifact.mkdir()
    files = {"main.js": b"release-owned-current", "manifest.json": b'{"version":"0.0.1"}', "styles.css": b""}
    for name, data in files.items():
        (artifact / name).write_bytes(data)
    (artifact / "integrity.json").write_text(json.dumps({name: sha_bytes(data) for name, data in files.items()}))
    install_bridge_files(backup.config.vault, artifact)
    plugin = backup.config.vault / ".obsidian/plugins/mastermind-bridge"
    (plugin / "data.json").write_bytes(b"user plugin settings stay opaque")
    (plugin / "main.js").write_bytes(b"previous-release")
    archive = tmp_path / "old-bridge.zip"
    backup.create(archive)
    restore.config = replace(restore.config, bridge_artifacts=artifact)
    restore.apply(archive)
    assert (plugin / "main.js").read_bytes() == files["main.js"]
    assert (plugin / "data.json").read_bytes() == b"user plugin settings stay opaque"
