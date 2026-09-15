import zipfile

import pytest

from mastermind.errors import DomainError
from mastermind.exports import Exports
from mastermind.fs import sha_bytes


def test_consistent_archive_and_mirror_coalesce_and_state_changes_invalidate(recovery):
    backup, _, _ = recovery
    backup.vault.write("root.md", "# root\n", None, create=True)
    exports = Exports(backup)
    archive = exports.prepare("archive")
    mirror = exports.prepare("mirror")
    assert archive["snapshot_id"] == mirror["snapshot_id"]
    assert archive["generation"] == mirror["generation"]
    with zipfile.ZipFile(mirror["path"]) as content:
        assert content.read("root.md") == b"# root\n"
    backup.verify_wrapper(archive["path"])
    exports.release(archive["snapshot_id"])
    exports.release(mirror["snapshot_id"])
    with backup.state.transaction():
        backup.state.set_setting("timezone", "Europe/Istanbul")
    changed = exports.prepare("archive")
    assert changed["snapshot_id"] != archive["snapshot_id"]
    assert not archive["path"].exists()
    exports.release(changed["snapshot_id"])


def test_mirror_is_independent_of_missing_archive_keys_and_leases_protect_download(recovery):
    backup, _, _ = recovery
    backup.vault.write("root.md", "first\n", None, create=True)
    exports = Exports(backup)
    first = exports.prepare("mirror")
    (backup.secrets.directory / "recovery_recipient").unlink()
    with pytest.raises(DomainError):
        exports.prepare("archive")
    assert first["path"].exists()
    backup.vault.write("root.md", "second\n", sha_bytes(backup.vault.read("root.md").encode()))
    second = exports.prepare("mirror")
    assert second["snapshot_id"] != first["snapshot_id"]
    exports.release(first["snapshot_id"])
    assert not first["path"].exists() and second["path"].exists()
    exports.release(second["snapshot_id"])


def test_receipt_matches_exact_export_and_is_monotonic(recovery):
    backup, _, _ = recovery
    backup.vault.write("root.md", "root\n", None, create=True)
    exports = Exports(backup)
    first = exports.prepare("mirror")
    receipt = {key: first[key] for key in ("generation", "sha256", "size")}
    with pytest.raises(DomainError):
        exports.receipt("archive", receipt)
    with pytest.raises(DomainError):
        exports.receipt("mirror", {**receipt, "sha256": "changed"})
    assert exports.receipt("mirror", receipt)["accepted"]
    backup.vault.write("root.md", "changed\n", sha_bytes(backup.vault.read("root.md").encode()))
    second = exports.prepare("mirror")
    exports.receipt("mirror", {key: second[key] for key in receipt})
    exports.receipt("mirror", receipt)
    assert backup.state.setting("mirror_verified_generation") == second["generation"]
    exports.release(first["snapshot_id"])
    exports.release(second["snapshot_id"])


def test_export_slot_bound_and_restart_cleanup(recovery):
    backup, _, _ = recovery
    backup.vault.write("root.md", "root\n", None, create=True)
    exports = Exports(backup)
    items = [exports.prepare("mirror") for _ in range(4)]
    with pytest.raises(DomainError) as full:
        exports.prepare("mirror")
    assert full.value.status == 429
    for item in items:
        exports.release(item["snapshot_id"])
    exports.reset()
    assert not list(exports.directory.iterdir())


def test_outbox_is_pruned_only_after_both_exact_pipeline_receipts(recovery):
    backup, _, _ = recovery
    backup.vault.write("root.md", "before", None, create=True)
    exports = Exports(backup)
    archive = exports.prepare("archive")
    mirror = exports.prepare("mirror")
    assert backup.state.one("SELECT COUNT(*) AS n FROM outbox")["n"] > 0
    exports.receipt("mirror", {key: mirror[key] for key in ("generation", "size", "sha256")})
    assert backup.state.one("SELECT COUNT(*) AS n FROM outbox")["n"] > 0
    backup.vault.write("root.md", "after", sha_bytes(b"before"))
    exports.receipt("archive", {key: archive[key] for key in ("generation", "size", "sha256")})
    pending = backup.state.rows("SELECT * FROM outbox")
    assert len(pending) == 1 and pending[0]["generation"] > archive["generation"]
    for item in (archive, mirror):
        exports.release(item["snapshot_id"])
