"""Isolated real Kernel/Volt/Wyvern fixture; credentials never enter output or compose."""
import json
import secrets
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / ".local/context-indexing-stack"
DIRECTORY.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))


def write(name, value):
    path = DIRECTORY / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def token(name):
    path = DIRECTORY / name
    if not path.exists():
        write(name, secrets.token_hex(32))
    return path.read_text()


def prepare():
    for name in ("ca.crt", "tls.crt", "tls.key", "entry.mjs"):
        shutil.copyfile(ROOT / ".local/integration" / name, DIRECTORY / name)
    for name in ("kernel-access", "kernel-session", "kernel.token", "updater.token", "volt-access",
                 "volt-device.key", "volt-kernel.token", "manager.token", "runtime.token", "client.token"):
        token(name)
    if len(token("volt-device.key")) == 64:
        write("volt-device.key", secrets.token_urlsafe(32))
    write("kernel-env.json", json.dumps({"KERNEL_DATA_DIR": "/app/data", "KERNEL_LISTEN_PORT": "18180",
        "KERNEL_ACCESS_KEY": token("kernel-access"), "KERNEL_SESSION_SECRET": token("kernel-session"),
        "KERNEL_SERVICE_TOKEN": token("kernel.token"), "UPDATER_CONTROL_TOKEN": token("updater.token"),
        "VOLT_URL": "https://volt.mastermind.test", "VOLT_KERNEL_TOKEN_FILE": "/fixture/volt-kernel.token",
        "NODE_EXTRA_CA_CERTS": "/fixture/ca.crt", "KERNEL_COOKIE_SECURE": "true", "KERNEL_TRUSTED_PROXIES": "10.195.0.10"}))
    write("volt-env.json", json.dumps({"VOLT_DATA_DIR": "/app/data", "VOLT_LISTEN_HOST": "0.0.0.0", "VOLT_PORT": "18184",
        "VOLT_DEVICE_KEY_FILE": "/fixture/volt-device.key", "VOLT_ACCESS_KEY_FILE": "/fixture/volt-access",
        "VOLT_KERNEL_TOKEN_FILE": "/fixture/volt-kernel.token", "VOLT_SECURE_COOKIES": "true",
        "VOLT_KERNEL_URL": "https://kernel.mastermind.test", "VOLT_TRUSTED_PROXIES": "10.195.0.10",
        "NODE_EXTRA_CA_CERTS": "/fixture/ca.crt"}))
    write("bootstrap.json", json.dumps({"kernel_origin": "https://kernel.mastermind.test",
        "kernel_credential_file": "/identity/runtime.token", "config_key": "wyvern.instances.context-indexing.config"}))
    write("link/link.json", json.dumps({"schema": "exocortex.wyvern.link.v1", "mode": "local",
        "instance_id": "context-indexing", "client_id": "mastermind", "socket": "/run/wyvern/client.sock",
        "token": token("client.token")}))
    write("initialize.py", "import os,shutil\nfrom pathlib import Path\n"
        "for name in ('kernel','volt','wyvern','socket','identity'):\n"
        " p=Path('/volumes')/name; p.mkdir(exist_ok=True); os.chown(p,10001,10001); os.chmod(p,0o750)\n"
        "p=Path('/volumes/identity/runtime.token'); shutil.copyfile('/fixture/runtime.token',p); os.chown(p,10001,10001); os.chmod(p,0o600)\n")
    write("nginx.conf", "user nginx;\nevents {}\nhttp { access_log off; error_log /dev/stderr warn;\n" + "\n".join(
        "server { listen 443 ssl; server_name "+name+".mastermind.test; ssl_certificate /fixture/tls.crt; "
        "ssl_certificate_key /fixture/tls.key; location / { proxy_pass http://"+name+":"+str(port)+"; "
        "proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto https; proxy_set_header X-Forwarded-For $remote_addr; }}"
        for name, port in (("kernel", 18180), ("volt", 18184)))+"\n}\n")
    common = {"init": True, "read_only": True, "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
              "mem_limit": "768m", "cpus": 2, "pids_limit": 128, "networks": ["private"],
              "logging": {"driver": "json-file", "options": {"max-size": "5m", "max-file": "2"}}}
    services = {name: {**common, "user": "10001:10001", "image": "mastermind-"+name+":context-indexing",
        "volumes": ["./:/fixture:ro", name+"-data:/app/data"], "tmpfs": ["/tmp:rw,nosuid,nodev,size=128m,mode=1777"],
        "command": ["node", "/fixture/entry.mjs", name, "node", "/app/server/index.js"],
        "depends_on": {"initialize": {"condition": "service_completed_successfully"}}} for name in ("kernel", "volt")}
    services["initialize"] = {"image": "python:3.12-slim-bookworm", "network_mode": "none", "user": "0:0",
        "volumes": ["./:/fixture:ro", *[name+"-data:/volumes/"+name for name in ("kernel", "volt", "wyvern")],
                    "wyvern-socket:/volumes/socket", "wyvern-identity:/volumes/identity"],
        "command": ["python", "/fixture/initialize.py"]}
    services["gateway"] = {"image": "nginx:1.29.4-alpine", "volumes": ["./:/fixture:ro"],
        "entrypoint": ["nginx", "-g", "daemon off;", "-c", "/fixture/nginx.conf"],
        "ports": ["127.0.0.1:19442:443"], "depends_on": ["kernel", "volt"],
        "networks": {"private": {"ipv4_address": "10.195.0.10", "aliases": ["kernel.mastermind.test", "volt.mastermind.test"]}, "edge": {}}}
    services["wyvern"] = {**common, "image": "mastermind-wyvern:context-indexing", "networks": ["private", "edge"],
        "environment": {"WYVERN_BOOTSTRAP_FILE": "/fixture/bootstrap.json", "NODE_EXTRA_CA_CERTS": "/fixture/ca.crt"},
        "volumes": ["./:/fixture:ro", "wyvern-data:/var/lib/wyvern", "wyvern-socket:/run/wyvern", "wyvern-identity:/identity:ro"],
        "tmpfs": ["/tmp:rw,nosuid,nodev,size=64m,mode=1777", "/run/wyvern-admin:rw,nosuid,nodev,size=1m,uid=10001,gid=10001,mode=700"],
        "depends_on": ["gateway"]}
    write("compose.yml", yaml.safe_dump({"name": "mastermind-context-indexing", "services": services,
        "volumes": {name: {} for name in ("kernel-data", "volt-data", "wyvern-data", "wyvern-socket", "wyvern-identity")},
        "networks": {"private": {"internal": True, "ipam": {"config": [{"subnet": "10.195.0.0/24"}]}}, "edge": {}}}, sort_keys=False))
    print("Prepared isolated context-indexing gateway fixture; no provider credentials written.")


