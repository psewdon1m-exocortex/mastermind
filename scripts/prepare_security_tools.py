"""Fetch checksum-pinned official scanners; no service data enters this step."""
import hashlib
import json
import tarfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    lock = json.loads((ROOT / ".github/security-tools.lock.json").read_text("utf-8"))
    target = ROOT / ".local/security-tools"
    target.mkdir(parents=True, exist_ok=True)
    for name, item in lock.items():
        archive = target / (name + ".tar.gz")
        if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != item["sha256"]:
            deadline = time.monotonic() + 300
            with httpx.stream("GET", item["url"], follow_redirects=True, timeout=30) as response:
                response.raise_for_status()
                size = 0
                with archive.open("wb") as output:
                    for chunk in response.iter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > 150 * 1024 * 1024 or time.monotonic() > deadline:
                            raise ValueError("Scanner download exceeded its bound")
                        output.write(chunk)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Scanner checksum did not match its official release")
        with tarfile.open(archive) as stream:
            member = stream.getmember(name)
            if not member.isfile() or member.size > 250 * 1024 * 1024:
                raise ValueError("Invalid scanner binary member")
            with stream.extractfile(member) as source:
                (target / name).write_bytes(source.read())
        (target / name).chmod(0o755)
        print("Verified " + name + " " + item["version"], flush=True)
    (target / "Dockerfile").write_text(
        "FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254\n"
        "COPY --chmod=0555 syft grype /usr/local/bin/\n"
        "ENV SYFT_CHECK_FOR_APP_UPDATE=false GRYPE_CHECK_FOR_APP_UPDATE=false GRYPE_DB_CACHE_DIR=/cache\n"
        "USER 10001:10001\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
