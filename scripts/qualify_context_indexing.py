"""Fixed-corpus local retrieval measurement. Calibration never reads held-out cases.

Run in an isolated Worker image with no network. The generated report identifies
synthetic fixtures explicitly and never claims a real legacy LLM baseline.
"""
import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import statistics
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from mastermind.audit import Audit
from mastermind.config import Config
from mastermind.context_indexing import ContextIndexing
from mastermind.context_indexing.graph import Graph, Scope, digest
from mastermind.context_indexing.pipeline import Pipeline, source_features
from mastermind.coordinator import Coordinator
from mastermind.curator_runtime import LocalCurator
from mastermind.embeddings import Embeddings
from mastermind.runtime_client import RuntimeClient
from mastermind.semantic import Semantic
from mastermind.state import State
from mastermind.vault import Vault


class OfflineWorker:
    def __init__(self, model_dir, model_lock, curator_dir, curator_lock):
        self.embedding = Embeddings(model_dir, model_lock)
        self.embedding.load()
        if self.embedding.session is None:
            raise ValueError("Verified embedding model is unavailable")
        self.curator = LocalCurator(curator_dir, curator_lock)
        self.cache = {}

    def request(self, method, route, data=None, **kwargs):
        if route == "/healthz":
            return {"embeddings_ready": True, "model_sha256": self.embedding.model_sha}
        if route == "/chunks":
            return {"chunks": self.embedding.chunks(data["text"]), "model_sha256": self.embedding.model_sha}
        if route == "/curator/status":
            return self.curator.status()
        if route == "/curator/assist":
            return self.curator.assist(data)
        raise ValueError(route)

    def embed(self, texts, *, query=False):
        key = digest([texts, query])
        if key not in self.cache:
            self.cache[key] = self.embedding.embed(texts, query=query)
        return self.cache[key]

    def close(self):
        self.curator.close()


