"""Actual local Kernel/Volt/Saturn integration; generated identities only."""
import argparse
import hashlib
import json
import re
import ssl
import subprocess
import time
import uuid
from pathlib import Path

import httpx

from mastermind.integrations import Chronos
from mastermind.kernel import Kernel
from mastermind.secret_store import SHELL_BINDINGS, ShellSecrets

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / ".local/integration"
BASE = "https://127.0.0.1:19441"
TRUST = ssl.create_default_context(cafile=FIXTURE / "ca.crt")


def client(service):
    return httpx.Client(base_url=BASE, verify=TRUST, trust_env=False, timeout=30,
                        headers={"Host": service + ".mastermind.test", "Origin": "https://" + service + ".mastermind.test"})


def checked(response, *statuses):
    if response.status_code not in (statuses or (200,)):
        # Responses may contain credentials on success. Failure evidence exposes only route and HTTP status.
        raise AssertionError(f"{response.request.method} {response.request.url.path}: HTTP {response.status_code}")
    return response.json() if response.content else None


def save(name, value):
    path = FIXTURE / name
    path.write_text(value, encoding="utf-8", newline="\n")
    path.chmod(0o600)


def seed_register():
    kernel, volt = client("kernel"), client("volt")
    checked(kernel.post("/api/auth/login", json={"access_key": (FIXTURE / "kernel-access").read_text()}))
    checked(volt.post("/api/v1/session", json={"access_key": (FIXTURE / "volt-access").read_text()}))
    defaults = json.loads((ROOT / ".local/services/kernel/data/defaults/register.json").read_text())
    values = {item["key"]: "integration-unconfigured" for item in defaults}
    for service in ("kernel", "volt", "saturn", "chronos"):
        values.update({f"services.{service}.sni": service + ".mastermind.test", f"services.{service}.port": "443"})
    values.update({"services.saturn.paths.backup_ingest": "/api/v1/backups", "services.saturn.paths.sync": "/dav/",
                   "mastermind.crusher.text_model": "integration-text-model", "mastermind.crusher.video_model": "integration-video-model",
                   SHELL_BINDINGS["chronos_service_token"]: (FIXTURE / "chronos-reader.token").read_text(),
                   "repositories.chronos.url": "https://github.com/psewdon1m-exocortex/chronos",
                   "repositories.mastermind.url": "https://github.com/psewdon1m-exocortex/mastermind",
                   "repositories.updater.url": "https://github.com/psewdon1m-exocortex/updater",
                   "repositories.neptune.url": "https://github.com/psewdon1m-exocortex/neptune",
                   "services.chronos.health.path": "/api/health", "services.chronos.health.contract": "private-readiness",
                   "services.chronos.backup.saturn_slug": "chronos-integration"})
    # A real Mastermind consumer profile needs every shell binding, including
    # backup trust/recovery and Share HMAC identity. These are synthetic keys
    # generated outside the repository; only Volt references enter Register.
    for name, binding in SHELL_BINDINGS.items():
        values[binding] = (ROOT / ".local/secrets/core" / name).read_text(encoding="utf-8")
    entries = checked(volt.get("/api/v1/entries"))["entries"]
    bindings = []
    for offset in range(0, len(values), 5):
        chunk = list(values.items())[offset:offset + 5]
        title = "Mastermind integration fixture " + str(offset // 5)
        existing = next((entry for entry in entries if entry["title"] == title), None)
        if existing is None:
            existing = checked(volt.post("/api/v1/entries", json={"title": title,
                "fields": [{"key": key, "value": value, "visibility": "secret" if ".secrets." in key else "plain"}
                           for key, value in chunk]}), 201)
        else:
            existing = checked(volt.put("/api/v1/entries/" + existing["id"], json={"title": title,
                "expected_revision": existing["revision"],
                "fields": [{"key": key, "value": value, "visibility": "secret" if ".secrets." in key else "plain"}
                           for key, value in chunk]}))
        for position, (key, _) in enumerate(chunk, 1):
            bindings.append({"key": key, "value": f"volt://{existing['id']}/{position}", "description": "Isolated local integration"})
    checked(kernel.put("/api/register/entries", json={"entries": bindings}))
    machine = client("kernel")  # Separate machine principal; no operator cookie.
    consumer = Kernel(BASE, lambda: (FIXTURE / "kernel.token").read_text(), client=machine)
    key = SHELL_BINDINGS["ai_provider_key"]
    assert consumer.resolve([key])[key] == values[key]
    assert consumer.origin_for("saturn") == "https://saturn.mastermind.test:443"
    assert all("volt://" in item["value"] for item in checked(kernel.get("/api/register"))["entries"])
    consumer.close()
    print("PASS: actual Volt -> Kernel -> consumer; exact secret and service discovery, reference-only Register.")


def saturn_enroll(deployment=None):
    if deployment is None:
        deployment = json.loads((FIXTURE / "enrollment.json").read_text())["deploymentId"] if (FIXTURE / "enrollment.json").exists() else "integration"
    owner = client("saturn")
    access = (FIXTURE / "saturn/dev-owner-bootstrap-token").read_text().strip()
    checked(owner.post("/api/v1/auth/login", json={"accessKey": access}), 200, 201)
    owner.headers["X-Vault-CSRF"] = owner.cookies.get("vault_csrf_dev")
    enrollment = checked(owner.post("/api/v1/backup-services/enrollments", json={
        "namespaceSlug": "mastermind", "deploymentId": deployment, "mirrorRoot": "mastermind",
        "name": "Mastermind integration", "requireEncryption": True}), 201)
    machine = client("saturn")
    redeemed = checked(machine.post("/api/v1/backup-enrollments/redeem", json={"code": enrollment["code"]}), 201)
    assert redeemed["mirrorMode"] == "zip-tree" and redeemed["mirrorRoot"] == "mastermind"
    assert redeemed["readerCapability"] == "neptune.resource-reader.v1" and redeemed["readerRoot"] == "root"
    assert len({redeemed["token"], redeemed["mirrorToken"], redeemed["readerToken"]}) == 3
    assert machine.post("/api/v1/backup-enrollments/redeem", json={"code": enrollment["code"]}).status_code == 401
    save("enrollment.json", json.dumps(redeemed))
    save("saturn-archive.token", redeemed["token"])
    save("saturn-mirror.token", redeemed["mirrorToken"])
    save("saturn-reader.token", redeemed["readerToken"])
    root = checked(machine.get("/api/v1/neptune-reader/resources", params={"path": "root", "limit": 2},
                               headers={"Authorization": "Bearer " + redeemed["readerToken"]}))
    assert len(root["entries"]) <= 2
    print("PASS: actual typed enrollment; independent archive/mirror/reader credentials; one-use code; scoped listing.")
    return redeemed


def saturn_reader():
    credentials = json.loads((FIXTURE / "enrollment.json").read_text())
    saturn = client("saturn")
    writer = {"Authorization": "Bearer " + credentials["mirrorToken"], "Content-Type": "application/octet-stream"}
    reader = {"Authorization": "Bearer " + credentials["readerToken"], "Content-Type": "application/octet-stream"}
    content = bytes(range(256)) * 8192
    filename = "Range fixture.bin"
    previous = saturn.head("/dav/mastermind/" + filename, headers=writer)
    if previous.status_code == 200:
        writer["If-Match"] = previous.headers["etag"]
    else:
        writer["If-None-Match"] = "*"
    response = saturn.put("/dav/mastermind/" + filename, headers=writer, content=content)
    assert response.status_code in (201, 204), f"Mirror write: {response.status_code}"
    route, params = "/api/v1/neptune-reader/resource-content", {"path": "root/mastermind/" + filename}
    full = saturn.get(route, params=params, headers=reader)
    assert full.status_code == 200 and hashlib.sha256(full.content).digest() == hashlib.sha256(content).digest()
    etag = full.headers["etag"]
    part = saturn.get(route, params=params, headers={**reader, "Range": "bytes=100-399", "If-Range": etag})
    assert part.status_code == 206 and part.content == content[100:400]
    assert part.headers["content-range"] == f"bytes 100-399/{len(content)}"
    suffix = saturn.get(route, params=params, headers={**reader, "Range": "bytes=-100"})
    assert suffix.status_code == 206 and suffix.content == content[-100:]
    stale = saturn.get(route, params=params, headers={**reader, "Range": "bytes=0-9", "If-Range": '"old"'})
    assert stale.status_code == 200 and stale.content == content
    for invalid in ["bytes=999999999-", "bytes=0-5,7-9", "bytes=-0"]:
        assert saturn.get(route, params=params, headers={**reader, "Range": invalid}).status_code == 416
    assert saturn.put("/dav/root/forbidden.txt", headers=reader, content=b"must-not-write").status_code == 403
    for token in [credentials["mirrorToken"], credentials["token"]]:
        assert saturn.get(route, params=params, headers={"Authorization": "Bearer " + token}).status_code in (401, 403)
    for path in ["root/../_system", "root/%2e%2e/private", "mastermind/file", "root\\file"]:
        assert saturn.get(route, params={"path": path}, headers=reader).status_code in (400, 403, 422)
    save("reader-fixture.json", json.dumps({"path": params["path"], "size": len(content),
                                           "sha256": hashlib.sha256(content).hexdigest(), "etag": etag}))
    print("PASS: actual Saturn/SFTP 2 MiB content, Range/If-Range, suffix, 416, reader immutability and credential separation.")


def neptune_reader():
    neptune = client("neptune")
    headers = {"X-Neptune-Token": (FIXTURE / "neptune-control.token").read_text(), "X-Neptune-Purpose": "owner-reference"}
    fixture = json.loads((FIXTURE / "reader-fixture.json").read_text())
    route = "/api/v1/projects/mastermind/resource-content"
    response = neptune.get(route, headers=headers, params={"path": fixture["path"]})
    assert response.status_code == 200, f"Neptune content: {response.status_code}"
    assert hashlib.sha256(response.content).hexdigest() == fixture["sha256"]
    part = neptune.get(route, headers={**headers, "Range": "bytes=100-399", "If-Range": response.headers["etag"]}, params={"path": fixture["path"]})
    assert part.status_code == 206 and part.content == response.content[100:400]
    assert neptune.get(route, headers={**headers, "X-Neptune-Purpose": "shared"}, params={"path": fixture["path"]}).status_code == 403
    assert neptune.get(route, headers={**headers, "X-Neptune-Token": "wrong"}, params={"path": fixture["path"]}).status_code == 401
    page = checked(neptune.get("/api/v1/projects/mastermind/resources", headers=headers, params={"path": "root", "limit": 2}))
    assert len(page["entries"]) <= 2
    print("PASS: actual Core-contract -> Neptune -> Kernel/Volt -> Saturn/SFTP streaming reader, Range and owner-purpose isolation.")


def chronos_card():
    owner = client("chronos")
    checked(owner.post("/api/auth/login", json={"access_key": (FIXTURE / "chronos-access").read_text()}))
    owner.headers["X-CSRF-Token"] = owner.cookies.get("chronos_csrf")
    created = checked(owner.post("/api/sessions", json={"category": "execution",
        "started_at": "2026-09-14T20:00:00+00:00", "stopped_at": "2026-09-14T20:15:00+00:00",
        "note": "Synthetic fixture: this note must not leave the one-event projection."}), 201)
    identifier = created["public_id"]
    route = "/api/v1/internal/mastermind/events/" + identifier
    reader = client("chronos")
    identity = {"Authorization": "Bearer " + (FIXTURE / "chronos-reader.token").read_text(), "X-Mastermind-Purpose": "owner-reference"}
    data = checked(reader.get(route, headers=identity))
    assert set(data) == {"schema", "audience", "id", "started_at", "ended_at"}
    assert reader.get(route).status_code == 401
    assert reader.get(route, headers={**identity, "X-Mastermind-Purpose": "shared"}).status_code == 403
    assert reader.get("/api/dashboard", headers=identity).status_code == 401

    class LocalGateway(httpx.BaseTransport):
        """Route local test DNS to its published loopback port; all bytes come from real services."""
        def __init__(self):
            self.transport = httpx.HTTPTransport(verify=TRUST)

        def handle_request(self, request):
            assert request.url.host == "chronos.mastermind.test"
            request.headers["Host"] = request.url.host
            request.url = request.url.copy_with(host="127.0.0.1", port=19441)
            return self.transport.handle_request(request)

        def close(self):
            self.transport.close()

    registry = Kernel(BASE, lambda: (FIXTURE / "kernel.token").read_text(), client=client("kernel"))
    adapter = Chronos(registry, ShellSecrets(None, registry), client=httpx.Client(transport=LocalGateway()))
    result = adapter.card(identifier)
    assert result["started_at"] == data["started_at"] and result["ended_at"] == data["ended_at"]
    assert set(result) == {"kind", "id", "started_at", "ended_at"}
    adapter.close()
    registry.close()
    print("PASS: actual Chronos event card, Core adapter, Kernel/Volt credential resolution, minimal projection and principal separation.")


def enrollment_repair():
    previous = json.loads((FIXTURE / "enrollment.json").read_text())
    current = saturn_enroll()
    saturn = client("saturn")
    for token, route, params in [(previous["readerToken"], "/api/v1/neptune-reader/resources", {"path": "root"}),
                                 (previous["mirrorToken"], "/dav/mastermind/", {})]:
        response = saturn.get(route, params=params, headers={"Authorization": "Bearer " + token})
        assert response.status_code == 401, f"Replaced credential was not revoked: {response.status_code}"
    assert saturn.get("/api/v1/neptune-reader/resources", params={"path": "root"},
                      headers={"Authorization": "Bearer " + current["readerToken"]}).status_code == 200
    print("PASS: actual PostgreSQL replacement triggers revoke both old mirror and reader credentials immediately.")

    def sql(statement):
        result = subprocess.run(["docker", "exec", "-i", "mastermind-integration-postgres-1", "psql", "-U", "vault", "-d", "vault", "-v", "ON_ERROR_STOP=1", "-tA"],
                                input=statement, capture_output=True, text=True, check=False)
        if result.returncode:
            raise AssertionError("Isolated PostgreSQL fault fixture failed")
        return result.stdout.strip()
    owner = client("saturn")
    checked(owner.post("/api/v1/auth/login", json={"accessKey": (FIXTURE / "saturn/dev-owner-bootstrap-token").read_text().strip()}), 200, 201)
    owner.headers["X-Vault-CSRF"] = owner.cookies.get("vault_csrf_dev")
    deployment = current["deploymentId"]
    assert re.fullmatch(r"[a-z0-9-]{1,63}", deployment)
    enrollment = checked(owner.post("/api/v1/backup-services/" + current["serviceId"] + "/enrollment"), 201)
    count_query = "SELECT count(*) FROM devices WHERE name LIKE 'Neptune mastermind/" + deployment + "%' AND state='active';"
    baseline = sql(count_query)
    sql("CREATE FUNCTION mastermind_fixture_fail_reader() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
        "IF NEW.name = 'Neptune mastermind/" + deployment + " reader' THEN RAISE EXCEPTION 'injected reader insertion failure'; END IF; RETURN NEW; END $$; "
        "CREATE TRIGGER mastermind_fixture_reader_failure BEFORE INSERT ON devices FOR EACH ROW EXECUTE FUNCTION mastermind_fixture_fail_reader();")
    try:
        failed = saturn.post("/api/v1/backup-enrollments/redeem", json={"code": enrollment["code"]})
        assert failed.status_code >= 400
        assert sql(count_query) == baseline
        assert saturn.get("/api/v1/neptune-reader/resources", params={"path": "root"},
                          headers={"Authorization": "Bearer " + current["readerToken"]}).status_code == 200
    finally:
        sql("DROP TRIGGER mastermind_fixture_reader_failure ON devices; DROP FUNCTION mastermind_fixture_fail_reader();")
    retry = checked(owner.post("/api/v1/backup-services/" + enrollment["service"]["id"] + "/enrollment"), 201)
    repaired = checked(saturn.post("/api/v1/backup-enrollments/redeem", json={"code": retry["code"]}), 201)
    assert repaired["readerCapability"] == "neptune.resource-reader.v1"
    checked(owner.delete("/api/v1/backup-services/" + enrollment["service"]["id"]), 200, 204)
    assert sql(count_query) == "0"
    saturn_enroll("integration-" + uuid.uuid4().hex[:8])
    print("PASS: actual partial-enrollment database failure, orphan capability cleanup, explicit re-enrollment repair and revoke.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--enroll", action="store_true")
    parser.add_argument("--reader", action="store_true")
    parser.add_argument("--neptune", action="store_true")
    parser.add_argument("--chronos", action="store_true")
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    if args.seed:
        seed_register()
    if args.enroll:
        saturn_enroll()
    if args.reader:
        saturn_reader()
    if args.neptune:
        neptune_reader()
    if args.chronos:
        chronos_card()
    if args.repair:
        enrollment_repair()
    print(f"Integration probe completed in {time.monotonic() - started:.2f}s.")
