"""Sign exact approved bytes, stage without latest, verify anonymously, then promote.

Publishing commands are used only by the protected service-tag workflow. Merely
running CI or assembling/validating a candidate never invokes these commands.
"""
import argparse
import base64
import copy
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from build_release import bootstrap, sign
from known_problems_gate import CATALOG, FINAL_ONLY, read_json, require
from known_problems_gate import verify as known_verify
from release_candidate import ASSETS, ROOT, digest, verify_registry_images

BASE_ASSETS = ASSETS | {"qualification-summary.json", "known-problems-pre-signing.json", "attestation.sigstore.json"}
SIGNED_ASSETS = BASE_ASSETS | {"mastermind-release.json.sig.json", "SHA256SUMS", "SHA256SUMS.sig.json"}


def identity(folder, revision, tag, repository):
    summary = read_json(folder / "qualification-summary.json")
    require(re.fullmatch(r"[a-f0-9]{40}", revision) and re.fullmatch(
        r"mastermind-v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", tag) and
        tag != "mastermind-v0.0.0" and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository), "Invalid release identity")
    require(summary.get("schema") == "mastermind.release-preflight.v1" and summary.get("status") == "PASS" and
            summary.get("revision") == revision and summary.get("tag") == tag and summary.get("repository") == repository and
            summary.get("manifest_sha256") == digest(folder / "mastermind-release.json") and
            set(summary.get("candidate_assets", {})) == ASSETS, "Protected job has no matching pre-signing result")
    for name, checksum in summary["candidate_assets"].items():
        require(not (folder / name).is_symlink() and digest(folder / name) == checksum, "Approved artifact changed: " + name)
    return summary


def verify_signature(path, public):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    envelope = read_json(path.with_name(path.name + ".sig.json"))
    key = serialization.load_pem_public_key(public.read_bytes())
    require(isinstance(key, rsa.RSAPublicKey) and key.key_size >= 3072 and
            envelope.get("schema") == "exocortex.release-signature.v1" and
            envelope.get("algorithm") == "RSA-PSS-SHA256", "Invalid signature format or key")
    import hashlib
    require(hashlib.sha256(key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)).hexdigest() == envelope.get("key_id"),
            "Signature public identity differs")
    key.verify(base64.b64decode(envelope["signature"], validate=True), path.read_bytes(),
               padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())


def signed_inventory(folder):
    verify_signature(folder / "SHA256SUMS", folder / "mastermind.pem")
    rows = (folder / "SHA256SUMS").read_text("utf-8").splitlines()
    inventory = {}
    for row in rows:
        match = re.fullmatch(r"([a-f0-9]{64})  ([A-Za-z0-9_.-]+)", row)
        require(match is not None and match[2] not in inventory, "Invalid or duplicate signed checksum entry")
        inventory[match[2]] = match[1]
    require(set(inventory) == SIGNED_ASSETS - {"SHA256SUMS", "SHA256SUMS.sig.json"}, "Signed asset inventory is incomplete")
    for name, checksum in inventory.items():
        path = folder / name
        require(path.is_file() and not path.is_symlink() and digest(path) == checksum, "Signed asset changed: " + name)
    return inventory


def verify_local(folder, revision, tag, repository, *, attestation=True):
    summary = identity(folder, revision, tag, repository)
    signed_inventory(folder)
    verify_signature(folder / "mastermind-release.json", folder / "mastermind.pem")
    spec = importlib.util.spec_from_file_location("mastermind_release_verifier", ROOT / "packaging/release_verify.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    manifest = verifier.verify(folder / "mastermind-release.json", folder / "mastermind-release.json.sig.json",
                               folder / "mastermind.pem", tag.removeprefix("mastermind-v"))
    require(manifest["mastermind"]["source_sha"] == revision and manifest["mastermind"]["components"] == summary["components"],
            "Signed source or image group differs")
    require(digest(folder / "mastermind-compose.tar.gz") == manifest["compose_bundle"]["sha256"], "Signed archive differs")
    with tempfile.TemporaryDirectory(prefix="mastermind-signed-bundle-") as temporary:
        verifier.extract(folder / "mastermind-compose.tar.gz", Path(temporary), manifest["files"])
    expected = bootstrap(f"https://github.com/{repository}/releases/download/{tag}",
                         (folder / "mastermind.pem").read_bytes(), manifest["version"])
    require((folder / "bootstrap.sh").read_bytes() == expected.encode(), "Bootstrap does not embed this exact verifier, public key and version")
    if attestation:
        subprocess.run(["gh", "attestation", "verify", str(folder / "mastermind-release.json"), "--bundle",
            str(folder / "attestation.sigstore.json"), "--repo", repository, "--signer-workflow",
            repository + "/.github/workflows/release.yml", "--source-digest", revision,
            "--source-ref", "refs/tags/" + tag, "--deny-self-hosted-runners"], check=True, capture_output=True, timeout=90)
    return summary


