"""Assemble unpublished signed artifacts served inside the qualification host."""
import hashlib
import io
import json
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"scripts"))
from build_release import sign

FIXTURE = ROOT/".local/host-fixture"


def main():
    release_root = FIXTURE/"release-assets/psewdon1m-exocortex"
    for source in sorted(FIXTURE.glob("release-*")):
        if source.name == "release-assets" or not (source/"mastermind-release.json").is_file():
            continue
        version = json.loads((source/"mastermind-release.json").read_text())["version"]
        target = release_root/"mastermind/releases/download"/("mastermind-v"+version)
        target.mkdir(parents=True, exist_ok=True)
        for path in source.iterdir():
            if path.is_file():
                shutil.copyfile(path, target/path.name)
    target = release_root/"neptune/releases/download/neptune-v0.1.7"
    target.mkdir(parents=True, exist_ok=True)
    source = ROOT/".local/services/neptune"
    artifact = target/"neptune-linux-x64.tar.gz"
    inputs = {"neptuned": source/".qualification-release/Neptune.Linux",
              "appsettings.json": source/".qualification-release/appsettings.json",
              **{name: source/"packaging/linux"/name for name in ("install.sh", "neptunectl", "neptune.service")}}
    with tarfile.open(artifact, "w:gz") as archive:
        for name, path in sorted(inputs.items()):
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if name in ("neptuned", "neptunectl", "install.sh") else 0o644
            if name != "neptuned":
                body = path.read_text("utf-8").encode("utf-8")
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
            else:
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
    with artifact.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = target/"neptune-linux-release-linux-x64.json"
    manifest.write_text(json.dumps({"schema": "exocortex.neptune.release.v1", "product": "neptune-linux",
        "version": "0.1.7", "runtime": "linux-x64", "artifact": artifact.name, "sha256": digest}, indent=2)+"\n", newline="\n")
    sign(manifest, FIXTURE/"neptune-signing.key")
    print("Prepared signed local Mastermind/Neptune release transport; artifacts remain unpublished")


if __name__ == "__main__":
    main()
