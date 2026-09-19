"""Preparation-time public artifact fetch. Runtime never downloads Curator code or weights."""
import argparse
import hashlib
import json
import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def fetch(record, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        with destination.open("rb") as stream:
            if destination.stat().st_size == record["size"] and hashlib.file_digest(stream, "sha256").hexdigest() == record["sha256"]:
                return
    if shutil.disk_usage(destination.parent).free < record["size"]+128*1024**2:
        raise ValueError("Insufficient preparation space")
    temporary = destination.with_suffix(destination.suffix+".receiving")
    try:
        digest, total = hashlib.sha256(), 0
        request = urllib.request.Request(record["url"], headers={"User-Agent": "Mastermind-context-indexing-prepare"})
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as stream:
            while block := response.read(1024**2):
                total += len(block)
                if total > record["size"]:
                    raise ValueError("Artifact exceeds locked size")
                digest.update(block)
                stream.write(block)
        if total != record["size"] or digest.hexdigest() != record["sha256"]:
            raise ValueError("Artifact failed integrity")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def unpack(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    emitted = set()

    def target(name):
        path = PurePosixPath(name)
        if path.is_absolute() or any(p in {"", ".", ".."} for p in path.parts):
            raise ValueError("Unsafe runner archive member")
        resolved = destination / path
        if not resolved.resolve().is_relative_to(destination.resolve()):
            raise ValueError("Unsafe runner destination")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        emitted.add(resolved)
        return resolved

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as container:
            for member in container.infolist():
                if not member.is_dir():
                    with container.open(member) as source, target(member.filename).open("wb") as output:
                        shutil.copyfileobj(source, output, 1024**2)
    else:
        with tarfile.open(archive, "r:gz") as container:
            for member in container.getmembers():
                if member.isfile():
                    with container.extractfile(member) as source, target(member.name).open("wb") as output:
                        shutil.copyfileobj(source, output, 1024**2)
                    target(member.name).chmod(member.mode & 0o755)
                elif member.issym() or member.islnk():
                    # Materialize only links to a regular member of this verified archive.
                    linked = (PurePosixPath(member.name).parent / member.linkname).as_posix() if member.issym() else member.linkname
                    visited = {member.name}
                    item = container.getmember(linked)
                    while item.issym() or item.islnk():
                        if item.name in visited or len(visited) >= 8:
                            raise ValueError("Cyclic runner archive link")
                        visited.add(item.name)
                        linked = (PurePosixPath(item.name).parent / item.linkname).as_posix() if item.issym() else item.linkname
                        item = container.getmember(linked)
                    if not item.isfile():
                        raise ValueError("Unsupported runner archive link")
                    with container.extractfile(item) as source, target(member.name).open("wb") as output:
                        shutil.copyfileobj(source, output, 1024**2)
                    target(member.name).chmod(item.mode & 0o755)
    return emitted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=ROOT/".local/models/curator")
    parser.add_argument("--platform", choices=("linux-x64", "windows-x64", "both"), default="linux-x64")
    args = parser.parse_args()
    lock = json.loads((ROOT/"curator-model.lock.json").read_text("utf-8"))
    fetch(lock["model"], args.destination/lock["model"]["filename"])
    for record in lock.get("licenses", []):
        fetch(record, args.destination/record["filename"])
    for platform in ("linux-x64", "windows-x64") if args.platform == "both" else (args.platform,):
        record = lock["runner"][platform]
        archive = args.destination/record["filename"]
        fetch(record, archive)
        emitted = unpack(archive, args.destination/platform)
        inventory = {path.relative_to(args.destination/platform).as_posix():
                     {"size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                     for path in sorted(emitted)}
        (args.destination/platform/"inventory.json").write_text(json.dumps({"archive_sha256": record["sha256"],
                                                                         "files": inventory}, indent=2), "utf-8")
    shutil.copyfile(ROOT/"curator-model.lock.json", args.destination/"curator-model.lock.json")
    print(json.dumps({"status": "VERIFIED", "model_sha256": lock["model"]["sha256"],
                      "runner": lock["runner"]["version"], "platform": args.platform}))


if __name__ == "__main__":
    main()
