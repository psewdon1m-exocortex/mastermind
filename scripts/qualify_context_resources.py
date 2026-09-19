"""Bounded offline Worker qualification; run under the release 2 GiB / 2 CPU limit."""
import argparse
import json
import time
from pathlib import Path

from mastermind.curator_runtime import LocalCurator
from mastermind.embeddings import Embeddings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    embedding = Embeddings(Path("/opt/mastermind/model"), Path("/app/embedding-model.lock.json"))
    curator = LocalCurator("/opt/mastermind/curator", "/app/curator-model.lock.json")
    try:
        embedding.load()
        assert embedding.session is not None
        curator.start()
        assert curator.status()["ready"], curator.status()
        reports = []
        for repeat in range(3):
            tick = time.monotonic()
            vector = embedding.embed(["photosynthesis carbon chlorophyll plants sunlight "*300]*16, query=True)
            assert len(vector["vectors"]) == 16 and all(len(v) == 384 for v in vector["vectors"])
            proposal = curator.assist({"query": "Plants converting light into chemical energy",
                "reason": "LOW_EVIDENCE", "candidates": [
                    {"handle": "e"+str(i), "title": "Biology", "excerpt": ("Photosynthesis chlorophyll carbon fixation. "*20)[:700]}
                    for i in range(8)]})
            assert proposal["proposal"]["request_second_pass"] is True
            assert set(proposal["proposal"]["evidence_handles"]) <= {"e"+str(i) for i in range(8)}
            reports.append({"repeat": repeat, "seconds": round(time.monotonic()-tick, 3), "usage": proposal["usage"]})
        memory = int(Path("/sys/fs/cgroup/memory.peak").read_text())
        events = dict(line.split() for line in Path("/sys/fs/cgroup/memory.events").read_text().splitlines())
        assert int(events["oom"]) == int(events["oom_kill"]) == 0
        report = {"schema": "context-indexing.resource-qualification.v1", "status": "PASS",
                  "network": "none", "cpu_limit": 2, "memory_limit_bytes": 2*1024**3, "memory_peak_bytes": memory,
                  "memory_events": events, "model_digest": curator.model_digest, "cycles": reports,
                  "seconds": round(time.monotonic()-started, 3)}
        if args.output:
            args.output.write_text(json.dumps(report, indent=2)+"\n", "utf-8")
        print(json.dumps(report), flush=True)
    finally:
        curator.close()


if __name__ == "__main__":
    main()
