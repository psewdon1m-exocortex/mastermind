"""Publish only frozen thresholds whose recorded safety and comparable-baseline gates pass."""
import hashlib
import json
from pathlib import Path

from qualify_context_indexing import evaluate

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = {name: ROOT/"artifacts"/filename for name, filename in {
        "calibration": "context-indexing-thresholds-acceptance.json",
        "held_out": "context-indexing-held-out-acceptance.json",
        "curator_regression": "context-indexing-curator-regression.json",
        "final_guard_regression": "context-indexing-final-guard-regression.json",
        "baseline": "context-indexing-legacy-baseline-acceptance.json"}.items()}
    reports = {name: json.loads(path.read_text()) for name, path in paths.items()}
    calibration = reports["calibration"]
    assert reports["held_out"]["calibration_sha256"] == hashlib.sha256(paths["calibration"].read_bytes()).hexdigest()
    assert len({report["corpus_sha256"] for report in reports.values()}) == 1
    for variant in ("complete", "vector", "curator"):
        metrics = reports["final_guard_regression"]["variants"][variant]["metrics"]
        assert metrics["auto_decisions"] >= 50 and metrics["precision"] >= .98 and metrics["must_pool_auto"] == 0
    baseline = reports["baseline"]
    ids = {row["id"] for row in baseline["cases"]}
    cases = [row for row in reports["final_guard_regression"]["variants"]["complete"]["cases"] if row["id"] in ids]
    observed = evaluate(cases, calibration["variants"]["complete"])
    assert observed["cases"] == baseline["metrics"]["cases"]
    assert observed["precision"] >= baseline["metrics"]["precision"] and observed["coverage"] >= baseline["metrics"]["coverage"]
    calibration.update(qualified=True, version="context-indexing.calibration.20260919.v1",
        rejection_guard_version="explicit-topic-exclusions.v1",
        evidence={name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()},
        comparison={"cases": len(cases), "legacy": baseline["metrics"], "context_indexing": observed},
        limitations=["Authored grouped synthetic corpus, not a universal accuracy estimate.",
                     "Legacy comparison was measured after frozen calibration and never used to tune thresholds.",
                     "Curator source-conflict guard was repaired after held-out failure; its repeat is a regression check, not unseen data.",
                     "Live technical-anchor counterexample added a conservative topic-exclusion rejection guard. Thresholds are unchanged; final replay is regression, not a fresh held-out evaluation.",
                     "Final Curator-on corpus invokes no refinements; no placement benefit is established. Keep default off."])
    target = ROOT/"src/mastermind/context_indexing/calibration.json"
    target.write_text(json.dumps(calibration, indent=2)+"\n")
    print("PASS: frozen thresholds accepted; baseline comparison and provenance retained.")


if __name__ == "__main__":
    main()
