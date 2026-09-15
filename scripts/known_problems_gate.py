"""Fail-closed Part 12 evidence validation; never turns a missing test into PASS."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

CATALOG = "PART_12_KNOWN_DEPLOYMENT_AND_OPERATIONS_PROBLEMS.md"
ROW = re.compile(r"^\|\s*\*\*([A-Z]+-[0-9]{2})\*\*\s*\|(.+)\|(.+)\|\s*$")
SHA = re.compile(r"[a-f0-9]{40}")
DIGEST = re.compile(r"[a-f0-9]{64}")
FINAL_ONLY = {"REL-06", "REL-09"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path, limit=2 * 1024 * 1024):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit, "Missing or oversized gate input")
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def catalog_ids(body):
    result = []
    for line in body.decode("utf-8").splitlines():
        if line.startswith("| **CAT-NN** |"):
            continue  # The central document's literal new-entry template is not an active ID.
        match = ROW.fullmatch(line)
        if not match:
            require(not line.startswith("| **"), "Malformed catalog row")
            continue
        identifier, problem, solution = match.groups()
        require(identifier not in result and len(problem.strip()) > 10 and len(solution.strip()) > 10,
                "Duplicate ID or empty catalog problem/solution")
        result.append(identifier)
    require(bool(result), "Empty problem catalog")
    return result


def evidence_file(root, name):
    require(isinstance(name, str) and not name.startswith(("/", "\\")) and ":" not in name,
            "Evidence must be an artifact-relative path")
    parts = name.replace("\\", "/").split("/")
    require(all(part not in ("", ".", "..") for part in parts), "Unsafe evidence path")
    current = root
    for part in parts:
        current = current / part
        require(not current.is_symlink(), "Evidence links are forbidden")
    require(current.resolve().is_relative_to(root.resolve()), "Evidence escapes its root")
    return current


def verify(report, catalog, lock, *, revision, tag, phase, evidence_root, manifest_sha256):
    require(SHA.fullmatch(revision) is not None and re.fullmatch(r"mastermind-v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", tag), "Invalid source or release identity")
    require(phase in {"pre-signing", "final"}, "Invalid gate phase")
    require(DIGEST.fullmatch(manifest_sha256) is not None, "Candidate manifest digest is required")
    catalog_hash = hashlib.sha256(catalog).hexdigest()
    identifiers = catalog_ids(catalog)
    require(not lock.get("includes_preexisting_worktree_changes"),
            "Publication needs an immutable central revision containing the effective catalog")
    require(SHA.fullmatch(lock.get("authority_revision", "")) is not None, "Unpinned central revision")
    require(lock.get("files", {}).get(CATALOG) == catalog_hash, "Catalog does not match the pinned policy bytes")
    expected = {"schema_version": 1, "service": "mastermind", "revision": revision, "release_tag": tag,
                "catalog_revision": lock["authority_revision"], "catalog_sha256": catalog_hash,
                "manifest_sha256": manifest_sha256}
    require(all(report.get(key) == value for key, value in expected.items()), "Stale or mismatched qualification identity")
    rows = report.get("checks")
    require(isinstance(rows, list) and len(rows) == len(identifiers), "Missing or extra problem classifications")
    require(all(isinstance(row, dict) for row in rows), "Invalid classification")
    require({row.get("id") for row in rows} == set(identifiers), "Duplicate, missing or unknown problem ID")
    deferred = []
    for row in rows:
        identifier, status = row["id"], row.get("status")
        if status == "N/A":
            require(isinstance(row.get("reason"), str) and len(row["reason"].strip()) >= 30 and
                    isinstance(row.get("inspected_paths"), list) and bool(row["inspected_paths"]) and
                    row.get("profile") == "mastermind.components.v1", identifier + ": N/A needs an inspected profile and reason")
            continue
        if status == "DEFERRED":
            require(phase == "pre-signing" and identifier in FINAL_ONLY and row.get("required_phase") == "final" and
                    isinstance(row.get("reason"), str) and len(row["reason"].strip()) >= 30,
                    identifier + ": only final signature/trust checks may be deferred")
            deferred.append(identifier)
            continue
        require(status == "PASS", identifier + ": unresolved classification blocks signing/publication")
        references = row.get("evidence")
        require(isinstance(references, list) and references, identifier + ": PASS needs executed evidence")
        for reference in references:
            require(isinstance(reference, dict) and DIGEST.fullmatch(reference.get("sha256", "")), "Missing evidence digest")
            path = evidence_file(evidence_root, reference.get("path"))
            proof = read_json(path)
            require(hashlib.sha256(path.read_bytes()).hexdigest() == reference["sha256"], "Evidence digest mismatch")
            require(proof.get("schema") == "mastermind.verification.v1" and proof.get("revision") == revision and
                    proof.get("status") == "PASS" and proof.get("manifest_sha256") == manifest_sha256 and
                    identifier in proof.get("problem_ids", []) and isinstance(proof.get("command"), str) and
                    bool(proof["command"].strip()) and type(proof.get("exit_code")) is int and proof["exit_code"] == 0,
                    identifier + ": evidence did not pass on this exact candidate")
    return {**expected, "phase": phase, "status": "PASS", "checked": len(rows), "deferred_final_checks": deferred}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("catalog", "verify"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--tag")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--central-checkout", type=Path)
    parser.add_argument("--phase", choices=("pre-signing", "final"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        lock = read_json(args.root / "docs/policy-lock.json")
        catalog = (args.root / "docs/policy" / CATALOG).read_bytes()
        identifiers = catalog_ids(catalog)
        require(hashlib.sha256(catalog).hexdigest() == lock["files"][CATALOG], "Catalog content changed")
        if args.command == "catalog":
            result = {"schema": "mastermind.catalog-check.v1", "status": "PASS", "active_ids": identifiers,
                      "publication_policy_ready": not lock.get("includes_preexisting_worktree_changes")}
        else:
            require(all((args.report, args.evidence_root, args.revision, args.tag, args.manifest, args.phase, args.central_checkout)), "Incomplete qualification arguments")
            central = subprocess.check_output(["git", "-C", str(args.central_checkout), "show", lock["authority_revision"] + ":" + CATALOG])
            require(central == catalog, "Effective catalog is absent from the immutable central revision")
            result = verify(read_json(args.report), catalog, lock, revision=args.revision, tag=args.tag,
                            phase=args.phase, evidence_root=args.evidence_root,
                            manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result = {"status": "FAIL", "reason": str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", newline="\n")
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
