"""Actual HTTP upload, persisted file lease, process SIGKILL/restart and retry."""
import concurrent.futures
import hashlib
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from probe_integrations import ROOT, FIXTURE, client


def docker(*args, check=True):
    result = subprocess.run(["docker", *args], capture_output=True)
    if check and result.returncode:
        raise RuntimeError("Qualification Docker operation failed: "+args[0])
    return result


def main():
    suffix = uuid.uuid4().hex
    name = "Restart qualification "+suffix+".bin"
    marker = "/app/data/mastermind-"+suffix+".held"
    env_path = FIXTURE/"saturn-env.json"
    original = env_path.read_bytes()
    environment = json.loads(original)
    assert not environment.get("NODE_OPTIONS"), "Unexpected pre-existing Saturn instrumentation"
    environment.update(NODE_OPTIONS="--import=/fixture/saturn-held-upload.mjs", MASTERMIND_QUALIFICATION_HOLD=name)
    shutil.copyfile(ROOT/"scripts/integration/saturn-held-upload.mjs", FIXTURE/"saturn-held-upload.mjs")
    credentials = json.loads((FIXTURE/"enrollment.json").read_text())
    write_headers = {"Authorization": "Bearer "+credentials["mirrorToken"], "Content-Type": "application/octet-stream", "If-None-Match": "*"}
    body = bytes(range(256))*8192
    route = "/dav/mastermind/"+name
    started = time.monotonic()
    def request():
        with client("saturn") as saturn:
            try:
                return saturn.put(route, headers=write_headers, content=body, timeout=60).status_code
            except Exception as error:
                return type(error).__name__
    try:
        env_path.write_text(json.dumps(environment), newline="\n")
        docker("compose", "-f", str(FIXTURE/"compose.yml"), "up", "-d", "--no-build", "--no-deps", "--force-recreate", "saturn")
        with client("saturn") as saturn:
            for attempt in range(90):
                if saturn.head(route, headers=write_headers).status_code in (200, 404):
                    break
                assert attempt < 89, "Saturn did not start"
                time.sleep(0.5)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(request)
            for attempt in range(120):
                if docker("exec", "mastermind-integration-saturn-1", "test", "-f", marker, check=False).returncode == 0:
                    break
                assert not pending.done(), "Upload completed before the held durable lease"
                assert attempt < 119, "Upload did not reach the held lease"
                time.sleep(0.25)
            docker("kill", "--signal", "KILL", "mastermind-integration-saturn-1")
            interrupted = pending.result(timeout=15)
            assert interrupted not in (200, 201, 204), "Interrupted upload was falsely acknowledged"
        docker("start", "mastermind-integration-saturn-1")
        with client("saturn") as saturn:
            for attempt in range(90):
                if saturn.head(route, headers=write_headers).status_code == 404:
                    break
                assert attempt < 89, "Saturn did not recover its unfinished upload"
                time.sleep(0.5)
            result = saturn.put(route, headers=write_headers, content=body, timeout=60)
            assert result.status_code in (201, 204), f"Retry failed with HTTP {result.status_code}"
            read = saturn.get("/api/v1/neptune-reader/resource-content", params={"path": "root/mastermind/"+name},
                              headers={"Authorization": "Bearer "+credentials["readerToken"]})
            assert read.status_code == 200 and read.content == body
            deletion = saturn.delete(route, headers={"Authorization": "Bearer "+credentials["mirrorToken"], "If-Match": read.headers["etag"]})
            assert deletion.status_code == 204
        report = {"actual_saturn_sigkill": True, "held_durable_lease": True, "interrupted_response": interrupted,
                  "retry": "PASS", "exact_reader_sha256": hashlib.sha256(body).hexdigest(), "owned_fixture_deleted": True,
                  "elapsed_seconds": round(time.monotonic()-started, 3)}
        (ROOT/"artifacts/saturn-restart-live.json").write_text(json.dumps(report, indent=2)+"\n")
        print(json.dumps(report))
    finally:
        env_path.write_bytes(original)
        docker("exec", "mastermind-integration-saturn-1", "node", "-e",
               "require('node:fs').rmSync(process.argv[1],{force:true})", marker, check=False)
        docker("compose", "-f", str(FIXTURE/"compose.yml"), "up", "-d", "--no-build", "--no-deps", "--force-recreate", "saturn")


if __name__ == "__main__":
    main()
