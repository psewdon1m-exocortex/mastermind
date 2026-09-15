"""Configure only the freshly imported, task-owned Ubuntu WSL test distribution."""
import json
import os
import shutil
from pathlib import Path

assert os.geteuid() == 0 and os.environ.get("WSL_DISTRO_NAME") == "mastermind-qualification"
source = Path(__file__).resolve().parents[2] / ".local/qualification-docker"
target = Path("/etc/docker/qualification-tls")
target.mkdir(mode=0o700, parents=True, exist_ok=True)
for name in ("ca.pem", "server-cert.pem", "server-key.pem"):
    shutil.copyfile(source / name, target / name)
    (target / name).chmod(0o600)
Path("/etc/wsl.conf").write_text("[boot]\nsystemd=true\n[network]\nhostname=mastermind-qualification-wsl\n", encoding="utf-8")
Path("/etc/docker/daemon.json").write_text(json.dumps({
    "hosts": ["unix:///var/run/docker.sock", "tcp://127.0.0.1:2376"],
    "tls": True, "tlsverify": True, "tlscacert": str(target / "ca.pem"),
    "tlscert": str(target / "server-cert.pem"), "tlskey": str(target / "server-key.pem"),
    "storage-driver": "overlay2", "log-driver": "local",
    "default-address-pools": [{"base": "10.246.0.0/16", "size": 24}],
}), encoding="utf-8")
override = Path("/etc/systemd/system/docker.service.d")
override.mkdir(parents=True, exist_ok=True)
(override / "qualification.conf").write_text("[Service]\nExecStart=\nExecStart=/usr/bin/dockerd --containerd=/run/containerd/containerd.sock\n", encoding="utf-8")
print("Prepared dedicated WSL Docker on loopback with mutual TLS; restart only this task's distribution")
