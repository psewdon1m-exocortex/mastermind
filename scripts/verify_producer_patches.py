"""Apply exported producer changes to clean locked baselines and compare bytes."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(directory, *args):
    return subprocess.check_output(["git", "-c", "core.autocrlf=false", "-C", str(directory), *args], stderr=subprocess.STDOUT)


def main():
    lock = json.loads((ROOT / "docs/compatibility.json").read_text("utf-8"))
    results = {}
    for service, value in lock["services"].items():
        source = ROOT / ".local/services" / service
        target = ROOT / ".local/patch-replay" / (service + "-" + value["patch_sha256"][:16])
        patch = ROOT / value["patch"]
        assert hashlib.sha256(patch.read_bytes()).hexdigest() == value["patch_sha256"]
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            git(ROOT, "clone", "--no-hardlinks", "--no-checkout", str(source), str(target))
            git(target, "config", "core.autocrlf", "false")
            git(target, "checkout", "--detach", value["baseline_source_sha"])
            git(target, "apply", "--check", "--binary", str(patch))
            git(target, "apply", "--index", "--binary", str(patch))
        assert git(target, "rev-parse", "HEAD").decode().strip() == value["baseline_source_sha"]
        hashes = {}
        for relative in value["modified_files"]:
            expected, actual = source / relative, target / relative
            assert expected.read_bytes() == actual.read_bytes(), service + ": replay mismatch: " + relative
            hashes[relative] = hashlib.sha256(actual.read_bytes()).hexdigest()
        results[service] = {"status": "PASS", "baseline": value["baseline_source_sha"], "patch_sha256": value["patch_sha256"], "files": hashes}
        print(service + ": PASS clean baseline + exported patch = qualified local source", flush=True)
    (ROOT / "artifacts/producer-patch-replay.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