def protect_sign(folder, key_file, revision, tag, repository):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    identity(folder, revision, tag, repository)
    require((folder / "attestation.sigstore.json").is_file(), "Provenance must exist before signing the full inventory")
    private = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    public = serialization.load_pem_public_key((folder / "mastermind.pem").read_bytes())
    require(isinstance(private, rsa.RSAPrivateKey) and private.key_size >= 3072 and
            private.public_key().public_numbers() == public.public_numbers(), "Protected signing key differs from the qualified bootstrap trust")
    sign(folder / "mastermind-release.json", key_file)
    names = SIGNED_ASSETS - {"SHA256SUMS", "SHA256SUMS.sig.json"}
    (folder / "SHA256SUMS").write_text("".join(digest(folder / name) + "  " + name + "\n" for name in sorted(names)), newline="\n")
    sign(folder / "SHA256SUMS", key_file)


class GitHub:
    def __init__(self, repository, token):
        require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository), "Invalid repository")
        require(bool(token), "Publication token is missing")
        self.repository, self.token = repository, token

    def request(self, method, path, data=None, *, upload=False):
        base = "https://uploads.github.com" if upload else "https://api.github.com"
        body = data if isinstance(data, bytes) else None if data is None else json.dumps(data).encode()
        request = urllib.request.Request(base + "/repos/" + self.repository + path, data=body, method=method,
            headers={"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "mastermind-release-verifier",
                     "Content-Type": "application/octet-stream" if upload else "application/json"})
        # Authenticated API calls must never forward the token across redirects.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, message, headers, new_url):
                return None
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=180) as response:
            return json.load(response)

    def release(self, tag):
        try:
            return self.request("GET", "/releases/tags/" + tag)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    def verify_tag(self, tag, revision):
        ref = self.request("GET", "/git/ref/tags/" + tag)["object"]
        for _ in range(8):
            if ref["type"] == "commit":
                require(ref["sha"] == revision, "Remote tag was moved to another commit")
                return
            require(ref["type"] == "tag" and re.fullmatch(r"[a-f0-9]{40}", ref["sha"]), "Invalid remote tag object")
            ref = self.request("GET", "/git/tags/" + ref["sha"])["object"]
        raise ValueError("Excessive nested annotated tags")

    def upload(self, release_id, path):
        require(type(release_id) is int, "Invalid release ID")
        return self.request("POST", f"/releases/{release_id}/assets?name=" + urllib.parse.quote(path.name, safe=""), path.read_bytes(), upload=True)


def stage(folder, revision, tag, repository, github):
    verify_local(folder, revision, tag, repository)
    github.verify_tag(tag, revision)
    release = github.release(tag)
    if release is None:
        release = github.request("POST", "/releases", {"tag_name": tag, "target_commitish": revision,
            "name": "Mastermind " + tag.removeprefix("mastermind-v"), "draft": False, "prerelease": True, "make_latest": "false",
            "body": "Immutable candidate awaiting anonymous artifact verification. Not the stable discovery release."})
    require(release.get("tag_name") == tag and release.get("draft") is False and release.get("prerelease") is True,
            "An existing final/draft release cannot be replaced or reinterpreted")
    existing = {item["name"]: item for item in release.get("assets", [])}
    require(len(existing) == len(release.get("assets", [])) and set(existing) <= SIGNED_ASSETS |
            {"known-problems-report.json", "final-signed-artifacts.json"}, "Unexpected or duplicate staged asset")
    for name in sorted(SIGNED_ASSETS):
        path = folder / name
        if name in existing:
            require(existing[name].get("size") == path.stat().st_size and existing[name].get("digest") == "sha256:" + digest(path),
                    "An existing immutable staged asset differs; replacement is forbidden")
        else:
            github.upload(release["id"], path)
    return release["id"]


