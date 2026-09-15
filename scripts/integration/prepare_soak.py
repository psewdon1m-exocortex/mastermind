"""Create independent disposable credentials for the eight-hour Runtime session."""
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[2] / ".local/runtime-soak"
root.mkdir(parents=True, exist_ok=True)
if not (root / "core/bootstrap_access_key").exists():
    common = {name: secrets.token_urlsafe(32) for name in ("bridge_token", "runtime_token", "vnc_password")}
    for scope, values in (("core", {**common, "bootstrap_access_key": secrets.token_urlsafe(32)}), ("runtime", common)):
        (root / scope).mkdir(mode=0o700)
        for name, value in values.items():
            with os.fdopen(os.open(root / scope / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
                output.write(value)
print("Independent disposable Runtime soak credentials ready")
