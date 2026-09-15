"""Actual 8 GiB boundary, cancellation and retention on the disposable host only."""
import argparse
import hashlib
import http.client
import json
import os
import resource
import secrets
import socket
import subprocess
import threading
import time
from pathlib import Path


class LocalConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(180)
        self.sock.connect("/run/exocortex/updater.sock")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Small transport smoke; never qualifies the 8 GiB gate")
    args = parser.parse_args()
    assert socket.gethostname() == "mastermind-qualification-host" and os.geteuid() == 0
    token = Path("/opt/exocortex/mastermind/secrets/core/updater_token").read_text()
    root = "/v1/heads/mastermind/backup-spools"
    directory = Path("/var/lib/updater/backups/spools")
    owned, steps = {}, []
    original = {p.name: (p / "metadata.json").read_bytes() for p in directory.iterdir()}
    def call(method, route, *, data=None, length=None, chunks=None, credential=token):
        connection = LocalConnection("updater.local")
        try:
            body = json.dumps(data).encode() if data is not None else b""
            headers = {"X-Updater-Token": credential, "Content-Length": str(len(body) if length is None else length),
                       "Content-Type": "application/json" if data is not None else "application/zip"}
            connection.putrequest(method, route)
            for key, value in headers.items():
                connection.putheader(key, value)
            connection.endheaders()
            if chunks is None:
                connection.send(body)
            else:
                for block in chunks:
                    connection.send(block)
            response = connection.getresponse()
            content = response.read(65537)
            assert len(content) <= 65536
            return response.status, json.loads(content) if content else None
        finally:
            connection.close()
    def check(name, condition, **evidence):
        assert condition, name
        record = {"name": name, "status": "PASS", **evidence}
        steps.append(record)
        print(json.dumps(record), flush=True)
    def create(size, digest):
        request = "boundary-" + secrets.token_hex(16)
        data = {"request_id": request, "filename": "mastermind-backup.zip", "size": size, "sha256": digest}
        status, spool = call("POST", root, data=data)
        assert status == 201
        owned[spool["spool_id"]] = request
        assert call("POST", root, data=data)[1]["spool_id"] == spool["spool_id"]
        return spool
    limit = 4 * 1024**2 if args.smoke else 8 * 1024**3
    oversized = {"request_id": "boundary-" + secrets.token_hex(16), "filename": "mastermind-backup.zip", "size": 8 * 1024**3 + 1, "sha256": "0" * 64}
    check("8 GiB plus one rejected before allocation", call("POST", root, data=oversized)[0] == 400)
    denied, _ = call("POST", root, data=oversized, credential="invalid-qualification-token")
    assert denied == 401, "Forged credential response: " + str(denied)
    check("forged credential denied", True)
    check("foreign head denied", call("POST", root.replace("mastermind", "foreign"), data=oversized)[0] in (401, 403))
    block = secrets.token_bytes(1024**2)
    digest = hashlib.sha256()
    for _ in range(limit // len(block)):
        digest.update(block)
    spool = create(limit, digest.hexdigest())
    pid = int(subprocess.check_output(["systemctl", "show", "updater.service", "--property=MainPID", "--value"], text=True).strip())
    def rss():
        status = Path(f"/proc/{pid}/status").read_text()
        return next(int(line.split()[1]) * 1024 for line in status.splitlines() if line.startswith("VmRSS:"))
    samples, stop = [rss()], threading.Event()
    def sample():
        while not stop.wait(0.1):
            samples.append(rss())
    observer = threading.Thread(target=sample, daemon=True)
    observer.start()
    started = time.monotonic()
    try:
        status, _ = call("PUT", root + "/" + spool["spool_id"] + "/content", length=limit,
                         chunks=(block for _ in range(limit // len(block))))
        assert status == 204
        status, sealed = call("POST", root + "/" + spool["spool_id"] + "/seal")
        check("actual bytes streamed and sealed", status == 200 and sealed["state"] == "SEALED" and sealed["sha256"] == digest.hexdigest(),
              bytes=limit, sha256=digest.hexdigest(), seconds=round(time.monotonic() - started, 3))
    finally:
        stop.set()
        observer.join()
    actual = directory / spool["spool_id"] / "mastermind-backup.zip"
    check("bounded memory and exact disk extent", actual.stat().st_size == limit and actual.stat().st_mode & 0o777 == 0o400
          and samples and max(samples) < 512 * 1024**2, updater_peak_rss=max(samples, default=0), client_peak_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
          disk_allocated_bytes=actual.stat().st_blocks * 512)
    data = {"request_id": spool["request_id"], "filename": "mastermind-backup.zip", "size": limit, "sha256": "0" * 64}
    check("request reuse cannot substitute content", call("POST", root, data=data)[0] == 400)
    incomplete = create(64 * 1024**2, "0" * 64)
    connection = LocalConnection("updater.local")
    connection.putrequest("PUT", root + "/" + incomplete["spool_id"] + "/content")
    connection.putheader("X-Updater-Token", token)
    connection.putheader("Content-Length", str(incomplete["size"]))
    connection.endheaders()
    for _ in range(8):
        connection.send(block)
    connection.close()
    time.sleep(1)
    check("cancelled partial upload cannot seal", call("POST", root + "/" + incomplete["spool_id"] + "/seal")[0] == 400)
    wrong = create(len(block), "0" * 64)
    assert call("PUT", root + "/" + wrong["spool_id"] + "/content", length=len(block), chunks=[block])[0] == 204
    check("wrong content hash cannot seal", call("POST", root + "/" + wrong["spool_id"] + "/seal")[0] == 400)
    # Advance only the expiry of unclaimed synthetic spools created by this run.
    # The actual daemon's periodic lifecycle must perform cleanup itself.
    for identifier, request in owned.items():
        path = directory / identifier / "metadata.json"
        assert path.resolve().is_relative_to(directory.resolve()) and not path.is_symlink()
        metadata = json.loads(path.read_text())
        assert metadata["request_id"] == request and metadata["head_id"] == "mastermind" and not metadata.get("claimed_by")
        metadata["expires_at"] = "2000-01-01T00:00:00Z"
        temporary = path.with_name("qualification-expiry.tmp")
        temporary.write_text(json.dumps(metadata))
        temporary.chmod(0o600)
        temporary.replace(path)
    until = time.monotonic() + 90
    while any((directory / identifier).exists() for identifier in owned) and time.monotonic() < until:
        time.sleep(1)
    check("actual periodic expiry removed only owned fixture spools", all(not (directory / identifier).exists() for identifier in owned)
          and all((directory / identifier / "metadata.json").read_bytes() == body for identifier, body in original.items()))
    status = "SMOKE_PASS" if args.smoke else "PASS"
    result = {"status": status, "scope": "opaque spool transport, not a logical archive Apply", "steps": steps}
    filename = "host-spool-smoke.json" if args.smoke else "host-spool-boundary.json"
    Path("/opt/qualification", filename).write_text(json.dumps(result, indent=2) + "\n")
    print(status + ": actual host spool transport and lifecycle; no Apply submitted", flush=True)


if __name__ == "__main__":
    main()
