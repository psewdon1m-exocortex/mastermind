"""Generated native-renderer fixtures in isolated Saturn/Chronos services."""
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from probe_integrations import FIXTURE, checked, client
from docker_paths import bind_path

directory = FIXTURE / "crusher"
directory.mkdir(exist_ok=True)
(directory / "preview.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="480" height="120"><rect width="480" height="120" fill="#163d35"/><text x="20" y="70" fill="white" font-size="28">Saturn native preview fixture</text></svg>')
subprocess.run(["docker", "build", "-f", str(ROOT / "scripts/integration/Dockerfile.media-fixture"),
    "-t", "mastermind-media-fixture:qualification", str(ROOT / "scripts/integration")], check=True)
fixture_image = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", "mastermind-media-fixture:qualification"], text=True).strip()
subprocess.run(["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "10001:10001", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true", "--memory", "512m", "--cpus", "2",
    "--mount", f"type=bind,source={bind_path(directory)},target=/fixture", fixture_image,
    "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10", "-t", "8",
    "-pix_fmt", "yuv420p", "-movflags", "+faststart", "/fixture/preview.mp4"], check=True)
credentials = json.loads((FIXTURE / "enrollment.json").read_text())
saturn = client("saturn")
paths = []
for name in ("preview.svg", "preview.mp4", "scan.pdf", "source.wav"):
    # Keep these generated sources in the test Vault too: the real mirror must
    # otherwise delete remotely injected files absent from its canonical tree.
    subprocess.run(["docker", "exec", "-i", "mastermind-development-runtime-1", "python", "-c",
        "from pathlib import Path; import sys; p=Path('/vault/current')/sys.argv[1]; body=sys.stdin.buffer.read(); "
        "assert not p.is_symlink(); "
        "assert not p.exists() or p.read_bytes()==body, 'Existing fixture path has different bytes'; "
        "p.open('xb').write(body) if not p.exists() else None", name],
        input=(directory/name).read_bytes(), check=True)
    headers = {"Authorization": "Bearer " + credentials["mirrorToken"], "Content-Type": "application/octet-stream"}
    route = "/dav/mastermind/" + name
    previous = saturn.head(route, headers=headers)
    headers["If-Match" if previous.status_code == 200 else "If-None-Match"] = previous.headers["etag"] if previous.status_code == 200 else "*"
    with (directory / name).open("rb") as source:
        result = saturn.put(route, headers=headers, content=source)
    assert result.status_code in (201, 204), f"Fixture source HTTP {result.status_code}"
    paths.append("root/mastermind/" + name)
chronos = client("chronos")
checked(chronos.post("/api/auth/login", json={"access_key": (FIXTURE / "chronos-access").read_text()}))
chronos.headers["X-CSRF-Token"] = chronos.cookies.get("chronos_csrf")
record_path = FIXTURE / "native-resources.json"
if record_path.exists():
    event = {"public_id": json.loads(record_path.read_text())["event_id"]}
else:
    ended = datetime.now(UTC)-timedelta(minutes=2)
    event = checked(chronos.post("/api/sessions", json={"category": "execution", "started_at": (ended-timedelta(minutes=1)).isoformat(),
        "stopped_at": ended.isoformat(), "note": "CHRONOS_PRIVATE_ANNOTATION_CANARY"}), 201)
destination = ROOT / ".local/secrets/core/chronos_service_token"
value = (FIXTURE / "chronos-reader.token").read_text()
if destination.exists():
    assert destination.read_text() == value, "Existing local credential differs from the generated fixture"
else:
    destination.write_text(value, encoding="utf-8")
record_path.write_text(json.dumps({"event_id": event["public_id"], "paths": paths, "media_fixture_image": fixture_image}))
print("PASS: actual Saturn image/video/audio/PDF fixtures and minimal Chronos event prepared.")
