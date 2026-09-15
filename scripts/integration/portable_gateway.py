"""Inbound-only fixture display proxy; isolated Obsidian has no outside network route."""
import asyncio

active = set()


async def connection(reader, writer):
    if len(active) >= 64:
        writer.close()
        return
    active.add(writer)
    upstream = None
    tasks = []
    try:
        remote, upstream = await asyncio.wait_for(asyncio.open_connection("obsidian", 8090), 5)
        async def copy(source, target):
            while chunk := await source.read(64*1024):
                target.write(chunk)
                await target.drain()
        tasks = [asyncio.create_task(copy(reader, upstream)), asyncio.create_task(copy(remote, writer))]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (OSError, TimeoutError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if upstream:
            upstream.close()
        writer.close()
        active.discard(writer)


async def main():
    server = await asyncio.start_server(connection, "0.0.0.0", 8090)
    async with server:
        await server.serve_forever()


asyncio.run(main())
