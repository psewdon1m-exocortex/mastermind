"""Create an unredeemed typed code for the isolated qualification host only."""
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"scripts"))
from probe_integrations import client, checked, FIXTURE
import probe_integrations

clean = "--clean-host" in sys.argv
probe_integrations.BASE = "https://127.0.0.1:"+("19443" if clean else "19442")

owner = client("saturn")
checked(owner.post("/api/v1/auth/login", json={"accessKey": (FIXTURE/"saturn/dev-owner-bootstrap-token").read_text().strip()}), 200, 201)
owner.headers["X-Vault-CSRF"] = owner.cookies.get("vault_csrf_dev")
path = ROOT/(".local/clean-install/enrollment.json" if clean else ".local/host-fixture/enrollment.json")
if path.exists():
    previous=json.loads(path.read_text())
    enrollment=checked(owner.post('/api/v1/backup-services/'+previous['service']['id']+'/enrollment'),201)
    deployment=previous['service']['deploymentId']
else:
    deployment = "host-"+uuid.uuid4().hex[:12]
    enrollment = checked(owner.post("/api/v1/backup-services/enrollments", json={
        "namespaceSlug": "mastermind", "deploymentId": deployment, "mirrorRoot": "mastermind",
        "name": "Mastermind isolated host qualification", "requireEncryption": True}), 201)
path.write_text(json.dumps(enrollment), encoding="utf-8")
path.chmod(0o600)
print("Created a private one-time Mastermind code for isolated deployment "+deployment+"; value withheld")
