import importlib.util
import io
import json
import shutil
import sys
import tarfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT/relative)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def release_tools():
    return module("release_verify", "packaging/release_verify.py"), module("mastermind_installer", "packaging/install.py"), \
        module("mastermind_release_builder", "scripts/build_release.py")


@pytest.fixture
def signed_release(tmp_path, release_tools):
    _, _, builder = release_tools
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private, public, manifest = tmp_path/"private.pem", tmp_path/"public.pem", tmp_path/"manifest.json"
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    image = "ghcr.io/qualification/mastermind/core@sha256:"+"a"*64
    value = {"schema_version": 1, "service": "mastermind", "version": "0.0.1",
        "image": {"reference": image.split("@")[0], "digest": "sha256:"+"a"*64},
        "compose_bundle": {"sha256": "b"*64},
        "mastermind": {"profile": "mastermind.components.v1", "platform": "linux/amd64", "source_sha": "d"*40,
            "bridge_version": "0.0.1", "model_sha256": "c"*64, "health_profile": "mastermind.functional.v1",
            "components": {name: image for name in ("core", "runtime", "worker")},
            "dependencies": {name: "0.0.1" for name in ("kernel", "volt", "saturn", "chronos", "neptune", "updater")}}}
    manifest.write_text(json.dumps(value))
    builder.sign(manifest, private)
    return manifest, manifest.with_name(manifest.name+".sig.json"), public, private


@pytest.mark.skipif(not shutil.which("openssl"), reason="OpenSSL is required on the Linux deployment host")
def test_release_authentication_exact_bytes_key_role_and_version(signed_release, release_tools):
    verifier, _, builder = release_tools
    manifest, envelope, public, private = signed_release
    original = manifest.read_bytes()
    assert verifier.verify(manifest, envelope, public, "0.0.1")["service"] == "mastermind"
    with pytest.raises(ValueError, match="identity"):
        verifier.verify(manifest, envelope, public, "0.0.2")
    manifest.write_bytes(original+b" ")
    with pytest.raises(ValueError, match="signature verification"):
        verifier.verify(manifest, envelope, public)
    value = json.loads(original)
    value["service"] = "saturn"
    manifest.write_text(json.dumps(value))
    builder.sign(manifest, private)
    with pytest.raises(ValueError, match="identity"):
        verifier.verify(manifest, envelope, public)
    public.write_bytes(rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    with pytest.raises(ValueError, match="signer"):
        verifier.verify(manifest, envelope, public)


@pytest.mark.parametrize("names", [["../escape"], ["/absolute"], ["a\\b"], ["a", "A"], ["file", "file/child"]])
def test_release_bundle_rejects_unsafe_paths_before_writing(tmp_path, release_tools, names):
    verifier, _, _ = release_tools
    archive, destination = tmp_path/"bundle.tar.gz", tmp_path/"out"
    destination.mkdir()
    with tarfile.open(archive, "w:gz") as output:
        for name in names:
            entry = tarfile.TarInfo(name)
            entry.size = 1
            output.addfile(entry, io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        verifier.extract(archive, destination)
    assert list(destination.iterdir()) == []


def test_release_bundle_rejects_links_and_removes_special_modes(tmp_path, release_tools):
    verifier, _, _ = release_tools
    archive, destination = tmp_path/"bundle.tar.gz", tmp_path/"out"
    destination.mkdir()
    with tarfile.open(archive, "w:gz") as output:
        entry = tarfile.TarInfo("alias")
        entry.type, entry.linkname = tarfile.SYMTYPE, "/etc/shadow"
        output.addfile(entry)
    with pytest.raises(ValueError, match="Unsafe"):
        verifier.extract(archive, destination)
    with tarfile.open(archive, "w:gz") as output:
        entry = tarfile.TarInfo("bin/start.sh")
        entry.mode, entry.size = 0o6777, 1
        output.addfile(entry, io.BytesIO(b"x"))
    verifier.extract(archive, destination)
    if sys.platform == "linux":
        assert (destination/"bin/start.sh").stat().st_mode & 0o7777 == 0o755


def test_production_compose_enforces_principals_and_loopback(tmp_path, release_tools):
    import copy
    import yaml
    _, installer, _ = release_tools
    source = yaml.safe_load((ROOT/"compose.production.yaml").read_text())
    images = {name: "test/"+name+"@sha256:"+"a"*64 for name in source["services"]}
    rendered = {"name": "mastermind", "services": {}}
    for name, service in source["services"].items():
        value = copy.deepcopy(service)
        value["image"] = images[name]
        value["volumes"] = []
        for raw in service["volumes"]:
            path, target, *readonly = raw.split(":")
            value["volumes"].append({"type": "bind" if path.startswith((".", "/")) else "volume",
                "source": str(tmp_path/path) if path.startswith(".") else path, "target": target, "read_only": readonly == ["ro"]})
        if name == "core":
            value["ports"] = [{"host_ip": "127.0.0.1", "target": 18390, "published": "18390"}]
        rendered["services"][name] = value
    installer.validate_profile(rendered, images, tmp_path)
    for change in (
        lambda v: v["services"]["worker"].update(privileged=True),
        lambda v: v["services"]["runtime"]["volumes"][0].update(source="core-data"),
        lambda v: v["services"]["worker"]["volumes"][1].update(source=str(tmp_path/"secrets/core")),
        lambda v: v["services"]["core"]["ports"][0].update(host_ip="0.0.0.0"),
        lambda v: v["services"]["core"]["volumes"][0].update(target="/etc"),
    ):
        candidate = copy.deepcopy(rendered)
        change(candidate)
        with pytest.raises(ValueError):
            installer.validate_profile(candidate, images, tmp_path)


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX umask qualification")
def test_preparation_enforces_directory_and_file_modes_under_restrictive_umask(tmp_path, release_tools, monkeypatch):
    import os
    _, installer, _ = release_tools
    # The non-root test container exercises real umask/stat; only host UID/GID
    # ownership assignment is left to the separate real Linux installation.
    monkeypatch.setattr(installer.os, "chown", lambda *_: None)
    (tmp_path/"mastermind-release.json").write_text(json.dumps({"version": "0.0.1", "mastermind": {
        "components": {name: name+"@sha256:"+"a"*64 for name in ("core", "runtime", "worker")}}}))
    previous = os.umask(0o077)
    try:
        installer.prepare(tmp_path)
    finally:
        os.umask(previous)
    assert (tmp_path/".env").stat().st_mode & 0o777 == 0o600
    for name in ("core", "runtime", "worker"):
        folder = tmp_path/"secrets"/name
        assert folder.stat().st_mode & 0o777 == 0o750
        assert all(path.stat().st_mode & 0o777 == 0o640 for path in folder.iterdir())
    assert (tmp_path/"secrets/core/worker_token").read_bytes() == (tmp_path/"secrets/worker/worker_token").read_bytes()
    assert not (tmp_path/"secrets/worker/bootstrap_access_key").exists()
