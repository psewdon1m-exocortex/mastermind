"""Run inside the isolated Core; report only protocol metadata, never credentials."""
import asyncio
import base64
from pathlib import Path

import websockets


async def probe():
    credential = Path('/run/mastermind/vnc_password').read_text()
    authorization = 'Basic '+base64.b64encode(('mastermind:'+credential).encode()).decode()
    async with websockets.connect('ws://runtime:8090/websockify',
        additional_headers={'Authorization': authorization}, proxy=None, ping_interval=None,
        subprotocols=['binary'], compression=None, origin='http://localhost:18394') as socket:
        frame = await socket.recv()
        print('Initial frame bytes:', len(frame))
        pong = await socket.ping()
        try:
            await asyncio.wait_for(pong, 5)
            print('PONG_CONFIRMED')
        except TimeoutError:
            print('PONG_NOT_IMPLEMENTED')


asyncio.run(probe())
