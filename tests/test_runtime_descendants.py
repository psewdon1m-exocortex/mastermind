import os
import subprocess
import sys
import json

import pytest


@pytest.mark.skipif(os.name != "posix", reason="Linux Runtime lifecycle")
def test_fresh_profile_preserves_native_trust_and_clears_pending_only_after_bridge(tmp_path, monkeypatch):
    import mastermind.runtime_supervisor as module
    monkeypatch.setattr(module, "install_bridge_files", lambda *_: None)
    supervisor = module.Supervisor()
    supervisor.home, supervisor.vault = tmp_path, tmp_path/"vault"
    supervisor.install_bridge()
    marker = tmp_path/"mastermind-native-setup.json"
    assert marker.exists()
    profile = tmp_path/".config/obsidian/obsidian.json"
    assert set(json.loads(profile.read_text())) == {"vaults", "updateDisabled"}
    monkeypatch.setattr(supervisor, "running", lambda: True)
    monkeypatch.setattr(supervisor, "bridge", lambda _: {"ready": False})
    assert supervisor.status()["owner_setup_required"] is True
    monkeypatch.setattr(supervisor, "bridge", lambda _: {"ready": True})
    assert supervisor.status()["owner_setup_required"] is False
    supervisor.install_bridge()
    assert not marker.exists()


@pytest.mark.skipif(os.name != "posix", reason="Linux child-subreaper semantics")
def test_double_forked_new_session_writer_blocks_stop_and_start(tmp_path):
    # Isolate subreaper state from pytest and its other child processes.
    script = r'''
import os, signal, subprocess, sys, time
from pathlib import Path
from mastermind.runtime_supervisor import Supervisor
from mastermind.errors import DomainError
supervisor = Supervisor()
folder = Path(sys.argv[1])
code = """
import os, sys, time
from pathlib import Path
folder=Path(sys.argv[1])
if os.fork(): os._exit(0)
os.setsid()
(folder/'child.pid').write_text(str(os.getpid()))
while True:
    (folder/'writer.txt').write_text('uncontrolled saved edit')
    time.sleep(.02)
"""
former_parent = subprocess.Popen([sys.executable,'-c',code,str(folder)],start_new_session=True)
supervisor.obsidian = former_parent
former_parent.wait(timeout=5)
deadline=time.monotonic()+5
while not (folder/'child.pid').exists() and time.monotonic()<deadline: time.sleep(.01)
pid=int((folder/'child.pid').read_text())
try:
    assert os.getpgid(pid)==pid and pid!=former_parent.pid
    for action in (lambda:supervisor.stop_verified('test'),supervisor.verify_no_writers):
        try: action()
        except DomainError as error: assert error.code=='VAULT_BUSY'
        else: raise AssertionError('Orphan writer was declared stopped')
    supervisor.allowed=True
    try: supervisor.start()
    except DomainError as error: assert error.code=='VAULT_BUSY'
    else: raise AssertionError('A new editor started beside an orphan writer')
    assert (folder/'writer.txt').read_text()=='uncontrolled saved edit'
finally:
    os.kill(pid,signal.SIGTERM)
    os.waitpid(pid,0)
supervisor.stop_verified('after-fixture-cleanup')
print('PASS adopted setsid writer rejected before stop/start; no data overwritten')
'''
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
