"""Standalone release verification. Python stdlib + system OpenSSL only."""
import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

MAX_BUNDLE = 128*1024**2
HASH = re.compile(r"[a-f0-9]{64}")
VERSION = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]+@sha256:[a-f0-9]{64}")


def sha256(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def regular(path, maximum):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum:
        raise ValueError("Expected a bounded ordinary file: " + path.name)
    return path.read_bytes()


def verify(manifest, envelope, public_key, version=None):
    body = regular(manifest, 2*1024**2)
    signed = json.loads(regular(envelope, 16384))
    regular(public_key, 16384)
    if signed.get("schema") != "exocortex.release-signature.v1" or signed.get("algorithm") != "RSA-PSS-SHA256":
        raise ValueError("Unsupported release signature")
    public = subprocess.run(["openssl", "pkey", "-pubin", "-in", str(public_key), "-outform", "DER"],
                            check=True, capture_output=True, timeout=10).stdout
    if hashlib.sha256(public).hexdigest() != signed.get("key_id"):
        raise ValueError("Release signer differs from the pinned identity")
    with tempfile.TemporaryDirectory(prefix="mastermind-signature-") as directory:
        signature = Path(directory)/"signature"
        signature.write_bytes(base64.b64decode(signed["signature"], validate=True))
        result = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(public_key),
                                 "-signature", str(signature), "-sigopt", "rsa_padding_mode:pss",
                                 "-sigopt", "rsa_pss_saltlen:32", str(manifest)], capture_output=True, timeout=10)
        if result.returncode:
            raise ValueError("Release signature verification failed")
    value = json.loads(body)
    group = value.get("mastermind", {})
    if value.get("schema_version") != 1 or value.get("service") != "mastermind" \
            or not VERSION.fullmatch(value.get("version", "")) or version and value["version"] != version \
            or group.get("profile") != "mastermind.components.v1" or group.get("platform") != "linux/amd64" \
            or group.get("bridge_version") != value["version"] \
            or not re.fullmatch(r"[a-f0-9]{40}", group.get("source_sha", "")) \
            or set(group.get("components", {})) != {"core", "runtime", "worker"} \
            or any(not IMAGE.fullmatch(image) for image in group["components"].values()) \
            or group.get("health_profile") != "mastermind.functional.v1" \
            or not HASH.fullmatch(group.get("model_sha256", "")):
        raise ValueError("Release identity or component profile is invalid")
    if group["components"]["core"] != value.get("image", {}).get("reference", "")+"@"+value.get("image", {}).get("digest", ""):
        raise ValueError("Primary image differs from the component group")
    for key in ("kernel", "volt", "saturn", "chronos", "neptune", "updater"):
        if not VERSION.fullmatch(group.get("dependencies", {}).get(key, "")):
            raise ValueError("The exact tested dependency tuple is missing")
    if not HASH.fullmatch(value.get("compose_bundle", {}).get("sha256", "")):
        raise ValueError("Bundle digest is missing")
    return value


class ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, location):
        parsed = urllib.parse.urlsplit(location)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.hostname not in {
                "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}:
            raise ValueError("Untrusted release download redirect")
        return super().redirect_request(request, fp, code, msg, headers, location)


def download(url, destination, limit):
    import time
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.port not in (None, 443) \
            or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Release assets must use an exact HTTPS GitHub release URL")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), ReleaseRedirect())
    deadline, size = time.monotonic()+180, 0
    with opener.open(urllib.request.Request(url, headers={"User-Agent": "mastermind-bootstrap"}), timeout=15) as response, \
            Path(destination).open("xb") as output:
        if int(response.headers.get("Content-Length", "0")) > limit:
            raise ValueError("Release asset exceeds its size limit")
        while chunk := response.read(65536):
            size += len(chunk)
            if size > limit or time.monotonic() > deadline:
                raise ValueError("Release download exceeded its byte/time limit")
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())


