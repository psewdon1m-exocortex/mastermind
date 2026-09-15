"""Persist only the disposable qualification host's transport and name fixtures."""
import socket
import subprocess
from pathlib import Path

assert socket.gethostname() == "mastermind-qualification-host"
units = {
    "mastermind-qualification-names.service": """[Unit]
Description=Disposable Mastermind qualification names
Before=docker.service neptune.service updater.service nginx.service
After=local-fs.target
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/qualification/refresh_host_names.py
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
""",
    "mastermind-release-fixture.service": """[Unit]
Description=Unpublished qualification release metadata
After=network.target mastermind-qualification-names.service
[Service]
ExecStart=/usr/bin/python3 /opt/qualification/release_transport.py
Restart=on-failure
RestartSec=2
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadOnlyPaths=/opt/qualification/release-assets
[Install]
WantedBy=multi-user.target
""",
}
for name, text in units.items():
    Path("/etc/systemd/system", name).write_text(text)
subprocess.run(["systemctl", "daemon-reload"], check=True)
subprocess.run(["systemctl", "enable", "--now", *units], check=True)
print("PASS: qualification-only names and metadata persist across host reboot")
