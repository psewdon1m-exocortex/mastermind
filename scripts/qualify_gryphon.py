"""Run real Mastermind/Gryphon with synthetic Telegram delivery and browser checks."""
import argparse
import os
import secrets
import shutil
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-image", default="mastermind-core:development")
    parser.add_argument("--gryphon", type=Path, default=ROOT.parent / "gryphon")
    parser.add_argument("--node-image", default="node:24-bookworm-slim")
    args = parser.parse_args()
    gateway = args.gryphon.resolve()
    if not (gateway / "dist/gateway.js").is_file():
        raise SystemExit("Build the local Gryphon checkout with pnpm build first.")
    identifier = "mastermind-gryphon-" + uuid.uuid4().hex[:10]
    work = ROOT / ".local" / identifier
    source, credentials = work / "source", work / "credentials"
    credentials.mkdir(parents=True)
    (work / "data").mkdir()
    for name in ("bootstrap_access_key", "mastermind.token"):
        (credentials / name).write_text(secrets.token_urlsafe(48), encoding="ascii")
    # Bind only executable source and synthetic credentials, never the owner's Vault.
    shutil.copytree(ROOT / "src", source / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (source / "scripts/integration").mkdir(parents=True)
    for name in ("gryphon_core.py", "gryphon_gateway.mjs"):
        shutil.copyfile(ROOT / "scripts/integration" / name, source / "scripts/integration" / name)
    if os.name == "posix" and os.getuid() == 0:
        for path in (work, *work.rglob("*")):
            os.chown(path, 10001, 10001)
    started, network, volume = [], False, False
    try:
        run("docker", "network", "create", identifier)
        network = True
        run("docker", "volume", "create", identifier)
        volume = True
        run("docker", "run", "--rm", "--network", "none", "--user", "0:0", "--mount",
            f"type=volume,source={identifier},target=/ipc", args.node_image, "node", "-e",
            "const fs=require('fs');fs.chownSync('/ipc',10001,10001);fs.chmodSync('/ipc',0o770)")
        common = ["--user", "10001:10001", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                  "--network", identifier, "--cpus", "2", "--pids-limit", "128",
                  "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m,mode=1777", "-e", "MASTERMIND_GRYPHON_FIXTURE=isolated-synthetic-v1"]
        gateway_name = identifier + "-gateway"
        run("docker", "run", "-d", "--name", gateway_name, *common, "--memory", "256m",
            "-p", "127.0.0.1:18497:18497", "--mount", f"type=volume,source={identifier},target=/run/gryphon",
            "--mount", f"type=bind,source={credentials / 'mastermind.token'},target=/clients/mastermind.token,readonly",
            "--mount", f"type=bind,source={gateway / 'dist'},target=/gryphon/dist,readonly",
            "--mount", f"type=bind,source={gateway / 'package.json'},target=/gryphon/package.json,readonly",
            "--mount", f"type=bind,source={source / 'scripts/integration/gryphon_gateway.mjs'},target=/fixture.mjs,readonly",
            args.node_image, "node", "/fixture.mjs")
        started.append(gateway_name)
        core = identifier + "-core"
        run("docker", "run", "-d", "--name", core, *common, "--memory", "1g", "--network-alias", "mastermind",
            "-p", "127.0.0.1:18496:18390", "--mount", f"type=volume,source={identifier},target=/run/gryphon,readonly",
            "--mount", f"type=bind,source={source},target=/suite,readonly",
            "--mount", f"type=bind,source={credentials},target=/credentials,readonly",
            "--mount", f"type=bind,source={work / 'data'},target=/fixture-data",
            "-e", "PYTHONPATH=/suite/src", "--entrypoint", "python", args.core_image,
            "/suite/scripts/integration/gryphon_core.py")
        started.append(core)
        run("node", "scripts/probe_gryphon.cjs", env={**os.environ, "MASTERMIND_GRYPHON_FIXTURE_DIR": str(credentials)})
    finally:
        for name in reversed(started):
            run("docker", "stop", "-t", "5", name)
            run("docker", "rm", name)
        if network:
            run("docker", "network", "rm", identifier)
        if volume:
            run("docker", "volume", "rm", identifier)
        for path in credentials.iterdir():
            path.unlink()


if __name__ == "__main__":
    main()
