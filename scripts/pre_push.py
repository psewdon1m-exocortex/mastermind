"""Validate all seven Part 06 areas against the complete outgoing revision."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from known_problems_gate import evidence_file, read_json, require

ROOT = Path(__file__).resolve().parents[1]
ZERO = "0" * 40
AREAS = {"backup_restore", "service_update", "documentation_view", "technical_documentation",
         "security", "public_discovery", "private_exposure"}


def changed_paths(root, base, revision):
    require(re.fullmatch(r"[a-f0-9]{40}", revision) and re.fullmatch(r"[a-f0-9]{40}", base), "Exact outgoing and base commits are required")
    command = ["git", "-C", str(root)]
    if base == ZERO:
        command += ["ls-tree", "-r", "--name-only", "-z", revision]
    else:
        command += ["diff", "--name-only", "-z", base, revision]
    return sorted(value.decode("utf-8") for value in subprocess.check_output(command).split(b"\0") if value)


def verify(record, *, root, evidence_root, base, revision):
    paths = changed_paths(root, base, revision)
    require(record.get("schema") == "mastermind.pre-push.v1" and record.get("revision") == revision and
            record.get("base_revision") == base and record.get("changed_paths") == paths, "Audit does not cover the exact outgoing diff")
    rows = record.get("areas")
    require(isinstance(rows, list) and len(rows) == len(AREAS) and
            all(isinstance(row, dict) for row in rows) and {row.get("area") for row in rows} == AREAS, "Each required area must occur exactly once")
    for row in rows:
        area = row["area"]
        require(isinstance(row.get("inspected_paths"), list) and row["inspected_paths"] and
                all(isinstance(path, str) and path in paths for path in row["inspected_paths"]), area + ": inspected outgoing paths are required")
        require(isinstance(row.get("assessment"), str) and len(row["assessment"].strip()) >= 30, area + ": concrete impact assessment is required")
        if row.get("status") == "N/A":
            require(area not in {"security", "private_exposure"}, area + " is always applicable to Mastermind")
            if area == "public_discovery":
                require(row.get("system_profile") == "non-indexable", "Public discovery N/A must classify the complete service")
            continue
        require(row.get("status") == "PASS", area + ": incomplete audit blocks push")
        evidence = row.get("evidence")
        require(isinstance(evidence, list) and evidence, area + ": executed evidence is required")
        for reference in evidence:
            path = evidence_file(evidence_root, reference.get("path"))
            proof = read_json(path)
            require(hashlib.sha256(path.read_bytes()).hexdigest() == reference.get("sha256"), "Evidence digest mismatch")
            require(proof.get("revision") == revision and proof.get("status") == "PASS", "Evidence is stale or failed")
            if proof.get("schema") == "mastermind.ci.v1":
                require(proof.get("steps") and all(step.get("exit_code") == 0 for step in proof["steps"]), "CI did not execute all required steps")
            else:
                require(proof.get("schema") == "mastermind.verification.v1" and type(proof.get("exit_code")) is int and
                        proof["exit_code"] == 0 and proof.get("command") and area in proof.get("areas", []), "Evidence does not verify this area")
    return {"schema": "mastermind.pre-push-result.v1", "status": "PASS", "revision": revision,
            "base_revision": base, "changed_paths": paths, "areas": sorted(AREAS)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path)
    parser.add_argument("--evidence-root", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--base")
    parser.add_argument("--revision")
    parser.add_argument("--hook", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/pre-push-result.json")
    args = parser.parse_args()
    try:
        requests = []
        if args.hook:
            records = Path(os.environ.get("MASTERMIND_PUSH_AUDITS", str(ROOT / "artifacts/pre-push")))
            for line in sys.stdin:
                local_ref, local_sha, remote_ref, remote_sha = line.split()
                require(local_sha != ZERO, "Ref deletion requires a separate reviewed repository-maintenance operation")
                revision = subprocess.check_output(["git", "rev-parse", local_sha + "^{commit}"], cwd=ROOT, text=True).strip()
                requests.append((records / (revision + ".json"), remote_sha, revision))
        else:
            require(args.record and args.base and args.revision, "Record, outgoing revision and base are required")
            requests.append((args.record, args.base, args.revision))
        require(requests, "No outgoing revisions were supplied")
        result = {"status": "PASS", "revisions": [verify(read_json(path), root=ROOT, evidence_root=args.evidence_root,
                                                        base=base, revision=revision) for path, base, revision in requests]}
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result = {"status": "FAIL", "reason": str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
