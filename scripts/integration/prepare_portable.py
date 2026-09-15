"""Download a real portable export and verify bytes before standard Obsidian opens it."""
import hashlib
import json
import secrets
import zipfile
from pathlib import Path

import httpx

from mastermind.fs import safe_relative
from mastermind.portable import HISTORY, MANIFEST

root = Path(__file__).resolve().parents[2]
origin = "http://localhost:18390"
folder = root / ".local/portable-qualification" / secrets.token_hex(8)
vault = folder / "vault"
vault.mkdir(parents=True)
with httpx.Client(base_url=origin, timeout=180, trust_env=False) as client:
    login = client.post("/api/auth/login", json={"access_key": (root / ".local/secrets/core/bootstrap_access_key").read_text("utf-8")},
                        headers={"Origin": origin})
    login.raise_for_status()
    # Production uses HTTPS; the local loopback fixture still uses secure cookies explicitly.
    cookie = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
    headers = {"Origin": origin, "X-CSRF-Token": login.json()["csrf"], "Cookie": cookie}
    client.headers.update(headers)
    for path, text in {"Portable target.md": "# Portable target\n\nOpened from an @ reference.\n",
                       "Portable removed.md": "A historical name.\n",
                       "Portable sample.md": "# Portable sample\n\n@Portable target\n\n[[Portable target]]\n\n"
                       "@Portable removed\n\n@chronos: portable-unavailable\n\n@saturn: root/portable-unavailable\n"}.items():
        previous = client.get("/api/note", params={"path": path})
        if previous.status_code == 200:
            result = client.put("/api/note", json={"path": path, "text": text, "expected_sha256": previous.json()["sha256"]})
        else:
            result = client.post("/api/notes", json={"path": path, "text": text})
        result.raise_for_status()
    removed = client.get("/api/note", params={"path": "Portable removed.md"}).json()
    client.request("DELETE", "/api/note", json={"path": removed["path"], "expected_sha256": removed["sha256"]}).raise_for_status()
    archive_path = folder / "vault.zip"
    with client.stream("POST", "/api/exports/portable") as response, archive_path.open("xb") as out:
        response.raise_for_status()
        digest, length = hashlib.sha256(), 0
        for chunk in response.iter_bytes(1024**2):
            length += len(chunk)
            assert length <= 8*1024**3
            out.write(chunk)
            digest.update(chunk)
        assert digest.hexdigest() == response.headers["x-content-sha256"]
        assert length == int(response.headers["content-length"])
with zipfile.ZipFile(archive_path) as archive:
    manifest = json.loads(archive.read(MANIFEST))
    originals = {item["path"]: item for item in manifest["original_files"]}
    for item in archive.infolist():
        relative = safe_relative(item.filename.rstrip("/"))
        destination = vault / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        with archive.open(item) as source, destination.open("xb") as target:
            while chunk := source.read(1024**2):
                target.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if relative in originals:
            assert (size, digest.hexdigest()) == (originals[relative]["size"], originals[relative]["sha256"])
        else:
            assert relative in (HISTORY, MANIFEST)
    assert "Portable removed" in json.loads(archive.read(HISTORY))["internal"]
(folder / "home").mkdir()
(root / ".local/portable.env").write_text("PORTABLE_FIXTURE_DIR=" + folder.as_posix() + "\n", "utf-8")
(root / "artifacts/portable-export-live.json").write_text(json.dumps({"byte_equality": "PASS", "original_files": len(originals),
    "generation": manifest["generation"], "archive_bytes": length, "history": "PASS"}, indent=2) + "\n", "utf-8")
print(f"PASS real portable export: {len(originals)} unchanged files, {length} bytes, history snapshot present")
