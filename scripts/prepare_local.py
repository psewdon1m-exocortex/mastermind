"""Generate disposable local integration credentials; never a production bootstrap."""
import base64
import os
import secrets
from pathlib import Path

import pyrage
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

directory = Path(__file__).resolve().parents[1] / ".local" / "secrets"
if os.name == "posix" and os.geteuid() != 0:
    raise SystemExit("On Linux run this one-time local credential preparation as root so the fixed container GID can read its own files.")
directory.mkdir(mode=0o700, parents=True, exist_ok=True)
if (directory / "core/bootstrap_access_key").exists():
    print("Existing disposable local credentials retained.")
else:
    identity = pyrage.x25519.Identity.generate()
    key = Ed25519PrivateKey.generate()
    common = {name: secrets.token_urlsafe(32) for name in ("bridge_token", "runtime_token", "vnc_password")}
    core = {**common, "bootstrap_access_key": secrets.token_urlsafe(32),
            "recovery_identity": str(identity), "recovery_recipient": str(identity.to_public()),
            "backup_signing_private": base64.b64encode(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode(),
            "backup_signing_public": base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode(),
            "share_pepper_v1": secrets.token_urlsafe(32)}
    for scope, values in (("core", core), ("runtime", common)):
        (directory / scope).mkdir(mode=0o700, exist_ok=True)
        for name, value in values.items():
            with os.fdopen(os.open(directory / scope / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
                output.write(value)
    print("Disposable local credentials created in the ignored .local directory.")

(directory / "worker").mkdir(mode=0o700, exist_ok=True)
paths = [directory / scope / "worker_token" for scope in ("core", "worker")]
existing = [path.read_bytes() for path in paths if path.exists()]
if len(set(existing)) > 1:
    raise SystemExit("Existing Core and Worker credentials differ; resolve the local fixture explicitly.")
value = existing[0] if existing else secrets.token_urlsafe(32).encode()
for path in paths:
    if not path.exists():
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
            output.write(value)
if os.name == "posix":
    for scope in ("core", "runtime", "worker"):
        folder = directory / scope
        os.chown(folder, 0, 10001)
        folder.chmod(0o750)
        for path in folder.iterdir():
            if not path.is_file() or path.is_symlink():
                raise SystemExit("Unexpected local credential entry")
            os.chown(path, 0, 10001)
            path.chmod(0o640)
print("Scoped Core/Runtime/Worker fixture credentials are ready; values were not printed.")
