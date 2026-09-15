"""Offline image inventory and vulnerability matching; only DB refresh has network."""
import argparse
import collections
import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path

from docker_paths import bind_path

ROOT = Path(__file__).resolve().parents[1]
TOOL = "mastermind-security-tools:qualification"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", type=Path, required=True, help="JSON mapping core/runtime/worker to immutable image identities")
    parser.add_argument("--scratch", type=Path, default=ROOT / ".local/security-audit", help="Disposable image archive storage; must have sufficient free disk")
    args = parser.parse_args()
    images = json.loads(args.images.read_text("utf-8"))
    if set(images) != {"core", "runtime", "worker"}:
        raise SystemExit("Supply the complete three-image candidate")
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    output, inputs = ROOT / "artifacts/supply-chain" / run_id, args.scratch.resolve() / run_id
    output.mkdir(parents=True)
    inputs.mkdir(parents=True)
    records = []
    def run(name, command, *, timeout=900):
        started = time.monotonic()
        path = output / (name + ".log")
        with path.open("wb") as log:
            completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        records.append({"name": name, "exit_code": completed.returncode, "seconds": round(time.monotonic() - started, 3),
                        "log_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        if completed.returncode:
            raise ValueError("Security tool step failed: " + name)
        print("PASS " + name, flush=True)
    volume = "mastermind-security-" + run_id.lower()
    result = {"schema": "mastermind.supply-chain.v1", "images": images, "steps": records, "reports": {}}
    try:
        run("storage", ["docker", "volume", "create", "--label", "mastermind.purpose=security-audit", volume])
        run("storage-owner", ["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "0:0",
            "--cap-drop", "ALL", "--cap-add", "CHOWN", "--cap-add", "FOWNER", "--mount", "type=volume,source=" + volume + ",target=/audit",
            "--entrypoint", "python", TOOL, "-c", "import os; os.chown('/audit',0,0); os.chmod('/audit',0o700); [os.makedirs('/audit/'+n,exist_ok=True) for n in ['cache','tmp']]; [(os.chown(p,10001,10001),os.chmod(p,0o700)) for p in ['/audit/cache','/audit/tmp','/audit']]"])
        base = ["docker", "run", "--rm", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "--memory", "2g", "--cpus", "2", "--mount", "type=volume,source=" + volume + ",target=/cache,volume-subpath=cache",
                "--mount", "type=volume,source=" + volume + ",target=/tmp,volume-subpath=tmp"]
        # No source tree, image archive or service credential is mounted during refresh.
        run("database-refresh", [*base, TOOL, "grype", "db", "update"], timeout=600)
        isolated = [*base, "--network", "none", "-e", "GRYPE_DB_AUTO_UPDATE=false", "--mount",
                    "type=bind,source=" + bind_path(inputs) + ",target=/input,readonly", "--mount",
                    "type=bind,source=" + bind_path(output) + ",target=/output", TOOL]
        for name, reference in images.items():
            identity = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", reference], text=True).strip()
            archive = inputs / (name + ".tar")
            run("export-" + name, ["docker", "save", "--output", str(archive), identity])
            run("sbom-" + name, [*isolated, "syft", "scan", "docker-archive:/input/" + archive.name,
                "-o", "syft-json=/output/" + name + ".syft.json", "-o", "cyclonedx-json=/output/" + name + ".cdx.json"])
            run("vulnerabilities-" + name, [*isolated, "grype", "sbom:/output/" + name + ".syft.json",
                "-o", "json", "--file", "/output/" + name + ".vulnerabilities.json"])
            findings = json.loads((output / (name + ".vulnerabilities.json")).read_text("utf-8"))
            counts = collections.Counter(item["vulnerability"]["severity"] for item in findings.get("matches", []))
            result["reports"][name] = {"image_id": identity, "severities": dict(counts),
                "files": {suffix: hashlib.sha256((output / (name + suffix)).read_bytes()).hexdigest()
                          for suffix in (".syft.json", ".cdx.json", ".vulnerabilities.json")}}
            print(name + " vulnerability counts: " + json.dumps(counts), flush=True)
        result["status"] = "REVIEW_REQUIRED" if any(item["severities"].get(level, 0) for item in result["reports"].values() for level in ("Critical", "High")) else "PASS"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        result.update(status="FAIL", reason=str(error))
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(result["status"] + ": " + str(output), flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
