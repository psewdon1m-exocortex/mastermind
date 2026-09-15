import hashlib
import importlib.util
import stat
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("install_worker_browser", ROOT / "scripts/install_worker_browser.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def browser_archive(tmp_path):
    def build(names=("chrome-linux64/chrome",), mode=stat.S_IFREG | 0o4755):
        archive = tmp_path / "browser.zip"
        with zipfile.ZipFile(archive, "w") as target:
            for name in names:
                entry = zipfile.ZipInfo(name)
                entry.external_attr = mode << 16
                target.writestr(entry, b"synthetic archive fixture")
        return {"schema": "mastermind.worker-browser.v1", "version": "153.0.8010.36",
            "url": "https://storage.googleapis.com/chrome-for-testing-public/153.0.8010.36/linux64/chrome-linux64.zip",
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "bytes": archive.stat().st_size,
            "executable": "chrome-linux64/chrome"}, archive
    return build, tmp_path / "installed"


def test_pinned_browser_extraction_strips_privileged_modes(browser_archive):
    build, output = browser_archive
    lock, archive = build()
    installer.install(lock, output, archive)
    assert (output / lock["executable"]).read_bytes() == b"synthetic archive fixture"
    assert (output / lock["executable"]).stat().st_mode & 0o7000 == 0
    with pytest.raises(ValueError, match="must be fresh"):
        installer.install(lock, output, archive)


@pytest.mark.parametrize("fault", ["checksum", "size", "url", "traversal", "absolute", "symlink", "foreign_root"])
def test_browser_archive_is_verified_before_any_extraction(browser_archive, fault):
    build, output = browser_archive
    if fault in {"traversal", "absolute", "foreign_root"}:
        lock, archive = build(({"traversal": "chrome-linux64/../../escape", "absolute": "/chrome-linux64/chrome",
                                "foreign_root": "foreign/chrome"}[fault],))
    elif fault == "symlink":
        lock, archive = build(mode=stat.S_IFLNK | 0o777)
    else:
        lock, archive = build()
        if fault == "checksum":
            lock["sha256"] = "a" * 64
        elif fault == "size":
            lock["bytes"] += 1
        else:
            lock["url"] = "https://untrusted.example/browser.zip"
    with pytest.raises(ValueError):
        installer.install(lock, output, archive)
    assert not output.exists()
