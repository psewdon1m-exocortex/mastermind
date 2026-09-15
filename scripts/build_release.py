"""Build a deterministic signed release from already-built immutable images.

Signing is a separate operation. CI must run verification without a private key,
then expose signing only to the exact mastermind-vX.Y.Z protected release job.
"""
import argparse
import base64
import gzip
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sign(path, key_file):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 3072:
        raise ValueError("Release signing requires an RSA key of at least 3072 bits")
    public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    envelope = {"schema": "exocortex.release-signature.v1", "algorithm": "RSA-PSS-SHA256", "key_id": digest(public),
                "signature": base64.b64encode(key.sign(path.read_bytes(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                                        salt_length=32), hashes.SHA256())).decode()}
    path.with_name(path.name+".sig.json").write_text(json.dumps(envelope, indent=2)+"\n", newline="\n")


def bootstrap(base, public, version):
    verifier = base64.b64encode((ROOT/"packaging/release_verify.py").read_bytes()).decode()
    return "#!/bin/sh\nset -eu\numask 077\n" \
        "command -v python3 >/dev/null && command -v openssl >/dev/null || { echo 'Python 3 and OpenSSL are required' >&2; exit 1; }\n" \
        "exec python3 - '"+base+"' '"+base64.b64encode(public).decode()+"' '"+version+"' <<'PYBOOTSTRAP'\n" \
        "import base64, sys\nsys.argv = ['release_verify', 'prepare', *sys.argv[1:]]\n" \
        "exec(compile(base64.b64decode('"+verifier+"'), '<embedded-release-verifier>', 'exec'))\nPYBOOTSTRAP\n"


def build(args):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    public = args.public_key.read_bytes()
    key = serialization.load_pem_public_key(public)
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 3072:
        raise ValueError("Bootstrap requires a pinned RSA public key of at least 3072 bits")
    if not re.fullmatch(r"[a-f0-9]{40}", args.source_sha) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        raise ValueError("An exact source revision and GitHub repository are required")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True)
    if actual != args.source_sha or dirty:
        raise ValueError("Release assembly requires the exact clean source commit")
    version = json.loads((ROOT/"bridge/manifest.json").read_text())["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid release version")
    components = json.loads(args.components.read_text())
    if set(components) != {"core", "runtime", "worker"} or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]+@sha256:[a-f0-9]{64}", v) for v in components.values()):
        raise ValueError("Supply the three already-built immutable image references")
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    base = f"https://github.com/{args.repository}/releases/download/mastermind-v{version}"
    files = {}
    for name in ("compose.production.yaml", "pyproject.toml", "requirements.lock", "requirements.worker.lock", "embedding-model.lock.json", "worker-browser.lock.json"):
        files[name] = (ROOT/name).read_bytes()
    for directory in ("packaging", "docs", "integrations/patches"):
        for path in (ROOT/directory).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc",):
                files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    if (ROOT/"README.md").exists():
        files["README.md"] = (ROOT/"README.md").read_bytes()
    requirement = (ROOT/"mastermind_service_requirements_final.md").read_text("utf-8")
    files["requirements.md"] = requirement.replace("../.docs/", "docs/policy/").encode()
    for path in args.updater_bundle.rglob("*"):
        if path.is_symlink():
            raise ValueError("Updater bundle must contain ordinary files")
        if path.is_file():
            name = "vendor/updater/"+path.relative_to(args.updater_bundle).as_posix()
            body = path.read_bytes()
            if name.endswith((".sh", ".service")) and b"\r" in body:
                raise ValueError("Qualified Linux installer inputs must already use LF: "+name)
            files[name] = body
    required_vendor = {"vendor/updater/"+name for name in ("install.sh", "updater-linux-amd64", "systemd/updater.service",
                      "release-trust/updater.pem", "release-trust/neptune.pem", "release-trust/gryphon.pem")}
    if not required_vendor.issubset(files):
        raise ValueError("The qualified signed Updater installer/trust bundle is incomplete")
    bundle = output/"mastermind-compose.tar.gz"
    with bundle.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped, \
            tarfile.open(fileobj=zipped, mode="w|") as archive:
        for name, body in sorted(files.items()):
            if any(part in (".local", ".env", "secrets", "private") for part in name.split("/")):
                raise ValueError("Private path entered the release bundle")
            info = tarfile.TarInfo(name)
            info.size, info.uid, info.gid, info.mtime = len(body), 0, 0, 0
            info.mode = 0o755 if name.endswith((".sh", "updater-linux-amd64")) else 0o644
            archive.addfile(info, io.BytesIO(body))
    image, image_digest = components["core"].rsplit("@", 1)
    model = json.loads((ROOT/"embedding-model.lock.json").read_text())
    manifest = {"schema_version": 1, "service": "mastermind", "version": version,
        "image": {"reference": image, "digest": image_digest},
        "compose_bundle": {"url": base+"/"+bundle.name, "sha256": digest(bundle.read_bytes())},
        "database_schema": 1, "minimum_updater_version": "0.4.7",
        "mastermind": {"profile": "mastermind.components.v1", "source_sha": args.source_sha, "platform": "linux/amd64",
            "components": components, "bridge_version": version, "obsidian_version": "1.13.7",
            "model_sha256": model["files"]["model.onnx"]["sha256"], "minimum_source_schema": 1, "maximum_source_schema": 1,
            "dependencies": {"kernel": "0.2.10", "volt": "0.1.5", "saturn": "0.1.15", "chronos": "0.1.1", "neptune": "0.1.7", "updater": "0.4.7"},
            "health_profile": "mastermind.functional.v1"},
        "files": {name: digest(body) for name, body in sorted(files.items())},
        "qualification": {"published": False, "producer_patch_lock": "docs/compatibility.json"}}
    path = output/"mastermind-release.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", newline="\n")
    (output/"bootstrap.sh").write_text(bootstrap(base, public, version), newline="\n")
    (output/"mastermind.pem").write_bytes(public)
    (output/"SHA256SUMS").write_text("".join(digest(p.read_bytes())+"  "+p.name+"\n" for p in sorted(output.iterdir())
        if p.is_file() and p.name != "SHA256SUMS" and not p.name.endswith(".sig.json")), newline="\n")
    print("Built unsigned Mastermind "+version+" at "+str(output)+"; run gates before signing")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("build")
    for name in ("output", "components", "public-key", "updater-bundle"):
        command.add_argument("--"+name, type=Path, required=True)
    command.add_argument("--repository", required=True)
    command.add_argument("--source-sha", required=True)
    command = commands.add_parser("sign")
    command.add_argument("manifest", type=Path)
    command.add_argument("--key-file", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        build(args)
    else:
        sign(args.manifest, args.key_file)


if __name__ == "__main__":
    main()
