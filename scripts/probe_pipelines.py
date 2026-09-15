"""Qualify actual native Core snapshot -> Neptune -> Saturn/SFTP pipelines."""
import hashlib
import json
import time
from pathlib import Path

import httpx
from probe_integrations import checked, client

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / ".local/integration"


def main():
    owner = httpx.Client(base_url="http://localhost:18390", timeout=150,
                         headers={"Origin": "http://localhost:18390"})
    login = checked(owner.post("/api/auth/login", json={
        "access_key": (ROOT / ".local/secrets/core/bootstrap_access_key").read_text()}))
    owner.headers["X-CSRF-Token"] = login["csrf"]
    # Chromium accepts Secure __Host cookies on localhost. httpx does not implement
    # that development exception; this protocol probe sends its own session explicitly.
    owner.headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in owner.cookies.items())
    note = "#main\nPipeline fixture, exact Unicode: café.\n"
    path = "Pipeline fixture.md"
    previous = owner.get("/api/note", params={"path": path})
    if previous.status_code == 404:
        checked(owner.post("/api/notes", json={"path": path, "text": note}))
    else:
        assert previous.status_code == 200, f"Owner note read: {previous.status_code}"
        checked(owner.put("/api/note", json={"path": path, "text": note,
            "expected_sha256": previous.headers["etag"].strip('"')}))
    neptune = client("neptune")
    headers = {"X-Neptune-Token": (FIXTURE / "neptune-control.token").read_text()}
    started = time.time()
    for route in ["runs", "mirror/runs"]:
        response = neptune.post("/v1/projects/mastermind/" + route, headers=headers)
        assert response.status_code == 202, f"Pipeline acceptance: {route}: {response.status_code}"
    deadline = time.monotonic() + 150
    while True:
        status = checked(neptune.get("/v1/projects/mastermind/status", headers=headers))
        if status["latest_run_state"] == "retry-wait" or status["mirror"]["state"] == "retry-wait":
            # Producer errors contain a generic protocol error; never print tokens or response bodies.
            raise AssertionError(f"Pipeline failure: archive={status['latest_error']}; mirror={status['mirror']['error']}")
        if not status["active"] and not status["mirror_active"] and status["latest_run_state"] == "complete" and status["mirror"]["state"] == "complete":
            break
        if time.monotonic() > deadline:
            raise AssertionError("Pipeline completion deadline exceeded")
        time.sleep(1)
    reader = {**headers, "X-Neptune-Purpose": "owner-reference"}
    content = neptune.get("/api/v1/projects/mastermind/resource-content", headers=reader,
                          params={"path": "root/mastermind/" + path})
    assert content.status_code == 200 and content.content == note.encode()
    (ROOT / "artifacts/pipeline-live.json").write_text(json.dumps({
        "archive": status["latest_run_state"], "mirror": status["mirror"]["state"],
        "mirror_note_sha256": hashlib.sha256(content.content).hexdigest(),
        "elapsed_seconds": round(time.time() - started, 2), "synthetic_data": True}, indent=2))
    print("PASS: actual official Obsidian/Core barrier -> independent Neptune archive and mirror -> Saturn/SFTP; exact note bytes.")


if __name__ == "__main__":
    main()
