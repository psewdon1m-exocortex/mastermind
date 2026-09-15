"""Host paths for the local Docker engine (Docker Desktop on Windows)."""
from pathlib import Path


def bind_path(path):
    return str(Path(path).resolve())
