"""Exercise recommendations in a synthetic native Obsidian and real local E5 fixture."""
import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def wait_url(url, seconds=90):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                value = json.load(response)
                if "search" not in value or value["ready"] and value["search"]["status"] == "READY":
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(.5)
    raise RuntimeError("Fixture did not become ready: " + url)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-image", default="mastermind-runtime:development")
    parser.add_argument("--worker-image", default="mastermind-worker:context-indexing")
    args = parser.parse_args()
    identifier = "mastermind-related-" + uuid.uuid4().hex[:10]
    work = ROOT / ".local" / identifier
    work.mkdir(parents=True)
    (work / "fixture.json").write_text(json.dumps({"fixture": "mastermind-related-notes/v1"}))
    vault = work / "core/vault/current"
    plugin = vault / ".obsidian/plugins/mastermind-bridge"
    plugin.mkdir(parents=True)
    for name in ("main.js", "manifest.json", "styles.css"):
        shutil.copyfile(ROOT / "bridge/dist" / name, plugin / name)
    notes = {"root.md": "[[Aircraft designers]]\n[[Composite materials]]\n[[Garden]]",
             "Draft.md": "# Working note\n\nAircraft structures and airplane wing materials.",
             "Aircraft designers.md": "Aircraft designers such as Andrei Tupolev and Sergei Ilyushin develop aerodynamic structures and airplane wing designs.",
             "Composite materials.md": "Carbon fibre composites and aluminium alloys are used in aircraft wings. These materials reduce airplane weight and improve structural strength.",
             "Garden.md": "Garden soil irrigation feeds flowers and plants. Watering vegetables and compost improve soil fertility.",
             "Other.md": "Photosynthesis converts sunlight into chemical energy in green leaves."}
    for name, text in notes.items():
        (vault / name).write_text(text, encoding="utf-8")
    (vault / ".obsidian/app.json").write_text(json.dumps({"alwaysUpdateLinks": True}))
    (vault / ".obsidian/community-plugins.json").write_text(json.dumps(["mastermind-bridge"]))
    (vault / ".obsidian/core-plugins.json").write_text(json.dumps(["file-explorer", "command-palette", "graph"]))
    secrets = work / "secrets"
    secrets.mkdir()
    for name in ("bootstrap_access_key", "bridge_token"):
        (secrets / name).write_text("synthetic-related-" + name)
    if os.name == "posix" and os.getuid() == 0:
        for path in [work, *work.rglob("*")]:
            os.chown(path, 10001, 10001)
    started = []
    network = False
    try:
        run("docker", "network", "create", identifier)
        network = True
        common = ["--user", "10001:10001", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                  "--network", identifier, "--cpus", "2", "--tmpfs", "/tmp:rw,nosuid,size=256m",
                  "--mount", f"type=bind,source={work},target=/qualification",
                  "--mount", f"type=bind,source={ROOT},target=/suite,readonly"]
        core = identifier + "-core"
        run("docker", "run", "-d", "--name", core, *common, "--memory", "2g", "--network-alias", "related-core",
            "-p", "127.0.0.1:18495:18495", "-e", "PYTHONPATH=/suite/src:/suite/scripts",
            "--entrypoint", "python", args.worker_image, "/suite/scripts/integration/related_core.py")
        started.append(core)
        wait_url("http://127.0.0.1:18495/fixture/status")
        runtime = identifier + "-runtime"
        run("docker", "run", "-d", "--name", runtime, *common, "--memory", "3g", "--shm-size", "256m",
            "-e", "HOME=/qualification/home", "-e", "DISPLAY=:1", "-p", "127.0.0.1:19394:9223",
            "--entrypoint", "python3", args.runtime_image, "/suite/scripts/integration/native_reference_runtime.py", "--related")
        started.append(runtime)
        wait_url("http://127.0.0.1:19394/json/version")
        run("node", "scripts/probe_related_notes.cjs", str(work))
    finally:
        for name in reversed(started):
            run("docker", "stop", "-t", "5", name)
            run("docker", "rm", name)
        if network:
            run("docker", "network", "rm", identifier)


if __name__ == "__main__":
    main()
