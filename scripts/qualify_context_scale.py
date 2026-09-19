"""Offline performance/protocol checks; repeated vectors do not measure quality."""
import argparse
import json
import resource
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from qualify_context_indexing import OfflineWorker

from mastermind.audit import Audit
from mastermind.config import Config
from mastermind.context_indexing import ContextIndexing
from mastermind.context_indexing.graph import Graph, Scope
from mastermind.context_indexing.pipeline import Pipeline
from mastermind.coordinator import Coordinator
from mastermind.runtime_client import RuntimeClient
from mastermind.semantic import VECTOR, Semantic
from mastermind.state import State
from mastermind.vault import Vault


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    worker = OfflineWorker(Path("/opt/mastermind/model"), Path("/app/embedding-model.lock.json"),
                           "/opt/mastermind/curator", "/app/curator-model.lock.json")
    report = {"schema": "context-indexing.scale.v1", "limitations": [
        "Synthetic 8,000-note workload with repeated real E5 vectors: performance only, not relevance quality.",
        "Curator ambiguity is forced by the protocol probe; it does not establish placement benefit."]}
    try:
        with tempfile.TemporaryDirectory() as directory:
            config = Config(home=Path(directory), runtime_mode="offline", test_mode=True)
            state = State(config.state / "mastermind.sqlite3")
            coordinator = Coordinator(config, state, RuntimeClient(config))
            vault = Vault(config, state, coordinator)
            service = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault,
                audit=Audit(config, state), data_ready=lambda: None)
            text = "Chlorophyll in green leaves absorbs sunlight. Photosynthesis converts water and carbon dioxide into sugars and releases oxygen.\n"
            notes = {"root.md": "[[Botany]]", "Botany.md": "#main\n[[Photosynthesis]]",
                "Photosynthesis.md": "#key\n" + text}
            notes.update({f"Notes/Leaf {i:05}.md": f"# Leaf {i:05}\n" + text * 20 +
                          ("\n[[Photosynthesis]]" if i % 2 else "\n@Photosynthesis")
                          for i in range(7997)})
            started = time.monotonic()
            coordinator.commit({p: body.encode() for p, body in notes.items()}, {p: None for p in notes})
            vault.index()
            report["create_and_index_seconds"] = round(time.monotonic() - started, 3)
            semantic = service.semantic = Semantic(service, worker=worker)
            semantic.refresh()
            context = ContextIndexing(service, worker=worker, semantic=semantic)
            context.settings.bootstrap()
            vector = VECTOR.pack(*worker.embed([text])["vectors"][0])
            with state.transaction() as db:
                for note in state.rows("SELECT path,sha FROM notes"):
                    db.execute("INSERT OR REPLACE INTO semantic_documents VALUES(?,?,?,?,?,?)",
                               (note["path"], note["sha"], semantic.model, "[]", 1, 1))
                    db.execute("INSERT OR REPLACE INTO semantic_chunks VALUES(?,?,?,?,?,?,?)",
                               (note["path"], 0, 0, 100, note["sha"], semantic.model, vector))
            graph = Graph(vault, Scope("owner"))
            context.index.sync(graph, limit=10000, deadline=time.monotonic()+60)
            context.index.profiles(graph, graph.structure(), context.settings.get(), limit=10000, deadline=time.monotonic()+30)
            measurements = []
            for _ in range(3):
                result, _ = context.pipeline.run({"text": "How do plants turn light into stored chemical energy?"},
                    configuration=context.settings.get())
                assert not result["truncated"] and "vector" not in result["missing_strategies"], result["missing_strategies"]
                assert result["results"] and result["timings"]["total_ms"] < 15000
                measurements.append(result["timings"]["total_ms"])
            report.update(notes=len(notes), vault_bytes=sum(len(t.encode()) for t in notes.values()),
                query_ms=measurements, database_bytes=(config.state / "mastermind.sqlite3").stat().st_size)
            worker.curator.start()
            assert worker.curator.status()["ready"]
            # Real model/second-retrieval protocol under a deliberately ambiguous assessment.
            calls, saved = [], {}
            original = worker.request
            def counted(method, route, *args, **kwargs):
                if route == "/curator/assist":
                    calls.append(route)
                return original(method, route, *args, **kwargs)
            worker.request = counted
            def checkpoint(key, action):
                if key not in saved:
                    saved[key] = action()
                return saved[key]
            def uncertain(*_):
                return {"status": "ambiguous", "reason": "PROTOCOL_QUALIFICATION"}
            pipeline = Pipeline(service, context.index, semantic=semantic, curator=context.curator)
            subject = {"text": "plants storing energy from daylight"}
            for _ in range(2):
                result, _ = pipeline.run(subject, configuration={**context.settings.get(), "curator_enabled": True},
                    assessment=uncertain, checkpoint=checkpoint)
                assert result["curator"]["invoked"] and result["curator"]["passes"] == 1
                assert result["curator"]["outcome"] in {"refined", "no_improvement"}, result["curator"]
            assert len(calls) == 1
            report["curator"] = {**result["curator"], "actual_inferences_across_replay": len(calls)}
            report["process_max_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            report["status"] = "PASS"
            state.close()
    finally:
        worker.close()
    args.output.write_text(json.dumps(report, indent=2) + "\n", "utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
