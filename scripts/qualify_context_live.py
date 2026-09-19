"""Real Worker + Wyvern/Kernel/Volt/Google processing in an isolated synthetic Vault."""
import argparse
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from mastermind.audit import Audit
from mastermind.auth import Auth
from mastermind.config import Config
from mastermind.context_indexing import ContextIndexing
from mastermind.context_indexing.template import DEFAULT_TEMPLATE
from mastermind.coordinator import Coordinator
from mastermind.crusher import Crusher
from mastermind.crusher_access import CrusherAccess
from mastermind.fs import sha_bytes
from mastermind.gemini import Gemini
from mastermind.runtime_client import RuntimeClient
from mastermind.secret_store import SecretStore
from mastermind.semantic import Semantic
from mastermind.state import State
from mastermind.vault import Vault
from mastermind.worker_client import WorkerClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    calibration = json.loads(args.calibration.read_text())
    report = {"schema": "context-indexing.live-qualification.v1", "status": "RUNNING",
        "boundaries": {"worker": "real Docker private HTTP", "generation": "real Google via Wyvern/Kernel/Volt",
                       "vault": "isolated synthetic files", "runtime": "offline coordinator (native Runtime checked separately)"}, "cases": []}
    with tempfile.TemporaryDirectory() as directory:
        config = Config(home=Path(directory), runtime_mode="offline", test_mode=True, worker_url="http://mastermind-context-worker:8092",
                        secret_backend="development-files", secret_directory=Path("/run/mastermind"))
        state = State(config.state/"mastermind.sqlite3")
        coordinator = Coordinator(config, state, RuntimeClient(config))
        vault = Vault(config, state, coordinator)
        audit = Audit(config, state)
        service = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault, audit=audit,
            secrets=SecretStore(config.secret_directory), data_ready=lambda: None)
        worker = WorkerClient(config, service.secrets)
        provider = Gemini(link_file=Path("/run/wyvern-link/link.json"))
        external_calls = []
        original = provider.gateway.call

        def checked_call(method, route, **kwargs):
            if "data" in kwargs:
                assert "PRIVATE_GRAPH_CANARY" not in json.dumps(kwargs["data"])
            external_calls.append(route)
            return original(method, route, **kwargs)
        provider.gateway.call = checked_call
        try:
            notes = {"root.md": "[[Physics]]", "Branches/Physics.md": "#main\n[[Electromagnetic induction]]\nPRIVATE_GRAPH_CANARY",
                "Branches/Electromagnetic induction.md": "#key\nChanging magnetic flux through a conducting coil creates an induced voltage.",
                "Notes/Coil experiment.md": "Moving a magnet into a coil induces voltage. Reversing the motion reverses voltage.\n[[Electromagnetic induction]]"}
            coordinator.commit({p: text.encode() for p, text in notes.items()}, {p: None for p in notes})
            vault.index()
            semantic = service.semantic = Semantic(service, worker=worker)
            context = service.context_indexing = ContextIndexing(service, worker=worker, semantic=semantic,
                calibration={**calibration, "qualified": True})
            context.settings.bootstrap()
            deadline = time.monotonic()+90
            while time.monotonic() < deadline:
                if not semantic.once() and semantic.status()["status"] == "READY":
                    break
                time.sleep(.05)
            assert semantic.status()["status"] == "READY"
            context.maintain()
            access = service.crusher_access = CrusherAccess(config, state, Auth(state, audit), audit)
            engine = Crusher(service, worker=worker, provider=provider)
            before = {path: sha_bytes(vault.read(path).encode()) for path in notes}
            sources = ["Electromagnetic induction experiment: moving a magnet into a conducting coil induces a voltage. Reversing the motion reverses the voltage. A stationary magnet creates no changing flux and no induced voltage.",
                       "Decorative napkin folding uses a sequence of folds to make a table ornament. This source describes the folding order and has no physics content."]
            for index, source in enumerate(sources):
                started = time.monotonic()
                receipt = access.accept("owner", "context-live-qualification-"+str(index), {"type": "text", "text": source})
                assert access.accept("owner", "context-live-qualification-"+str(index), {"type": "text", "text": source})["job_id"] == receipt["job_id"]
                deadline = time.monotonic()+240
                while time.monotonic() < deadline:
                    engine.once()
                    row = state.one("SELECT * FROM jobs WHERE id=?", (receipt["job_id"],))
                    if row["state"] in ("COMPLETED", "FAILED", "WAITING_CONFIGURATION"):
                        break
                    time.sleep(.2)
                record = json.loads(row["record"])
                if row["state"] != "COMPLETED":
                    raise AssertionError("Live job failed: "+str(record.get("public_error", {}).get("code", row["state"])))
                path = record["committed_path"]
                text = vault.read(path)
                assert path.startswith("root/crusher/") and "## Кратко" in text and "## Основной материал" in text and "## Связи" in text
                assert "PRIVATE_GRAPH_CANARY" not in text and "context_snapshot" not in record and record["results"] == {}
                assert record["context_receipt"]["template_sha256"] == sha_bytes(DEFAULT_TEMPLATE.encode())
                assert all(sha_bytes(vault.read(path).encode()) == digest for path, digest in before.items())
                report["cases"].append({"source": "known physics" if index == 0 else "unindexed craft", "state": row["state"],
                    "path": path, "sha256": sha_bytes(text.encode()), "branch_link": "[[Electromagnetic induction]]" in text,
                    "pool_link": "[[pool]]" in text, "seconds": round(time.monotonic()-started, 3),
                    "stages": [v["state"] for v in record["transitions"]]})
                assert ("[[Electromagnetic induction]]" if index == 0 else "[[pool]]") in text
                print(json.dumps({"completed": index+1, "seconds": report["cases"][-1]["seconds"]}), flush=True)
            assert len([path for path, _ in vault.files() if path.startswith("root/crusher/")]) == 2
            report.update(status="PASS", provider_targets=provider.targets, external_calls=external_calls,
                          graph_canary_transmitted=False, parent_notes_unchanged=True, retained_template_text=False)
            args.output.write_text(json.dumps(report, indent=2)+"\n")
            print("PASS: actual extraction, understanding, context-indexing, typed generation, template, branch/pool, idempotency and cleanup.", flush=True)
        finally:
            provider.close()
            worker.close()
            state.close()


if __name__ == "__main__":
    main()