def anonymous_download(url, destination, size, checksum):
    # The exact GitHub download URL is supplied by the locally verified identity,
    # never by candidate metadata or a GitHub API response. No auth/cookies here.
    class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, message, headers, new_url):
            parsed = urllib.parse.urlsplit(new_url)
            require(parsed.scheme == "https" and parsed.hostname in {"github.com", "release-assets.githubusercontent.com",
                    "objects.githubusercontent.com"} and not parsed.username, "Unexpected release asset redirect")
            return super().redirect_request(request, fp, code, message, headers, new_url)
    request = urllib.request.Request(url, headers={"User-Agent": "mastermind-anonymous-installer-check"})
    with urllib.request.build_opener(HTTPSRedirect()).open(request, timeout=180) as response, destination.open("xb") as target:
        copied = 0
        while chunk := response.read(min(1024 * 1024, size - copied + 1)):
            copied += len(chunk)
            require(copied <= size, "Remote asset exceeds its signed size")
            target.write(chunk)
    require(copied == size and digest(destination) == checksum, "Anonymous download differs from the signed candidate")


def anonymous_verify(folder, revision, tag, repository):
    summary = verify_local(folder, revision, tag, repository)
    with tempfile.TemporaryDirectory(prefix="mastermind-anonymous-release-") as temporary:
        downloaded = Path(temporary)
        for name in sorted(SIGNED_ASSETS):
            path = folder / name
            anonymous_download(f"https://github.com/{repository}/releases/download/{tag}/{name}",
                               downloaded / name, path.stat().st_size, digest(path))
        verify_local(downloaded, revision, tag, repository)
    verify_registry_images(summary["components"], summary["image_ids"])
    report = read_json(folder / "known-problems-pre-signing.json")
    proof = {"schema": "mastermind.verification.v1", "revision": revision, "manifest_sha256": summary["manifest_sha256"],
             "status": "PASS", "problem_ids": sorted(FINAL_ONLY), "exit_code": 0,
             "command": "python scripts/release_promote.py smoke --revision " + revision + " --tag " + tag,
             "assets": {name: digest(folder / name) for name in sorted(SIGNED_ASSETS)},
             "checks": ["anonymous complete download", "RSA-PSS signatures", "bundle inventory", "bootstrap trust", "GitHub provenance identity"]}
    evidence = folder / "evidence" / "final-signed-artifacts.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(proof, indent=2) + "\n", newline="\n")
    final = copy.deepcopy(report)
    for row in final["checks"]:
        if row["id"] in FINAL_ONLY:
            identifier = row["id"]
            row.clear()
            row.update(id=identifier, status="PASS",
                       evidence=[{"path": evidence.name, "sha256": digest(evidence)}])
    lock = read_json(ROOT / "docs/policy-lock.json")
    known_verify(final, (ROOT / "docs/policy" / CATALOG).read_bytes(), lock, revision=revision, tag=tag,
                 phase="final", evidence_root=folder / "evidence", manifest_sha256=summary["manifest_sha256"])
    (folder / "known-problems-report.json").write_text(json.dumps(final, indent=2) + "\n", newline="\n")
    return proof


def finalize(folder, revision, tag, repository, github):
    # Re-exercise anonymous availability in the final fresh job; a stale green
    # result cannot move discovery after an asset was removed or replaced.
    anonymous_verify(folder, revision, tag, repository)
    github.verify_tag(tag, revision)
    release = github.release(tag)
    require(release and release.get("prerelease") is True and release.get("draft") is False, "No immutable staged release to finalize")
    existing = {item["name"]: item for item in release.get("assets", [])}
    for path in (folder / "known-problems-report.json", folder / "evidence/final-signed-artifacts.json"):
        if path.name in existing:
            require(existing[path.name].get("digest") == "sha256:" + digest(path), "Existing final evidence differs")
        else:
            github.upload(release["id"], path)
    github.request("PATCH", "/releases/" + str(release["id"]), {"prerelease": False, "make_latest": "true",
        "body": "Qualified immutable Mastermind release. Signatures, checksums, provenance and complete qualification evidence are attached."})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("sign", "verify", "stage", "smoke", "finalize"))
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    for name in ("revision", "tag", "repository"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    common = (args.folder, args.revision, args.tag, args.repository)
    if args.command == "sign":
        require(args.key_file is not None, "Private key file required only in protected signing step")
        protect_sign(args.folder, args.key_file, args.revision, args.tag, args.repository)
    elif args.command == "verify":
        verify_local(*common)
    elif args.command == "smoke":
        anonymous_verify(*common)
    else:
        github = GitHub(args.repository, os.environ.get("GH_TOKEN", ""))
        (stage if args.command == "stage" else finalize)(*common, github)
    print("PASS " + args.command + " " + args.tag)


if __name__ == "__main__":
    main()
