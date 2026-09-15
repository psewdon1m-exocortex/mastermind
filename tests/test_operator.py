from datetime import datetime
from types import SimpleNamespace

import pytest
from test_api import api as api_fixture
from test_api import authenticate

api = api_fixture


def test_shell_settings_authority_conflicts_and_authentication(api):
    client, service = api
    for route in ("settings", "metrics", "analytics"):
        assert client.get('/api/owner/'+route).status_code == 401
    assert client.get('/api/appearance').json() == {"accent": "#00A8FF"}
    authenticate(client)
    original = client.get('/api/owner/settings').json()
    order = list(reversed(original['orders']['navigation']))
    changed = client.patch('/api/owner/settings', json={"revision": 0, "orders": {"navigation": order},
        "sidebar": "auto", "timezone": "America/New_York", "accent": "#62ff8c"})
    assert changed.status_code == 200
    assert client.get('/api/owner/settings').json()['orders']['navigation'] == order
    assert client.get('/api/appearance').json() == {"accent": "#62FF8C"}
    assert client.patch('/api/owner/settings', json={"revision": 0, "accent": "#FFFFFF"}).status_code == 409
    assert service.state.setting('shell')['accent'] == '#62FF8C'


@pytest.mark.parametrize('value', [
    {"accent": "#010101"}, {"accent": "red"}, {"accent": 123}, {"timezone": "../private"},
    {"timezone": "Unknown/Location"}, {"orders": {"navigation": ['settings']*6}},
    {"orders": {"settings": []}}, {"orders": {"unknown": []}}, {"sidebar": "floating"},
    {"kernel_token": "must-not-persist"}, {"revision": True},
])
def test_invalid_settings_are_atomic(api, value):
    client, service = api
    authenticate(client)
    before = service.operator.preferences()
    assert client.patch('/api/owner/settings', json={"revision": 0, **value}).status_code == 422
    assert service.operator.preferences() == before


def test_analytics_timezone_day_boundaries_normalization_and_domain_only(api):
    client, service = api
    authenticate(client)
    with service.state.transaction() as db:
        for number, stamp in enumerate(('2026-03-08T04:59:59+00:00', '2026-03-08T05:00:00+00:00',
                                       '2026-03-09T03:59:59+00:00')):
            db.execute("INSERT INTO activity VALUES(?,NULL,'EDIT','A.md',?)",
                       (str(number), datetime.fromisoformat(stamp).timestamp()))
    service.audit.emit('note.read', actor='owner')
    service.operator.change({"revision": 0, "timezone": "America/New_York"})
    result = client.get('/api/owner/analytics?first=2026-03-07&last=2026-03-09').json()
    assert [d['count'] for d in result['days']] == [1, 2, 0]
    assert [d['level'] for d in result['days']] == [2, 4, 0]
    assert result['max_activity'] == 2
    assert client.get('/api/owner/analytics?first=2020-01-01&last=2026-01-01').status_code == 422


def test_telemetry_uses_vault_bavail_and_core_monotonic_lifetime(api, monkeypatch):
    client, service = api
    authenticate(client)
    paths = []
    def statvfs(path):
        paths.append(path)
        return SimpleNamespace(f_blocks=100, f_frsize=1024, f_bavail=25, f_bfree=40)
    monkeypatch.setattr('mastermind.operator.os.statvfs', statvfs, raising=False)
    monkeypatch.setattr('mastermind.operator.time.monotonic', lambda: service.started+123)
    result = client.get('/api/owner/metrics').json()
    assert paths == [service.config.vault]
    assert result['disk']['used'] == 75*1024
    assert result['disk']['percent'] == 75
    assert result['uptime_seconds'] == 123
    assert result['cpu']['percent'] is None  # A first sample is unknown, not a healthy zero.
