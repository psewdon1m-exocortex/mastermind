import time

import pytest
from fastapi.testclient import TestClient

from mastermind.api import create_app
from mastermind.config import Config
from mastermind.fs import atomic_write


@pytest.fixture
def api(tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    atomic_write(secrets / "bootstrap_access_key", b"test-owner-access-key")
    atomic_write(secrets / "chronos_report_token", b"test-chronos-report-token")
    config = Config(home=tmp_path / "data", public_url="https://mastermind.test",
                    secret_directory=secrets, runtime_mode="offline", test_mode=True)
    app = create_app(config)
    with TestClient(app, base_url=config.public_url) as client:
        deadline = time.monotonic() + 5
        while client.get("/readyz").status_code != 200 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert client.get("/readyz").status_code == 200
        yield client, app.state.service


def test_chronos_template_read_and_idempotent_monthly_note(api):
    client, service = api
    service.vault.write("Branch/chronos_analytics.md", "#key\nChronos branch", None, create=True)
    source = "---\nperiod: \"{{chronos.month}}\"\ntimezone: \"{{chronos.timezone}}\"\n---\n# {{chronos.total}}\n{{chronos.category_chart}}\n{{chronos.daily_chart}}\n@chronos_analytics\n"
    service.vault.write("root/templates/chronos_note.md", source, None, create=True)
    route = "/api/v1/internal/chronos/monthly-template"
    assert client.get(route, params={"path": "root/templates/chronos_note.md"}).status_code == 401
    headers = {"Authorization": "Bearer test-chronos-report-token"}
    template = client.get(route, params={"path": "root/templates/chronos_note.md"}, headers=headers)
    assert template.status_code == 200, template.text
    info = template.json()
    assert info["anchor"] == "Branch/chronos_analytics.md"
    assert client.get(route, params={"path": "Branch/chronos_analytics.md"}, headers=headers).status_code == 422
    body = "---\nperiod: \"2026-09\"\ntimezone: \"Europe/Istanbul\"\n---\n# 10 ч\n\n```mermaid\npie\n    \"Recovery\" : 600\n```\n\n@chronos_analytics\n"
    payload = {"month": "2026-09", "timezone": "Europe/Istanbul", "template_path": info["path"],
               "template_sha256": info["sha256"], "text": body}
    report_route = "/api/v1/internal/chronos/monthly-reports"
    assert client.post(report_route, json=payload).status_code == 401
    first = client.post(report_route, json=payload, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["path"] == "Chronos 2026-09.md"
    assert first.json()["created"] is True
    assert service.vault.read("Chronos 2026-09.md") == body
    graph = service.vault.graph()
    assert ["Branch/chronos_analytics.md", "Chronos 2026-09.md"] in graph["edges"]
    repeat = client.post(report_route, json=payload, headers=headers)
    assert repeat.status_code == 200 and repeat.json()["created"] is False
    changed = client.post(report_route, json={**payload, "text": body + "Correction\n"}, headers=headers)
    assert changed.status_code == 409
    assert len([path for path, _ in service.vault.files() if path.startswith("Chronos ")]) == 1


def test_chronos_report_rejects_changed_template_or_wrong_link(api):
    client, service = api
    service.vault.write("chronos_analytics.md", "Branch", None, create=True)
    service.vault.write("other.md", "Other", None, create=True)
    source = "---\nperiod: \"{{chronos.month}}\"\ntimezone: \"{{chronos.timezone}}\"\n---\n{{chronos.total}}\n{{chronos.category_chart}}\n{{chronos.daily_chart}}\n@chronos_analytics\n"
    service.vault.write("root/templates/chronos_note.md", source, None, create=True)
    headers = {"Authorization": "Bearer test-chronos-report-token"}
    info = client.get("/api/v1/internal/chronos/monthly-template", params={"path": "root/templates/chronos_note.md"}, headers=headers).json()
    payload = {"month": "2026-09", "timezone": "Europe/Istanbul", "template_path": info["path"],
               "template_sha256": "0" * 64,
               "text": "---\nperiod: 2026-09\ntimezone: Europe/Istanbul\n---\n@chronos_analytics\n"}
    route = "/api/v1/internal/chronos/monthly-reports"
    assert client.post(route, json=payload, headers=headers).json()["error"]["code"] == "REPORT_TEMPLATE_CHANGED"
    wrong = {**payload, "template_sha256": info["sha256"], "text": payload["text"].replace("@chronos_analytics", "@other")}
    assert client.post(route, json=wrong, headers=headers).status_code == 422
    assert not (service.config.vault / "Chronos 2026-09.md").exists()