def fixture(path):
    spec = importlib.util.spec_from_file_location("context_corpus", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = module.dataset()
    assert len(data["cases"]) >= 300
    assert len([c for c in data["cases"] if c["split"] == "test"]) >= 100
    groups = {}
    for case in data["cases"]:
        assert case["group"] not in groups or groups[case["group"]] == case["split"]
        groups[case["group"]] = case["split"]
        assert case["source"] not in data["notes"].values()
        assert not case["must_pool"] or not case["acceptable"]
    return data


def evaluate(rows, threshold):
    decisions = [r for r in rows if r["top"] and not r["truncated"] and r["score"] >= threshold["score"]
                 and r["gap"] >= threshold["gap"] and r["lexical"] >= threshold["lexical"]]
    correct = sum(r["top"] in r["acceptable"] for r in decisions)
    total = len(decisions)
    precision = correct/total if total else None
    # Descriptive Wilson interval only; correlated paraphrases are explicitly disclosed.
    if total:
        z = 1.96
        center = (precision+z*z/(2*total))/(1+z*z/total)
        half = z*math.sqrt(precision*(1-precision)/total+z*z/(4*total*total))/(1+z*z/total)
        interval = [round(center-half, 4), round(center+half, 4)]
    else:
        interval = None
    labelled = [r for r in rows if r["acceptable"]]
    timings = sorted(r["ms"] for r in rows)
    return {"cases": len(rows), "auto_decisions": total, "precision": precision,
            "descriptive_precision_interval_95": interval, "coverage": total/len(rows),
            "must_pool_auto": sum(r["must_pool"] for r in decisions), "pool_rate": 1-total/len(rows),
            "candidate_recall_at_200": sum(bool(set(r["candidate_targets"]) & set(r["acceptable"])) for r in labelled)/max(1, len(labelled)),
            "top_1": sum(r["top"] in r["acceptable"] for r in labelled)/max(1, len(labelled)),
            "top_3": sum(bool(set(r["top3"]) & set(r["acceptable"])) for r in labelled)/max(1, len(labelled)),
            "latency_p50_ms": statistics.median(timings), "latency_p95_ms": timings[min(len(timings)-1, math.ceil(len(timings)*.95)-1)],
            "curator_invocations": sum(r["curator"].get("invoked", False) for r in rows),
            "curator_refinements": sum(r["curator"].get("outcome") == "refined" for r in rows)}


def thresholds(rows):
    best = None
    for score, gap, lexical in itertools.product([v/100 for v in range(15, 101, 5)], [v/200 for v in range(51)], [0, .2, .3, .4, .5, .6]):
        threshold = {"score": score, "gap": gap, "lexical": lexical}
        metrics = evaluate(rows, threshold)
        if metrics["precision"] is not None and metrics["precision"] >= .98 and metrics["must_pool_auto"] == 0:
            preference = (metrics["auto_decisions"], metrics["precision"], gap, lexical, score)
            if best is None or preference > best[0]:
                best = preference, threshold, metrics
    if best is None:
        raise ValueError("No safe calibration operating point exists")
    return best[1], best[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("calibration", "test"), required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--ablations", action="store_true")
    args = parser.parse_args()
    corpus = fixture(args.corpus)
    corpus_sha = digest(corpus)
    worker = OfflineWorker(Path("/opt/mastermind/model"), Path("/app/embedding-model.lock.json"),
                           "/opt/mastermind/curator", "/app/curator-model.lock.json")
    if args.phase == "test":
        calibration = json.loads(args.calibration.read_text("utf-8"))
        assert calibration["corpus_sha256"] == corpus_sha
    else:
        calibration = None
    report = {"schema": "context-indexing.quality.v1", "corpus_sha256": corpus_sha, "origin": corpus["origin"],
              "phase": args.phase, "embedding_sha256": worker.embedding.model_sha,
              "baseline": {"status": "PENDING_REAL_PROVIDER", "note": "No simulated provider is reported as a legacy quality baseline."},
              "limitations": ["Authored synthetic corpus; no universal accuracy claim.",
                              "Paraphrases are grouped by domain; case-level Wilson intervals are descriptive, not independent-sample guarantees."],
              "variants": {}}
    try:
        with tempfile.TemporaryDirectory(prefix="context-qualification-") as directory:
            config = Config(home=Path(directory), runtime_mode="offline", test_mode=True)
            state = State(config.state/"mastermind.sqlite3")
            coordinator = Coordinator(config, state, RuntimeClient(config))
            vault = Vault(config, state, coordinator)
            service = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault, audit=Audit(config, state), data_ready=lambda: None)
            coordinator.commit({p: body.encode() for p, body in corpus["notes"].items()}, {p: None for p in corpus["notes"]})
            vault.index()
            semantic = Semantic(service, worker=worker)
            service.semantic = semantic
            context = ContextIndexing(service, worker=worker, semantic=semantic)
            if calibration:
                # Candidate thresholds are fixed before opening held-out cases;
                # this injection is confined to the isolated measurement process.
                context.policy.calibration = {**calibration, "qualified": True}
            context.settings.bootstrap()
            for _ in range(1000):
                if not semantic.once():
                    break
            assert semantic.status()["status"] == "READY"
            graph = Graph(vault, Scope("crusher"))
            context.index.sync(graph, limit=10000, deadline=time.monotonic()+30)
            context.index.profiles(graph, graph.structure(), context.settings.get(), limit=10000, deadline=time.monotonic()+30)
            variants = {"complete": (), "vector": ("vector",)}
            if args.ablations:
                variants.update(no_profiles=("profiles",), no_expansion=("expansion",), curator=())
                worker.curator.start()
                assert worker.curator.status()["ready"]
            for variant, disabled in variants.items():
                pipeline = Pipeline(service, context.index, semantic=semantic, curator=context.curator, disabled=disabled)
                configuration = {**context.settings.get(), "curator_enabled": variant == "curator"}
                rows = []
                for case in [v for v in corpus["cases"] if v["split"] == args.phase]:
                    subject = source_features({"title": "", "summary": case["source"], "topics": [], "entities": []})
                    result, snapshot = pipeline.run(subject, scope=Scope("crusher"), query_type="placement_analysis",
                        configuration=configuration, assessment=lambda result, graph, configuration=configuration: context.policy.assess(result, graph, configuration))
                    targets = {p for value in result["results"] for p in snapshot.structure().memberships(value["path"])}
                    ranking = result.get("placement_candidates", [])
                    first = ranking[0] if ranking else {}
                    rows.append({"id": case["id"], "group": case["group"], "acceptable": case["acceptable"], "must_pool": case["must_pool"],
                        "top": first.get("path"), "top3": [v["path"] for v in ranking], "candidate_targets": sorted(targets),
                        "score": first.get("score", 0), "gap": result.get("gap", 0), "lexical": first.get("features", {}).get("lexical", 0),
                        "truncated": result["truncated"] or result.get("multiple_topics", False) or result.get("counterevidence", False), "missing": result["missing_strategies"], "ms": result["timings"]["total_ms"],
                        "curator": result["curator"], "ranked_features": [{k: v[k] for k in ("path", "score", "features")} for v in ranking]})
                    if len(rows) % 20 == 0:
                        print(json.dumps({"variant": variant, "completed": len(rows)}), flush=True)
                if args.phase == "calibration":
                    threshold, metrics = thresholds(rows)
                else:
                    threshold = calibration["variants"].get(variant, calibration["variants"]["complete"])
                    metrics = evaluate(rows, threshold)
                report["variants"][variant] = {"threshold": threshold, "metrics": metrics, "cases": rows}
            report["index_bytes"] = state.one("SELECT SUM(length(record)) AS n FROM context_profiles")["n"]
            if args.phase == "calibration":
                value = {"version": "context-indexing.calibration.v1", "policy_version": "crusher.placement.v1", "qualified": False,
                         "corpus_sha256": corpus_sha, "calibration_report_sha256": digest(report), "embedding_sha256": worker.embedding.model_sha,
                         "variants": {key: value["threshold"] for key, value in report["variants"].items()}}
                value["variants"]["complete:curator"] = value["variants"]["complete"]
                args.calibration.write_text(json.dumps(value, indent=2)+"\n", "utf-8")
                report["status"] = "CALIBRATED_NOT_HELD_OUT_QUALIFIED"
            else:
                metrics = report["variants"]["complete"]["metrics"]
                report["status"] = "PASS" if metrics["auto_decisions"] >= 50 and metrics["precision"] >= .98 and metrics["must_pool_auto"] == 0 else "FAIL"
                report["calibration_sha256"] = hashlib.sha256(args.calibration.read_bytes()).hexdigest()
            args.output.write_text(json.dumps(report, indent=2)+"\n", "utf-8")
            print(json.dumps({"status": report["status"], "variants": {key: value["metrics"] for key, value in report["variants"].items()}}), flush=True)
            state.close()
    finally:
        worker.close()


if __name__ == "__main__":
    main()
