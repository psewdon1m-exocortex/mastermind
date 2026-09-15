"""Own-service installer; preparation never starts containers or edits ingress."""
import argparse
import grp
import json
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from release_verify import regular, sha256, verify

ROOT = Path("/opt/exocortex/mastermind")
POLICY = "mastermind.installation.v1"


def run(args, *, cwd=None, timeout=300, capture=False, accepted_codes=(0,)):
    # Never print command arguments: some installer operations carry credentials
    # in their input file, and diagnostic failures must remain bounded.
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(args, cwd=cwd, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
        output.seek(0)
        body = output.read(1024*1024+1)
        if result.returncode not in accepted_codes or len(body) > 1024*1024:
            raise ValueError("Host command failed: "+Path(args[0]).name+" (exit "+str(result.returncode)+")")
        return body.decode("utf-8") if capture else None


def write(path, value, *, mode=0o600, gid=None, exclusive=False):
    path = Path(path)
    if path.is_symlink() or exclusive and path.exists():
        raise ValueError("Refusing to replace prepared file: "+path.name)
    descriptor, name = tempfile.mkstemp(prefix=".mastermind-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(value.encode("utf-8") if isinstance(value, str) else value)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(name, mode)
        if gid is not None:
            os.chown(name, 0, gid)
        os.replace(name, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        Path(name).unlink(missing_ok=True)


def parse_env(path):
    value = regular(path, 128*1024).decode("utf-8")
    info = path.lstat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("The service .env must be root-owned mode 0600")
    result = {}
    for line in value.splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, text = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or key in result or any(c in text for c in "\x00\r\n$`\"'"):
            raise ValueError("Invalid or duplicate environment assignment")
        result[key] = text
    return result


def update_env(path, changes):
    lines, seen = [], set()
    for line in path.read_text("utf-8").splitlines():
        key = line.partition("=")[0]
        if key in changes:
            line = key+"="+changes[key]
            seen.add(key)
        lines.append(line)
    lines += [key+"="+value for key, value in changes.items() if key not in seen]
    write(path, "\n".join(lines)+"\n")


def prepare(directory):
    if (directory/".env").exists():
        raise ValueError("An existing installation cannot be prepared again")
    manifest = json.loads(regular(directory/"mastermind-release.json", 2*1024**2))
    internal = {key: secrets.token_urlsafe(32) for key in ("runtime_token", "bridge_token", "vnc_password", "worker_token",
                "bootstrap_access_key", "updater_token", "neptune_control_token", "neptune_export_token")}
    scopes = {"core": internal, "runtime": {k: internal[k] for k in ("runtime_token", "bridge_token", "vnc_password")},
              "worker": {"worker_token": internal["worker_token"]}}
    secret_root = directory/"secrets"
    secret_root.mkdir(mode=0o750)
    secret_root.chmod(0o750)
    for scope, values in scopes.items():
        folder = secret_root/scope
        folder.mkdir(mode=0o750)
        os.chown(folder, 0, 10001)
        folder.chmod(0o750)  # bootstrap runs under umask 077; enforce group traversal
        for name, value in values.items():
            write(folder/name, value, mode=0o640, gid=10001, exclusive=True)
    constants = {"MASTERMIND_VERSION": manifest["version"],
        **{"MASTERMIND_"+k.upper()+"_IMAGE": v for k, v in manifest["mastermind"]["components"].items()},
        "MASTERMIND_RELEASE_SHA256": sha256(directory/"mastermind-release.json"),
        "UPDATER_SERVICE_ID": "mastermind", "UPDATER_COMPOSE_PROJECT_DIR": str(ROOT),
        "UPDATER_COMPOSE_FILE": "compose.production.yaml", "UPDATER_COMPOSE_SERVICE": "core",
        "UPDATER_CONTAINER_NAME": "mastermind-core-1", "UPDATER_IMAGE_VARIABLE": "MASTERMIND_CORE_IMAGE",
        "UPDATER_VERSION_VARIABLE": "MASTERMIND_VERSION", "UPDATER_LOCAL_HEALTH_URL": "http://127.0.0.1:18390/healthz",
        "UPDATER_CONTROL_TOKEN": internal["updater_token"], "UPDATER_SOCKET_GID": "10001", "NEPTUNE_SOCKET_GID": "10001"}
    text = "# OPERATOR INPUT — edit only this section; values are literal, never shell code.\n" \
        "MASTERMIND_PUBLIC_URL=\nKERNEL_URL=\nKERNEL_TOKEN_FILE=\nTRUST_CA_FILE=\nMASTERMIND_TIMEZONE=UTC\n" \
        "\n# GENERATED — installer and signed release own these values.\n"
    write(directory/".env", text+"".join(k+"="+v+"\n" for k, v in constants.items()), exclusive=True)
    write(directory/"installation.json", json.dumps({"schema": POLICY, "state": "PREPARED", "version": manifest["version"]})+"\n")


def origin(value):
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query \
            or parsed.fragment or parsed.path not in ("", "/") or parsed.port not in (None, 443):
        raise ValueError("Operator URLs must be canonical HTTPS origins on port 443")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", parsed.hostname):
        raise ValueError("Use an ASCII canonical hostname")
    return parsed.hostname


def compose(directory, *args, **kwargs):
    return run(["docker", "compose", "--env-file", str(directory/".env"), "-f", str(directory/"compose.production.yaml"),
                "--project-directory", str(directory), *args], cwd=directory, **kwargs)


def validate_profile(rendered, images, directory):
    if rendered.get("name") != "mastermind" or set(rendered.get("services", {})) != {"core", "runtime", "worker"}:
        raise ValueError("Compose must contain exactly the three Mastermind components")
    data = {"core": {"core-data": "/data", "vault-data": "/data/vault"},
            "runtime": {"runtime-data": "/home/mastermind", "vault-data": "/vault"}, "worker": {"work-data": "/work"}}
    for name, service in rendered["services"].items():
        if service.get("image") != images[name] or service.get("user") != "10001:10001" \
                or service.get("read_only") is not True or service.get("privileged") or service.get("network_mode") \
                or service.get("cap_add") or service.get("devices") or service.get("cap_drop") != ["ALL"] \
                or service.get("entrypoint") or service.get("command") or service.get("build"):
            raise ValueError("Component violates the fixed privilege profile: "+name)
        ports = service.get("ports", [])
        if name != "core" and ports or name == "core" and (len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1"
                or ports[0].get("target") != 18390 or str(ports[0].get("published")) != "18390"):
            raise ValueError("Component exposes an unsupported port")
        mounted = {}
        for volume in service.get("volumes", []):
            if volume.get("type") == "volume":
                if data[name].get(volume["source"]) != volume["target"] or volume["source"] in mounted:
                    raise ValueError("Component crosses a data boundary")
                mounted[volume["source"]] = volume["target"]
            elif volume.get("type") == "bind":
                source = volume["source"]
                allowed = {str(directory/"secrets"/name): "/run/mastermind"}
                if name == "core":
                    allowed.update({"/run/exocortex": "/run/exocortex", "/run/neptune": "/run/neptune"})
                if not volume.get("read_only") or allowed.get(source) != volume["target"]:
                    raise ValueError("Component requests an unowned host path")
            else:
                raise ValueError("Unsupported component mount")
        if mounted != data[name]:
            raise ValueError("A required component data volume is missing")


def install(directory):
    if directory != ROOT or platform.machine() != "x86_64":
        raise ValueError("The qualified production profile requires /opt/exocortex/mastermind on Linux amd64")
    config = parse_env(directory/".env")
    manifest = verify(directory/"mastermind-release.json", directory/"mastermind-release.json.sig.json",
                      Path("/etc/exocortex/release-trust/mastermind.pem"))
    if config.get("MASTERMIND_RELEASE_SHA256") != sha256(directory/"mastermind-release.json") \
            or config.get("MASTERMIND_VERSION") != manifest["version"]:
        raise ValueError("Environment release lock differs from the authenticated release")
    for name, image in manifest["mastermind"]["components"].items():
        if config.get("MASTERMIND_"+name.upper()+"_IMAGE") != image:
            raise ValueError("An immutable image lock was edited")
    origin(config.get("MASTERMIND_PUBLIC_URL", ""))
    origin(config.get("KERNEL_URL", ""))
    from zoneinfo import ZoneInfo
    ZoneInfo(config["MASTERMIND_TIMEZONE"])
    token_path = Path(config.get("KERNEL_TOKEN_FILE", ""))
    if not token_path.is_absolute():
        raise ValueError("KERNEL_TOKEN_FILE must name an absolute root-owned file")
    token_info = token_path.lstat()
    if token_info.st_uid != 0 or stat.S_IMODE(token_info.st_mode) & 0o077:
        raise ValueError("Kernel bootstrap credential must be root-owned and private")
    token = regular(token_path, 128*1024).decode("utf-8")
    if not token or any(ord(c) < 33 or ord(c) > 126 or c in "'\"$`" for c in token):
        raise ValueError("Kernel machine credential must be an exact HTTP header token without a trailing newline")
    write(directory/"secrets/core/kernel_token", token, mode=0o640, gid=10001)
    ca_path = Path(config.get("TRUST_CA_FILE") or "/etc/ssl/certs/ca-certificates.crt")
    write(directory/"secrets/core/trust_ca.crt", regular(ca_path, 2*1024**2), mode=0o644)
    update_env(directory/".env", {"KERNEL_SERVICE_TOKEN": token})
    run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=15)
    # Exact images are pulled before any container or database is changed.
    for image in manifest["mastermind"]["components"].values():
        run(["docker", "pull", image], timeout=1800)
        if run(["docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", image], capture=True).strip() != "linux/amd64":
            raise ValueError("Image architecture differs from the signed profile")
    updater = directory/"vendor/updater"
    if not (updater/"install.sh").is_file() or not (updater/"updater-linux-amd64").is_file():
        raise ValueError("The signed bundle does not contain its qualified host Updater installer")
    run(["sh", str(updater/"install.sh"), "mastermind", str(directory/".env"), str(updater/"updater-linux-amd64")], timeout=180)
    update_env(directory/".env", {"UPDATER_SOCKET_GID": str(grp.getgrnam("updater").gr_gid),
                                 "NEPTUNE_SOCKET_GID": str(grp.getgrnam("neptune-clients").gr_gid)})
    rendered = json.loads(compose(directory, "config", "--format", "json", capture=True))
    validate_profile(rendered, manifest["mastermind"]["components"], directory)
    for name in ("core-data", "vault-data", "runtime-data", "work-data"):
        actual = "mastermind_"+name
        listing = json.loads(run(["docker", "volume", "ls", "--filter", "name=^"+actual+"$", "--format", "json"], capture=True) or "null")
        if listing is None:
            run(["docker", "volume", "create", "--label", "com.docker.compose.project=mastermind",
                 "--label", "com.docker.compose.volume="+name, actual])
        info = json.loads(run(["docker", "volume", "inspect", actual], capture=True))[0]
        if info.get("Labels", {}).get("com.docker.compose.project") != "mastermind":
            raise ValueError("A volume with this name belongs to another deployment")
    initialize = "import os; [(os.chown(p,10001,10001),os.chmod(p,0o700)) for p in ['/data','/vault','/runtime','/work']]"
    run(["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "0:0", "--cap-drop", "ALL",
         "--cap-add", "CHOWN", "--cap-add", "FOWNER", "--security-opt", "no-new-privileges:true",
         "--mount", "type=volume,source=mastermind_core-data,target=/data", "--mount", "type=volume,source=mastermind_vault-data,target=/vault",
         "--mount", "type=volume,source=mastermind_runtime-data,target=/runtime", "--mount", "type=volume,source=mastermind_work-data,target=/work",
         "--entrypoint", "python", manifest["mastermind"]["components"]["core"], "-c", initialize], timeout=30)
    compose(directory, "up", "-d", "--no-build", "--wait", "--wait-timeout", "120", timeout=150)
    result = run(["docker", "exec", "mastermind-core-1", "mastermind", "doctor"], capture=True, timeout=120, accepted_codes=(0, 1))
    diagnostic = json.loads(result)
    # Neptune is enrolled separately by the owner with Saturn's one-time code.
    # Initial installation must prove Core/Runtime/Worker/Kernel/Updater, while
    # reporting an unconfigured replication dependency without fabricating PASS.
    required = [*diagnostic["checks"].values(),
                *(v for k, v in diagnostic["dependencies"].items() if k != "neptune")]
    if not diagnostic.get("canonical_ready") or any(v["status"] != "PASS" for v in required):
        write(directory/"installation.json", json.dumps({"schema": POLICY, "state": "NOT_READY", "doctor": diagnostic})+"\n")
        raise ValueError("Local readiness failed; inspect installation.json and run mastermind-install doctor")
    write(directory/"installation.json", json.dumps({"schema": POLICY, "state": "LOCAL_READY", "version": manifest["version"],
          "installed_at": time.time(), "edge": "NOT_VERIFIED", "doctor": diagnostic})+"\n")
    print("Mastermind "+manifest["version"]+" is ready on 127.0.0.1:18390.")
    print("Initial owner Access Key: /opt/exocortex/mastermind/secrets/core/bootstrap_access_key (value not printed).")
    print("Next: configure host Nginx using packaging/nginx, nginx -t, then verify canonical HTTPS from outside this host.")
    if diagnostic["dependencies"]["neptune"]["status"] != "PASS":
        print("Neptune remains unconfigured: enter the Mastermind setup code from Saturn in Settings > Backup.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "install", "status", "doctor"), nargs="?", default="install")
    parser.add_argument("--directory", type=Path, default=ROOT)
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0:
        raise ValueError("This installer requires root on Linux")
    if args.action == "prepare":
        prepare(args.directory)
    elif args.action == "install":
        import fcntl
        with Path("/run/lock/mastermind-install.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            install(args.directory)
    elif args.action == "status":
        print(compose(args.directory, "ps", "--format", "json", capture=True))
    else:
        print(run(["docker", "exec", "mastermind-core-1", "mastermind", "doctor"], timeout=120, capture=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        raise SystemExit("Mastermind installer: "+str(error)) from None
