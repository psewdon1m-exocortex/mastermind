"""Copy only this task's stopped fixtures from Desktop into the isolated E: WSL daemon.

The original containers/volumes stay preserved. Private transfer files never enter
release output. Both daemon identities and every container/volume name are checked.
"""
import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PureWindowsPath

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from image_candidate import config_identity

CACHE = Path("E:/mastermind-qualification-cache-20260915/stand-transfer")
NAMES = [
    "mastermind-integration-postgres-1", "mastermind-integration-sftp-1", "mastermind-integration-kernel-1",
    "mastermind-integration-volt-1", "mastermind-integration-chronos-1", "mastermind-integration-saturn-1",
    "mastermind-integration-gateway-1", "mastermind-host-services-saturn-host-1", "mastermind-host-services-saturn-worker-1",
    "mastermind-host-services-gateway-1", "mastermind-qualification-registry", "mastermind-qualification-host",
    "mastermind-development-runtime-1", "mastermind-development-worker-1", "mastermind-development-core-1",
    "mastermind-integration-neptune-1",
]
HOST = "mastermind-qualification-host"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--finish-copied", action="store_true", help="Resume only after every volume has a successful retained transfer record")
    parser.add_argument("--resume-volume-archives", action="store_true", help="Resume this stopped fixture's verified archive imports using large 9p reads")
    args = parser.parse_args()
    assert os.name == "nt" and CACHE.resolve() == Path("E:/mastermind-qualification-cache-20260915/stand-transfer")
    CACHE.mkdir(parents=True, exist_ok=True)
    source = dict(os.environ)
    for key in ("DOCKER_HOST", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "DOCKER_CONTEXT"):
        source.pop(key, None)
    source["DOCKER_CONTEXT"] = "desktop-linux"
    destination = {key: value for key, value in source.items() if key != "DOCKER_CONTEXT"}
    destination.update(DOCKER_HOST="tcp://localhost:2376", DOCKER_TLS_VERIFY="1", DOCKER_CERT_PATH=str(ROOT / ".local/qualification-docker"))
    def docker(arguments, *, remote=False, timeout=1800):
        return subprocess.check_output(["docker", *arguments], env=destination if remote else source, text=True, stderr=subprocess.STDOUT, timeout=timeout)
    assert docker(["info", "--format", "{{.Name}}"], timeout=20).strip() == "docker-desktop"
    assert docker(["info", "--format", "{{.Name}}"], remote=True, timeout=20).strip() == "mastermind-qualification-wsl"
    resuming = args.finish_copied or args.resume_volume_archives
    configuration = json.loads((CACHE / "containers.private.json").read_text("utf-8")) if resuming else json.loads(docker(["inspect", *NAMES]))
    assert {item["Name"].lstrip("/") for item in configuration} == set(NAMES)
    existing = set(docker(["ps", "-a", "--format", "{{.Names}}"], remote=True).splitlines())
    if not resuming:
        assert not existing.intersection(NAMES), "Destination already contains part of the stand; inspect before resuming"
        (CACHE / "containers.private.json").write_text(json.dumps(configuration, indent=2), encoding="utf-8")
    networks = {name for item in configuration for name in item["NetworkSettings"]["Networks"]}
    definitions = json.loads(docker(["network", "inspect", *sorted(networks)]))
    assert all(item["Driver"] == "bridge" and item["Name"].startswith("mastermind-") for item in definitions)
    volumes = {mount["Name"] for item in configuration for mount in item["Mounts"] if mount["Type"] == "volume"}
    assert all(re.fullmatch(r"mastermind-[a-z0-9_-]+", name) for name in volumes)
    volume_records = json.loads(docker(["volume", "inspect", *sorted(volumes)]))
    if resuming:
        logs = [ROOT / "artifacts" / name for name in ("stand-wsl-transfer.log", "stand-wsl-transfer-resume.log")]
        copied = set(re.findall(r"^COPIED (mastermind-[a-z0-9_-]+)$", "\n".join(path.read_text("utf-8") for path in logs if path.exists()), re.MULTILINE))
        assert copied <= volumes
        assert all(not item["State"]["Running"] for item in json.loads(docker(["inspect", *NAMES]))), "Original fixtures must remain stopped"
        if args.resume_volume_archives:
            assert all(not item["State"]["Running"] for item in json.loads(docker(["inspect", *sorted(existing.intersection(NAMES))], remote=True))) if existing.intersection(NAMES) else True
            for record in volume_records:
                if record["Name"] not in copied:
                    transfer_volume(record, docker, resume=True)
        else:
            assert copied == volumes, "Every completed volume copy must have its original successful execution record"
        finish(configuration, definitions, docker, existing)
        return
    docker(["stop", "--time", "60", *[item["Name"].lstrip("/") for item in configuration if item["State"]["Running"]]], timeout=180)
    print("STOPPED only the 16 explicitly named Mastermind qualification fixtures", flush=True)
    images = {item["Config"]["Image"] for item in configuration if item["Name"].lstrip("/") != HOST}
    images.add("ubuntu:24.04")
    images_file = CACHE / "images.tar"
    docker(["save", "--output", str(images_file), *sorted(images)])
    docker(["load", "--input", str(images_file)], remote=True)
    print("COPIED fixture images into the separate daemon", flush=True)
    host_image = "mastermind-private-host:qualification-transfer-20260915"
    rootfs = CACHE / "host-rootfs.private.tar"
    docker(["export", "--output", str(rootfs), HOST])
    docker(["import", str(rootfs), host_image], remote=True)
    for record in volume_records:
        transfer_volume(record, docker)
    finish(configuration, definitions, docker, existing)


