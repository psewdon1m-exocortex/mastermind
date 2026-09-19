import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("ref", ["refs/tags/v0.0.0", "refs/tags/mastermind-v0.0.2", "refs/tags/saturn-v0.0.1", "refs/tags/v01.0.1", "refs/tags/mastermind-v0.0.1-rc.1"])
def test_ci_rejects_foreign_malformed_or_different_version_tag(ref):
    with pytest.raises(ValueError):
        load("ci").validate_ref(ref, "0.0.1")


def test_plain_validation_cannot_publish_and_actions_match_immutable_lock():
    ci = load("ci")
    assert ci.validate_ref("refs/tags/v0.0.1", "0.0.1") == "verification"
    assert ci.validate_ref("refs/tags/mastermind-v0.0.1", "0.0.1") == "release-candidate"
    lock = json.loads((ROOT / ".github/actions.lock.json").read_text("utf-8"))
    body = (ROOT / ".github/workflows/ci.yml").read_text("utf-8")
    workflow = yaml.safe_load(body)
    assert workflow["permissions"] == {"contents": "read"}
    assert "secrets." not in body
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                action, digest = step["uses"].split("@")
                assert digest == lock[action]["sha"]


def test_bridge_build_is_read_only_and_only_its_tag_can_publish_verified_artifacts():
    body = (ROOT / ".github/workflows/bridge.yml").read_text("utf-8")
    workflow = yaml.load(body, Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"pull_request", "push", "workflow_dispatch"}
    assert workflow["on"]["push"] == {"branches": ["main"], "tags": ["bridge-v*"]}
    assert workflow["permissions"] == {"contents": "read"}
    build, publish = workflow["jobs"]["build"], workflow["jobs"]["publish"]
    assert build.get("permissions", workflow["permissions"]) == {"contents": "read"}
    assert "github.token" not in json.dumps(build) and "secrets." not in body
    assert publish["needs"] == "build" and publish["permissions"] == {"contents": "write"}
    assert publish["if"] == "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/bridge-v')"
    assert all(not job["runs-on"].startswith("self-hosted") for job in (build, publish))
    assert not any("npm " in step.get("run", "") for step in publish["steps"])
    assert "bridge_release.py verify" in publish["steps"][-2]["run"]
    assert "GH_TOKEN" not in publish["steps"][-2].get("env", {})
    assert publish["steps"][-1]["env"]["GH_TOKEN"] == "${{ github.token }}"
    lock = json.loads((ROOT / ".github/actions.lock.json").read_text("utf-8"))
    for job in (build, publish):
        for step in job["steps"]:
            if "uses" in step:
                action, digest = step["uses"].split("@")
                assert digest == lock[action]["sha"]
                if action == "actions/checkout":
                    assert step["with"]["persist-credentials"] == "false"


@pytest.fixture
def audit(tmp_path, monkeypatch):
    gate = load("pre_push")
    revision, base = "a" * 40, "b" * 40
    monkeypatch.setattr(gate, "changed_paths", lambda *_: ["src/mastermind/api.py"])
    proof = {"schema": "mastermind.verification.v1", "status": "PASS", "revision": revision,
             "command": "python scripts/qualification.py", "exit_code": 0, "areas": sorted(gate.AREAS)}
    path = tmp_path / "proof.json"
    path.write_text(json.dumps(proof))
    rows = [{"area": area, "status": "PASS", "assessment": "Inspected route changes and exercised the applicable boundary.",
             "inspected_paths": ["src/mastermind/api.py"],
             "evidence": [{"path": "proof.json", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]} for area in sorted(gate.AREAS)]
    record = {"schema": "mastermind.pre-push.v1", "revision": revision, "base_revision": base,
              "changed_paths": ["src/mastermind/api.py"], "areas": rows}
    return record, lambda value: gate.verify(value, root=tmp_path, evidence_root=tmp_path, base=base, revision=revision)


@pytest.mark.parametrize("fault", ["security_na", "private_na", "missing_area", "stale_diff", "unknown", "no_proof", "wrong_proof", "unreviewed_path"])
def test_incomplete_outgoing_review_blocks_push(audit, fault):
    original, verify = audit
    assert verify(original)["status"] == "PASS"
    value = copy.deepcopy(original)
    if fault.endswith("_na"):
        next(row for row in value["areas"] if row["area"] == ("security" if fault == "security_na" else "private_exposure"))["status"] = "N/A"
    elif fault == "missing_area":
        value["areas"].pop()
    elif fault == "stale_diff":
        value["changed_paths"] = []
    elif fault == "unknown":
        value["areas"][0]["status"] = "UNKNOWN"
    elif fault == "no_proof":
        value["areas"][0]["evidence"] = []
    elif fault == "wrong_proof":
        value["areas"][0]["evidence"][0]["sha256"] = "e" * 64
    else:
        value["areas"][0]["inspected_paths"] = ["unreviewed"]
    with pytest.raises(ValueError):
        verify(value)
