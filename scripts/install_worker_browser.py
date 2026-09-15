"""Build-time installation of the checksum-pinned official stable browser."""
import argparse
import hashlib
import json
import re
import shutil
import stat
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


def install(lock, destination, archive=None):
    version = lock.get("version", "")
    if lock.get("schema") != "mastermind.worker-browser.v1" or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", version) or \
            lock.get("url") != f"https://storage.googleapis.com/chrome-for-testing-public/{version}/linux64/chrome-linux64.zip" or \
            not re.fullmatch(r"[a-f0-9]{64}", lock.get("sha256", "")) or lock.get("executable") != "chrome-linux64/chrome":
        raise ValueError("Browser lock must identify an exact official Linux x64 release")
    if destination.exists():
        raise ValueError("Browser output must be fresh")
    with tempfile.TemporaryDirectory(prefix="mastermind-browser-") as temporary:
        if archive is None:
            archive = Path(temporary) / "browser.zip"
            started, size = time.monotonic(), 0
            request = urllib.request.Request(lock["url"], headers={"User-Agent": "mastermind-pinned-browser-build"})
            with urllib.request.urlopen(request, timeout=30) as response, archive.open("wb") as target:
                if response.url != lock["url"]:
                    raise ValueError("Unexpected browser download redirect")
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 512 * 1024**2 or time.monotonic() - started > 300:
                        raise ValueError("Browser download exceeded its limit")
                    target.write(chunk)
        with archive.open("rb") as source:
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
        if archive.stat().st_size != lock["bytes"] or checksum != lock["sha256"]:
            raise ValueError("Browser archive differs from its immutable checksum")
        with zipfile.ZipFile(archive) as zipped:
            members = zipped.infolist()
            seen = set()
            if len(members) > 5000 or sum(item.file_size for item in members) > 2 * 1024**3:
                raise ValueError("Browser archive exceeded extraction bounds")
            for item in members:
                path = PurePosixPath(item.filename)
                mode = item.external_attr >> 16
                if path.is_absolute() or ".." in path.parts or "\\" in item.filename or \
                        not path.parts or path.parts[0] != "chrome-linux64" or item.filename in seen or \
                        stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ValueError("Unsafe browser archive member")
                seen.add(item.filename)
            destination.mkdir(parents=True)
            for item in members:
                path = destination.joinpath(*PurePosixPath(item.filename).parts)
                if item.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with zipped.open(item) as source, path.open("xb") as target:
                        shutil.copyfileobj(source, target, 1024 * 1024)
                    path.chmod(0o755 if item.external_attr >> 16 & 0o111 else 0o644)
        executable = destination / lock["executable"]
        if not executable.is_file():
            raise ValueError("Pinned browser executable is missing")
        executable.chmod(0o755)
    print("Installed official stable browser " + version + " with verified SHA-256")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    install(json.loads(args.lock.read_text("utf-8")), args.destination, args.archive)
