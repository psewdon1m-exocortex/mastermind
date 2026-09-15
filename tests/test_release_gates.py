import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("known_problems_gate", ROOT / "scripts/known_problems_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.fixture
def qualification(tmp_path):
    catalog = b"| **REL-01** | Concrete problem description | Concrete prevention and proof |\n| **REL-06** | Artifact signature mismatch | Verify the signed candidate bytes |\n"
    revision, digest = "a" * 40, "b" * 64
    lock = {"authority_revision": "c" * 40, "files": {gate.CATALOG: hashlib.sha256(catalog).hexdigest()}}
    proof = {"schema": "mastermind.verification.v1", "revision": revision, "manifest_sha256": digest,
             "status": "PASS", "problem_ids": ["REL-01", "REL-06"], "command": "python scripts/qualification.py", "exit_code": 0}
    path = tmp_path / "executed.json"
    path.write_text(json.dumps(proof))
    report = {"schema_version": 1, "service": "mastermind", "revision": revision, "release_tag": "mastermind-v0.0.1",
              "catalog_revision": lock["authority_revision"], "catalog_sha256": lock["files"][gate.CATALOG], "manifest_sha256": digest,
              "checks": [{"id": identifier, "status": "PASS", "evidence": [{"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]}
                         for identifier in ("REL-01", "REL-06")]}
    def verify(value=report, phase="pre-signing"):
        return gate.verify(value, catalog, lock, revision=revision, tag="mastermind-v0.0.1", phase=phase,
                           evidence_root=tmp_path, manifest_sha256=digest)
    return report, lock, path, verify


def test_complete_exact_candidate_qualification_and_final_phase(qualification):
    report, _, _, verify = qualification
    assert verify()["checked"] == 2
    report["checks"][1] = {"id": "REL-06", "status": "DEFERRED", "required_phase": "final",
                           "reason": "Requires final protected-job candidate signature verification."}
    assert verify()["deferred_final_checks"] == ["REL-06"]
    with pytest.raises(ValueError, match="only final"):
        verify(phase="final")
    report["checks"][0] = {**report["checks"][1], "id": "REL-01"}
    with pytest.raises(ValueError, match="only final"):
        verify()


@pytest.mark.parametrize("fault", ["missing", "duplicate", "unknown", "fail", "stale_source", "stale_catalog", "stale_artifact", "no_evidence", "unexplained_na", "forged_na", "path_escape"])
def test_unresolved_or_cross_candidate_evidence_never_opens_signing(qualification, fault):
    original, _, _, verify = qualification
    report = copy.deepcopy(original)
    row = report["checks"][0]
    if fault == "missing":
        report["checks"].pop()
    elif fault == "duplicate":
        report["checks"][1] = row
    elif fault in ("unknown", "fail"):
        row["status"] = fault.upper()
    elif fault.startswith("stale_"):
        report[{"stale_source": "revision", "stale_catalog": "catalog_sha256", "stale_artifact": "manifest_sha256"}[fault]] = "d" * 64
    elif fault == "no_evidence":
        row["evidence"] = []
    elif fault in ("unexplained_na", "forged_na"):
        row.update(status="N/A", reason="Not relevant" if fault == "unexplained_na" else "A long reason without inspected paths is insufficient.")
    else:
        row["evidence"][0]["path"] = "../executed.json"
    with pytest.raises(ValueError):
        verify(report)


def test_uncommitted_central_catalog_and_tampered_artifact_block(qualification):
    _, lock, path, verify = qualification
    lock["includes_preexisting_worktree_changes"] = True
    with pytest.raises(ValueError, match="immutable central"):
        verify()
    lock["includes_preexisting_worktree_changes"] = False
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="digest mismatch"):
        verify()


def test_catalog_and_evidence_reject_duplicate_keys_and_ids(tmp_path):
    row = b"| **REL-01** | A concrete problem description | A concrete prevention rule |\n"
    with pytest.raises(ValueError, match="Duplicate"):
        gate.catalog_ids(row + row)
    with pytest.raises(ValueError, match="Malformed"):
        gate.catalog_ids(b"| **REL-1** | x | y |\n")
    path = tmp_path / "ambiguous.json"
    path.write_text('{"status":"FAIL","status":"PASS"}')
    with pytest.raises(ValueError, match="Duplicate JSON"):
        gate.read_json(path)
