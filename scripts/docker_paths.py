"""Explicit bind-path translation for the isolated WSL qualification daemon."""
import os
import re
from pathlib import Path


def bind_path(path):
    value = Path(path).resolve()
    if os.environ.get("MASTERMIND_DOCKER_PATH_STYLE") != "wsl":
        return str(value)
    if os.name != "nt" or not re.fullmatch(r"[A-Za-z]:", value.drive):
        raise ValueError("WSL bind translation requires a local Windows drive path")
    return "/mnt/" + value.drive[0].lower() + "/" + value.as_posix()[3:]
