"""Create independent disposable credentials for the eight-hour Runtime session."""
import argparse
import os
import re
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--name", default="runtime-soak")
args = parser.parse_args()
if not re.fullmatch(r"runtime-soak(?:-[a-z0-9-]+)?", args.name):
    raise SystemExit("Use an isolated Runtime soak fixture name")
root = Path(__file__).resolve().parents[2] / ".local" / args.name
root.mkdir(parents=True, exist_ok=True)
if not (root / "core/bootstrap_access_key").exists():
    common = {name: secrets.token_urlsafe(32) for name in ("bridge_token", "runtime_token", "vnc_password")}
    for scope, values in (("core", {**common, "bootstrap_access_key": secrets.token_urlsafe(32)}), ("runtime", common)):
        (root / scope).mkdir(mode=0o700)
        for name, value in values.items():
            with os.fdopen(os.open(root / scope / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
                output.write(value)
print("Independent disposable Runtime soak credentials ready")
