"""Run in a network-disabled Core image with only the scoped Neptune Unix socket."""
import asyncio
import hashlib
import json
from pathlib import Path

from mastermind.config import Config
from mastermind.integrations import Neptune


async def main():
    fixture = json.loads(Path("/fixture/reader-fixture.json").read_text())
    config = Config(Path("/tmp/core-reader"), neptune_socket="/run/neptune/neptuned.sock",
                    neptune_token_file=Path("/fixture/neptune-control.token"))
    adapter = Neptune(config)
    metadata = await adapter.request("resource-metadata", fixture["path"])
    assert metadata["size_bytes"] == fixture["size"]
    response = await adapter.request("resource-content", fixture["path"])
    digest = hashlib.sha256()
    async for chunk in adapter.stream(response):
        digest.update(chunk)
    assert digest.hexdigest() == fixture["sha256"] and adapter.active == 0
    response = await adapter.request("resource-content", fixture["path"], headers={"Range": "bytes=100-399"})
    assert response.status_code == 206
    chunks = [chunk async for chunk in adapter.stream(response)]
    assert b"".join(chunks) == (bytes(range(256)) * 2)[100:400]
    assert adapter.active == 0
    await adapter.close()
    print("PASS: actual Core adapter in network-disabled container -> scoped Unix socket -> Neptune -> Saturn/SFTP.")


asyncio.run(main())
