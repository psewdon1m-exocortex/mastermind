"""Disposable native-reference qualification: synthetic Vault, no service credentials."""
import json
import os
import socket
import socketserver
import subprocess
import threading
import time
from pathlib import Path

home = Path("/qualification/home")
profile = home / ".config/obsidian"
profile.mkdir(parents=True, exist_ok=True)
(profile / "obsidian.json").write_text(json.dumps({"vaults": {"references": {
    "path": "/qualification/vault", "open": True, "ts": int(time.time()*1000)}}, "updateDisabled": True}))
assert not any(key.startswith("MASTERMIND_") for key in os.environ)


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        import select
        with socket.create_connection(("127.0.0.1", 9222)) as upstream:
            peers = {self.request: upstream, upstream: self.request}
            while True:
                readable, _, _ = select.select(list(peers), [], [], 60)
                if not readable:
                    return
                for peer in readable:
                    data = peer.recv(65536)
                    if not data:
                        return
                    peers[peer].sendall(data)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


server = Server(("0.0.0.0", 9223), Relay)
threading.Thread(target=server.serve_forever, daemon=True).start()
display = subprocess.Popen(["Xkasmvnc", ":1", "-geometry", "1440x1000", "-depth", "24",
    "-nolisten", "tcp", "-httpd", "/usr/share/kasmvnc/www", "-websocketPort", "8090",
    "-interface", "127.0.0.1", "-sslOnly", "0", "-AlwaysShared", "-SecurityTypes", "None"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(150):
        if subprocess.run(["xdpyinfo", "-display", ":1"], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, check=False).returncode == 0:
            break
        time.sleep(.1)
    else:
        raise RuntimeError("Qualification display failed")
    subprocess.Popen(["openbox"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result = subprocess.run(["/opt/obsidian/obsidian", "--no-sandbox", "--disable-dev-shm-usage",
        "--remote-debugging-port=9222", "--user-data-dir=" + str(profile)], check=False)
finally:
    server.shutdown()
    display.terminate()
raise SystemExit(result.returncode)
