"""Validate an already qualified candidate before a job can access release secrets.

The candidate directory is provisioned on a dedicated qualification runner. It
contains immutable outputs from the complete local/host/native qualification; this
module neither manufactures those results nor rebuilds an image during promotion.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from known_problems_gate import CATALOG, evidence_file, read_json, require
from known_problems_gate import verify as known_verify
from pre_push import verify as push_verify
from validate_repository import versions

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = {"core", "runtime", "worker"}
CHECKS = {"storage_recovery", "native_runtime", "producer_contracts", "shell_browser", "crusher",
          "security_boundaries", "host_bootstrap", "host_install_repair", "host_update",
          "oldest_supported_update", "fault_recovery", "large_handoff", "reader_pipelines", "resource_limits"}
ASSETS = {"mastermind-release.json", "mastermind-compose.tar.gz", "mastermind.pem", "bootstrap.sh",
          "core.cdx.json", "runtime.cdx.json", "worker.cdx.json", "provenance.json"}
SHA = re.compile(r"[a-f0-9]{64}")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def referenced(candidate, reference):
    require(isinstance(reference, dict) and SHA.fullmatch(reference.get("sha256", "")), "Hashed evidence reference required")
    path = evidence_file(candidate, reference.get("path"))
    require(digest(path) == reference["sha256"], "Candidate evidence digest differs: " + path.name)
    return read_json(path), path


def verify_registry_images(components, identities):
    # Empty Docker client configuration proves anonymous installer access. The
    # image manifests are immutable; this never creates/moves a registry tag.
    with tempfile.TemporaryDirectory(prefix="mastermind-anonymous-registry-") as temporary:
        for name, reference in sorted(components.items()):
            subprocess.run(["docker", "--config", temporary, "pull", "--platform", "linux/amd64", "--quiet", reference],
                           check=True, capture_output=True, timeout=900)
            actual = subprocess.check_output(["docker", "--config", temporary, "image", "inspect", "--format", "{{.Id}}", reference], text=True).strip()
            require(actual == identities[name], "Registry image differs from the tested object: " + name)


def validate_results(record, candidate, revision, manifest_digest, components):
    require(record.get("schema") == "mastermind.release-qualification.v1" and record.get("revision") == revision and
            record.get("manifest_sha256") == manifest_digest and record.get("components") == components,
            "Qualification belongs to another source or artifact set")
    identities = record.get("image_ids", {})
    require(set(identities) == COMPONENTS and all(re.fullmatch(r"sha256:[a-f0-9]{64}", v) for v in identities.values()),
            "Complete tested image identities are required")
    ci, ci_path = referenced(candidate, record.get("ci"))
    require(ci.get("schema") == "mastermind.ci.v1" and ci.get("revision") == revision and
            ci.get("status") == "PASS" and ci.get("images") == identities, "Full exact-image CI did not pass")
    steps = ci.get("steps", [])
    names = {step.get("name") for step in steps}
    require(len(names) == len(steps) and {"repository", "exposure", "catalog", "python-lint", "bridge-check",
            "bridge-tests", "bridge-build", "linux-tests", "real-worker-sandbox", "real-worker-browser", "secret-history", "secret-source"} <= names,
            "Required CI commands are missing or repeated")
    for step in steps:
        require(type(step.get("exit_code")) is int and step["exit_code"] == 0 and step.get("command"), "CI command failed or was not executed")
        name = step["name"]
        require(re.fullmatch(r"[a-z0-9-]+", name), "Invalid CI log name")
        log = evidence_file(candidate, (ci_path.parent / (name + ".log")).relative_to(candidate).as_posix())
        require(digest(log) == step.get("log_sha256"), "Executed CI log changed")
    require(set(record.get("checks", {})) == CHECKS, "Complete profile qualification is required")
    for name, reference in record["checks"].items():
        proof, _ = referenced(candidate, reference)
        require(proof.get("schema") == "mastermind.verification.v1" and proof.get("revision") == revision and
                proof.get("manifest_sha256") == manifest_digest and proof.get("status") == "PASS" and
                proof.get("components") == components and name in proof.get("checks", []) and
                type(proof.get("exit_code")) is int and proof["exit_code"] == 0 and proof.get("command"),
                name + ": missing, failed or stale executed qualification")
        require(proof.get("raw_evidence"), name + ": raw executed output is required")
        for raw in proof["raw_evidence"]:
            path = evidence_file(candidate, raw.get("path"))
            require(digest(path) == raw.get("sha256"), name + ": original execution output changed")
    soak, _ = referenced(candidate, record.get("native_runtime"))
    require(soak.get("schema") == "mastermind.native-runtime-regression.v1" and
            soak.get("revision") == revision and soak.get("status") == "PASS" and
            0 < soak.get("elapsed_ms", 0) <= 900_000 and soak.get("checkpoints", 0) >= 6 and
            soak.get("frames", 0) > 0 and soak.get("connections", 0) >= 3 and
            soak.get("coordinated_mutations", 0) >= 2 and soak.get("portable_exports", 0) >= 1 and
            soak.get("export_bytes", 0) >= 350 * 1024**2 and
            soak.get("content_preserved") is True and soak.get("single_copy_markers") is True and soak.get("activity_delivered") is True and
            soak.get("long_duration_stability") == "NOT_TESTED_BY_OWNER_DECISION",
            "Complete bounded native regression and explicit long-duration exclusion are required")
    containers = soak.get("containers", [])
    require(len(containers) == 2 and {item.get("name") for item in containers} == {"core", "runtime"} and
            all(item.get("image") == identities[item["name"]] and item.get("oom") is False and
                item.get("restarts") == 0 for item in containers), "Native regression used different images or had a container failure")
    security, security_path = referenced(candidate, record.get("supply_chain"))
    require(security.get("schema") == "mastermind.supply-chain.v1" and security.get("status") == "PASS" and
            security.get("images") == identities and set(security.get("reports", {})) == COMPONENTS,
            "Unresolved supply-chain findings block release signing")
    for component, report in security["reports"].items():
        require(report.get("image_id") == identities[component] and
                all(report.get("severities", {}).get(level, 0) == 0 for level in ("High", "Critical")),
                "High/Critical findings require remediation and a fresh scan")
        for suffix in (".syft.json", ".cdx.json", ".vulnerabilities.json"):
            path = evidence_file(candidate, (security_path.parent / (component + suffix)).relative_to(candidate).as_posix())
            require(digest(path) == report.get("files", {}).get(suffix), "Security report changed")
    return identities


def prepare(candidate, output, central, revision, tag, repository):
    require(re.fullmatch(r"[a-f0-9]{40}", revision), "Full candidate revision required")
    require(tag == "mastermind-v" + versions(ROOT) and tag != "mastermind-v0.0.0", "Exact service release tag required")
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository), "Exact repository required")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tagged = subprocess.check_output(["git", "rev-parse", "refs/tags/" + tag + "^{commit}"], cwd=ROOT, text=True).strip()
    require(actual == tagged == revision and not subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT), "Clean immutable tagged source required")
    candidate = candidate.resolve()
    record = read_json(candidate / "qualification.json")
    payload = candidate / "payload"
    require(set(record.get("assets", {})) == ASSETS and
            {path.name for path in payload.iterdir()} == ASSETS, "Public candidate asset inventory must be exact")
    for name, checksum in record["assets"].items():
        path = evidence_file(candidate, "payload/" + name)
        require(digest(path) == checksum, "Candidate asset changed: " + name)
    manifest = read_json(payload / "mastermind-release.json")
    manifest_digest = digest(payload / "mastermind-release.json")
    require(manifest.get("service") == "mastermind" and manifest.get("version") == tag.removeprefix("mastermind-v") and
            manifest.get("mastermind", {}).get("source_sha") == revision, "Manifest identity differs from tag")
    components = manifest["mastermind"]["components"]
    require(set(components) == COMPONENTS and all(re.fullmatch(
        r"ghcr\.io/[a-z0-9_.-]+/[a-z0-9_./-]+@sha256:[a-f0-9]{64}", value) for value in components.values()),
        "Production qualification requires the three immutable registry references")
    require(manifest.get("compose_bundle") == {
        "url": f"https://github.com/{repository}/releases/download/{tag}/mastermind-compose.tar.gz",
        "sha256": digest(payload / "mastermind-compose.tar.gz")}, "Bundle URL or bytes differ from this immutable release")
    identities = validate_results(record, candidate, revision, manifest_digest, components)
    security, _ = referenced(candidate, record["supply_chain"])
    for name in COMPONENTS:
        require(record["assets"][name + ".cdx.json"] == security["reports"][name]["files"][".cdx.json"],
                "Public SBOM differs from the exact image scan")
    provenance = read_json(payload / "provenance.json")
    require(provenance.get("schema") == "mastermind.image-provenance.v1" and provenance.get("revision") == revision and
            provenance.get("components") == components and provenance.get("image_ids") == identities and
            provenance.get("ci_sha256") == record["ci"]["sha256"] and provenance.get("manifest_sha256") == manifest_digest,
            "Image build provenance differs from the tested source, CI output or manifest")
    # Patched sibling checkouts cannot silently masquerade as published producer releases.
    producers = read_json(ROOT / "docs/compatibility.json")
    require(producers.get("published") is True and all(item.get("status") == "PUBLISHED_QUALIFIED"
            for item in producers["services"].values()), "Required producer patches are not yet published and qualified")
    lock = read_json(ROOT / "docs/policy-lock.json")
    catalog = (ROOT / "docs/policy" / CATALOG).read_bytes()
    central_catalog = subprocess.check_output(["git", "-C", str(central), "show", lock["authority_revision"] + ":" + CATALOG])
    require(central_catalog == catalog, "Effective policy is absent from the immutable central commit")
    known, _ = referenced(candidate, record.get("known_problems"))
    known_result = known_verify(known, catalog, lock, revision=revision, tag=tag, phase="pre-signing",
                                evidence_root=candidate, manifest_sha256=manifest_digest)
    audit, _ = referenced(candidate, record.get("pre_push"))
    push_verify(audit, root=ROOT, evidence_root=candidate, base=audit.get("base_revision"), revision=revision)
    verify_registry_images(components, identities)
    require(not output.exists(), "Promotion output is immutable; use a fresh directory")
    output.mkdir(parents=True)
    for name in ASSETS:
        shutil.copyfile(payload / name, output / name)
    summary = {"schema": "mastermind.release-preflight.v1", "status": "PASS", "revision": revision, "tag": tag,
               "repository": repository, "manifest_sha256": manifest_digest, "components": components,
               "image_ids": identities, "checks": sorted(CHECKS), "qualification_sha256": digest(candidate / "qualification.json"),
               "native_runtime": record["native_runtime"]["sha256"], "supply_chain": record["supply_chain"]["sha256"],
               "known_problems": known_result, "candidate_assets": record["assets"]}
    (output / "qualification-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    (output / "known-problems-pre-signing.json").write_text(json.dumps(known, indent=2) + "\n", encoding="utf-8", newline="\n")
    # Only public, individually checked outputs enter the GitHub job artifact.
    public_evidence = output / "evidence"
    for row in known["checks"]:
        for reference in row.get("evidence", []):
            source = evidence_file(candidate, reference["path"])
            target = public_evidence / reference["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    require(all(digest(output / name) == checksum for name, checksum in record["assets"].items()),
            "Candidate changed during promotion copy")
    known_verify(known, catalog, lock, revision=revision, tag=tag, phase="pre-signing",
                 evidence_root=public_evidence, manifest_sha256=manifest_digest)
    return summary


def main():
    parser = argparse.ArgumentParser()
    for name in ("candidate", "output", "central"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("revision", "tag", "repository"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.candidate, args.output, args.central, args.revision, args.tag, args.repository)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result = {"status": "FAIL", "reason": str(error)}
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
