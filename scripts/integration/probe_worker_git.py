"""Actual public Git clone through the restricted Worker proxy/sandbox."""
import json
import time
from pathlib import Path

from mastermind.worker import Worker


def main():
    worker = Worker(Path("/work"), Path("/opt/mastermind/model"), Path("/app/embedding-model.lock.json"),
                    Path("/run/mastermind/worker_token"))
    identifier = "c"*32
    started = time.monotonic()
    result = worker.git(identifier, "https://github.com/octocat/Hello-World.git")
    extracted = worker.extract(identifier)
    assert "Hello World" in extracted["text"] or "Hello world" in extracted["text"]
    assert ".git/" not in extracted["text"]
    assert not (Path("/work") / identifier / "repository").exists()
    worker.cleanup(identifier)
    print(json.dumps({"public_git_clone": "PASS", "sandbox_extraction": "PASS", "source_bytes": result["size"],
                      "sha256": result["sha256"], "seconds": round(time.monotonic()-started, 2)}))


if __name__ == "__main__":
    main()
