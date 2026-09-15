"""Export all required producer changes out of ignored local qualification clones."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {"updater": ("0.4.7", ("cmd/", "internal/", ".gitattributes")),
            "neptune": ("0.1.7", ("src/", "tests/")),
            "saturn": ("0.1.15", ("apps/", "packages/")),
            "chronos": ("0.1.1", ("app/", "tests/"))}


def git(directory, *args, codes=(0,)):
    result = subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=directory, capture_output=True)
    if result.returncode not in codes:
        raise RuntimeError("Git failed while exporting the local producer candidate")
    return result.stdout


def main():
    target = ROOT/"integrations/patches"
    target.mkdir(parents=True, exist_ok=True)
    lock = {"schema": "mastermind.producer-patches.v1", "published": False, "services": {}}
    for name, (version, allowed) in SERVICES.items():
        directory = ROOT/".local/services"/name
        baseline = git(directory, "rev-parse", "HEAD").decode().strip()
        tracked = git(directory, "diff", "--name-only", "-z", "HEAD").decode().split("\0")
        untracked = git(directory, "ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")
        selected = sorted(p for p in tracked if p.startswith(allowed))
        patch = git(directory, "diff", "--binary", "HEAD", "--", *selected) if selected else b""
        added = sorted(p for p in untracked if p.startswith(allowed))
        for path in added:
            patch += git(directory, "diff", "--no-index", "--binary", "--", "/dev/null", path, codes=(0, 1))
        filename = name+"-"+version+"-mastermind.patch"
        (target/filename).write_bytes(patch)
        lock["services"][name] = {"baseline_version": version, "baseline_source_sha": baseline,
            "patch": "integrations/patches/"+filename, "patch_sha256": hashlib.sha256(patch).hexdigest(),
            "modified_files": selected+added, "status": "LOCAL_QUALIFICATION_CANDIDATE"}
    (ROOT/"docs/compatibility.json").write_text(json.dumps(lock, indent=2)+"\n", newline="\n")
    print("Exported four local producer candidates; none is represented as a published upstream release")


if __name__ == "__main__":
    main()
