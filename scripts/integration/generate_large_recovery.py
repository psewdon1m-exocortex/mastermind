"""Create a representative synthetic recovery archive from a local test backup.

Run in an isolated, network-disabled Core container. No running service volume
is mounted. Key paths refer only to generated qualification credentials.
"""
import hashlib
import json
import os
import time
from pathlib import Path

from mastermind.audit import Audit
from mastermind.auth import Auth
from mastermind.backup import Backup
from mastermind.config import Config
from mastermind.coordinator import Coordinator
from mastermind.restore import Restore
from mastermind.runtime_client import RuntimeClient
from mastermind.secret_store import SecretStore
from mastermind.state import State
from mastermind.vault import Vault


def main():
    root = Path("/qualification")
    config = Config(root / "generated-home", runtime_mode="offline", test_mode=True,
                    bridge_artifacts=Path("/app/bridge"))
    if config.state.exists():
        raise RuntimeError("Use a fresh qualification directory; existing state is preserved.")
    state = State(config.state / "mastermind.sqlite3")
    coordinator = Coordinator(config, state, RuntimeClient(config))
    vault = Vault(config, state, coordinator)
    audit = Audit(config, state)
    auth = Auth(state, audit)
    backup = Backup(config, state, coordinator, vault, SecretStore(Path("/secrets")), audit)
    try:
        Restore(backup, auth).apply(root / "original.zip", create_safety_backup=False)
        target = config.vault / "Large qualification.bin"
        digest = hashlib.sha256()
        with target.open("xb") as stream:
            for _ in range(350):
                block = os.urandom(1024**2)
                stream.write(block)
                digest.update(block)
            stream.flush()
            os.fsync(stream.fileno())
        started = time.monotonic()
        output = root / "large.zip"
        backup.create(output)
        record = {"synthetic_data": True, "attachment_bytes": target.stat().st_size,
                  "attachment_sha256": digest.hexdigest(), "archive_bytes": output.stat().st_size,
                  "generation_seconds": round(time.monotonic()-started, 3)}
        (root / "fixture.json").write_text(json.dumps(record, indent=2))
        print(json.dumps(record), flush=True)
    finally:
        state.close()


if __name__ == "__main__":
    main()
