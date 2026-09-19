from test_api import api as api_fixture
from test_api import authenticate

from mastermind.wyvern import Wyvern

api = api_fixture


def test_wyvern_settings_are_owner_only_and_cannot_select_another_client(api, monkeypatch):
    client, _service = api
    assert client.get('/api/owner/wyvern').status_code == 401
    assert client.post('/api/owner/wyvern/bindings', json={}).status_code == 401
    authenticate(client)
    monkeypatch.setattr(Wyvern, 'status', lambda self: {'llm_ready': False, 'client_linked': True})
    assert client.get('/api/owner/wyvern').json()['llm_ready'] is False
    calls = []
    monkeypatch.setattr(Wyvern, 'call', lambda self, method, route, **kwargs: calls.append((method, route, kwargs)) or
                        {'instance_id': 'host', 'client_id': 'mastermind', 'binding_revision': 5, 'bindings': kwargs['data']['bindings']})
    change = {'bindings': {'text': {'adapter_id': 'google', 'profile': 'default'}}, 'expected_revision': 4, 'request_id': 'test-wyvern-binding-123'}
    assert client.post('/api/owner/wyvern/bindings', json={**change, 'client_id': 'laboratory'}).status_code == 422
    assert calls == []
    assert client.post('/api/owner/wyvern/bindings', json=change).status_code == 200
    assert calls == [('POST', '/v1/bindings', {'data': change})]
    assert client.post('/api/owner/wyvern/connect', json={'head_id': 'other'}).status_code == 422


def test_missing_gateway_does_not_remove_settings_card(api):
    client, _ = api
    authenticate(client)
    status = client.get('/api/owner/wyvern')
    assert status.status_code == 200 and status.json()['llm_ready'] is False
    assert 'wyvern' in client.get('/api/owner/settings').json()['orders']['settings']
