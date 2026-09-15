"""Run inside the real non-root, read-only Worker container with --network none."""
import json
import time
from pathlib import Path

import numpy as np
import psutil

from mastermind.fs import atomic_json, sha_file
from mastermind.worker import Worker


def main():
    credential = Path("/run/mastermind/worker_token")
    credential.write_text("synthetic-worker-identity-canary")
    Path("/work/other").mkdir()
    Path("/work/other/canary").write_text("synthetic-other-job-canary")
    worker = Worker(Path("/work"), Path("/opt/mastermind/model"), Path("/app/embedding-model.lock.json"), credential)
    start = time.monotonic()
    worker.start()
    assert worker.embeddings.session is not None, "Offline model failed to load"
    query = np.array(worker.embeddings.embed(["Архитектура базы знаний"], query=True)["vectors"][0])
    vectors = np.array(worker.embeddings.embed(["Knowledge base architecture and semantic organization.",
                                               "A recipe for baking chocolate cookies."])["vectors"])
    similarity = vectors @ query
    assert similarity[0] > similarity[1], "Cross-language semantic ranking failed"
    long_text = "Knowledge architecture and semantic links. "*2000
    parts = worker.embeddings.chunks(long_text)
    batch = [long_text[item["start"]:item["end"]] for item in parts[:16]]
    result = worker.embeddings.embed(batch)
    assert max(result["token_counts"]) <= 512 and len(result["vectors"]) <= 16
    identifier = "b"*32
    folder = worker.reserve(identifier, 100)
    worker.active = None
    worker.sandbox(folder, mode="probe")
    boundary = json.loads((folder / "probe.json").read_text())
    assert set(boundary["denied"]) == {"network", "service_identity", "sibling_job"}, boundary
    (folder / "source").write_text("# Source heading\n\nUseful facts from an isolated text document.\n")
    atomic_json(folder / "source.json", {"name": "document.txt", "mime": "text/plain",
                                        "sha256": sha_file(folder / "source"), "size": (folder / "source").stat().st_size})
    extracted = worker.extract(identifier)
    assert "Useful facts" in extracted["text"] and not extracted["needs_media"]
    assert "synthetic" not in json.dumps(extracted)
    worker.cleanup(identifier)
    assert not folder.exists()
    rss = psutil.Process().memory_info().rss
    assert rss < 2*1024**3
    print(json.dumps({"offline_model": "PASS", "cross_language_ranking": "PASS", "sandbox": boundary,
                      "actual_extraction": "PASS", "batch": len(batch), "max_tokens": max(result["token_counts"]),
                      "rss_bytes": rss, "seconds": round(time.monotonic()-start, 2)}))


if __name__ == "__main__":
    main()
