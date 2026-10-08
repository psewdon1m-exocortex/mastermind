import copy
import hashlib
import importlib.util
import io
import json
import subprocess
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
              "catalog_repository": gate.CATALOG_REPOSITORY, "catalog_path": gate.CATALOG_PATH,
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


@pytest.mark.parametrize("fault", ["missing", "duplicate", "unknown", "fail", "stale_source", "stale_catalog", "stale_artifact", "no_evidence", "unexplained_na", "forged_na", "path_escape", "foreign_catalog", "foreign_catalog_path"])
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
    elif fault.startswith("foreign_catalog"):
        report["catalog_path" if fault.endswith("path") else "catalog_repository"] = "foreign"
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


def test_pending_policy_adoption_cannot_open_publication(qualification):
    _, lock, _, verify = qualification
    lock['publication_ready'] = False
    with pytest.raises(ValueError, match='adoption is pending'):
        verify()


@pytest.fixture
def policy_reference(tmp_path, monkeypatch):
    monkeypatch.delenv('MASTERMIND_POLICY_CHECKOUT', raising=False)
    root = tmp_path/'service'
    (root/'docs').mkdir(parents=True)
    body = b'| **REL-01** | Concrete catalog problem | A verified prevention rule |\n'
    lock = {'schema': 'mastermind.policy-reference.v1', 'repository': gate.CATALOG_REPOSITORY,
            'authority_revision': 'a'*40, 'files': {gate.CATALOG: hashlib.sha256(body).hexdigest()},
            'publication_ready': False}
    (root/'docs/policy-lock.json').write_text(json.dumps(lock))
    return root, lock, body


def test_external_catalog_is_bounded_and_digest_verified(policy_reference, monkeypatch):
    root, lock, body = policy_reference
    urls = []
    def response(url, timeout):
        urls.append(url)
        assert timeout == 20
        return io.BytesIO(body)
    monkeypatch.setattr(gate.urllib.request, 'urlopen', response)
    observed, catalog = gate.policy_catalog(root)
    assert observed == lock and catalog == body
    assert urls == ['https://raw.githubusercontent.com/psewdon1m-exocortex/general/'
                    + lock['authority_revision'] + '/' + gate.CATALOG]
    for invalid in (body+b'changed', b'x'*(2*1024*1024+1)):
        monkeypatch.setattr(gate.urllib.request, 'urlopen', lambda *a, data=invalid, **kw: io.BytesIO(data))
        with pytest.raises(ValueError, match='pinned digest'):
            gate.policy_catalog(root)


def test_checkout_uses_locked_commit_and_never_falls_back(policy_reference, tmp_path, monkeypatch):
    root, lock, body = policy_reference
    central = tmp_path/'central'
    central.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(central), *args], stderr=subprocess.PIPE)
    git('init', '-q')
    (central/gate.CATALOG).write_bytes(body)
    git('add', gate.CATALOG)
    git('-c', 'user.name=Policy fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Synthetic catalog fixture')
    lock['authority_revision'] = git('rev-parse', 'HEAD').decode().strip()
    (root/'docs/policy-lock.json').write_text(json.dumps(lock))
    (central/gate.CATALOG).write_text('Uncommitted changes must not enter pinned evidence.')
    def forbidden(*args, **kwargs):
        pytest.fail('An explicit checkout failure must not fall back to the network')
    monkeypatch.setattr(gate.urllib.request, 'urlopen', forbidden)
    assert gate.policy_catalog(root, central)[1] == body
    lock['authority_revision'] = 'b'*40
    (root/'docs/policy-lock.json').write_text(json.dumps(lock))
    with pytest.raises(subprocess.CalledProcessError):
        gate.policy_catalog(root, central)


def test_foreign_policy_source_is_rejected_before_io(policy_reference, monkeypatch):
    root, lock, _ = policy_reference
    lock['repository'] = 'https://example.invalid/foreign'
    (root/'docs/policy-lock.json').write_text(json.dumps(lock))
    monkeypatch.setattr(gate.urllib.request, 'urlopen', lambda *a, **kw: pytest.fail('Unexpected fetch'))
    with pytest.raises(ValueError, match='Invalid central policy'):
        gate.policy_catalog(root)
