"""Reproducible read-only CI gates; this command never signs or publishes."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import uuid
from pathlib import Path

from docker_paths import bind_path
from image_candidate import reuse
from validate_repository import versions

ROOT = Path(__file__).resolve().parents[1]
GITLEAKS = "ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"


def validate_ref(ref, version):
    if not ref.startswith("refs/tags/"):
        return "verification"
    tag = ref.removeprefix("refs/tags/")
    if tag not in {"v" + version, "mastermind-v" + version} or version == "0.0.0":
        raise ValueError("Tag must match the exact nonzero service version")
    return "release-candidate" if tag.startswith("mastermind-") else "verification"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default=os.environ.get("GITHUB_REF", ""))
    parser.add_argument("--images", action="store_true")
    parser.add_argument("--secrets", action="store_true")
    parser.add_argument("--reuse-images", type=Path, help="Verified unchanged OCI candidate; avoid rebuilding after qualification-only edits")
    args = parser.parse_args()
    if os.name == "nt" and shutil.disk_usage(ROOT).free < 12 * 1024**3:
        raise SystemExit("CI requires at least 12 GiB of free host disk before large image/backup tests")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT):
        raise SystemExit("CI evidence requires a clean committed source revision")
    profile = validate_ref(args.ref, versions(ROOT))
    output = ROOT / "artifacts/ci" / revision
    output.mkdir(parents=True, exist_ok=True)
    scratch = ROOT / ".local/ci" / (revision[:12] + "-" + uuid.uuid4().hex[:12])
    source = scratch / "source"
    source.mkdir(parents=True)
    archive = scratch / "source.tar"
    subprocess.run(["git", "archive", "--format=tar", "--output=" + str(archive), revision], cwd=ROOT, check=True)
    with tarfile.open(archive) as stream:
        if any(not item.isfile() and not item.isdir() for item in stream.getmembers()):
            raise SystemExit("CI source export rejects links and special files")
        stream.extractall(source, filter="data")
    steps = []
    def run(name, command, *, timeout=3600):
        started = time.monotonic()
        path = output / (name + ".log")
        print("RUN " + name, flush=True)
        with path.open("wb") as log:
            try:
                result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 124
        record = {"name": name, "command": command, "exit_code": code,
                  "seconds": round(time.monotonic() - started, 3), "log_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        steps.append(record)
        if code:
            raise ValueError(name + " failed; inspect " + str(path))
        print("PASS " + name, flush=True)
    result = {"schema": "mastermind.ci.v1", "revision": revision, "profile": profile, "steps": steps}
    npm = "npm.cmd" if os.name == "nt" else "npm"
    try:
        run("repository", [sys.executable, "scripts/validate_repository.py"])
        run("exposure", [sys.executable, "scripts/exposure_inventory.py"])
        run("catalog", [sys.executable, "scripts/known_problems_gate.py", "catalog", "--output", str(output / "catalog.json")])
        run("python-lint", [sys.executable, "-m", "ruff", "check", "src", "tests"])
        for path in sorted((ROOT / "packaging").rglob("*.sh")):
            run("shell-" + path.stem, ["sh", "-n", str(path)])
        for path in sorted((ROOT / "scripts").glob("*.cjs")):
            run("syntax-" + path.stem, ["node", "--check", str(path)])
        run("bridge-check", [npm, "--prefix", "bridge", "run", "check"])
        run("bridge-tests", [npm, "--prefix", "bridge", "test"])
        run("bridge-build", [npm, "--prefix", "bridge", "run", "build"])
        # Portable-export tests consume the freshly built Bridge, which is an
        # ignored build output and therefore deliberately absent from git archive.
        shutil.copytree(ROOT / "bridge/dist", source / "bridge/dist")
        if args.images or args.reuse_images:
            run("offline-model", [sys.executable, "scripts/fetch_embedding_model.py"])
            images = {}
            if args.reuse_images:
                images, result["image_reuse"] = reuse(ROOT, args.reuse_images, revision)
                print("PASS unchanged source inputs and original OCI-to-image identity", flush=True)
            for component in (() if args.reuse_images else ("core", "runtime", "worker")):
                tag = "mastermind-" + component + ":ci-" + revision[:12]
                command = ["docker", "build", "-f", "Dockerfile" + ("" if component == "core" else "." + component), "-t", tag]
                if component == "worker":
                    command += ["--build-context", "embedding=" + str(ROOT / ".local/models/multilingual-e5-small")]
                run("image-" + component, [*command, "."])
                images[component] = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", tag], text=True).strip()
                if not re.fullmatch(r"sha256:[a-f0-9]{64}", images[component]):
                    raise ValueError("Image build did not yield an immutable identity")
            result["images"] = images
            volume = "mastermind-ci-" + scratch.name
            run("test-storage", ["docker", "volume", "create", "--label", "mastermind.purpose=ci-tests", volume])
            run("test-storage-owner", ["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "0:0",
                "--cap-drop", "ALL", "--cap-add", "CHOWN", "--cap-add", "FOWNER", "--security-opt", "no-new-privileges:true",
                "--mount", "type=volume,source=" + volume + ",target=/verification", "--entrypoint", "python", images["core"],
                "-c", "import os; os.chown('/verification',0,0); os.chmod('/verification',0o700); os.makedirs('/verification/worker'); [(os.chown(p,10001,10001),os.chmod(p,0o700)) for p in ['/verification/worker','/verification']]"])
            result["test_storage_volume"] = volume
            isolated = ["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "10001:10001",
                        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--memory", "2g", "--cpus", "2",
                        "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m,mode=1777", "--mount", "type=bind,source=" + bind_path(source) + ",target=/suite,readonly",
                        "--mount", "type=volume,source=" + volume + ",target=/verification"]
            run("linux-tests", [*isolated, "--entrypoint", "python", images["worker"], "-m", "pytest", "/suite/tests", "-q",
                                "-o", "pythonpath=/app/src", "-p", "no:cacheprovider", "--basetemp=/verification/pytest"], timeout=600)
            run("real-worker-sandbox", [*isolated, "--mount", "type=volume,source=" + volume + ",target=/work,volume-subpath=worker",
                "--tmpfs", "/run/mastermind:rw,nosuid,nodev,size=1m,mode=1777", "--entrypoint", "python", images["worker"],
                "/suite/scripts/integration/probe_worker.py"], timeout=180)
            run("real-worker-browser", [*isolated, "--mount", "type=volume,source=" + volume + ",target=/work,volume-subpath=worker",
                "--tmpfs", "/run/mastermind:rw,nosuid,nodev,size=1m,mode=1777", "--entrypoint", "python", images["worker"],
                "/suite/scripts/integration/probe_worker_browser.py"], timeout=180)
        else:
            run("component-tests", [sys.executable, "-m", "pytest", "-q", "--junitxml=" + str(output / "tests.xml")], timeout=600)
        if args.secrets:
            scan = ["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                    "--mount", "type=bind,source=" + bind_path(ROOT) + ",target=/repo,readonly",
                    "--mount", "type=bind,source=" + bind_path(source) + ",target=/source,readonly", "--entrypoint", "/usr/bin/gitleaks", GITLEAKS]
            run("secret-history", [*scan, "git", "/repo", "--config", "/repo/.gitleaks.toml", "--redact", "--no-banner", "--log-opts=--all"])
            run("secret-source", [*scan, "dir", "/source", "--config", "/repo/.gitleaks.toml", "--redact", "--no-banner"])
        result["status"] = "PASS"
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result.update(status="FAIL", reason=str(error))
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(result["status"] + " CI " + revision, flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