def transfer_volume(record, docker, *, resume=False):
    name = record["Name"]
    archive = name + ".private.tar"
    path = CACHE / archive
    if not resume or not path.exists():
        docker(["run", "--rm", "--network", "none", "--read-only", "--mount", "type=volume,source=" + name + ",target=/from,readonly",
            "--mount", "type=bind,source=" + str(CACHE) + ",target=/transfer", "--entrypoint", "tar", "ubuntu:24.04",
            "--blocking-factor=2048", "-cpf", "/transfer/" + archive, "-C", "/from", "."])
    assert path.is_file() and not path.is_symlink() and path.stat().st_size >= 10240 and path.stat().st_size % 512 == 0
    with path.open("rb") as stream:
        stream.seek(-1024, 2)
        assert stream.read() == bytes(1024), "A partial archive must never be used to restore the fixture"
    create = ["volume", "create"]
    for key, value in (record.get("Labels") or {}).items():
        create += ["--label", key + "=" + value]
    docker([*create, name], remote=True)
    docker(["run", "--rm", "--network", "none", "--read-only", "--mount", "type=volume,source=" + name + ",target=/to",
        "--mount", "type=bind,source=/mnt/e/mastermind-qualification-cache-20260915/stand-transfer,target=/transfer,readonly",
        "--entrypoint", "tar", "ubuntu:24.04", "--blocking-factor=2048", "--read-full-records", "-xpf", "/transfer/" + archive, "-C", "/to"], remote=True, timeout=3600)
    print("COPIED " + name, flush=True)


def loaded_image_identities(configuration, archive_path, docker):
    # Desktop exports OCI indexes, while the separate overlay2 daemon loads
    # image-config identities and need not retain the original RepoDigest alias.
    # Resolve the exact exported bytes; never substitute a similarly named tag.
    identities = {}
    with tarfile.open(archive_path) as archive:
        for item in configuration:
            if item["Name"].lstrip("/") == HOST or item["Image"] in identities:
                continue
            identity = config_identity(archive, item["Image"])
            observed = docker(["image", "inspect", "--format", "{{.Id}}", identity], remote=True).strip()
            if observed != identity:
                raise ValueError("Imported fixture image differs from its exported OCI identity")
            identities[item["Image"]] = identity
    return identities


