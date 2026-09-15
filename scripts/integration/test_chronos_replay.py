"""Exercise the patched Chronos image against a new, isolated disposable database."""
import json
import secrets
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POSTGRES = "postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"


def main():
    run_id = uuid.uuid4().hex[:12]
    name = "mastermind-chronos-replay-" + run_id
    private = ROOT / ".local/chronos-replay" / run_id
    output = ROOT / "artifacts/chronos-replay" / run_id
    private.mkdir(parents=True)
    output.mkdir(parents=True)
    lock = json.loads((ROOT / "docs/compatibility.json").read_text())["services"]["chronos"]
    source = ROOT / ".local/patch-replay" / ("chronos-" + lock["patch_sha256"][:16])
    password = secrets.token_urlsafe(32)
    (private / "db.env").write_text("POSTGRES_DB=chronos_test\nPOSTGRES_USER=qualification\nPOSTGRES_PASSWORD=" + password + "\n", encoding="utf-8")
    (private / "test.env").write_text("TEST_DATABASE_URL=postgresql://qualification:" + password + "@db:5432/chronos_test\n", encoding="utf-8")
    identity = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", "mastermind-chronos:integration"], text=True).strip()
    subprocess.run(["docker", "image", "tag", identity, name + ":base"], check=True)
    (private / "Dockerfile").write_text("FROM " + name + ":base\nUSER root\nCOPY requirements-dev.lock /tmp/requirements-dev.lock\nRUN pip install --no-cache-dir --require-hashes -r /tmp/requirements-dev.lock\nUSER 10001:10001\n", encoding="utf-8")
    (private / "requirements-dev.lock").write_bytes((source / "requirements-dev.lock").read_bytes())
    result = {"image_id": identity, "patch_sha256": lock["patch_sha256"],
              "isolation": "new internal network and new database volume", "steps": []}
    def run(step, command, timeout=900):
        started = time.monotonic()
        with (output / (step + ".log")).open("wb") as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        result["steps"].append({"name": step, "exit_code": completed.returncode, "seconds": round(time.monotonic() - started, 3)})
        if completed.returncode:
            raise RuntimeError(step + " failed")
        print("PASS " + step, flush=True)
    try:
        run("build-test-image", ["docker", "build", "-t", name + ":tests", str(private)])
        run("network", ["docker", "network", "create", "--internal", "--label", "mastermind.purpose=chronos-tests", name])
        run("volume", ["docker", "volume", "create", "--label", "mastermind.purpose=chronos-tests", name])
        run("database", ["docker", "run", "-d", "--name", name + "-db", "--network", name, "--network-alias", "db",
            "--env-file", str(private / "db.env"), "--mount", "type=volume,source=" + name + ",target=/var/lib/postgresql/data",
            "--memory", "512m", "--cpus", "1", POSTGRES])
        for _ in range(60):
            if subprocess.run(["docker", "exec", name + "-db", "pg_isready", "-U", "qualification", "-d", "chronos_test"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("New disposable database did not become ready")
        run("pytest", ["docker", "run", "--rm", "--name", name + "-tests", "--network", name, "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--memory", "2g", "--cpus", "2", "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m",
            "--tmpfs", "/app/data:rw,nosuid,nodev,size=128m,uid=10001,gid=10001,mode=700", "--env-file", str(private / "test.env"),
            "--mount", "type=bind,source=" + str(source) + ",target=/suite,readonly", "-e", "PYTHONPATH=/app", "-w", "/app",
            "--entrypoint", "python", name + ":tests", "-m", "pytest", "/suite/tests", "-q", "-p", "no:cacheprovider"], timeout=1800)
        result["status"] = "PASS"
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        result.update(status="FAIL", reason=str(error))
    finally:
        # Names are generated here, never read from caller input or an existing deployment.
        subprocess.run(["docker", "rm", "-f", name + "-tests", name + "-db"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(result["status"] + ": " + str(output), flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
