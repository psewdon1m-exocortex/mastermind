"""Start a credential-free Obsidian fixture, run native probes, then remove its container.

Requires Docker, a built Runtime image, bridge/dist and repository Node dependencies.
Never mounts a service Vault or publishes the editor itself.
"""
import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".local/native-reference-qualification"
CONTAINER = "mastermind-native-reference-qualification"


def run(*args, **kwargs):
    return subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="mastermind-runtime:development")
    args = parser.parse_args()
    marker = WORK / "synthetic-fixture.json"
    if WORK.exists() and not marker.exists():
        raise SystemExit("The qualification directory already exists without its ownership marker.")
    WORK.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"fixture": "mastermind-native-references/v1"}), encoding="utf-8")
    vault = WORK / "vault"
    plugin = vault / ".obsidian/plugins/mastermind-bridge"
    plugin.mkdir(parents=True, exist_ok=True)
    for filename in ("main.js", "manifest.json", "styles.css"):
        shutil.copyfile(ROOT / "bridge/dist" / filename, plugin / filename)
    defaults = {
        "Source.md": "# Source\n",
        "Native.md": "# Native\n",
        "Excluded.md": "# Excluded\n",
        ".obsidian/app.json": json.dumps({"alwaysUpdateLinks": True}),
        ".obsidian/community-plugins.json": json.dumps(["mastermind-bridge"]),
        ".obsidian/core-plugins.json": json.dumps(["file-explorer", "graph", "backlink", "outgoing-link", "command-palette"]),
        ".obsidian/plugins/mastermind-bridge/portable-history.json": json.dumps({
            "format": "mastermind-portable-history/v1", "internal": ["Deleted"], "saturn": ["root/spec.pdf"]}),
    }
    if not (vault / "Renamed.md").exists():
        defaults["Target.md"] = "# Target\n"
    for filename, content in defaults.items():
        path = vault / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    # On Linux the nonroot Runtime user must own only this synthetic fixture.
    if os.name == "posix" and os.getuid() == 0:
        for directory, children, files in os.walk(WORK):
            os.chown(directory, 10001, 10001)
            for filename in files:
                os.chown(Path(directory) / filename, 10001, 10001)
    started = False
    try:
        run("docker", "run", "-d", "--name", CONTAINER, "--label", "mastermind.fixture=native-references",
            "--user", "10001:10001", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "3g", "--cpus", "2", "--pids-limit", "256", "--shm-size", "256m",
            "--tmpfs", "/tmp:rw,nosuid,size=256m", "-e", "HOME=/qualification/home", "-e", "DISPLAY=:1",
            "-p", "127.0.0.1:19393:9223", "--mount", f"type=bind,source={WORK},target=/qualification",
            "--mount", f"type=bind,source={ROOT / 'scripts/integration/native_reference_runtime.py'},target=/runner.py,readonly",
            "--entrypoint", "python3", args.image, "/runner.py")
        started = True
        for _ in range(60):
            try:
                with urllib.request.urlopen("http://127.0.0.1:19393/json/version", timeout=1) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                time.sleep(.5)
        else:
            raise RuntimeError("Disposable native editor did not start")
        run("node", "scripts/probe_native_references.cjs")
        run("node", "scripts/probe_native_reference_scaling.cjs")
    finally:
        if started:
            run("docker", "stop", "-t", "5", CONTAINER)
            run("docker", "rm", CONTAINER)


if __name__ == "__main__":
    main()
