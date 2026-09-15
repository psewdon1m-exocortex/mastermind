import hashlib
import importlib
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest
import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def promotion(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("release_promote"), importlib.import_module("release_candidate")


@pytest.fixture
def qualified(tmp_path, promotion):
    _, gate = promotion
    revision, manifest = "a" * 40, "b" * 64
    images = {name: "sha256:" + str(number) * 64 for number, name in enumerate(sorted(gate.COMPONENTS), 1)}
    components = {name: "ghcr.io/example/" + name + "@" + value for name, value in images.items()}
    def save(name, data):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return {"path": name, "sha256": gate.digest(path)}
    steps = []
    for name in ("repository", "exposure", "catalog", "python-lint", "bridge-check", "bridge-tests", "bridge-build",
                 "linux-tests", "real-worker-sandbox", "real-worker-browser", "secret-history", "secret-source"):
        path = tmp_path / (name + ".log")
        path.write_text("Synthetic adversarial-test evidence; never release qualification.\n")
        steps.append({"name": name, "exit_code": 0, "command": ["synthetic-unit-fixture"], "log_sha256": gate.digest(path)})
    record = {"schema": "mastermind.release-qualification.v1", "revision": revision,
              "manifest_sha256": manifest, "components": components, "image_ids": images,
              "ci": save("ci.json", {"schema": "mastermind.ci.v1", "revision": revision, "status": "PASS", "images": images, "steps": steps})}
    record["checks"] = {name: save(name + ".json", {"schema": "mastermind.verification.v1", "revision": revision,
        "manifest_sha256": manifest, "components": components, "status": "PASS", "checks": [name], "exit_code": 0,
        "command": "synthetic-unit-fixture", "raw_evidence": [{"path": "linux-tests.log", "sha256": gate.digest(tmp_path / "linux-tests.log")} ]})
        for name in gate.CHECKS}
    record["native_soak"] = save("soak.json", {"status": "PASS", "elapsed_ms": 28_800_000, "checkpoints": 96, "frames": 1000,
        "containers": [{"name": name, "image": images[name], "oom": False, "restarts": 0} for name in ("core", "runtime")]})
    security = {"schema": "mastermind.supply-chain.v1", "status": "PASS", "images": images, "reports": {}}
    for name, image_id in images.items():
        files = {}
        for suffix in (".syft.json", ".cdx.json", ".vulnerabilities.json"):
            files[suffix] = save(name + suffix, {"fixture": "unit"})["sha256"]
        security["reports"][name] = {"image_id": image_id, "severities": {}, "files": files}
    record["supply_chain"] = save("security.json", security)
    return record, tmp_path, revision, manifest, components, save


def test_complete_qualification_receipts_are_verified(qualified, promotion):
    record, path, revision, manifest, components, _ = qualified
    assert promotion[1].validate_results(record, path, revision, manifest, components) == record["image_ids"]


@pytest.mark.parametrize("fault", ["stale", "missing_check", "missing_log", "changed_log", "failed_ci", "missing_ci_step",
    "changed_raw_evidence", "short_soak", "smoke_soak", "interrupted_soak", "wrong_soak_image", "restart_soak",
    "oom_soak", "no_frames", "few_checkpoints", "unreviewed_security", "forged_security_pass", "changed_sbom", "path_escape"])
def test_incomplete_or_mismatched_evidence_never_opens_signing(qualified, promotion, fault):
    record, path, revision, manifest, components, save = qualified
    if fault == "stale":
        record["revision"] = "c" * 40
    elif fault == "missing_check":
        record["checks"].pop("host_bootstrap")
    elif fault == "missing_log":
        (path / "linux-tests.log").unlink()
    elif fault in {"changed_log", "changed_raw_evidence"}:
        (path / "linux-tests.log").write_text("altered")
    elif fault in {"failed_ci", "missing_ci_step"}:
        ci = json.loads((path / "ci.json").read_text())
        if fault == "failed_ci":
            ci["steps"][0]["exit_code"] = 1
        else:
            ci["steps"].pop()
        record["ci"] = save("ci.json", ci)
    elif "soak" in fault or fault in {"no_frames", "few_checkpoints"}:
        soak = json.loads((path / "soak.json").read_text())
        if fault == "short_soak":
            soak["elapsed_ms"] -= 1
        elif fault in {"smoke_soak", "interrupted_soak"}:
            soak["status"] = "SMOKE_PASS" if fault == "smoke_soak" else "ENVIRONMENT_INTERRUPTED"
        elif fault == "wrong_soak_image":
            soak["containers"][0]["image"] = "sha256:" + "f" * 64
        elif fault == "restart_soak":
            soak["containers"][0]["restarts"] = 1
        elif fault == "oom_soak":
            soak["containers"][0]["oom"] = True
        else:
            soak["frames" if fault == "no_frames" else "checkpoints"] = 0
        record["native_soak"] = save("soak.json", soak)
    elif fault in {"unreviewed_security", "forged_security_pass"}:
        security = json.loads((path / "security.json").read_text())
        if fault == "unreviewed_security":
            security["status"] = "REVIEW_REQUIRED"
        else:
            security["reports"]["core"]["severities"]["Critical"] = 1
        record["supply_chain"] = save("security.json", security)
    elif fault == "changed_sbom":
        (path / "core.cdx.json").write_text("{}")
    else:
        record["ci"]["path"] = "../outside.json"
    with pytest.raises((ValueError, OSError)):
        promotion[1].validate_results(record, path, revision, manifest, components)


@pytest.fixture
def signed_candidate(tmp_path, promotion):
    promoter, gate = promotion
    folder = tmp_path / "public"
    folder.mkdir()
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    key = tmp_path / "fixture-private.pem"
    key.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (folder / "mastermind.pem").write_bytes(private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    revision, tag, repo = "a" * 40, "mastermind-v0.0.1", "example/mastermind"
    components = {name: "ghcr.io/example/" + name + "@sha256:" + "b" * 64 for name in gate.COMPONENTS}
    body = b"Synthetic fixture bundle.\n"
    with tarfile.open(folder / "mastermind-compose.tar.gz", "w:gz") as archive:
        info = tarfile.TarInfo("README.md")
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
    manifest = {"schema_version": 1, "service": "mastermind", "version": "0.0.1", "database_schema": 1,
        "minimum_updater_version": "0.4.7", "files": {"README.md": hashlib.sha256(body).hexdigest()},
        "image": {"reference": components["core"].split("@")[0], "digest": "sha256:" + "b" * 64},
        "compose_bundle": {"url": f"https://github.com/{repo}/releases/download/{tag}/mastermind-compose.tar.gz",
                           "sha256": gate.digest(folder / "mastermind-compose.tar.gz")},
        "mastermind": {"profile": "mastermind.components.v1", "platform": "linux/amd64", "source_sha": revision,
            "bridge_version": "0.0.1", "obsidian_version": "1.13.7", "health_profile": "mastermind.functional.v1",
            "components": components, "model_sha256": "c" * 64, "minimum_source_schema": 1, "maximum_source_schema": 1,
            "dependencies": {name: "0.0.1" for name in ("kernel", "volt", "saturn", "chronos", "neptune", "updater")}}}
    (folder / "mastermind-release.json").write_text(json.dumps(manifest))
    (folder / "bootstrap.sh").write_text(promoter.bootstrap(f"https://github.com/{repo}/releases/download/{tag}",
        (folder / "mastermind.pem").read_bytes(), "0.0.1"), newline="\n")
    for name in ("core.cdx.json", "runtime.cdx.json", "worker.cdx.json", "provenance.json", "known-problems-pre-signing.json", "attestation.sigstore.json"):
        (folder / name).write_text('{"fixture":"unit; no real GitHub attestation"}')
    summary = {"schema": "mastermind.release-preflight.v1", "status": "PASS", "revision": revision, "tag": tag,
        "repository": repo, "manifest_sha256": gate.digest(folder / "mastermind-release.json"), "components": components,
        "candidate_assets": {name: gate.digest(folder / name) for name in gate.ASSETS}}
    (folder / "qualification-summary.json").write_text(json.dumps(summary))
    promoter.protect_sign(folder, key, revision, tag, repo)
    return folder, key, revision, tag, repo


@pytest.mark.skipif(not shutil.which("openssl"), reason="The real deployment verifier requires OpenSSL")
def test_real_signatures_bundle_and_bootstrap_are_bound(signed_candidate, promotion):
    folder, _, revision, tag, repo = signed_candidate
    assert promotion[0].verify_local(folder, revision, tag, repo, attestation=False)["status"] == "PASS"
    original = (folder / "bootstrap.sh").read_bytes()
    (folder / "bootstrap.sh").write_bytes(original + b"echo altered\n")
    with pytest.raises(ValueError, match="artifact changed"):
        promotion[0].verify_local(folder, revision, tag, repo, attestation=False)


@pytest.mark.parametrize("fault", ["manifest", "checksums", "signature", "missing_sbom", "wrong_key", "plain_tag", "stale_sha"])
def test_signed_asset_substitution_and_wrong_identity_fail(signed_candidate, promotion, fault):
    folder, key, revision, tag, repo = signed_candidate
    promoter, _ = promotion
    if fault == "wrong_key":
        key.write_bytes(rsa.generate_private_key(public_exponent=65537, key_size=3072).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        with pytest.raises(ValueError, match="signing key differs"):
            promoter.protect_sign(folder, key, revision, tag, repo)
        return
    if fault == "plain_tag":
        tag = "v0.0.1"
    elif fault == "stale_sha":
        revision = "f" * 40
    elif fault == "missing_sbom":
        (folder / "worker.cdx.json").unlink()
    else:
        name = {"manifest": "mastermind-release.json", "checksums": "SHA256SUMS", "signature": "mastermind-release.json.sig.json"}[fault]
        path = folder / name
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises((ValueError, OSError, InvalidSignature)):
        promoter.identity(folder, revision, tag, repo)
        promoter.signed_inventory(folder)


def test_stage_never_moves_latest_and_rejects_existing_asset_changes(signed_candidate, promotion, monkeypatch):
    folder, _, revision, tag, repo = signed_candidate
    promoter, _ = promotion
    monkeypatch.setattr(promoter, "verify_local", lambda *a: None)
    class Remote:
        def __init__(self):
            self.current, self.calls = None, []
        def verify_tag(self, actual_tag, actual_revision):
            assert (actual_tag, actual_revision) == (tag, revision)
        def release(self, actual_tag):
            return self.current
        def request(self, method, route, data):
            assert method == "POST" and route == "/releases"
            assert data["make_latest"] == "false" and data["prerelease"] is True
            self.calls.append(data)
            self.current = {"id": 1, "tag_name": tag, "draft": False, "prerelease": True, "assets": []}
            return self.current
        def upload(self, release_id, path):
            assert release_id == 1
            self.current["assets"].append({"name": path.name, "size": path.stat().st_size, "digest": "sha256:" + promoter.digest(path)})
    remote = Remote()
    assert promoter.stage(folder, revision, tag, repo, remote) == 1
    count = len(remote.current["assets"])
    assert count == len(promoter.SIGNED_ASSETS)
    assert promoter.stage(folder, revision, tag, repo, remote) == 1
    assert len(remote.current["assets"]) == count and len(remote.calls) == 1
    remote.current["assets"][0]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="replacement is forbidden"):
        promoter.stage(folder, revision, tag, repo, remote)
    remote.current["prerelease"] = False
    with pytest.raises(ValueError, match="cannot be replaced"):
        promoter.stage(folder, revision, tag, repo, remote)


def test_final_alias_never_moves_when_anonymous_smoke_fails(signed_candidate, promotion, monkeypatch):
    folder, _, revision, tag, repo = signed_candidate
    promoter, _ = promotion
    def unavailable(*args):
        raise ValueError("Anonymous required asset returned HTTP 404")
    monkeypatch.setattr(promoter, "anonymous_verify", unavailable)
    with pytest.raises(ValueError, match="HTTP 404"):
        promoter.finalize(folder, revision, tag, repo, object())


def test_registry_must_deliver_exact_tested_image_without_saved_credentials(promotion, monkeypatch):
    _, gate = promotion
    calls = []
    def pull(command, **options):
        assert command[0:2] == ["docker", "--config"]
        assert not list(Path(command[2]).iterdir())
        assert command[3:7] == ["pull", "--platform", "linux/amd64", "--quiet"]
        calls.append(command)
    monkeypatch.setattr(gate.subprocess, "run", pull)
    monkeypatch.setattr(gate.subprocess, "check_output", lambda *a, **k: "sha256:" + "a" * 64 + "\n")
    images = {"core": "ghcr.io/example/core@sha256:" + "b" * 64}
    gate.verify_registry_images(images, {"core": "sha256:" + "a" * 64})
    assert len(calls) == 1
    with pytest.raises(ValueError, match="differs from the tested"):
        gate.verify_registry_images(images, {"core": "sha256:" + "f" * 64})


def test_final_signed_checks_preserve_both_catalog_ids(signed_candidate, promotion, monkeypatch):
    folder, _, revision, tag, repo = signed_candidate
    promoter, _ = promotion
    summary = json.loads((folder / "qualification-summary.json").read_text())
    summary["image_ids"] = {}
    monkeypatch.setattr(promoter, "verify_local", lambda *args: summary)
    monkeypatch.setattr(promoter, "verify_registry_images", lambda *args: None)
    monkeypatch.setattr(promoter, "anonymous_download", lambda url, target, *a: shutil.copyfile(folder / target.name, target))
    report = {"checks": [{"id": identifier, "status": "DEFERRED"} for identifier in ("REL-06", "REL-09")]}
    (folder / "known-problems-pre-signing.json").write_text(json.dumps(report))
    verified = []
    def verify(report, catalog, lock, **kwargs):
        assert kwargs["phase"] == "final"
        assert [row["id"] for row in report["checks"]] == ["REL-06", "REL-09"]
        assert all(row["status"] == "PASS" for row in report["checks"])
        proof = json.loads((folder / "evidence/final-signed-artifacts.json").read_text())
        assert proof["problem_ids"] == ["REL-06", "REL-09"]
        verified.append(report)
    monkeypatch.setattr(promoter, "known_verify", verify)
    assert promoter.anonymous_verify(folder, revision, tag, repo)["status"] == "PASS"
    assert len(verified) == 1
    assert json.loads((folder / "known-problems-report.json").read_text()) == verified[0]


def test_release_workflow_has_no_plain_tag_or_preflight_signing_permissions():
    # BaseLoader preserves YAML's `on` key instead of interpreting it as bool.
    workflow = yaml.load((ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader)
    assert workflow["on"] == {"push": {"tags": ["mastermind-v*"]}}
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    assert jobs["sign"]["needs"] == "preflight" and jobs["sign"]["environment"] == "mastermind-release-signing"
    assert jobs["publish"]["needs"] == "sign" and jobs["publish"]["environment"] == "mastermind-release-publication"
    assert "secrets." not in json.dumps(jobs["preflight"])
    assert "secrets." not in json.dumps(jobs["publish"])
    assert jobs["sign"]["permissions"]["contents"] == "read"
    assert jobs["publish"]["permissions"]["contents"] == "write"
    locks = json.loads((ROOT / ".github/actions.lock.json").read_text())
    for job in jobs.values():
        for step in job["steps"]:
            if "uses" in step:
                action, commit = step["uses"].split("@")
                assert commit == locks[action]["sha"]
