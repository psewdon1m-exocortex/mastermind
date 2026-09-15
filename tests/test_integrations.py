import asyncio
from dataclasses import replace

import httpx
import pytest

from mastermind.config import Config
from mastermind.errors import DomainError
from mastermind.integrations import Chronos, Neptune, resource_path


@pytest.mark.parametrize("path", ["root/../secret", "root/%2e%2e/private", "root\\private", "/root", "root//file", "root/file\0"])
def test_resource_path_is_canonical(path):
    with pytest.raises(DomainError):
        resource_path(path)


def neptune(tmp_path, handler):
    token = tmp_path / "control.token"
    token.write_text("fixture-neptune-token")
    config = Config(tmp_path, neptune_socket="/test/neptune.sock", neptune_token_file=token)
    return Neptune(config, client=httpx.AsyncClient(base_url="http://neptune", transport=httpx.MockTransport(handler)))


def test_stream_lease_released_on_cancel_and_four_active_limit(tmp_path):
    async def run():
        class Content(httpx.AsyncByteStream):
            closed = False

            async def __aiter__(self):
                yield b"a" * (256 * 1024)
                await asyncio.sleep(60)

            async def aclose(self):
                self.closed = True
        streams = []

        def handler(request):
            assert request.headers["X-Neptune-Purpose"] == "owner-reference"
            assert request.headers["X-Neptune-Token"] == "fixture-neptune-token"
            stream = Content()
            streams.append(stream)
            return httpx.Response(200, headers={"content-length": str(512 * 1024), "etag": '"v1"'}, stream=stream)
        adapter = neptune(tmp_path, handler)
        opened = [await adapter.request("resource-content", "root/file") for _ in range(4)]
        assert adapter.active == 4
        with pytest.raises(DomainError) as full:
            await adapter.request("resource-content", "root/file")
        assert full.value.status == 429
        generator = adapter.stream(opened[0])
        assert len(await anext(generator)) == 256 * 1024
        task = asyncio.create_task(anext(generator))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert adapter.active == 3 and streams[0].closed
        for response in opened:
            await adapter.release(response)
        assert adapter.active == 0 and all(stream.closed for stream in streams)
        await adapter.close()
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["outside", "nested", "oversize", "type", "cursor", "timeout", "404", "401", "redirect"])
def test_metadata_errors_release_slots_and_do_not_expose_upstream_payload(tmp_path, fault):
    entry = {"path": "root/child", "size_bytes": 0, "type": "file", "etag": '"v1"'}
    result = {"entries": [entry], "next_cursor": None}
    if fault == "outside":
        entry["path"] = "root-other/private"
    elif fault == "nested":
        entry["path"] = "root/child/private"
    elif fault == "oversize":
        result["padding"] = "x" * (1024 * 1024)
    elif fault == "type":
        entry["size_bytes"] = True
    elif fault == "cursor":
        result["next_cursor"] = "x" * 2049

    def handler(request):
        if fault == "timeout":
            raise httpx.ReadTimeout("private upstream secret")
        return httpx.Response(int(fault) if fault.isdigit() else 302 if fault == "redirect" else 200, json=result)

    async def run():
        adapter = neptune(tmp_path, handler)
        for _ in range(6):
            with pytest.raises(DomainError) as error:
                await adapter.request("resources", "root")
            assert "private upstream secret" not in str(error.value)
            assert adapter.active == 0
        await adapter.close()
    asyncio.run(run())


def test_shared_and_missing_configuration_never_open_transport(tmp_path):
    def forbidden(request):
        pytest.fail("Forbidden request reached Neptune")
    async def run():
        adapter = neptune(tmp_path, forbidden)
        with pytest.raises(DomainError) as shared:
            await adapter.request("resources", "root", purpose="shared")
        assert shared.value.status == 403
        adapter.config = replace(adapter.config, neptune_token_file=None)
        with pytest.raises(DomainError) as missing:
            await adapter.request("resources", "root")
        assert missing.value.code == "NEPTUNE_NOT_CONFIGURED"
        assert adapter.active == 0
        await adapter.close()
    asyncio.run(run())


def test_chronos_minimal_fields_and_thirty_second_cache():
    class Registry:
        def origin_for(self, service):
            assert service == "chronos"
            return "https://chronos.local"
    class Secrets:
        def read(self, name):
            assert name == "chronos_service_token"
            return "reader-token"
    clock = [0]
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer reader-token"
        assert request.headers["x-mastermind-purpose"] == "owner-reference"
        return httpx.Response(200, json={"schema": "chronos.mastermind-event.v1", "audience": "mastermind",
            "id": "t-12345678", "started_at": "2026-09-15T00:00:00+00:00", "ended_at": None,
            "private_note": "must not escape projection"})
    adapter = Chronos(Registry(), Secrets(), client=httpx.Client(transport=httpx.MockTransport(handler)), clock=lambda: clock[0])
    first = adapter.card("t-12345678")
    assert set(first) == {"kind", "id", "started_at", "ended_at"}
    clock[0] = 29
    assert adapter.card("t-12345678") == first and len(calls) == 1
    clock[0] = 30
    assert adapter.card("t-12345678") == first and len(calls) == 2
    adapter.close()
