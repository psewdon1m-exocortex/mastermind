import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("image_candidate", Path(__file__).resolve().parents[1] / "scripts/image_candidate.py")
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def archive_fixture(tmp_path, *, platform=None, tamper=False):
    path = tmp_path / "candidate.tar"
    with tarfile.open(path, "w") as archive:
        def add(value, alter=False):
            body = json.dumps(value).encode()
            digest = hashlib.sha256(body).hexdigest()
            if alter:
                body += b" "
            member = tarfile.TarInfo("blobs/sha256/" + digest)
            member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
            return "sha256:" + digest
        config = add({"rootfs": {"diff_ids": ["sha256:" + "b" * 64]}}, tamper)
        manifest = add({"config": {"digest": config}})
        index = add({"manifests": [{"digest": manifest, "platform": platform or {"architecture": "amd64", "os": "linux"}}]})
    return path, index, config


def test_imported_image_identity_is_bound_to_original_oci_index(tmp_path):
    path, index, config = archive_fixture(tmp_path)
    with tarfile.open(path) as archive:
        assert candidate.config_identity(archive, index) == config


@pytest.mark.parametrize("arguments", [{"tamper": True}, {"platform": {"architecture": "arm64", "os": "linux"}}])
def test_oci_reuse_rejects_modified_bytes_or_other_platform(tmp_path, arguments):
    path, index, _ = archive_fixture(tmp_path, **arguments)
    with tarfile.open(path) as archive, pytest.raises(ValueError):
        candidate.config_identity(archive, index)


def test_service_code_change_requires_new_image_before_reading_evidence(tmp_path, monkeypatch):
    record = tmp_path / "reuse.json"
    record.write_text(json.dumps({"source_revision": "a" * 40}), encoding="utf-8")
    commands = []
    def changed(command, **kwargs):
        commands.append(command)
        return b"src/mastermind/api.py\n"
    monkeypatch.setattr(candidate.subprocess, "check_output", changed)
    with pytest.raises(ValueError, match="build inputs changed"):
        candidate.reuse(tmp_path, record, "b" * 40)
    assert len(commands) == 1
    assert {"src", "runtime", "bridge", "Dockerfile.runtime", "requirements.worker.lock"}.issubset(commands[0])
