"""Representative actual Core -> Neptune -> Saturn/SFTP streaming qualification."""
import hashlib
import json
import subprocess
import threading
import time

from probe_integrations import FIXTURE, ROOT, checked, client


def rss():
    value = subprocess.run(["docker", "exec", "mastermind-integration-neptune-1", "sh", "-c",
        "awk '/^VmRSS:/ {total += $2} END {print total*1024}' /proc/[0-9]*/status"],
        check=True, capture_output=True, text=True)
    return int(float(value.stdout.strip()))


def main():
    expected = json.loads((ROOT / ".local/large-recovery/fixture.json").read_text())
    baseline = rss()
    peak = baseline
    stop = threading.Event()
    def monitor():
        nonlocal peak
        while not stop.wait(0.5):
            peak = max(peak, rss())
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    started = time.monotonic()
    try:
        with client("neptune") as neptune:
            neptune.timeout = 60
            headers = {"X-Neptune-Token": (FIXTURE / "neptune-control.token").read_text()}
            for route in ("runs", "mirror/runs"):
                result = neptune.post("/v1/projects/mastermind/"+route, headers=headers)
                assert result.status_code == 202, f"{route}: {result.status_code}"
            while True:
                status = checked(neptune.get("/v1/projects/mastermind/status", headers=headers))
                if not status["active"] and status["latest_run_state"] in {"retry-wait", "export-failed"}:
                    raise AssertionError("Archive pipeline failed: "+str(status["latest_error"]))
                if not status["mirror_active"] and status["mirror"]["state"] == "retry-wait":
                    raise AssertionError("Mirror pipeline failed: "+str(status["mirror"]["error"]))
                if not status["active"] and not status["mirror_active"] and status["latest_run_state"] == status["mirror"]["state"] == "complete":
                    break
                assert time.monotonic()-started < 900, "Pipelines exceeded 15 minutes"
                time.sleep(2)
            digest, size = hashlib.sha256(), 0
            with neptune.stream("GET", "/api/v1/projects/mastermind/resource-content", headers={
                **headers, "X-Neptune-Purpose": "owner-reference"}, params={"path": "root/mastermind/Large qualification.bin"}) as response:
                assert response.status_code == 200
                assert int(response.headers["content-length"]) == expected["attachment_bytes"]
                for block in response.iter_bytes(1024**2):
                    size += len(block)
                    digest.update(block)
            assert size == expected["attachment_bytes"] and digest.hexdigest() == expected["attachment_sha256"]
    finally:
        stop.set()
        thread.join()
    evidence = {"synthetic_data": True, "archive": "complete", "mirror": "complete", "reader_bytes": size,
                "reader_sha256": digest.hexdigest(), "elapsed_seconds": round(time.monotonic()-started, 3),
                "neptune_baseline_rss": baseline, "neptune_peak_rss": peak, "neptune_extra_rss": peak-baseline}
    (ROOT / "artifacts/large-pipelines.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence), flush=True)
    assert peak-baseline <= 128*1024**2, "Neptune extra RSS exceeds 128 MiB"


if __name__ == "__main__":
    main()
