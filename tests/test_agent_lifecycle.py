from dataclasses import replace

import pytest
from test_api import api as api_fixture
from test_api import authenticate

from mastermind.agent_lifecycle import AgentLifecycle
from mastermind.errors import DomainError

api = api_fixture
CODE = 'A'*32


def setup(service, monkeypatch, *, lost=False, partial=False):
    monkeypatch.setattr(service, 'config', replace(service.config, updater_socket='/fixture/updater.sock',
        updater_token_file=service.config.home / 'generated-token'))
    calls, jobs = [], []
    def call(method, route, *, data=None):
        calls.append((method, route, data))
        if method == 'POST':
            jobs.append({'id': 'neptune-123-abcdef', 'request_id': data['request_id'],
                'head_id': 'mastermind', 'service': 'neptune-initialization', 'state': 'INSTALLING',
                'message': 'PRIVATE_AGENT_DIAGNOSTIC', 'enrollment_code': CODE})
            if lost:
                raise DomainError('UPDATER_UNAVAILABLE', 'A generated response was lost.', 503)
            return jobs[-1]
        if route.startswith('/v1/jobs?'):
            return {'jobs': jobs}
        return jobs[-1]
    async def control(action):
        assert action == 'status'
        return {'product': 'neptune-linux', 'project': {'projectId': 'mastermind', 'enabled': False,
            'mirror': {'root': 'mastermind', 'mode': 'zip-tree'}, 'reader': None if partial else
                {'root': 'root', 'capability': 'neptune.resource-reader.v1', 'credential_ready': True}}}
    monkeypatch.setattr(service.updates.updater, 'call', call)
    monkeypatch.setattr(service.neptune, 'control', control)
    async def reader(operation, path, **kwargs):
        assert (operation, path, kwargs) == ('resources', 'root', {'limit': 1})
        return {'entries': [], 'next_cursor': None}
    monkeypatch.setattr(service.neptune, 'request', reader)
    return calls, jobs


def test_initialization_uses_own_updater_head_and_verifies_three_scopes(api, monkeypatch):
    client, service = api
    authenticate(client)
    calls, jobs = setup(service, monkeypatch)
    result = client.post('/api/owner/agents/neptune/enroll', json={'code': CODE})
    assert result.status_code == 200 and result.json()['state'] == 'INSTALLING'
    request = calls[0][2]
    assert request['head_id'] == request['project_id'] == 'mastermind'
    assert request['export_url'] == service.config.neptune_export_url
    assert client.post('/api/owner/agents/neptune/enroll', json={'code': CODE}).status_code == 409
    journal = (service.agent_lifecycle.directory / 'neptune.json').read_text()
    assert CODE not in journal and 'PRIVATE_AGENT_DIAGNOSTIC' not in journal
    jobs[0]['state'] = 'COMPLETED'
    completed = client.get('/api/owner/agents/neptune/initialization').json()
    assert completed['state'] == 'COMPLETED'
    assert completed['capabilities'] == ['archive', 'mirror', 'reader']
    assert CODE not in str(completed)


def test_lost_acceptance_response_recovers_by_request_id_after_restart(api, monkeypatch):
    client, service = api
    authenticate(client)
    calls, jobs = setup(service, monkeypatch, lost=True)
    assert client.post('/api/owner/agents/neptune/enroll', json={'code': CODE}).status_code == 503
    previous = service.agent_lifecycle.record['request_id']
    service.agent_lifecycle = AgentLifecycle(service)
    jobs[0]['state'] = 'ENROLLING'
    result = client.get('/api/owner/agents/neptune/initialization').json()
    assert result['state'] == 'ENROLLING' and result['request_id'] == previous
    assert sum(method == 'POST' for method, _, _ in calls) == 1


def test_completed_agent_job_with_missing_reader_is_partial_failure(api, monkeypatch):
    client, service = api
    authenticate(client)
    _, jobs = setup(service, monkeypatch, partial=True)
    client.post('/api/owner/agents/neptune/enroll', json={'code': CODE})
    jobs[0]['state'] = 'COMPLETED'
    assert client.get('/api/owner/agents/neptune/initialization').json()['error'] == 'NEPTUNE_PARTIAL_CONFIGURATION'


@pytest.mark.parametrize('code', ['123456', ' '+CODE, CODE+' ', CODE+'\n', 123])
def test_codes_have_exact_separate_neptune_format(api, code):
    client, service = api
    authenticate(client)
    assert client.post('/api/owner/agents/neptune/enroll', json={'code': code}).status_code == 422
    assert service.agent_lifecycle.record is None


def test_unknown_local_updater_does_not_create_a_phantom_job(api):
    client, service = api
    authenticate(client)
    assert client.post('/api/owner/agents/neptune/enroll', json={'code': CODE}).status_code == 503
    assert service.agent_lifecycle.record is None
