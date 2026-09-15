"""Resolve only this task's Compose fixtures for its separate WSL Docker daemon."""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from docker_paths import bind_path


def translate(value, base):
    resolved = (base / value).resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError("Qualification bind escapes the task workspace")
    return bind_path(resolved)


def profile(source, base):
    document = yaml.safe_load(source.read_text("utf-8"))
    for service in document.get("services", {}).values():
        service.pop("build", None)  # Run only images already built and qualified.
        for position, mount in enumerate(service.get("volumes", [])):
            if isinstance(mount, dict):
                if mount.get("type") == "bind":
                    mount["source"] = translate(mount["source"], base)
                continue
            match = re.fullmatch(r"((?:[A-Za-z]:)?[^:]+):(/[^:]+)(?::([^:]+))?", mount)
            if not match:
                raise ValueError("Unexpected qualification mount syntax")
            origin, target, mode = match.groups()
            if origin.startswith((".", "/", "\\")) or re.match(r"[A-Za-z]:", origin):
                service["volumes"][position] = {"type": "bind", "source": translate(origin, base),
                                                "target": target, "read_only": mode == "ro"}
        if "env_file" in service or "configs" in service or "secrets" in service:
            raise ValueError("New fixture path-bearing fields require explicit review")
    return document


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci-report", type=Path, required=True)
    args = parser.parse_args()
    import os
    assert os.name == "nt" and os.environ.get("MASTERMIND_DOCKER_PATH_STYLE") == "wsl"
    report = json.loads(args.ci_report.read_text("utf-8"))
    assert report["status"] == "PASS" and set(report["images"]) == {"core", "runtime", "worker"}
    output = ROOT / ".local/wsl-fixture"
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    selections = {
        "integration": (ROOT / ".local/integration/compose.yml", ROOT / ".local/integration"),
        "development": (ROOT / "compose.development.yml", ROOT),
        "core-override": (ROOT / ".local/integration/core-override.yml", ROOT),
        "crusher-override": (ROOT / "scripts/integration/crusher-fixture.compose.yml", ROOT),
        "host-saturn": (ROOT / ".local/host-fixture/saturn-api/compose.yml", ROOT / ".local/host-fixture/saturn-api"),
    }
    for name, (source, base) in selections.items():
        value = profile(source, base)
        if name == "development":
            for component, image in report["images"].items():
                assert re.fullmatch(r"sha256:[a-f0-9]{64}", image)
                value["services"][component]["image"] = image
        path = output / (name + ".json")
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")
        path.chmod(0o600)
    print("Prepared task-owned WSL fixture profiles with exact qualified component images; original files preserved")


if __name__ == "__main__":
    main()
