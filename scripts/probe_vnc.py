import asyncio

from websockets.asyncio.client import connect

from mastermind.api import Service
from mastermind.config import Config


async def main():
    context = Service(Config.environment())
    try:
        for path in ("/websockify", "/", "/websockify?", "/websockify?path=websockify"):
            try:
                async with connect("ws://runtime:8090" + path, additional_headers=context.vnc_headers(),
                                   subprotocols=["binary"], origin="http://runtime:8090", proxy=None, open_timeout=3) as socket:
                    print(path, "CONNECTED", repr(await asyncio.wait_for(socket.recv(), 2))[:80])
            except Exception as error:  # noqa: BLE001 - diagnostic probe reports protocol failures
                print(path, type(error).__name__, getattr(getattr(error, "response", None), "status_code", None))
    finally:
        context.state.close()


asyncio.run(main())
