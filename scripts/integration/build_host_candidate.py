"""Build unpublished signed candidates in independent, disposable clones."""
import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / ".local/host-fixture"


def run(*args, cwd=ROOT):
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.STDOUT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--fault", choices=("none", "migration", "functional", "delay"), default="none")
    parser.add_argument("--base", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", args.version):
        raise SystemExit("Invalid numeric candidate version")
    base = args.base or (ROOT if args.fault == "none" else ROOT / ".local/release-source/0.0.2")
    source = ROOT / ".local/release-source" / args.version
    if source.exists():
        raise SystemExit("Candidate already exists; immutable qualification artifacts may not be replaced")
    run("git", "clone", "--no-hardlinks", str(base), str(source))
    old_version = tomllib.loads((source / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    for name in ("src/mastermind/__init__.py", "pyproject.toml"):
        path = source / name
        body = path.read_text("utf-8")
        declaration = '__version__' if name.endswith('__init__.py') else 'version'
        body, count = re.subn(r'^' + declaration + r'\s*=\s*"' + re.escape(old_version) + r'"',
                             declaration + ' = "' + args.version + '"', body, count=1, flags=re.MULTILINE)
        assert count == 1, "Exact version declaration is absent"
        path.write_text(body, encoding="utf-8", newline="\n")
    for name in ("bridge/manifest.json", "bridge/package.json", "bridge/package-lock.json", "package.json", "package-lock.json", "component-lock.json"):
        path = source / name
        data = json.loads(path.read_text("utf-8"))
        assert data["version"] == old_version
        data["version"] = args.version
        if name.endswith("package-lock.json"):
            assert data["packages"][""]["version"] == old_version
            data["packages"][""]["version"] = args.version
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    cli = source / "src/mastermind/cli.py"
    needle = "            migrate(config, args.request, args.version, args.schema)\n"
    injection = needle + "            from .fs import atomic_write\n            atomic_write(config.vault / 'Qualification rejected candidate.md', b'Unaccepted candidate wrote this file.\\n')\n"
    if args.fault == "migration":
        injection += "            raise DomainError('QUALIFICATION_MIGRATION_FAILURE', 'Injected unpublished candidate failure.', 500)\n"
    if args.fault == "delay":
        injection += "            time.sleep(45)\n"
    if args.fault != "none":
        body = cli.read_text("utf-8")
        assert needle in body, "Migration fault injection point is absent"
        cli.write_text(body.replace(needle, injection), encoding="utf-8", newline="\n")
    if args.fault == "functional":
        api = source / "src/mastermind/api.py"
        api.write_text(api.read_text("utf-8").replace('        def verify():\n            identity = data["request_id"]',
            '        def verify():\n            raise DomainError("QUALIFICATION_FUNCTIONAL_FAILURE", "Injected unpublished candidate failure.", 503)\n            identity = data["request_id"]'), encoding="utf-8", newline="\n")
    run("git", "add", ".", cwd=source)
    run("git", "-c", "user.name=Mastermind qualification", "-c", "user.email=qualification@localhost", "commit", "-m", "Unpublished " + args.fault + " fault candidate " + args.version, cwd=source)
    revision = run("git", "rev-parse", "HEAD", cwd=source).strip()
    npm = "npm.cmd" if __import__("os").name == "nt" else "npm"
    run(npm, "ci", cwd=source / "bridge")
    run(npm, "run", "build", cwd=source / "bridge")
    components = {}
    for component in ("core", "runtime", "worker"):
        tag = f"127.0.0.1:18500/mastermind/{component}:qualification-{args.version}"
        command = ["docker", "build", "-f", str(source / ("Dockerfile" if component == "core" else "Dockerfile." + component)), "-t", tag]
        if component == "worker":
            command += ["--build-context", "embedding=" + str(ROOT / ".local/models/multilingual-e5-small")]
        command.append(str(source))
        log = ROOT / "artifacts" / f"candidate-{args.version}-{component}.log"
        with log.open("w") as output:
            subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
            subprocess.run(["docker", "push", tag], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
        refs = json.loads(run("docker", "image", "inspect", "--format", "{{json .RepoDigests}}", tag))
        reference = next(value for value in refs if value.startswith("127.0.0.1:18500/"))
        components[component] = reference.replace("127.0.0.1:18500", "registry.mastermind.test:5000", 1)
        print("Built and pushed unpublished", args.version, component, flush=True)
    lock = FIXTURE / ("components-" + args.version + ".json")
    lock.write_text(json.dumps(components, indent=2) + "\n", newline="\n")
    output = FIXTURE / ("release-" + args.version)
    python = sys.executable
    print(run(python, str(source / "scripts/build_release.py"), "build", "--output", str(output), "--components", str(lock),
        "--public-key", str(FIXTURE / "mastermind.pem"), "--updater-bundle", str(FIXTURE / "updater"),
        "--wyvern-bundle", str(FIXTURE / "wyvern"),
        "--repository", "psewdon1m-exocortex/mastermind", "--source-sha", revision))
    print(run(python, "scripts/build_release.py", "sign", str(output / "mastermind-release.json"), "--key-file", str(FIXTURE / "mastermind-signing.key")))
    print(run(python, "scripts/integration/prepare_release_transport.py"))
    print(run("docker", "cp", str(FIXTURE / "release-assets") + "/.", "mastermind-qualification-host:/opt/qualification/release-assets/"))
    print("READY: unpublished", args.version, args.fault, revision)


if __name__ == "__main__":
    main()
