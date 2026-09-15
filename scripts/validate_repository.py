"""Offline structural checks on the complete standalone service checkout."""
import argparse
import ast
import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path
from urllib.parse import unquote

from known_problems_gate import catalog_ids, require

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+)(?:\s+\"[^\"]*\")?)\)")


def versions(root):
    package = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))
    version = package["project"]["version"]
    require(re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version), "Invalid numeric service version")
    namespace = ast.parse((root / "src/mastermind/__init__.py").read_text("utf-8"))
    python_version = next(ast.literal_eval(node.value) for node in namespace.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets))
    observed = [python_version]
    for name in ("bridge/manifest.json", "bridge/package.json", "bridge/package-lock.json", "component-lock.json"):
        observed.append(json.loads((root / name).read_text("utf-8"))["version"])
    observed.append(json.loads((root / "bridge/package-lock.json").read_text("utf-8"))["packages"][""]["version"])
    if (root / "package.json").exists():
        observed.extend(json.loads((root / name).read_text("utf-8"))["version"] for name in ("package.json", "package-lock.json"))
    require(all(value == version for value in observed), "Service/Bridge/package versions disagree")
    return version


def links(root):
    paths = [root / "README.md", root / "mastermind_service_requirements_final.md", *sorted((root / "docs").rglob("*.md"))]
    failures = []
    for path in paths:
        text = path.read_text("utf-8")
        text = re.sub(r"^```[^\n]*\n.*?^```\s*$", "", text, flags=re.M | re.S)
        for match in LINK.finditer(text):
            target = match[1] or match[2]
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            clean = unquote(target.split("#", 1)[0].split("?", 1)[0])
            resolved = (path.parent / clean).resolve()
            if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                failures.append(path.relative_to(root).as_posix() + ": " + target)
    require(not failures, "Broken standalone documentation links: " + "; ".join(failures))
    return len(paths)


def policy(root):
    lock = json.loads((root / "docs/policy-lock.json").read_text("utf-8"))
    actual = {path.name for path in (root / "docs/policy").glob("PART_*.md")}
    require(actual == set(lock["files"]), "Policy snapshot inventory changed")
    for name, digest in lock["files"].items():
        require(hashlib.sha256((root / "docs/policy" / name).read_bytes()).hexdigest() == digest, "Policy content lock mismatch: " + name)
    for name, digest in lock.get("assets", {}).items():
        path = (root / "docs/policy" / name).resolve()
        require(path.is_relative_to((root / "docs/policy").resolve()) and path.is_file() and
                hashlib.sha256(path.read_bytes()).hexdigest() == digest, "Policy asset lock mismatch: " + name)
    identifiers = catalog_ids((root / "docs/policy/PART_12_KNOWN_DEPLOYMENT_AND_OPERATIONS_PROBLEMS.md").read_bytes())
    compatibility = json.loads((root / "docs/compatibility.json").read_text("utf-8"))
    for service, candidate in compatibility["services"].items():
        path = (root / candidate["patch"]).resolve()
        require(path.is_relative_to(root.resolve()) and path.is_file(), "Producer patch is missing: " + service)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == candidate["patch_sha256"], "Producer patch digest changed: " + service)
    return len(identifiers)


def inputs(root):
    components = json.loads((root / "component-lock.json").read_text("utf-8"))
    runtime = (root / "Dockerfile.runtime").read_text("utf-8")
    for artifact in (components["kasmvnc"]["asset"], *components["obsidian"]["assets"]):
        require(artifact["url"] in runtime and artifact["digest"].removeprefix("sha256:") in runtime,
                "Native runtime archive differs from its official component lock")
    for name in ("Dockerfile", "Dockerfile.runtime", "Dockerfile.worker"):
        stages = set()
        for line in (root / name).read_text("utf-8").splitlines():
            if line.startswith("FROM "):
                require(re.fullmatch(r"FROM [a-zA-Z0-9._:/-]+@sha256:[a-f0-9]{64}(?: AS [a-zA-Z0-9_-]+)?", line) or
                        line.split()[1] in stages, "Unpinned base image: " + name)
                if " AS " in line:
                    stages.add(line.split(" AS ", 1)[1])
    for name in ("requirements.lock", "requirements.worker.lock"):
        lines = (root / name).read_text("utf-8").splitlines()
        require(all(not line.strip() or line.startswith("#") or re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+", line) for line in lines), "Unpinned Python requirement: " + name)
    for name in ("bridge/package.json", "package.json"):
        if not (root / name).exists():
            continue
        document = json.loads((root / name).read_text("utf-8"))
        require(all(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) for group in ("dependencies", "devDependencies")
                    for version in document.get(group, {}).values()), "Unpinned Node dependency: " + name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/repository-check.json")
    args = parser.parse_args()
    try:
        version = versions(args.root)
        documents = links(args.root)
        identifiers = policy(args.root)
        inputs(args.root)
        subprocess.run(["git", "-C", str(args.root), "diff", "--check"], check=True, capture_output=True)
        result = {"status": "PASS", "version": version, "documents": documents, "active_problem_ids": identifiers}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        result = {"status": "FAIL", "reason": str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