def finish(configuration, definitions, docker, existing):
    host_image = "mastermind-private-host:qualification-transfer-20260915"
    identities = loaded_image_identities(configuration, CACHE / "images.tar", docker)
    current_networks = set(docker(["network", "ls", "--format", "{{.Name}}"], remote=True).splitlines())
    for network in definitions:
        if network["Name"] in current_networks:
            actual = json.loads(docker(["network", "inspect", network["Name"]], remote=True))[0]
            assert all(actual[key] == network[key] for key in ("Driver", "Internal", "IPAM")), "Existing network differs from the copied fixture"
            continue
        arguments = ["network", "create", "--driver", "bridge"]
        if network["Internal"]:
            arguments.append("--internal")
        for entry in network["IPAM"]["Config"]:
            arguments += ["--subnet", entry["Subnet"], "--gateway", entry["Gateway"]]
        for key, value in network.get("Labels", {}).items():
            arguments += ["--label", key + "=" + value]
        docker([*arguments, network["Name"]], remote=True)
    tls = ROOT / ".local/qualification-docker"
    context = ssl.create_default_context(cafile=str(tls / "ca.pem"))
    context.load_cert_chain(tls / "cert.pem", tls / "key.pem")
    with httpx.Client(base_url="https://localhost:2376/v1.52", verify=context, trust_env=False, timeout=180) as client:
        for item in configuration:
            name = item["Name"].lstrip("/")
            body, host = dict(item["Config"]), dict(item["HostConfig"])
            if name == HOST:
                body["Image"] = host_image
            else:
                body["Image"] = identities[item["Image"]]
            binds = []
            for mount in item["Mounts"]:
                if mount["Type"] not in {"bind", "volume"}:
                    continue
                path = mount["Name"] if mount["Type"] == "volume" else mount["Source"]
                if mount["Type"] == "bind":
                    prefix = "/run/desktop/mnt/host/"
                    if path.startswith(prefix):
                        suffix = path.removeprefix(prefix)
                        assert re.match(r"[a-z]/", suffix)
                        path = suffix[0].upper() + ":/" + suffix[2:]
                    windows = PureWindowsPath(path)
                    assert windows.is_absolute() and str(windows).lower().startswith(str(ROOT).lower() + "\\"), "Unexpected bind outside the task"
                    path = "/mnt/" + windows.drive[0].lower() + "/" + windows.as_posix()[3:]
                binds.append(path + ":" + mount["Destination"] + (":rw" if mount["RW"] else ":ro"))
            host["Binds"] = binds
            host.pop("Mounts", None)
            endpoints = {}
            for network, data in item["NetworkSettings"]["Networks"].items():
                endpoints[network] = {"Aliases": [alias for alias in data.get("Aliases") or [] if not re.fullmatch(r"[a-f0-9]{12,64}", alias)],
                                      "IPAMConfig": {"IPv4Address": data["IPAddress"]}}
            body.update(HostConfig=host, NetworkingConfig={"EndpointsConfig": endpoints})
            if name in existing:
                actual = json.loads(docker(["inspect", name], remote=True))[0]
                assert actual["State"]["Status"] == "created" and all(actual["Config"].get(key) == body.get(key) for key in
                    ("Image", "Hostname", "User", "Env", "Cmd", "Entrypoint", "Labels")), "Existing container does not match this unstarted fixture"
                assert actual["HostConfig"].get("Binds") == host["Binds"] and actual["HostConfig"].get("PortBindings") == host.get("PortBindings")
                continue
            response = client.post("/containers/create", params={"name": name}, json=body)
            if response.status_code != 201:
                (CACHE / (name + ".create-error.private.txt")).write_text(response.text, encoding="utf-8")
                raise RuntimeError("Cannot recreate " + name + "; inspect private transfer diagnostics")
    for name in NAMES:
        docker(["start", name], remote=True)
        if name.endswith("postgres-1"):
            time.sleep(3)
    print("PASS transfer: original stopped fixtures preserved; copied stand runs on E: with private TLS control", flush=True)


if __name__ == "__main__":
    main()
