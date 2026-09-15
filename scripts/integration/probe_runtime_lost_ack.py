"""Exercise lost control responses against the real isolated Obsidian Runtime.

Run inside this task's idle soak Core before starting the long probe. Only the
client acknowledgement is faulted; supervisor/Bridge/Obsidian remain real.
"""
import json
import secrets
import time
from urllib.parse import urlsplit

from mastermind.config import Config
from mastermind.errors import DomainError
from mastermind.fs import sha_file
from mastermind.runtime_client import RuntimeClient
from mastermind.secret_store import read_credential_file


def main():
    config = Config.environment()
    assert config.secret_backend == "development-files" and urlsplit(config.public_url).hostname == "localhost"
    note = config.vault / "Runtime soak.md"
    assert note.is_file(), "This probe is restricted to the generated soak fixture"
    before = sha_file(note)
    client = RuntimeClient(config, lambda: read_credential_file(config.secret_directory / "runtime_token"))
    original = client.request
    def ready():
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            status = original("GET", "/internal/status", timeout=10)
            lifecycle = original("GET", "/internal/lifecycle", timeout=10)
            if status.get("bridge", {}).get("ready") and not lifecycle.get("paused"):
                return
            time.sleep(0.5)
        raise AssertionError("Native Runtime did not return to ready after the cancelled pause")
    ready()
    results = []
    for native in (False, True):
        identity = "qualification-lost-" + secrets.token_hex(8)
        fault_route = "/internal/native-prepare" if native else "/internal/quiesce"
        calls = []
        def lost_ack(method, route, payload=None, *, _calls=calls, _fault_route=fault_route, **kwargs):
            result = original(method, route, payload, **kwargs)
            _calls.append(route)
            if route == _fault_route:
                raise DomainError("RUNTIME_UNAVAILABLE", "Synthetic lost acknowledgement after real supervisor acceptance", 503)
            return result
        client.request = lost_ack
        started = time.monotonic()
        try:
            if native:
                client.prepare_native(identity)
            else:
                with client.pause(identity):
                    raise AssertionError("An unacknowledged pause must not reach the caller mutation")
        except DomainError as error:
            assert error.code == "RUNTIME_UNAVAILABLE"
        else:
            raise AssertionError("The injected response loss was not observed")
        finally:
            client.request = original
        assert "/internal/cancel-quiesce" in calls and not client.pending_cancellations
        ready()
        assert sha_file(note) == before
        results.append({"kind": "native-prepare" if native else "snapshot-pause", "status": "PASS",
                        "seconds": round(time.monotonic() - started, 3)})
    print(json.dumps({"schema": "mastermind.runtime-lost-ack.v1", "status": "PASS", "checks": results,
                      "saved_note_sha256": before, "real_supervisor_bridge_obsidian": True}))


if __name__ == "__main__":
    main()