def extract(bundle, destination):
    import unicodedata
    seen, members, total = {}, [], 0
    with tarfile.open(bundle, "r:gz") as archive:
        for entry in archive:
            name = entry.name
            if not entry.isfile() or not name or "\\" in name or ":" in name or name.startswith("/") \
                    or any(part in ("", ".", "..") for part in name.split("/")) \
                    or any(ord(c) < 32 for c in name) or len(name.encode()) > 4096:
                raise ValueError("Unsafe release bundle entry")
            key = unicodedata.normalize("NFC", name).casefold()
            if key in seen or any(key.startswith(old+"/") or old.startswith(key+"/") for old in seen):
                raise ValueError("Colliding release bundle paths")
            seen[key] = True
            total += entry.size
            if len(seen) > 10000 or total > 256*1024**2 or entry.size < 0:
                raise ValueError("Release bundle exceeds extraction limits")
            members.append(entry)
        for entry in members:
            target = Path(destination)/entry.name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            with archive.extractfile(entry) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024*1024)
            target.chmod(0o755 if entry.mode & 0o111 else 0o644)


def prepare(base, key_bytes, version):
    import platform
    if os.geteuid() != 0 or platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("Bootstrap requires root on Linux amd64")
    if not VERSION.fullmatch(version) or not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/download/mastermind-v"+re.escape(version), base):
        raise ValueError("Bootstrap must name an exact service-qualified release")
    target = Path("/opt/exocortex/mastermind")
    if target.exists() or target.is_symlink():
        raise ValueError("Mastermind already exists; use its explicit update or repair workflow")
    trust = Path("/etc/exocortex/release-trust/mastermind.pem")
    if trust.exists() or trust.is_symlink():
        if regular(trust, 16384) != key_bytes:
            raise ValueError("Existing Mastermind signing identity differs; explicit trust rotation is required")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    with tempfile.TemporaryDirectory(prefix=".mastermind-prepare-", dir=target.parent) as directory:
        work = Path(directory)
        key = work/"mastermind.pem"
        key.write_bytes(key_bytes)
        manifest, envelope, bundle = work/"mastermind-release.json", work/"mastermind-release.json.sig.json", work/"bundle.tar.gz"
        download(base+"/mastermind-release.json", manifest, 2*1024**2)
        download(base+"/mastermind-release.json.sig.json", envelope, 16384)
        value = verify(manifest, envelope, key, version)
        expected = base+"/mastermind-compose.tar.gz"
        if value["compose_bundle"]["url"] != expected:
            raise ValueError("Bundle belongs to another repository, role or version")
        download(expected, bundle, MAX_BUNDLE)
        if sha256(bundle) != value["compose_bundle"]["sha256"]:
            raise ValueError("Release bundle checksum mismatch")
        stage = work/"deployment"
        stage.mkdir(mode=0o750)
        extract(bundle, stage)
        for file in (manifest, envelope):
            shutil.copyfile(file, stage/file.name)
        # Prepared files are durable and reviewable before any service is started.
        subprocess.run(["python3", str(stage/"packaging/install.py"), "prepare", "--directory", str(stage)], check=True)
        trust.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        if not trust.exists():
            with trust.open("xb") as output:
                output.write(key_bytes)
            trust.chmod(0o644)
        stage.rename(target)
    wrapper = Path("/usr/local/sbin/mastermind-install")
    if wrapper.exists() or wrapper.is_symlink():
        raise ValueError("mastermind-install command already belongs to another installation")
    wrapper.write_text('#!/bin/sh\nexec python3 /opt/exocortex/mastermind/packaging/install.py "$@"\n')
    wrapper.chmod(0o755)
    print("Prepared Mastermind "+version+"; no application was started.")
    print("Edit only OPERATOR INPUT in /opt/exocortex/mastermind/.env")
    print("Continue: sudo mastermind-install install")


if __name__ == "__main__":
    import sys
    try:
        if len(sys.argv) == 5 and sys.argv[1] == "prepare":
            prepare(sys.argv[2], base64.b64decode(sys.argv[3], validate=True), sys.argv[4])
        else:
            raise ValueError("Use the generated immutable release bootstrap")
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        raise SystemExit("Mastermind bootstrap: "+str(error)) from None
