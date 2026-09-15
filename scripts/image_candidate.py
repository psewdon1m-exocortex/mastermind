"""Reuse the same tested OCI bytes when only qualification scripts/docs changed."""
import hashlib
import json
import re
import subprocess
import tarfile
from pathlib import Path

BUILD_INPUTS = ["Dockerfile", "Dockerfile.runtime", "Dockerfile.worker", ".dockerignore", ".gitattributes",
                "requirements.lock", "requirements.worker.lock", "embedding-model.lock.json", "worker-browser.lock.json",
                "scripts/install_worker_browser.py", "src", "runtime", "bridge", "bin"]


def config_identity(archive, digest):
    def blob(identity):
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", identity):
            raise ValueError("Invalid OCI identity")
        member = archive.getmember("blobs/sha256/" + identity[7:])
        if not member.isfile() or member.size > 2 * 1024**2:
            raise ValueError("Invalid OCI metadata blob")
        body = archive.extractfile(member).read()
        if hashlib.sha256(body).hexdigest() != identity[7:]:
            raise ValueError("OCI metadata digest mismatch")
        return json.loads(body)
    manifest = blob(digest)
    if "manifests" in manifest:
        selected = [item for item in manifest["manifests"] if item.get("platform") == {"architecture": "amd64", "os": "linux"}]
        if len(selected) != 1:
            raise ValueError("Expected one exact Linux amd64 image manifest")
        manifest = blob(selected[0]["digest"])
    identity = manifest["config"]["digest"]
    blob(identity)
    return identity


def reuse(root, path, revision):
    record = json.loads(Path(path).read_text("utf-8"))
    original = record["source_revision"]
    if not re.fullmatch(r"[a-f0-9]{40}", original):
        raise ValueError("Original image build revision is required")
    if subprocess.check_output(["git", "diff", "--name-only", original, revision, "--", *BUILD_INPUTS], cwd=root):
        raise ValueError("Image build inputs changed; these images cannot qualify the new source")
    previous_path = Path(record["build_report"])
    body = previous_path.read_bytes()
    if hashlib.sha256(body).hexdigest() != record["build_report_sha256"]:
        raise ValueError("Original build evidence changed")
    previous = json.loads(body)
    if previous.get("revision") != original or set(previous.get("images", {})) != {"core", "runtime", "worker"}:
        raise ValueError("Original build record does not identify a complete candidate")
    for component in previous["images"]:
        step = [step for step in previous["steps"] if step["name"] == "image-" + component]
        if len(step) != 1 or step[0]["exit_code"] != 0:
            raise ValueError("Original component did not build successfully")
    result = {}
    with tarfile.open(record["oci_archive"]) as archive:
        for component, original_id in previous["images"].items():
            identity = config_identity(archive, original_id)
            actual = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", identity], text=True).strip()
            if actual != identity:
                raise ValueError("Loaded image identity differs from the qualified OCI config")
            result[component] = identity
    return result, {"source_revision": original, "build_report_sha256": record["build_report_sha256"],
                    "original_oci_images": previous["images"], "checked_build_inputs": BUILD_INPUTS}
