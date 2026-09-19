import base64
import hashlib
import hmac
import json
from dataclasses import replace

import httpx
import pytest
from test_api import api as api_fixture
from test_api import authenticate
from test_owner_operations import keys

from mastermind.errors import DomainError
from mastermind.fs import atomic_write

api = api_fixture


def prepared(service):
    keys(service)
    updates = service.updates
    token = service.config.secret_directory / 'updater_token'
    atomic_write(token, b'synthetic-scoped-token')
    updates.config = replace(updates.config, updater_token_file=token, updater_socket='/run/synthetic.sock')
    updates.record = {'request_id': 'f'*32, 'version': '0.0.9', 'phase': 'SNAPSHOT', 'preparation_id': 'prepared-id'}
    updates.save()
    folder = updates.directory / updates.record['request_id']
    updates.prepare_snapshot(service.backup, folder, '', updates.record['request_id'])
    return updates, folder


def test_download_is_single_use_and_removes_all_server_snapshot_bytes(api):
    client, service = api
    updates, folder = prepared(service)
    assert not (folder / 'snapshot').exists()
    assert updates.record['phase'] == 'WAITING_SAVED'
    route = '/api/owner/updates/' + updates.record['request_id'] + '/backup'
    assert client.get(route).status_code == 401
    authenticate(client)
    result = client.get(route)
    assert result.status_code == 200
    assert hashlib.sha256(result.content).hexdigest() == updates.record['sha256']
    assert updates.record['download_complete'] and updates.record['download_consumed']
    assert not (folder / 'mastermind-backup.zip').exists()
    assert client.get(route).status_code == 409
    assert updates.blocks
    assert client.post('/api/owner/updates/' + updates.record['request_id'] + '/cancel', json={}).status_code == 200
    assert not updates.blocks


def test_aborted_download_cannot_authorize_installation_and_restart_cleans_bytes(api):
    _, service = api
    updates, folder = prepared(service)
    stream, _ = updates.download(updates.record['request_id'])
    stream.read(10)
    stream.close()
    updates.downloaded(updates.record['request_id'], False)
    assert not (folder / 'mastermind-backup.zip').exists()
    assert not updates.record['download_complete']
    with pytest.raises(DomainError, match='confirm'):
        updates.apply_request()
    updates.start()
    assert updates.record['phase'] == 'FAILED' and not updates.blocks


def test_saved_file_stream_is_checked_before_signed_handoff(api, monkeypatch):
    client, service = api
    updates, folder = prepared(service)
    authenticate(client)
    request_id = updates.record['request_id']
    data = client.get('/api/owner/updates/' + request_id + '/backup').content
    calls, streamed = [], []
    def call(method, route, **kwargs):
        calls.append((method, route, kwargs))
        if route.endswith('/backup-spools'):
            return {'spool_id': 'e'*32}
        assert route.endswith('/seal')
        return {'state':'SEALED', 'size':len(data), 'sha256':hashlib.sha256(data).hexdigest()}
    monkeypatch.setattr(updates.updater, 'call', call)
    async def receiver(request):
        async for chunk in request.stream:
            streamed.append(chunk)
        return httpx.Response(204)
    monkeypatch.setattr('mastermind.updates.httpx.AsyncHTTPTransport', lambda **_: httpx.MockTransport(receiver))
    route = '/api/owner/updates/' + request_id + '/saved-backup'
    headers = {'X-Update-Saved':'1', 'X-Content-SHA256':updates.record['sha256'], 'Content-Type':'application/zip'}
    assert client.put(route, content=data).status_code == 409
    assert not calls
    response = client.put(route, content=data, headers=headers)
    assert response.status_code == 200, response.text
    assert b''.join(streamed) == data
    assert updates.record['phase'] == 'SAVED'
    assert not list(folder.glob('*.zip')) and not (folder / 'snapshot').exists()
    request = updates.apply_request()
    body, signature = request['backup_receipt'].split('.')
    decode = lambda value: base64.urlsafe_b64decode(value + '='*(-len(value)%4))
    assert hmac.compare_digest(decode(signature), hmac.new(b'synthetic-scoped-token',body.encode(),hashlib.sha256).digest())
    proof = json.loads(decode(body))
    assert proof['sha256'] == hashlib.sha256(data).hexdigest() and proof['size'] == len(data)
    assert proof['id'] == request_id and proof['version'] == '0.0.9'
    assert request['operator_saved'] is True and request['backup'] == {'spool_id':'e'*32}
    assert client.put(route, content=data, headers=headers).status_code == 200
    assert len(calls) == 2  # replay never starts a second upload


@pytest.mark.parametrize('corrupt', [False, True])
def test_failed_group_recovery_streams_only_original_own_copy(api, monkeypatch, corrupt):
    client, service = api
    updates, folder = prepared(service)
    authenticate(client)
    request_id = updates.record['request_id']
    data = client.get('/api/owner/updates/' + request_id + '/backup').content
    updates.save(phase='APPLY_REQUESTED', operator_saved=True, job_id='own-job', job_state='ROLLBACK_FAILED', error='UPDATE_RECOVERY_REQUIRED')
    calls = []
    def call(method, route, **kwargs):
        calls.append((method, route))
        if route == '/v1/jobs/own-job':
            return {'head_id':updates.config.updater_head_id, 'service':'mastermind', 'request_id':request_id,
                    'state':'ROLLBACK_FAILED', 'mutation_started':True, 'rollback_available':True, 'backup_sha256':updates.record['sha256']}
        if method == 'DELETE':
            return None
        if route.endswith('/backup-spools'):
            return {'spool_id':'d'*32}
        if route.endswith('/seal'):
            return {'state':'SEALED','size':len(data),'sha256':updates.record['sha256']}
        assert route == '/v2/jobs/own-job/rollback-saved-spool'
        assert kwargs['data'] == {'spool_id':'d'*32, 'operator_saved':True}
        return {'state':'ROLLING_BACK'}
    monkeypatch.setattr(updates.updater, 'call', call)
    async def receiver(request):
        await request.aread()
        return httpx.Response(204)
    monkeypatch.setattr('mastermind.updates.httpx.AsyncHTTPTransport', lambda **_: httpx.MockTransport(receiver))
    headers={'X-Update-Saved':'1','X-Content-SHA256':updates.record['sha256'],'Content-Type':'application/zip'}
    result=client.put('/api/owner/updates/'+request_id+'/saved-backup',content=(b'x'+data[1:]) if corrupt else data,headers=headers)
    assert result.status_code == (409 if corrupt else 200), result.text
    assert updates.blocks and not updates.record['recovery_uploading']
    assert not list(folder.glob('*.zip')) and not (folder/'snapshot').exists()
    if corrupt:
        assert calls[-1][0] == 'DELETE'
        assert not any(route.endswith('rollback-saved-spool') for _,route in calls)
    else:
        assert updates.record['job_state'] == 'ROLLING_BACK'
