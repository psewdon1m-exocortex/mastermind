import base64
import hashlib
import time

import pyrage
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
from test_api import api as api_fixture
from test_api import authenticate

from mastermind.errors import DomainError
from mastermind.fs import atomic_write

api = api_fixture


def test_restore_audit_failure_does_not_report_committed_data_as_failed(api, monkeypatch, tmp_path):
    _, service = api
    keys(service)
    source = tmp_path / "before.zip"
    service.backup.create(source)
    emit = service.audit.emit
    def failing(action, **kwargs):
        if action == "restore.apply":
            raise OSError("injected audit storage failure")
        return emit(action, **kwargs)
    monkeypatch.setattr(service.audit, "emit", failing)
    result = service.restore.apply(source)
    assert result["state"] == "COMPLETED" and result["warnings"] == ["AUDIT_UNAVAILABLE"]
    assert service.restore.last_warning == "AUDIT_UNAVAILABLE"


def keys(service):
    key = Ed25519PrivateKey.generate()
    identity = pyrage.x25519.Identity.generate()
    values = {'recovery_identity': str(identity), 'recovery_recipient': str(identity.to_public()),
              'backup_signing_private': base64.b64encode(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode(),
              'backup_signing_public': base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()}
    for name, value in values.items():
        atomic_write(service.config.secret_directory / name, value.encode())


def wait(service, identifier):
    deadline = time.monotonic()+20
    while time.monotonic() < deadline:
        result = service.owner_operations.read(identifier)
        if result['state'] != 'RUNNING':
            return result
        time.sleep(.01)
    raise AssertionError('Owner operation did not finish')


def test_owner_backup_download_inspect_restore_and_session_revocation(api, monkeypatch):
    client, service = api
    keys(service)
    failures = []
    original_apply = service.restore.apply
    def apply(*args, **kwargs):
        try:
            return original_apply(*args, **kwargs)
        except Exception:
            import traceback
            failures.append(traceback.format_exc())
            raise
    monkeypatch.setattr(service.restore, 'apply', apply)
    assert client.post('/api/owner/operations', json={'kind': 'backup'}).status_code == 401
    authenticate(client)
    client.post('/api/notes', json={'path': 'State.md', 'text': 'before'})
    identifier = client.post('/api/owner/operations', json={'kind': 'backup'}).json()['id']
    assert wait(service, identifier)['state'] == 'COMPLETED'
    download = client.get('/api/owner/operations/'+identifier+'/download')
    assert download.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == download.headers['x-content-sha256']
    assert service.owner_operations.leases[identifier] == 0
    operation = client.post('/api/owner/operations', json={'kind': 'restore', 'size': len(download.content)}).json()
    route = '/api/owner/operations/'+operation['id']
    received = client.put(route+'/content', content=download.content).json()
    assert received['state'] == 'UPLOADED'
    assert client.post(route+'/confirm', json={'action': 'restore', 'sha256': received['sha256']}).status_code == 409
    assert client.post(route+'/confirm', json={'action': 'inspect', 'sha256': '0'*64}).status_code == 409
    assert client.post(route+'/confirm', json={'action': 'inspect', 'sha256': received['sha256']}).status_code == 200
    checked = wait(service, operation['id'])
    assert checked['state'] == 'AWAITING_CONFIRMATION'
    assert checked['inspection']['notes'] == 1
    note = client.get('/api/note?path=State.md').json()
    client.put('/api/note', json={'path': 'State.md', 'text': 'after', 'expected_sha256': note['sha256']})
    assert client.post(route+'/confirm', json={'action': 'restore', 'sha256': received['sha256']}).status_code == 200
    restored = wait(service, operation['id'])
    assert restored['state'] == 'COMPLETED', failures
    assert client.get('/api/auth/session').status_code == 401
    authenticate(client)
    assert client.get('/api/note?path=State.md').json()['text'] == 'before'
    assert client.get(route).json()['stage'] == 'RESTORED'


def test_upload_limits_fail_cleanup_and_active_download_lease(api):
    client, service = api
    authenticate(client)
    assert client.post('/api/owner/operations', json={'kind': 'restore', 'size': 8*1024**3+1}).status_code == 413
    identifier = client.post('/api/owner/operations', json={'kind': 'restore', 'size': 3}).json()['id']
    route = '/api/owner/operations/'+identifier
    assert client.put(route+'/content', content=b'overflow').status_code == 413
    assert not (service.owner_operations.directory / identifier / 'upload.zip').exists()
    assert client.get(route).json()['state'] == 'FAILED'
    assert client.delete(route).status_code == 200
    assert client.get(route).status_code == 404
    identifier = client.post('/api/owner/operations', json={'kind': 'logs'}).json()['id']
    assert wait(service, identifier)['state'] == 'COMPLETED'
    service.owner_operations.download(identifier)
    assert client.delete('/api/owner/operations/'+identifier).status_code == 409
    service.owner_operations.release(identifier)
    assert client.delete('/api/owner/operations/'+identifier).status_code == 200


def test_exact_rotation_requires_two_matching_values_and_preserves_old_session_on_failure(api):
    client, _ = api
    authenticate(client)
    values = {'current_access_key': ' exact 🔐 key ', 'new_access_key': ' \r\n次🔑 '}
    assert client.post('/api/auth/rotate', json=values).status_code == 422
    assert client.post('/api/auth/rotate', json={**values, 'confirm_access_key': 'different'}).status_code == 422
    assert client.get('/api/auth/session').status_code == 200
    assert client.post('/api/auth/rotate', json={**values, 'confirm_access_key': values['new_access_key']}).status_code == 200
    assert client.get('/api/auth/session').status_code == 200


def test_expired_download_rejected_while_existing_lease_can_finish(api):
    _, service = api
    operations = service.owner_operations
    identifier = operations.create('logs')['id']
    record = wait(service, identifier)
    operations.download(identifier)
    operations.save(record, expires_at=time.time()-1)
    with pytest.raises(DomainError, match='expired'):
        operations.download(identifier)
    operations.cleanup()
    assert (operations.directory / identifier).exists()
    operations.release(identifier)
    operations.cleanup()
    assert not (operations.directory / identifier).exists()


def test_completed_operation_survives_audit_failure(api, monkeypatch):
    _, service = api
    original = service.audit.emit
    def failed(action, **kwargs):
        if action.startswith('owner.'):
            raise OSError('generated disk failure')
        return original(action, **kwargs)
    monkeypatch.setattr(service.audit, 'emit', failed)
    identifier = service.owner_operations.create('logs')['id']
    assert wait(service, identifier)['state'] == 'COMPLETED'
    service.owner_operations.thread.join()
    assert service.operation_audit_failure == 'AUDIT_UNAVAILABLE'


def test_operation_parent_symlink_is_not_followed(api, tmp_path):
    import os
    if os.name != 'posix':
        pytest.skip('Linux descriptor boundary')
    _, service = api
    operations = service.owner_operations
    identifier = operations.create('restore', 3)['id']
    original = operations.directory / identifier
    moved = tmp_path / 'outside-operation'
    original.rename(moved)
    original.symlink_to(moved, target_is_directory=True)
    try:
        with pytest.raises(DomainError, match='ordinary directory'):
            operations.read(identifier)
    finally:
        original.unlink()
        moved.rename(original)
