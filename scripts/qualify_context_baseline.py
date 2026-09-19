"""Real legacy placement, fixed subset; synthetic source data only, real Wyvern requests."""
import argparse
import json
import tempfile
import time
from pathlib import Path

from qualify_context_indexing import OfflineWorker, fixture

from mastermind.config import Config
from mastermind.context_indexing.graph import digest
from mastermind.coordinator import Coordinator
from mastermind.gemini import Gemini
from mastermind.hierarchy import Hierarchy
from mastermind.runtime_client import RuntimeClient
from mastermind.state import State
from mastermind.vault import Vault


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=Path("/corpus/corpus.py"))
    args = parser.parse_args()
    corpus = fixture(args.corpus)
    # Predeclared selection: first positive paraphrase and both negative cases
    # for every held-out topic. Never select cases using algorithm outcomes.
    cases = [c for c in corpus["cases"] if c["split"] == "test" and (c["must_pool"] or c["id"].endswith("-0"))]
    assert len(cases) == 30
    worker = OfflineWorker(Path("/opt/mastermind/model"), Path("/app/embedding-model.lock.json"),
                           "/opt/mastermind/curator", "/app/curator-model.lock.json")
    provider = Gemini(link_file=Path("/run/wyvern-link/link.json"))
    report = {"schema": "context-indexing.legacy-baseline.v1", "corpus_sha256": digest(corpus),
              "origin": "Real retained Hierarchy.place with real Google through Wyvern/Kernel/Volt",
              "selection": "Each held-out topic: first positive paraphrase and both must_pool cases (30 total)",
              "timing_limitation": "Baseline collected after frozen calibration; it was not used for threshold tuning.",
              "cases": []}
    if args.output.exists():
        report = json.loads(args.output.read_text())
        assert report["corpus_sha256"] == digest(corpus)
    try:
        provider.models()
        with tempfile.TemporaryDirectory() as directory:
            config = Config(home=Path(directory), runtime_mode="offline", test_mode=True)
            state = State(config.state/"mastermind.sqlite3")
            coordinator = Coordinator(config, state, RuntimeClient(config))
            vault = Vault(config, state, coordinator)
            coordinator.commit({p: body.encode() for p, body in corpus["notes"].items()}, {p: None for p in corpus["notes"]})
            vault.index()
            legacy = Hierarchy(vault, worker, provider)
            done = {row["id"] for row in report["cases"]}
            count_cache = {}
            original_count = provider.token_count

            def count(model, text):
                key = digest([model, text])
                if key not in count_cache:
                    count_cache[key] = original_count(model, text)
                return count_cache[key]
            provider.token_count = count
            for case in cases:
                if case["id"] in done:
                    continue
                started = time.monotonic()
                cached = {}

                def checkpoint(key, callback, cached=cached, **kwargs):
                    if key not in cached:
                        cached[key] = callback()
                    return cached[key]
                result = legacy.place({"title": "", "summary": case["source"], "topics": [], "entities": []}, "text",
                    checkpoint=checkpoint, budget={"unique": {}, "transmitted": 0})
                report["cases"].append({"id": case["id"], "must_pool": case["must_pool"], "acceptable": case["acceptable"],
                    "anchor": result["anchor"], "diagnostic": result["diagnostic"], "seconds": round(time.monotonic()-started, 3)})
                report["target"] = provider.targets.get("text")
                args.output.write_text(json.dumps(report, indent=2)+"\n")
                print(json.dumps({"completed": len(report["cases"]), "total": len(cases)}), flush=True)
            selected = [row for row in report["cases"] if row["anchor"]]
            report["metrics"] = {"cases": len(cases), "auto_decisions": len(selected), "coverage": len(selected)/len(cases),
                "precision": sum(row["anchor"] in row["acceptable"] for row in selected)/max(1, len(selected)),
                "must_pool_auto": sum(row["must_pool"] for row in selected)}
            report["status"] = "MEASURED"
            args.output.write_text(json.dumps(report, indent=2)+"\n")
            print(json.dumps(report["metrics"]), flush=True)
            state.close()
    finally:
        provider.close()
        worker.close()


if __name__ == "__main__":
    main()
