import json
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from mastermind.api import create_app
from mastermind.config import Config
from mastermind.fs import atomic_write

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from exposure_inventory import discovered


def inventory():
    return json.loads((ROOT / "docs/exposure-inventory.json").read_text("utf-8"))["routes"]


def test_all_methods_and_paths_have_an_explicit_nonindexable_classification():
    rows = inventory()
    assert sorted((Path(row["source"]).name, row["method"], row["path"]) for row in rows) == discovered(ROOT)
    assert all(row["principal"] and row["exposure"] and row["indexable"] is False for row in rows)


def test_owner_http_apis_are_reachable_through_the_explicit_ingress_allowlist():
    text = (ROOT / "packaging/nginx/mastermind-server.conf.template").read_text("utf-8")
    patterns = re.findall(r"^\s+location ~ (\S+) \{", text, re.MULTILINE)
    for row in inventory():
        if row["component"] == "core" and row["principal"] == "owner" and row["path"].startswith("/api/"):
            assert any(re.search(pattern, row["path"]) for pattern in patterns), row["path"]


def test_every_owner_route_rejects_anonymous_and_forged_trust_headers(tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    atomic_write(secrets / "bootstrap_access_key", b"test-only-exposure-key")
    config = Config(home=tmp_path / "data", public_url="https://mastermind.test", secret_directory=secrets,
                    runtime_mode="offline", test_mode=True)
    app = create_app(config)
    with TestClient(app, base_url="https://mastermind.test") as client:
        for row in inventory():
            if row["component"] != "core" or row["principal"] != "owner" or row["method"] == "WEBSOCKET":
                continue
            path = re.sub(r"\{[^}]+\}", "a" * 32, row["path"])
            response = client.request(row["method"], path, headers={"Origin": config.public_url,
                "User-Agent": "Googlebot", "X-Verified-Bot": "true", "X-Forwarded-For": "127.0.0.1"})
            assert response.status_code == 401, (row["method"], path, response.status_code)
