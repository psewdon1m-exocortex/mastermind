"""Exercise the combined Weaver Settings GUI in a disposable native Core."""
import os
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn

from mastermind.api import create_app
from mastermind.config import Config


def main():
    with tempfile.TemporaryDirectory(prefix='weaver-ui-') as directory:
        home = Path(directory)
        credentials = home/'credentials'
        credentials.mkdir()
        key = credentials/'bootstrap_access_key'
        key.write_text(secrets.token_urlsafe(32), encoding='utf-8')
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        origin = f'http://127.0.0.1:{listener.getsockname()[1]}'
        config = Config(home=home/'core', public_url=origin, runtime_mode='offline', test_mode=True,
                        secret_backend='development-files', secret_directory=credentials)
        app = create_app(config)
        app.state.service.vault.write('root.md', '# root', None, create=True)
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic()+30
            while time.monotonic() < deadline:
                try:
                    if httpx.get(origin+'/healthz', trust_env=False, timeout=1).status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(.1)
            else:
                raise AssertionError('Core startup deadline')
            subprocess.run(['node', 'scripts/probe_context_indexing.cjs'], check=True, timeout=120,
                env={**os.environ, 'CONTEXT_PROBE_ORIGIN': origin, 'CONTEXT_PROBE_KEY_FILE': str(key),
                     'CONTEXT_PROBE_OUTPUT': 'artifacts/weaver/ui'})
        finally:
            server.should_exit = True
            thread.join(timeout=30)
            listener.close()


if __name__ == '__main__':
    main()
