"""Kill only the disposable host Updater after a signed fault candidate writes."""
import json
import socket
import subprocess
import time
from pathlib import Path

assert socket.gethostname() == "mastermind-qualification-host"
version = "0.0.5"
manifest = Path("/opt/qualification/release-assets/psewdon1m-exocortex/mastermind/releases/download/mastermind-v0.0.5/mastermind-release.json")
image = json.loads(manifest.read_text())["mastermind"]["components"]["core"]
deadline = time.monotonic() + 300
while time.monotonic() < deadline:
    for path in Path("/var/lib/updater/jobs").glob("*.json"):
        job = json.loads(path.read_text())
        if job.get("service") != "mastermind" or job.get("head_id") != "mastermind" or job.get("version") != version or job.get("state") != "APPLYING" or job.get("mutation_started") is not True:
            continue
        ids = subprocess.check_output(["docker", "ps", "--filter", "label=com.docker.compose.project=mastermind", "--filter", "label=com.docker.compose.oneoff=True", "-q"], text=True).split()
        for identifier in ids:
            actual = subprocess.check_output(["docker", "inspect", "--format", "{{.Config.Image}}", identifier], text=True).strip()
            if actual != image:
                continue
            check = subprocess.run(["docker", "exec", identifier, "python", "-c", "from pathlib import Path; assert Path('/data/vault/current/Qualification rejected candidate.md').is_file()"], capture_output=True)
            if check.returncode:
                continue
            pid = subprocess.check_output(["systemctl", "show", "--property=MainPID", "--value", "updater"], text=True).strip()
            subprocess.run(["systemctl", "kill", "--kill-whom=main", "--signal=SIGKILL", "updater"], check=True)
            print(json.dumps({"status": "INJECTED", "version": version, "job_id": job["id"], "previous_pid": pid, "candidate_write_observed": True}), flush=True)
            while time.monotonic() < deadline:
                result = json.loads(path.read_text())
                if result["state"] in ("ROLLED_BACK", "ROLLBACK_FAILED", "COMPLETED", "FAILED"):
                    print(json.dumps({"state": result["state"], "job_id": result["id"], "message": result.get("message")}), flush=True)
                    if result["state"] == "ROLLED_BACK":
                        raise SystemExit(0)
                    if result.get("recovery_pending") is not True:
                        raise SystemExit(1)
                time.sleep(1)
            raise SystemExit("Recovery deadline")
    time.sleep(0.25)
raise SystemExit("The exact owned fault-candidate mutation was not observed; nothing killed")
