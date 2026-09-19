"""Package standalone Bridge downloads and publish immutable GitHub prereleases."""
import argparse
import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import Path

from known_problems_gate import read_json, require
from release_promote import GitHub
from validate_repository import versions

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_FILES = ("main.js", "manifest.json", "styles.css")
METADATA = "bridge-release.json"
LIMIT = 32 * 1024 * 1024


def file_bytes(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= LIMIT,
            "Missing, linked or oversized artifact: " + path.name)
    return path.read_bytes()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def identity(version, revision, tag):
    require(isinstance(version, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version)
            and version != "0.0.0", "Invalid Bridge version")
    require(re.fullmatch(r"[a-f0-9]{40}", revision), "Exact source revision is required")
    require(tag == "bridge-v" + version, "Tag must match bridge-v plus the exact Bridge version")


def manifest(folder):
    value = read_json(folder / "manifest.json")
    require(value.get("id") == "mastermind-bridge" and value.get("isDesktopOnly") is True,
            "Unexpected Bridge identity or platform")
    return value


def archive_name(version):
    return "mastermind-bridge-" + version + ".zip"


def checksums(payload):
    return "".join(sha(data) + "  " + name + "\n" for name, data in sorted(payload.items())).encode()


def package(root, output, revision, tag=None):
    version = versions(root)
    tag = "bridge-v" + version if tag is None else tag
    identity(version, revision, tag)
    source = root / "bridge/dist"
    require(not source.is_symlink(), "Linked build directory")
    value = manifest(source)
    require(value == manifest(root / "bridge") and value["version"] == version,
            "Built manifest is stale; rebuild Bridge")
    payload = {name: file_bytes(source / name) for name in PLUGIN_FILES}
    require(read_json(source / "integrity.json") == {name: sha(data) for name, data in payload.items()},
            "Build integrity mismatch; rebuild Bridge")
    archive = io.BytesIO()
    # A fixed timestamp, modes and ordering make repeated packages byte-identical.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
        for name, data in sorted(payload.items()):
            entry = zipfile.ZipInfo("mastermind-bridge/" + name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            stream.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    payload[archive_name(version)] = archive.getvalue()
    payload[METADATA] = json_bytes({
        "schema": "mastermind.bridge-release.v1", "version": version, "revision": revision, "tag": tag,
        "distribution": "portable-prerelease", "managed_core_version": version,
        "native_reference_obsidian_version": read_json(root / "component-lock.json")["obsidian"]["version"].removeprefix("v"),
        "files": {name: sha(data) for name, data in payload.items()},
    })
    payload["SHA256SUMS"] = checksums(payload)
    output.mkdir(parents=True, exist_ok=True)
    require(not output.is_symlink() and not any(output.iterdir()), "Output directory must be empty")
    for name, data in payload.items():
        (output / name).write_bytes(data)
    return verify(output, revision, tag)


def verify(folder, revision, tag):
    require(folder.is_dir() and not folder.is_symlink(), "Missing or linked release directory")
    value = manifest(folder)
    version = value.get("version")
    identity(version, revision, tag)
    names = {*PLUGIN_FILES, archive_name(version), METADATA, "SHA256SUMS"}
    require({path.name for path in folder.iterdir()} == names, "Unexpected release file inventory")
    payload = {name: file_bytes(folder / name) for name in names}
    require(payload.pop("SHA256SUMS") == checksums(payload), "Release checksum mismatch")
    metadata = read_json(folder / METADATA)
    require(metadata.get("schema") == "mastermind.bridge-release.v1" and metadata.get("version") == version
            and metadata.get("revision") == revision and metadata.get("tag") == tag
            and metadata.get("distribution") == "portable-prerelease"
            and metadata.get("managed_core_version") == version,
            "Release metadata does not match the source, tag or distribution")
    require(isinstance(metadata.get("native_reference_obsidian_version"), str)
            and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", metadata["native_reference_obsidian_version"]),
            "Missing pinned native reference version")
    require(metadata.get("files") == {name: sha(data) for name, data in payload.items() if name != METADATA},
            "Release metadata hash mismatch")
    with zipfile.ZipFile(io.BytesIO(payload[archive_name(version)])) as stream:
        entries = stream.infolist()
        expected = {"mastermind-bridge/" + name for name in PLUGIN_FILES}
        require(len(entries) == len(expected) and {entry.filename for entry in entries} == expected,
                "Unexpected ZIP file inventory")
        for entry in entries:
            name = entry.filename.split("/")[1]
            require(entry.file_size == len(payload[name]) and entry.external_attr >> 16 == 0o100644
                    and not entry.flag_bits & 1, "Unsafe ZIP entry")
            require(stream.read(entry) == payload[name], "ZIP and loose plugin assets differ")
    return metadata


def release_notes(metadata):
    version = metadata["version"]
    return (
        f"Mastermind Bridge {version} — standalone desktop preview.\n\n"
        f"Download `{archive_name(version)}` and extract its `mastermind-bridge` folder into "
        "`<vault>/.obsidian/plugins/`, then enable Mastermind Bridge in Obsidian. "
        "The three loose plugin files are also attached. Verify downloads with `SHA256SUMS`.\n\n"
        f"Native @ links in Graph, Local graph and link panes require the pinned Obsidian "
        f"{metadata['native_reference_obsidian_version']}; other versions disable that integration. "
        "Portable mode uses local notes and reference history. Live Chronos/Saturn cards require "
        "the managed service connection; remote enrollment and Vault synchronization are not included. "
        f"Managed installations retain the Bridge bundled with Core {version}. "
        "This preview does not qualify a whole-service update or installation through Community Plugins.\n\n"
        f"Source commit: `{metadata['revision']}`. See `bridge/README.md` in that revision for details.\n"
    )


def publish(folder, revision, tag, github):
    metadata = verify(folder, revision, tag)
    github.verify_tag(tag, revision)
    payload = {path.name: file_bytes(path) for path in folder.iterdir()}
    release = github.release(tag)
    if release is None:
        release = github.request("POST", "/releases", {
            "tag_name": tag, "target_commitish": revision, "name": "Mastermind Bridge " + metadata["version"],
            "draft": True, "prerelease": True, "make_latest": "false", "body": release_notes(metadata),
        })
    require(release.get("tag_name") == tag and release.get("prerelease") is True
            and type(release.get("draft")) is bool and type(release.get("id")) is int,
            "Existing release has a different identity or is not a Bridge prerelease")
    release_id = release["id"]

    def remote_assets():
        # Six assets fit on one page; an extra page would necessarily violate the inventory.
        assets = github.request("GET", f"/releases/{release_id}/assets?per_page=100")
        by_name = {asset["name"]: asset for asset in assets}
        require(len(by_name) == len(assets) and set(by_name) <= set(payload), "Unexpected remote release assets")
        for name, asset in by_name.items():
            require(asset.get("state") == "uploaded" and asset.get("size") == len(payload[name])
                    and asset.get("digest") == "sha256:" + sha(payload[name]),
                    "Remote artifact differs; replacement is forbidden: " + name)
        return by_name

    existing = remote_assets()
    require(release["draft"] or set(existing) == set(payload), "Published release is incomplete; refusing to modify it")
    for name in sorted(set(payload) - set(existing)):
        github.upload(release_id, folder / name)
    require(set(remote_assets()) == set(payload), "Remote release is incomplete")
    github.verify_tag(tag, revision)
    if release["draft"]:
        release = github.request("PATCH", f"/releases/{release_id}", {
            "draft": False, "prerelease": True, "make_latest": "false", "body": release_notes(metadata),
        })
        require(release.get("draft") is False and release.get("prerelease") is True,
                "GitHub did not finalize the Bridge prerelease")
    return {"status": "PASS", "tag": tag, "revision": revision, "assets": sorted(payload)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("package", "verify", "publish"))
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--tag", help="Required for verify/publish; defaults to bridge-v<version> when packaging")
    args = parser.parse_args()
    if args.command == "package":
        result = package(ROOT, args.folder, args.revision, args.tag)
    elif args.command == "verify":
        result = verify(args.folder, args.revision, args.tag)
    else:
        require(os.environ.get("GITHUB_EVENT_NAME") == "push"
                and os.environ.get("GITHUB_REF") == "refs/tags/" + (args.tag or "")
                and os.environ.get("GITHUB_SHA") == args.revision,
                "Publication requires the matching GitHub tag-push job")
        result = publish(args.folder, args.revision, args.tag,
                         GitHub(os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GH_TOKEN", "")))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
