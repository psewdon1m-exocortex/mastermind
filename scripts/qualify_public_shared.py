"""Real Core and Chromium qualification of both public note presentations.

Only synthetic, marked, disposable data. No owner Vault or external service.
"""
import json
import socket
import subprocess
import sys
import threading
import time
import uuid
from urllib.error import HTTPError
from urllib.request import urlopen
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mastermind.api import create_app
from mastermind.config import Config
from mastermind.fs import atomic_write


def main():
    work = ROOT / ".local/qualification" / ("public-shared-" + uuid.uuid4().hex[:12])
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    config = Config(work / "data", runtime_mode="offline", test_mode=True,
                    secret_directory=work / "secrets", secret_backend="development-files",
                    public_url="http://127.0.0.1:" + str(sock.getsockname()[1]))
    secrets = {"bootstrap_access_key": "synthetic-public-shared-key", "bridge_token": "synthetic-bridge-only",
               "share_pepper_v1": "synthetic-public-shared-pepper"}
    for name, value in secrets.items():
        atomic_write(config.secret_directory / name, value.encode())
    source = ("---\nprivate: NEVER_DISCLOSE_FRONTMATTER\n---\n\n# Fixture knowledge\n\n"
              "Knowledge architecture organizes facts into meaningful branches.\n\n"
              "@NEVER_DISCLOSE_TARGET\n\n## Observations\n\n"
              "- A shared note stays connected to its source.\n- Changes are checked before saving.\n\n"
              "```python\nprint('Visible example')\n```\n")
    for mode in ("notes",):
        atomic_write(config.vault / mode / "Fixture knowledge.md", source.encode())
        atomic_write(config.vault / mode / "Empty note.md", b"")
        atomic_write(config.vault / mode / ("A long note title " * 6 + ".md"),
                     ("A long paragraph for scrolling, line wrapping and reading. " * 10 + "\n\n").encode() * 60)
    app = create_app(config)
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        if not server.started:
            raise RuntimeError("Synthetic Core did not start")
        while time.monotonic() < deadline:
            try:
                with urlopen(config.public_url + "/readyz", timeout=2) as response:
                    if response.status == 200:
                        break
            except HTTPError:
                pass
            time.sleep(.1)
        else:
            raise RuntimeError("Synthetic canonical data did not become ready: " + str(app.state.service.failure))
        fixture = {"fixture": "mastermind-public-shared/v1", "origin": config.public_url, "source": source, "modes": {}}
        for mode in ("public", "legacy"):
            note = "notes/Fixture knowledge.md"
            shared = app.state.service.shared
            fixture["modes"][mode] = {
                "path": note,
                "edit": shared.create(note, permission="edit", password="1", expires_at=int(time.time())+3600),
                "view": shared.create(note, permission="view"),
                "empty": shared.create("notes/Empty note.md"),
                "long": shared.create("notes/" + "A long note title "*6 + ".md"),
            }
        atomic_write(work / "fixture.json", json.dumps(fixture).encode())
        subprocess.run(["node", "scripts/probe_public_shared.cjs", str(work)], cwd=ROOT, check=True, timeout=240)
        for mode in fixture["modes"]:
            result = (config.vault / fixture["modes"][mode]["path"]).read_text("utf-8")
            assert "NEVER_DISCLOSE_FRONTMATTER" in result and "@NEVER_DISCLOSE_TARGET" in result
            assert "Merged browser draft" in result and "Owner concurrent change" in result
        print("PASS canonical files retain protected data and both explicitly merged edits", flush=True)
    finally:
        server.should_exit = True
        thread.join(timeout=30)
        sock.close()
        for name in secrets:
            (config.secret_directory / name).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
