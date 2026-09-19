import hashlib
import json

import httpx
import pytest

from mastermind.errors import DomainError
from mastermind.kernel import Kernel, checked_origin
from mastermind.secret_store import SHELL_BINDINGS, ShellSecrets

REF = "volt://7183e550-f61b-4c3c-827f-434aa07ba3af/1"


def fixture_peer():
    values = {"services": {"mastermind": {"secrets": {"chronos_service_token": REF}}}}
    snapshot = {"schema": "exocortex.register.snapshot.v1", "values": values,
                "checksum": "sha256:" + hashlib.sha256(json.dumps({"values": values},
                    ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    state = {"calls": 0, "value": "  opaque\n秘密\t  ", "status": 200, "snapshot": snapshot}

    def handler(request):
        state["calls"] += 1
        assert request.headers["authorization"] == "Bearer fixture-credential"
        if request.method == "GET":
            return httpx.Response(state["status"], json=state["snapshot"])
        assert json.loads(request.content) == {"keys": [SHELL_BINDINGS["chronos_service_token"]]}
        return httpx.Response(state["status"], json={"schema": "exocortex.register.resolution.v1", "values": {
            SHELL_BINDINGS["chronos_service_token"]: {"value": state["value"], "secret": True, "volt_revision": 1}}})
    return state, httpx.Client(transport=httpx.MockTransport(handler))


def test_exact_memory_cache_expiry_rotation_and_cold_start(tmp_path):
    peer, client = fixture_peer()
    clock = [0]
    kernel = Kernel("https://kernel.local", lambda: "fixture-credential", client=client, clock=lambda: clock[0])
    store = ShellSecrets(tmp_path, kernel)
    assert store.read("chronos_service_token") == "  opaque\n秘密\t  "
    assert peer["calls"] == 2
    peer["status"] = 503
    assert store.read("chronos_service_token") == peer["value"]
    clock[0] = 61
    with pytest.raises(DomainError):
        store.read("chronos_service_token")
    # A local plaintext file cannot become a fallback when Kernel resolution fails.
    (tmp_path / "chronos_service_token").write_text("forbidden-fallback")
    assert not store.available("chronos_service_token")
    peer.update(status=200, value="rotated")
    assert store.read("chronos_service_token") == "rotated"
    kernel.invalidate()
    peer["status"] = 503
    assert not store.available("chronos_service_token")
    assert list(tmp_path.iterdir()) == [tmp_path / "chronos_service_token"]
    kernel.close()
    assert kernel.cache == {}


@pytest.mark.parametrize("fault", ["hash", "plaintext", "missing", "schema", "oversize", "redirect"])
def test_untrusted_register_responses_are_bounded_and_do_not_replace_cache(fault):
    peer, client = fixture_peer()
    kernel = Kernel("https://kernel.local", lambda: "fixture-credential", client=client)
    if fault == "hash":
        peer["snapshot"]["checksum"] = "sha256:" + "0" * 64
    elif fault == "plaintext":
        peer["snapshot"]["values"]["services"]["mastermind"]["secrets"]["chronos_service_token"] = "not-a-volt-ref"
    elif fault == "missing":
        peer["snapshot"]["values"] = {}
    elif fault == "schema":
        peer["snapshot"]["schema"] = "wrong"
    elif fault == "oversize":
        peer["snapshot"]["padding"] = "x" * (1024 * 1024)
    elif fault == "redirect":
        peer["status"] = 302
    with pytest.raises(DomainError):
        kernel.resolve([SHELL_BINDINGS["chronos_service_token"]])
    assert kernel.cache == {}


@pytest.mark.parametrize("origin", ["http://external.test", "https://user@host.test", "https://host.test/path",
    "https://host.test?token=secret", "https://host.test:0", "https://host.test:65536", "https://host.test/#fragment"])
def test_bad_bootstrap_origins(origin):
    with pytest.raises(DomainError):
        checked_origin(origin)


@pytest.mark.parametrize("origin", ["https://kernel.test", "https://kernel.test:443", "http://localhost:18180", "http://127.0.0.1:18180"])
def test_good_bootstrap_origins(origin):
    assert checked_origin(origin) == origin
