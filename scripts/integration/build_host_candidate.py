"""Build unpublished signed fault candidates in independent, disposable clones."""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / ".local/host-fixture"


def run(*args, cwd=ROOT):
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.STDOUT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("version", choices=("0.0.3", "0.0.4", "0.0.5"))
    parser.add_argument("--fault", choices=("migration", "functional", "delay"), required=True)
    args = parser.parse_args()
    source = ROOT / ".local/release-source" / args.version
    if source.exists():
        raise SystemExit("Candidate already exists; immutable qualification artifacts may not be replaced")
    run("git", "clone", "--no-hardlinks", str(ROOT / ".local/release-source/0.0.2"), str(source))
    for name in ("src/mastermind/__init__.py", "pyproject.toml", "bridge/manifest.json", "bridge/package.json", "bridge/package-lock.json"):
        path = source / name
        path.write_text(path.read_text().replace('0.0.2', args.version), newline="\n")
    cli = source / "src/mastermind/cli.py"
    needle = "            migrate(config, args.request, args.version, args.schema)\n"
    injection = needle + "            from .fs import atomic_write\n            atomic_write(config.vault / 'Qualification rejected candidate.md', b'Unaccepted candidate wrote this file.\\n')\n"
    if args.fault == "migration":
        injection += "            raise DomainError('QUALIFICATION_MIGRATION_FAILURE', 'Injected unpublished candidate failure.', 500)\n"
    if args.fault == "delay":
        injection += "            time.sleep(45)\n"
    cli.write_text(cli.read_text().replace(needle, injection), newline="\n")
    if args.fault == "functional":
        api = source / "src/mastermind/api.py"
        api.write_text(api.read_text().replace('        def verify():\n            identity = data["request_id"]',
            '        def verify():\n            raise DomainError("QUALIFICATION_FUNCTIONAL_FAILURE", "Injected unpublished candidate failure.", 503)\n            identity = data["request_id"]'), newline="\n")
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
    python = str(ROOT / ".venv/Scripts/python.exe")
    print(run(python, str(source / "scripts/build_release.py"), "build", "--output", str(output), "--components", str(lock),
        "--public-key", str(FIXTURE / "mastermind.pem"), "--updater-bundle", str(FIXTURE / "updater"),
        "--repository", "psewdon1m-exocortex/mastermind", "--source-sha", revision))
    print(run(python, "scripts/build_release.py", "sign", str(output / "mastermind-release.json"), "--key-file", str(FIXTURE / "mastermind-signing.key")))
    print(run(python, "scripts/integration/prepare_release_transport.py"))
    print(run("docker", "cp", str(FIXTURE / "release-assets") + "/.", "mastermind-qualification-host:/opt/qualification/release-assets/"))
    print("READY: unpublished", args.version, args.fault, revision)


if __name__ == "__main__":
    main()
