"""Test-only standard Obsidian session: no Core, no supervisor, no host credentials."""
import json
import os
import subprocess
import time
from pathlib import Path

home = Path("/copy/home")
assert not any(key.startswith("MASTERMIND_") for key in os.environ)
profile = home / ".config/obsidian"
profile.mkdir(parents=True, exist_ok=True)
(profile / "obsidian.json").write_text(json.dumps({"vaults": {"portable": {"path": "/copy/vault", "open": True,
    "ts": int(time.time()*1000)}}, "updateDisabled": True}))
password = "portable-fixture-only"
subprocess.run(["kasmvncpasswd", "-u", "portable", "-r", "-w", str(home / ".kasmpasswd")],
               input=(password + "\n" + password + "\n").encode(), check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
display = subprocess.Popen(["Xkasmvnc", ":1", "-geometry", "1440x900", "-depth", "24", "-nolisten", "tcp",
    "-httpd", "/usr/share/kasmvnc/www", "-websocketPort", "8090", "-interface", "0.0.0.0",
    "-KasmPasswordFile", str(home / ".kasmpasswd"), "-sslOnly", "0", "-AlwaysShared", "-SecurityTypes", "None",
    "-publicIP", "127.0.0.1", "-FrameRate", "30", "-RectThreads", "2"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(150):
    ready = subprocess.run(["xdpyinfo", "-display", ":1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if ready.returncode == 0:
        break
    time.sleep(.1)
else:
    raise RuntimeError("Portable display failed")
subprocess.Popen(["openbox"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
result = subprocess.run(["/opt/obsidian/obsidian", "--no-sandbox", "--disable-dev-shm-usage",
                         "--user-data-dir=" + str(profile)], check=False)
display.terminate()
raise SystemExit(result.returncode)
