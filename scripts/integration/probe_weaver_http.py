"""Disposable Core classes → actual Worker HTTP → local E5/Bibliotekar probe.

No production Vault, provider credential or remote service is used. Source
acquisition/generation are tested separately; this probe exercises Weaver itself.
"""
import argparse
import json
import os
import secrets
import socket
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import uvicorn

from mastermind.audit import Audit
from mastermind.config import Config
from mastermind.coordinator import Coordinator
from mastermind.errors import DomainError
from mastermind.runtime_client import RuntimeClient
from mastermind.secret_store import SecretStore
from mastermind.state import State
from mastermind.vault import Vault
from mastermind.weaver import Lookup, Scope, Similar, Walk, Weaver
from mastermind.worker import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, default=Path('artifacts/weaver/http.json'))
    args = parser.parse_args()
    root = args.root.resolve()
    with tempfile.TemporaryDirectory(prefix='weaver-http-') as directory:
        home = Path(directory)
        credentials = home/'credentials'
        credentials.mkdir()
        (credentials/'worker_token').write_text(secrets.token_urlsafe(32), encoding='utf-8')
        environment = {'MASTERMIND_WORK_DIRECTORY': home/'work',
            'MASTERMIND_WORKER_TOKEN_FILE': credentials/'worker_token',
            'MASTERMIND_MODEL_DIRECTORY': root/'.local/models/multilingual-e5-small',
            'MASTERMIND_MODEL_INVENTORY': root/'embedding-model.lock.json',
            'MASTERMIND_CURATOR_DIRECTORY': root/'.local/models/curator',
            'MASTERMIND_CURATOR_INVENTORY': root/'curator-model.lock.json'}
        before = {key: os.environ.get(key) for key in environment}
        os.environ.update({key: str(value) for key, value in environment.items()})
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        origin = f'http://127.0.0.1:{listener.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(create_app(), log_level='error', access_log=False))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        config = Config(home=home/'core', runtime_mode='offline', test_mode=True, worker_url=origin)
        state = State(config.state/'mastermind.db')
        coordinator = Coordinator(config, state, RuntimeClient(config))
        vault = Vault(config, state, coordinator)
        service = SimpleNamespace(config=config, state=state, coordinator=coordinator, vault=vault,
            audit=Audit(config, state), secrets=SecretStore(credentials), data_ready=lambda: None)
        engine = Weaver(service)
        thread.start()
        try:
            deadline = time.monotonic()+90
            while time.monotonic() < deadline:
                try:
                    health = engine.semantic.worker.request('GET', '/healthz', timeout=2)
                    if health['embeddings_ready'] and not health['active']:
                        break
                except DomainError as error:
                    if error.code not in {'WORKER_UNAVAILABLE', 'WORKER_TIMEOUT'}:
                        raise
                time.sleep(.2)
            else:
                raise AssertionError('Worker startup deadline')
            assert httpx.get(origin+'/healthz', trust_env=False).status_code == 401
            notes = {'root.md': '[[Birds]] [[Electronics]]',
                'Birds.md': '#main\nMigrating birds. [[Navigation]]',
                'Navigation.md': '#key\nMigrating birds navigate using magnetic fields and celestial cues.',
                'Migration.md': 'Bird migration uses a magnetic compass and celestial navigation. [[Navigation]]',
                'Electronics.md': '#main\nElectric circuits. [[Diode]]',
                'Diode.md': '#key\nA semiconductor diode permits electric current in one direction.',
                'Secret.md': 'Private hidden context and identifiers.'}
            coordinator.commit({p: t.encode() for p, t in notes.items()}, {p: None for p in notes})
            vault.index()
            engine.settings.bootstrap()
            for _ in range(100):
                if not engine.semantic.once():
                    break
            assert engine.semantic.status()['status'] == 'READY'
            query = engine.run(Lookup('Как перелётные птицы ориентируются по магнитному полю?'))
            assert any(i['path'] in {'Navigation.md', 'Migration.md'} for i in query['results'][:3]), query
            similar = engine.run(Similar('Migration.md', notes['Migration.md']))
            assert 'Navigation.md' in {i['path'] for i in similar['items']}
            limited = engine.run(Lookup('magnetic compass', scope=Scope('owner', frozenset({'Diode.md'}))))
            assert all(i['path'] == 'Diode.md' for i in limited['results'])
            walked = engine.run(Walk('Birds.md', direction='outgoing'))
            assert {n['id'] for n in walked['nodes']} == {'Birds.md', 'Navigation.md'}
            old = state.one("SELECT sha FROM notes WHERE path='Migration.md'")['sha']
            vault.write('Migration.md', 'Cooking bread and cakes.', old)
            # Stale vectors must disappear before the incremental rebuild.
            assert 'Migration.md' not in {i['path'] for i in engine.semantic.search('magnetic compass')['results']}
            for _ in range(100):
                if not engine.semantic.once():
                    break
            assert engine.semantic.status()['status'] == 'READY'
            assert vault.read('Secret.md') == notes['Secret.md']
            # Exercise the configured local assistant through the actual Worker
            # transport. Its terms cannot become independent relevance evidence.
            engine.service.state.set_setting('context_indexing', {**engine.settings.get(), 'curator_enabled': True})
            assisted = engine.run(Lookup('Sumerian cuneiform contracts on clay tablets',
                scope=Scope('owner', frozenset({'Diode.md'})), context='none'))
            assert assisted['bibliotekar']['invoked'] and assisted['bibliotekar']['passes'] == 1, assisted['bibliotekar']
            assert assisted['search_passes'] <= 2 and not assisted['results']
            assert assisted['evidence_packet']['schema'] == 'weaver.evidence.v1'
            report = {'status': 'PASS', 'transport': 'loopback HTTP with scoped Worker identity',
                'embedding_model': engine.semantic.model, 'bibliotekar': engine.bibliotekar.status(),
                'bibliotekar_assist': assisted['bibliotekar'],
                'checks': ['unauthorized denied', 'real bilingual retrieval', 'related notes', 'scoped retrieval',
                           'graph traversal', 'edit invalidation and incremental rebuild',
                           'one bounded real Bibliotekar call, original-topic verification and unchanged scope'],
                'limitations': ['No Runtime, Linux sandbox or external generation provider in this native probe.']}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
            print(json.dumps(report))
        finally:
            engine.semantic.close()
            server.should_exit = True
            thread.join(timeout=30)
            listener.close()
            state.close()
            for key, value in before.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == '__main__':
    main()
