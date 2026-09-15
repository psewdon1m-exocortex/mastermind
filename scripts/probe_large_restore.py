"""Actual owner maintenance protocol and native Runtime on a 350 MiB archive."""
import argparse
import hashlib
import json
import subprocess
import time
from contextlib import closing
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / ".local/large-recovery"


def checked(response):
    if response.status_code != 200:
        raise AssertionError(f"{response.request.method} {response.request.url.path}: {response.status_code}")
    return response.json()


def login():
    client = httpx.Client(base_url="http://localhost:18390", timeout=120,
                         headers={"Origin": "http://localhost:18390"})
    value = checked(client.post("/api/auth/login", json={
        "access_key": (ROOT / ".local/secrets/core/bootstrap_access_key").read_text()}))
    client.headers.update({"X-CSRF-Token": value["csrf"],
                           "Cookie": "; ".join(f"{k}={v}" for k, v in client.cookies.items())})
    deadline = time.monotonic()+90
    while checked(client.get("/api/status"))["status"] != "HEALTHY":
        assert time.monotonic() < deadline, "Runtime readiness timeout"
        time.sleep(1)
    return client


def wait(client, identifier, target):
    deadline = time.monotonic()+15*60
    while True:
        value = checked(client.get("/api/owner/operations/"+identifier))
        if value["state"] == target:
            return value
        assert value["state"] not in {"FAILED", "INTERRUPTED"}, value.get("error", value["state"])
        assert time.monotonic() < deadline, "Maintenance deadline exceeded"
        time.sleep(1)


def main():
    args = argparse.ArgumentParser()
    args.add_argument("mode", choices=("prepare", "restore"))
    mode = args.parse_args().mode
    DIRECTORY.mkdir(exist_ok=True)
    with closing(login()) as client:
        if mode == "prepare":
            operation = checked(client.post("/api/owner/operations", json={"kind": "backup"}))
            record = wait(client, operation["id"], "COMPLETED")
            digest = hashlib.sha256()
            with client.stream("GET", "/api/owner/operations/"+record["id"]+"/download") as response:
                assert response.status_code == 200
                with (DIRECTORY / "original.zip").open("xb") as output:
                    for block in response.iter_bytes(1024**2):
                        output.write(block)
                        digest.update(block)
            assert digest.hexdigest() == record["sha256"]
            checked(client.delete("/api/owner/operations/"+record["id"]))
            print("PASS: fresh consistent native source backup downloaded and verified.", flush=True)
            return
        source = DIRECTORY / "large.zip"
        with source.open("rb") as content:
            digest = hashlib.file_digest(content, "sha256").hexdigest()
        operation = checked(client.post("/api/owner/operations", json={"kind": "restore", "size": source.stat().st_size}))
        identifier = operation["id"]
        with source.open("rb") as content:
            uploaded = checked(client.put("/api/owner/operations/"+identifier+"/content", content=content))
        assert uploaded["sha256"] == digest
        checked(client.post("/api/owner/operations/"+identifier+"/confirm", json={"action": "inspect", "sha256": digest}))
        wait(client, identifier, "AWAITING_CONFIRMATION")
        started = time.monotonic()
        checked(client.post("/api/owner/operations/"+identifier+"/confirm", json={"action": "restore", "sha256": digest}))
        deadline = time.monotonic()+120
        while client.get("/api/status").status_code != 401:
            assert time.monotonic() < deadline, "Restore pause exceeded 120 seconds"
            time.sleep(0.5)
        with closing(login()) as restored:
            result = wait(restored, identifier, "COMPLETED")
        elapsed = time.monotonic()-started
        expected = json.loads((DIRECTORY / "fixture.json").read_text())
        actual = subprocess.run(["docker", "exec", "mastermind-development-core-1", "python", "-c",
            "import hashlib,json,pathlib; p=pathlib.Path('/data/vault/current/Large qualification.bin'); "
            "print(json.dumps({'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),"
            "'size':p.stat().st_size,'copies':len(list(p.parent.parent.glob('.verify-*')))}))"],
            capture_output=True, text=True, check=True)
        verified = json.loads(actual.stdout)
        assert verified["sha256"] == expected["attachment_sha256"]
        assert verified["size"] == expected["attachment_bytes"] and verified["copies"] == 0
        assert elapsed < 120
        evidence = {**expected, "native_restore_seconds": round(elapsed, 3), "state": result["state"],
                    "old_session": "REVOKED", "native_runtime": "READY", "verified_copy_removed": True}
        (ROOT / "artifacts/large-native-restore.json").write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence), flush=True)


if __name__ == "__main__":
    main()
