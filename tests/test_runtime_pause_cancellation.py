import threading
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from mastermind.errors import DomainError
from mastermind.runtime_client import RuntimeClient
from mastermind.runtime_supervisor import Supervisor


@pytest.fixture
def supervisor():
    # Only the transport/lease state machine is synthetic here. Real process,
    # dirty-buffer and browser boundaries have separate image/host tests.
    supervisor = object.__new__(Supervisor)
    supervisor.lock = threading.RLock()
    supervisor.leases, supervisor.cancelled_quiesces = set(), set()
    supervisor.native_operation = None
    supervisor.running = lambda: False
    supervisor.stops, supervisor.starts = [], []
    supervisor.stop_verified = lambda identity: supervisor.stops.append(identity)
    supervisor.start = lambda: supervisor.starts.append(set(supervisor.leases))
    return supervisor


def test_cancel_before_a_delayed_quiesce_prevents_a_late_orphan(supervisor):
    assert supervisor.cancel_quiesce("lost") == {"cancelled": True}
    with pytest.raises(DomainError) as error:
        supervisor.quiesce("lost")
    assert error.value.code == "QUIESCE_CANCELLED"
    assert not supervisor.leases and not supervisor.stops


def test_cancel_after_acceptance_releases_only_its_own_lease(supervisor):
    supervisor.quiesce("retained-update")
    supervisor.quiesce("lost")
    supervisor.cancel_quiesce("lost")
    assert supervisor.leases == {"retained-update"}
    assert supervisor.starts[-1] == {"retained-update"}
    supervisor.cancel_quiesce("lost")
    assert supervisor.leases == {"retained-update"}


def test_cancelled_identity_limit_never_evicts_a_tombstone(supervisor):
    supervisor.cancelled_quiesces = {str(number) for number in range(1024)}
    supervisor.cancel_quiesce("overflow")
    assert len(supervisor.cancelled_quiesces) == 1024
    for identity in ("0", "overflow", "another"):
        with pytest.raises(DomainError):
            supervisor.quiesce(identity)
    assert not supervisor.stops


@pytest.mark.parametrize("lost_cancel_response", [False, True])
def test_lost_pause_ack_never_mutates_and_reconciles_transport_recovery(service, supervisor, lost_cancel_response):
    config = replace(service[0], runtime_mode="supervised")
    client = RuntimeClient(config)
    cancellations = []
    def request(method, route, payload=None, **kwargs):
        if route == "/internal/quiesce":
            supervisor.quiesce(payload["operation_id"])
            raise DomainError("RUNTIME_UNAVAILABLE", "Synthetic lost acknowledgement", 503)
        assert route == "/internal/cancel-quiesce"
        result = supervisor.cancel_quiesce(payload["operation_id"])
        cancellations.append(payload["operation_id"])
        if lost_cancel_response and len(cancellations) == 1:
            raise DomainError("RUNTIME_UNAVAILABLE", "Synthetic lost cancellation response", 503)
        return result
    client.request = request
    with pytest.raises(DomainError, match="lost acknowledgement"), client.pause("lost"):
        pytest.fail("The caller must not mutate without a verified pause")
    assert not supervisor.leases
    assert client.pending_cancellations == ({"lost"} if lost_cancel_response else set())
    client.reconcile_cancellations()
    assert not client.pending_cancellations and not supervisor.leases


def test_uncertain_accepted_apply_never_cancels_the_retained_barrier(service, supervisor):
    client = RuntimeClient(replace(service[0], runtime_mode="supervised"))
    calls = []
    def request(method, route, payload=None, **kwargs):
        calls.append(route)
        assert route == "/internal/quiesce"
        return supervisor.quiesce(payload["operation_id"])
    client.request = request
    retained = False
    with pytest.raises(DomainError, match="Apply acknowledgement"), client.pause("apply", resume_if=lambda: not retained):
        retained = True
        raise DomainError("UPDATER_UNAVAILABLE", "Lost Apply acknowledgement", 503)
    assert supervisor.leases == {"apply"}
    assert not client.pending_cancellations
    assert calls == ["/internal/quiesce"]


def test_cancel_unfreezes_only_its_own_safe_native_preparation(supervisor):
    calls = []
    supervisor.bridge = lambda *args: calls.append(args)
    supervisor.running = lambda: True
    supervisor.native_operation = "native"
    supervisor.cancel_quiesce("another")
    assert supervisor.native_operation == "native" and not calls
    supervisor.cancel_quiesce("native")
    assert supervisor.native_operation is None and calls == [("/unfreeze", {})]
    with pytest.raises(DomainError):
        supervisor.check_pause_identity("native")


@pytest.mark.parametrize("native", [False, True])
def test_lost_safe_release_is_reconciled_without_repeating_the_mutation(service, supervisor, native):
    client = RuntimeClient(replace(service[0], runtime_mode="supervised"))
    supervisor.leases.add("complete")
    if native:
        supervisor.native_operation = "complete"
    def request(method, route, payload=None, **kwargs):
        if route == ("/internal/native-release" if native else "/internal/resume"):
            raise DomainError("RUNTIME_UNAVAILABLE", "Synthetic lost release request", 503)
        assert route == "/internal/cancel-quiesce"
        return supervisor.cancel_quiesce(payload["operation_id"])
    client.request = request
    client.release_pause("complete", native=native)
    assert not client.pending_cancellations and not supervisor.leases
    assert supervisor.native_operation is None


def test_lost_native_prepare_ack_is_cancelled_before_a_file_plan_exists(service, supervisor):
    client = RuntimeClient(replace(service[0], runtime_mode="supervised"))
    def request(method, route, payload=None, **kwargs):
        if route == "/internal/native-prepare":
            supervisor.native_operation = payload["operation_id"]
            raise DomainError("RUNTIME_UNAVAILABLE", "Synthetic lost native preparation acknowledgement", 503)
        assert route == "/internal/cancel-quiesce"
        return supervisor.cancel_quiesce(payload["operation_id"])
    client.request = request
    with pytest.raises(DomainError, match="native preparation"):
        client.prepare_native("native")
    assert supervisor.native_operation is None and not client.pending_cancellations
    with pytest.raises(DomainError):
        supervisor.check_pause_identity("native")


def test_cancellation_control_route_requires_its_private_principal(supervisor, monkeypatch):
    from types import SimpleNamespace

    import mastermind.runtime_supervisor as module
    supervisor.secrets = SimpleNamespace(read=lambda name: "synthetic-runtime-qualification-control")
    monkeypatch.setattr(module, "Supervisor", lambda: supervisor)
    client = TestClient(module.create_app())
    assert client.post("/internal/cancel-quiesce", json={"operation_id": "native"}).status_code == 401
    assert not supervisor.cancelled_quiesces
    headers = {"Authorization": "Bearer synthetic-runtime-qualification-control"}
    assert client.post("/internal/cancel-quiesce", headers=headers, json={"operation_id": "../invalid"}).status_code == 422
    assert not supervisor.cancelled_quiesces
    response = client.post("/internal/cancel-quiesce", headers=headers, json={"operation_id": "native"})
    assert response.status_code == 200 and response.json() == {"cancelled": True}
    assert supervisor.cancelled_quiesces == {"native"}
