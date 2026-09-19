"""Standalone release regression tests; only Python's standard library is needed."""
import copy
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import bridge_release as release

REVISION = "a" * 40


class FakeGitHub:
    def __init__(self):
        self.current = None
        self.assets = {}
        self.mutations = []
        self.tag_checks = 0
        self.move_on_check = None
        self.fail_upload = None

    def verify_tag(self, tag, revision):
        self.tag_checks += 1
        if self.tag_checks == self.move_on_check:
            raise ValueError("Remote tag moved")

    def release(self, tag):
        return copy.deepcopy(self.current)

    def request(self, method, path, data=None):
        if method == "GET":
            return list(copy.deepcopy(self.assets).values())
        self.mutations.append((method, path, copy.deepcopy(data)))
        if method == "POST":
            self.current = {"id": 41, **data}
        else:
            self.current.update(data)
        return copy.deepcopy(self.current)

    def upload(self, release_id, path):
        if path.name == self.fail_upload:
            raise OSError("Interrupted upload")
        self.mutations.append(("upload", path.name, None))
        self.assets[path.name] = {"name": path.name, "state": "uploaded", "size": path.stat().st_size,
                                  "digest": "sha256:" + release.sha(path.read_bytes())}


class BridgeReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        for name in ("pyproject.toml", "src/mastermind/__init__.py", "bridge/manifest.json",
                     "bridge/package.json", "bridge/package-lock.json", "component-lock.json",
                     "package.json", "package-lock.json"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        self.version = release.versions(self.root)
        self.tag = "bridge-v" + self.version
        self.dist = self.root / "bridge/dist"
        self.dist.mkdir()
        (self.dist / "main.js").write_bytes(b"module.exports = class Bridge {};\n")
        (self.dist / "styles.css").write_bytes(b".bridge { color: inherit; }\n")
        shutil.copyfile(self.root / "bridge/manifest.json", self.dist / "manifest.json")
        (self.dist / "integrity.json").write_bytes(release.json_bytes({
            name: release.sha((self.dist / name).read_bytes()) for name in release.PLUGIN_FILES}))
        self.folder = Path(self.temporary.name) / "package"
        self.github = FakeGitHub()

    def package(self):
        return release.package(self.root, self.folder, REVISION, self.tag)

    def publish(self):
        return release.publish(self.folder, REVISION, self.tag, self.github)

    def rehash(self):
        """Simulate an internally consistent but semantically invalid incoming artifact."""
        metadata_path = self.folder / release.METADATA
        metadata = json.loads(metadata_path.read_bytes())
        metadata["files"] = {path.name: release.sha(path.read_bytes()) for path in self.folder.iterdir()
                             if path.name not in {release.METADATA, "SHA256SUMS"}}
        metadata_path.write_bytes(release.json_bytes(metadata))
        (self.folder / "SHA256SUMS").write_bytes(release.checksums({
            path.name: path.read_bytes() for path in self.folder.iterdir() if path.name != "SHA256SUMS"}))

    def test_exact_inventory_excludes_history_secrets_and_test_bundles(self):
        for name in ("portable-history.json", ".env", "portable.cjs", "vault-note.md"):
            (self.dist / name).write_text("local data must stay local")
        metadata = self.package()
        self.assertEqual(metadata["revision"], REVISION)
        self.assertEqual(len(list(self.folder.iterdir())), 6)
        with zipfile.ZipFile(self.folder / release.archive_name(self.version)) as archive:
            self.assertEqual(sorted(archive.namelist()), ["mastermind-bridge/" + name for name in sorted(release.PLUGIN_FILES)])
            installed = Path(self.temporary.name) / "vault/.obsidian/plugins"
            archive.extractall(installed)
            for name in release.PLUGIN_FILES:
                self.assertEqual((installed / "mastermind-bridge" / name).read_bytes(), (self.dist / name).read_bytes())
        for path in self.folder.iterdir():
            self.assertNotIn(b"local data must stay local", path.read_bytes())

    def test_repeated_package_is_byte_identical(self):
        self.package()
        second = self.folder.with_name("second")
        release.package(self.root, second, REVISION, self.tag)
        self.assertEqual({p.name: p.read_bytes() for p in self.folder.iterdir()},
                         {p.name: p.read_bytes() for p in second.iterdir()})

    def test_package_refuses_existing_output_without_replacing_files(self):
        self.package()
        before = (self.folder / "main.js").read_bytes()
        with self.assertRaisesRegex(ValueError, "empty"):
            self.package()
        self.assertEqual((self.folder / "main.js").read_bytes(), before)

    def test_rejects_wrong_tag_revision_and_non_numeric_versions(self):
        for version, revision, tag in ((self.version, REVISION, "mastermind-v" + self.version),
                                       (self.version, REVISION, "bridge-v9.9.9"),
                                       (self.version, "main", self.tag),
                                       ("01.0.0", REVISION, "bridge-v01.0.0"),
                                       ("0.0.0", REVISION, "bridge-v0.0.0")):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.identity(version, revision, tag)

    def test_version_mismatch_and_stale_build_are_rejected(self):
        source = self.root / "bridge/package.json"
        original = source.read_bytes()
        source.write_bytes(release.json_bytes({**json.loads(original), "version": "9.9.9"}))
        with self.assertRaisesRegex(ValueError, "versions disagree"):
            self.package()
        source.write_bytes(original)
        (self.dist / "main.js").write_bytes(b"edited after build")
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            self.package()
        self.assertFalse(self.folder.exists())

    def test_stale_built_manifest_is_rejected(self):
        path = self.dist / "manifest.json"
        path.write_bytes(release.json_bytes({**json.loads(path.read_bytes()), "description": "Old description"}))
        with self.assertRaisesRegex(ValueError, "manifest is stale"):
            self.package()

    def test_added_file_or_changed_download_blocks_publication(self):
        self.package()
        extra = self.folder / "portable-history.json"
        extra.write_text("private history")
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.publish()
        extra.unlink()
        (self.folder / "main.js").write_bytes(b"corrupted download")
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.publish()
        self.assertEqual(self.github.mutations, [])

    def test_wrong_metadata_source_rejected_even_with_updated_checksums(self):
        self.package()
        path = self.folder / release.METADATA
        data = json.loads(path.read_bytes())
        data["revision"] = "b" * 40
        path.write_bytes(release.json_bytes(data))
        self.rehash()
        with self.assertRaisesRegex(ValueError, "metadata does not match"):
            self.publish()

    def test_zip_rejects_path_escape_duplicates_links_and_different_bytes(self):
        self.package()
        archive_path = self.folder / release.archive_name(self.version)
        for fault in ("escape", "duplicate", "link", "bytes"):
            with self.subTest(fault=fault):
                buffer = io.BytesIO()
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with zipfile.ZipFile(buffer, "w") as archive:
                        for name in release.PLUGIN_FILES:
                            entry = zipfile.ZipInfo("mastermind-bridge/" + name)
                            entry.create_system = 3
                            entry.external_attr = 0o100644 << 16
                            data = (self.folder / name).read_bytes()
                            if name == "main.js":
                                if fault == "escape":
                                    entry.filename = "../main.js"
                                elif fault == "link":
                                    entry.external_attr = 0o120777 << 16
                                elif fault == "bytes":
                                    data = b"x" * len(data)
                            archive.writestr(entry, data)
                            if fault == "duplicate" and name == "main.js":
                                archive.writestr(entry, data)
                archive_path.write_bytes(buffer.getvalue())
                self.rehash()
                with self.assertRaises(ValueError):
                    self.publish()
        self.assertEqual(self.github.mutations, [])

    def test_symlink_plugin_input_is_rejected(self):
        path = self.dist / "main.js"
        source = path.with_name("real-main.js")
        path.rename(source)
        try:
            path.symlink_to(source)
        except OSError:
            self.skipTest("Symlink creation is unavailable on this host")
        with self.assertRaisesRegex(ValueError, "linked"):
            self.package()

    def test_publish_checks_all_assets_then_opens_prerelease_without_latest(self):
        self.package()
        self.assertEqual(self.publish()["status"], "PASS")
        mutations = self.github.mutations
        self.assertEqual(mutations[0][0], "POST")
        self.assertTrue(mutations[0][2]["draft"])
        self.assertEqual(sum(row[0] == "upload" for row in mutations), 6)
        self.assertEqual(mutations[-1][0], "PATCH")
        self.assertFalse(self.github.current["draft"])
        self.assertTrue(self.github.current["prerelease"])
        self.assertTrue(all(data["make_latest"] == "false" for method, _, data in mutations if method != "upload"))
        self.assertEqual(self.github.tag_checks, 2)

    def test_retry_resumes_partial_draft_and_is_noop_after_publication(self):
        self.package()
        self.github.fail_upload = "main.js"
        with self.assertRaises(OSError):
            self.publish()
        self.assertTrue(self.github.current["draft"])
        uploaded = set(self.github.assets)
        self.assertTrue(uploaded)
        self.github.fail_upload = None
        self.publish()
        self.assertEqual(sum(row[0] == "upload" for row in self.github.mutations), 6)
        self.assertEqual(sum(row[0] == "POST" for row in self.github.mutations), 1)
        previous = copy.deepcopy(self.github.mutations)
        self.publish()
        self.assertEqual(previous, self.github.mutations)

    def test_changed_or_incomplete_published_release_is_never_rewritten(self):
        self.package()
        self.publish()
        before = copy.deepcopy(self.github.mutations)
        self.github.assets["main.js"]["digest"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(ValueError, "replacement is forbidden"):
            self.publish()
        del self.github.assets["main.js"]
        with self.assertRaisesRegex(ValueError, "Published release is incomplete"):
            self.publish()
        self.assertEqual(before, self.github.mutations)

    def test_remote_tag_change_keeps_release_draft(self):
        self.package()
        self.github.move_on_check = 2
        with self.assertRaisesRegex(ValueError, "tag moved"):
            self.publish()
        self.assertTrue(self.github.current["draft"])
        self.assertFalse(any(row[0] == "PATCH" for row in self.github.mutations))

    def test_upload_digest_must_be_verified_before_draft_is_opened(self):
        self.package()
        upload = self.github.upload

        def corrupt(release_id, path):
            upload(release_id, path)
            self.github.assets[path.name]["digest"] = None

        self.github.upload = corrupt
        with self.assertRaisesRegex(ValueError, "replacement is forbidden"):
            self.publish()
        self.assertTrue(self.github.current["draft"])

    def test_cli_never_publishes_from_pr_manual_dispatch_or_service_tag(self):
        for event, ref, revision in (("pull_request", "refs/pull/1/merge", REVISION),
                                    ("workflow_dispatch", "refs/tags/" + self.tag, REVISION),
                                    ("push", "refs/tags/mastermind-v" + self.version, REVISION),
                                    ("push", "refs/tags/" + self.tag, "b" * 40)):
            with self.subTest(event=event, ref=ref), patch.dict(os.environ, {
                    "GITHUB_EVENT_NAME": event, "GITHUB_REF": ref, "GITHUB_SHA": revision}), \
                    patch.object(sys, "argv", ["bridge_release.py", "publish", "--folder", str(self.folder),
                                               "--revision", REVISION, "--tag", self.tag]), \
                    patch.object(release, "GitHub") as client:
                with self.assertRaisesRegex(ValueError, "tag-push job"):
                    release.main()
                client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