def enroll():
    import hashlib
    import ssl
    import uuid

    import httpx
    from probe_integrations import checked, client

    from mastermind.kernel import Kernel

    def local(name):
        return httpx.Client(base_url="https://127.0.0.1:19442", verify=ssl.create_default_context(cafile=DIRECTORY/"ca.crt"),
            trust_env=False, timeout=30, headers={"Host": name+".mastermind.test", "Origin": "https://"+name+".mastermind.test"})
    kernel, volt = local("kernel"), local("volt")
    checked(kernel.post("/api/auth/login", json={"access_key": token("kernel-access")}))
    checked(volt.post("/api/v1/session", json={"access_key": token("volt-access")}))
    unmigrated = [entry for entry in checked(kernel.get("/api/register"))["entries"]
                  if not entry["value"].startswith("volt://")]
    references = []
    for offset in range(0, len(unmigrated), 5):
        chunk = unmigrated[offset:offset+5]
        entry = checked(volt.post("/api/v1/entries", json={"title": "Context default bindings "+str(offset),
            "fields": [{"key": item["key"], "value": item["value"] or "unconfigured", "visibility": "plain"} for item in chunk]}), 201)
        references.extend({"key": item["key"], "value": "volt://"+entry["id"]+"/"+str(i), "description": "Fixture default"}
                          for i, item in enumerate(chunk, 1))
    if references:
        checked(kernel.put("/api/register/entries", json={"entries": references}))
    entries = checked(volt.get("/api/v1/entries"))["entries"]
    if not any(v["title"] == "Context gateway discovery" for v in entries):
        entry = checked(volt.post("/api/v1/entries", json={"title": "Context gateway discovery", "fields": [
            {"key": "services.volt.sni", "value": "volt.mastermind.test", "visibility": "plain"},
            {"key": "services.volt.port", "value": "443", "visibility": "plain"}]}), 201)
        checked(kernel.put("/api/register/entries", json={"entries": [
            {"key": name, "value": "volt://"+entry["id"]+"/"+str(i), "description": "Isolated gateway discovery"}
            for i, name in enumerate(("services.volt.sni", "services.volt.port"), 1)]}))
    checked(kernel.post("/api/wyvern/instances/context-indexing/enroll", json={role+"_token_sha256":
        hashlib.sha256(token(role+".token").encode()).hexdigest() for role in ("manager", "runtime")}))
    manager = local("kernel")
    manager.headers["Authorization"] = "Bearer "+token("manager.token")
    route = "/api/v1/wyvern/context-indexing"
    current = checked(manager.get(route))
    if "google" not in current["config"]["adapters"]:
        old = Kernel("https://127.0.0.1:19441", lambda: (ROOT/".local/integration/kernel.token").read_text(), client=client("kernel"))
        resolved = old.resolve(["services.mastermind.secrets.ai_provider_key", "mastermind.crusher.text_model"])
        current = checked(manager.post(route+"/mutations", json={"operation": "adapter.put", "expected_revision": current["revision"],
            "request_id": uuid.uuid4().hex, "adapter_id": "google", "credential": resolved["services.mastermind.secrets.ai_provider_key"],
            "adapter": {"name": "Context indexing qualification", "driver": "google", "enabled": True,
                "profiles": {"default": {"model": resolved["mastermind.crusher.text_model"], "max_output_tokens": 8000,
                    "capabilities": ["text", "structured_output", "token_count", "image", "pdf", "audio", "video", "youtube"]}}}}))
        old.close()
        resolved.clear()
    if "mastermind" not in current["config"]["clients"]:
        checked(manager.post(route+"/mutations", json={"operation": "client.put", "expected_revision": current["revision"],
            "request_id": uuid.uuid4().hex, "client_id": "mastermind", "client": {"enabled": True,
                "token_sha256": hashlib.sha256(token("client.token").encode()).hexdigest(), "allowed_adapters": ["google"],
                "bindings": {name: {"adapter_id": "google", "profile": "default"} for name in ("text", "media")}}}))
    for connection in (kernel, volt, manager):
        connection.close()
    print("Enrolled scoped Wyvern instance. Provider key moved in memory over TLS into encrypted fixture Volt; no key output/files.")


if __name__ == "__main__":
    if sys.argv[1:] == ["enroll"]:
        enroll()
    else:
        prepare()
