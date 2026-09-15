"""Generate only owned synthetic acceptance data inside the disposable host Core."""
import hashlib
import json
import os
from pathlib import Path

root=Path('/data/vault/current')
target=root/'Host qualification.bin'
if target.exists():
    raise SystemExit('Owned fixture already exists; inspect its receipt instead of overwriting')
temporary=root/'.host-qualification-generating'
digest=hashlib.sha256()
with temporary.open('xb') as output:
    for _ in range(350):
        block=os.urandom(1024*1024)
        output.write(block)
        digest.update(block)
    output.flush()
    os.fsync(output.fileno())
temporary.rename(target)
opaque=root/'.obsidian/plugins/qualification-opaque'
opaque.mkdir()
(opaque/'data.json').write_bytes(b'{"synthetic_plugin_secret":"opaque-qualification-only-0123456789"}\n')
print(json.dumps({'fixture':target.name,'size':target.stat().st_size,'sha256':digest.hexdigest(),'opaque_plugin_fixture':True}))
