import base64

import pyrage
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from mastermind.audit import Audit
from mastermind.auth import Auth
from mastermind.backup import Backup
from mastermind.config import Config
from mastermind.coordinator import Coordinator
from mastermind.fs import atomic_write
from mastermind.restore import Restore
from mastermind.runtime_client import RuntimeClient
from mastermind.secret_store import SecretStore
from mastermind.state import State
from mastermind.vault import Vault


@pytest.fixture
def service(tmp_path):
    config = Config(tmp_path, runtime_mode="offline", test_mode=True)
    state = State(config.state / "mastermind.db")
    coordinator = Coordinator(config, state, RuntimeClient(config))
    vault = Vault(config, state, coordinator)
    yield config, state, coordinator, vault
    state.close()

@pytest.fixture
def recovery(service, tmp_path):
    config, state, coordinator, vault = service
    directory = tmp_path / "external-recovery-keys"
    directory.mkdir()
    identity = pyrage.x25519.Identity.generate()
    key = Ed25519PrivateKey.generate()
    values = {
        "recovery_identity": str(identity), "recovery_recipient": str(identity.to_public()),
        "backup_signing_private": base64.b64encode(
            key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode(),
        "backup_signing_public": base64.b64encode(key.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw)).decode(),
        "share_pepper_v1": "a-test-only-opaque-pepper-value",
    }
    for name, value in values.items():
        atomic_write(directory / name, value.encode())
    audit = Audit(config, state)
    auth = Auth(state, audit)
    backup = Backup(config, state, coordinator, vault, SecretStore(directory), audit)
    return backup, Restore(backup, auth), auth



