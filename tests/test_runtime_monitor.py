import threading
from types import SimpleNamespace

from mastermind.runtime_monitor import RuntimeMonitor


def monitor(service):
    _, state, coordinator, vault = service
    calls = []
    def request(method, route, payload=None, **kwargs):
        calls.append(route)
        if route == "/internal/lifecycle":
            return {"boot_id": "new-boot", "busy": False, "paused": False, "running": False, "startup_allowed": False}
        return {}
    context = SimpleNamespace(config=SimpleNamespace(runtime_mode="supervised"), ready=True, state=state, vault=vault,
        coordinator=coordinator, runtime=SimpleNamespace(request=request), data_ready=lambda: None,
        updates=SimpleNamespace(blocks=False), dirty=SimpleNamespace(flush=lambda: calls.append("flush")),
        activity=SimpleNamespace(ingest=lambda value: None), audit=SimpleNamespace(emit=lambda *args, **kwargs: None))
    return RuntimeMonitor(context), calls


def test_independent_runtime_restart_repeats_recovery_before_reopening(service):
    observer, calls = monitor(service)
    observer.service.vault.write("Saved.md", "Durable text", None, create=True)
    observer.check()
    assert calls == ["/internal/lifecycle", "/internal/begin-recovery", "flush", "/internal/allow-start"]
    assert observer.boot == "new-boot" and observer.service.vault.read("Saved.md") == "Durable text"


def test_runtime_observer_never_releases_a_retained_update_or_native_barrier(service):
    observer, calls = monitor(service)
    observer.service.updates.blocks = True
    observer.check()
    assert not calls
    observer.service.updates.blocks = False
    observer.service.runtime.request = lambda *args, **kwargs: {"boot_id": "same", "paused": True, "running": False}
    observer.check()
    assert observer.boot is None
    acquired, release = threading.Event(), threading.Event()
    def mutation():
        with observer.service.coordinator.lock:
            acquired.set()
            release.wait(timeout=5)
    thread = threading.Thread(target=mutation)
    thread.start()
    assert acquired.wait(timeout=2)
    try:
        observer.service.runtime.request = lambda *args, **kwargs: calls.append("unexpected")
        observer.check()
        assert not calls
    finally:
        release.set()
        thread.join(timeout=2)
