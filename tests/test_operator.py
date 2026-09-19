from datetime import datetime
from types import SimpleNamespace

import pytest
from test_api import api as api_fixture
from test_api import authenticate

api = api_fixture


def test_hash_worker_owns_a_narrow_module_import_policy(api):
    client, _ = api
    response = client.get('/assets/hash-worker.js')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/javascript')
    policy = response.headers['content-security-policy']
    assert "default-src 'none';" in policy
    assert "script-src 'self';" in policy
    assert 'unsafe-eval' not in policy and 'unsafe-inline' not in policy
    assert 'connect-src' not in policy  # Network falls back to default-src none.
    assert "worker-src 'self';" in client.get('/crusher').headers['content-security-policy']
    for path in ('/assets/sha256.js', '/assets/crusher.js', '/api/appearance', '/s/invalid'):
        assert "script-src 'self'" not in client.get(path).headers['content-security-policy']


def test_tab_icons_are_bounded_pngs_without_a_content_policy_exception(api):
    client, _ = api
    import struct
    for size in (16, 32, 64):
        icon = client.get(f'/assets/favicon-{size}.png')
        assert icon.status_code == 200
        assert icon.headers['content-type'].startswith('image/png')
        assert icon.content.startswith(b'\x89PNG\r\n\x1a\n')
        assert struct.unpack('>II', icon.content[16:24]) == (size, size)
        assert len(icon.content) < 20000
        assert 'img-src data:' not in icon.headers['content-security-policy']
    for route in ('/assets/brand-mark.png', '/assets/missing.svg', '/api/health', '/s/not-a-share'):
        assert 'img-src data:' not in client.get(route).headers['content-security-policy']
    assert "img-src 'self';" in client.get('/login').headers['content-security-policy']
    assert client.get('/shared').status_code == 200
    assert client.get('/shares').status_code == 200  # Legacy bookmark, canonicalized by the Shell.


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
    # A fractional baseline reproduces cancellation rounding on fresh CI hosts.
    monkeypatch.setattr(service, 'started', 165.4)
    monkeypatch.setattr('mastermind.operator.time.monotonic', lambda: service.started+123)
    result = client.get('/api/owner/metrics').json()
    assert paths == [service.config.vault]
    assert result['disk']['used'] == 75*1024
    assert result['disk']['percent'] == 75
    assert result['uptime_seconds'] == pytest.approx(123, rel=0, abs=1e-9)
    assert result['cpu']['percent'] is None  # A first sample is unknown, not a healthy zero.


def test_saved_layout_survives_retired_analytics_and_status_cards(api):
    client, service = api
    authenticate(client)
    service.state.set_setting('shell', {'revision': 7, 'orders': {
        'navigation': ['settings', 'analytics', 'shares', 'crusher', 'vault', 'dashboard'],
        'dashboard': ['uptime', 'operations', 'disk', 'ram', 'cpu'],
        'analytics': ['notes', 'heatmap', 'connectedness', 'edges', 'broken'],
    }})
    prefs = client.get('/api/owner/settings').json()
    assert prefs['revision'] == 7
    assert prefs['orders']['navigation'] == ['settings', 'shares', 'crusher', 'vault', 'dashboard']
    assert prefs['orders']['dashboard'] == [
        'uptime', 'disk', 'ram', 'cpu', 'connectedness', 'items', 'heatmap', 'crusher_access']
    assert 'analytics' not in prefs['orders']
    order = list(reversed(prefs['orders']['dashboard']))
    saved = client.patch('/api/owner/settings', json={'revision': 7, 'orders': {'dashboard': order}})
    assert saved.status_code == 200
    assert client.get('/api/owner/settings').json()['orders']['dashboard'] == order


def test_dashboard_counts_notes_and_attachments_but_not_hidden_state(api):
    client, service = api
    authenticate(client)
    vault = service.config.vault
    for name in ['A.md', 'media/image.png', 'document.pdf', 'Map.canvas', 'nested/Other.MD',
                 '.obsidian/plugins/demo/main.js', '.trash/Deleted.md', 'nested/.hidden.md']:
        path = vault / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'Fixture')
    service.vault.index()
    response = client.get('/api/owner/analytics').json()
    assert response['items'] == {'total': 5, 'notes': 2, 'attachments': 3}
    assert response['notes'] == 2
    (vault / 'document.pdf').unlink()
    assert client.get('/api/owner/analytics').json()['items']['total'] == 4
