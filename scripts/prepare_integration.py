"""Generate isolated local-service fixtures. No production identities or user Vault data."""
import datetime
import ipaddress
import json
import secrets
import subprocess
from pathlib import Path

import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / ".local" / "integration"
SERVICES = ROOT / ".local" / "services"
FIXTURE.mkdir(parents=True, exist_ok=True)


def save(name, value):
    path = FIXTURE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")
    path.chmod(0o600)


def token(name):
    path = FIXTURE / name
    if not path.exists():
        save(name, secrets.token_urlsafe(32))
    return path.read_text(encoding="utf-8")


def tls():
    if (FIXTURE / "ca.crt").exists():
        return
    ca_key, key = rsa.generate_private_key(65537, 2048), rsa.generate_private_key(65537, 2048)
    now = datetime.datetime.now(datetime.UTC)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Mastermind isolated integration CA")])
    ca = x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key()) \
        .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1)) \
        .not_valid_after(now + datetime.timedelta(days=30)) \
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True).sign(ca_key, hashes.SHA256())
    names = [x509.DNSName(name) for name in ["localhost", "kernel.mastermind.test", "volt.mastermind.test",
                                           "saturn.mastermind.test", "chronos.mastermind.test", "mastermind.test"]]
    names.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    cert = x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mastermind.test")])) \
        .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number()) \
        .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=29)) \
        .add_extension(x509.SubjectAlternativeName(names), critical=False).sign(ca_key, hashes.SHA256())
    save("ca.crt", ca.public_bytes(serialization.Encoding.PEM).decode())
    save("tls.crt", cert.public_bytes(serialization.Encoding.PEM).decode())
    save("tls.key", key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()).decode())


tls()
node = subprocess.run(["node", "--input-type=module", "-e",
    ("import {prepareDevelopmentEnvironment} from './scripts/prepare-dev.mjs'; "
    "const x=await prepareDevelopmentEnvironment({postgresPort:19532,sftpPort:19222,runtimeNamespace:'mastermind-integration'}); "
    "process.stdout.write(JSON.stringify(x.environment));")], cwd=SERVICES / "saturn", capture_output=True, text=True, check=False)
if node.returncode:
    raise SystemExit("Saturn fixture generation failed; inspect the local preparation script.")
saturn = json.loads(node.stdout)
for name, value in list(saturn.items()):
    if name.endswith("_FILE") and value:
        source = Path(value)
        save("saturn/" + source.name, source.read_text(encoding="utf-8"))
        saturn[name] = "/fixture/saturn/" + source.name
    elif name.endswith(("_DIR", "_DIRECTORY")):
        saturn[name] = "/app/data/" + name.lower()
saturn.update(API_HOST="0.0.0.0", API_PORT="3000", WORKER_HOST="0.0.0.0", STORAGE_HOST="sftp", STORAGE_PORT="22",
              PUBLIC_ORIGIN="https://saturn.mastermind.test", API_TRUSTED_PROXIES="10.194.0.10",
              DATABASE_URL=saturn["DATABASE_URL"].replace("127.0.0.1:19532", "postgres:5432"),
              PG_DUMP_BIN="pg_dump", PG_RESTORE_BIN="pg_restore", PG_DUMP_PREFIX_ARGS="[]", PG_RESTORE_PREFIX_ARGS="[]",
              PG_COMMAND_CONNECTION_ARGS="[]", ARCHIVE_7Z_BIN="7zz")
save("saturn-env.json", json.dumps(saturn))
save("kernel-env.json", json.dumps({
    "KERNEL_DATA_DIR": "/app/data", "KERNEL_LISTEN_PORT": "18180", "KERNEL_ACCESS_KEY": token("kernel-access"),
    "KERNEL_SESSION_SECRET": token("kernel-session"), "KERNEL_SERVICE_TOKEN": token("kernel.token"),
    "UPDATER_CONTROL_TOKEN": token("updater.token"), "VOLT_URL": "https://volt.mastermind.test",
    "VOLT_KERNEL_TOKEN_FILE": "/fixture/volt-kernel.token", "NODE_EXTRA_CA_CERTS": "/fixture/ca.crt",
    "KERNEL_COOKIE_SECURE": "true", "KERNEL_TRUSTED_PROXIES": "10.194.0.10"}))
token("volt-kernel.token")
token("volt-device.key")
token("volt-access")
save("volt-env.json", json.dumps({
    "VOLT_DATA_DIR": "/app/data", "VOLT_DEVICE_KEY_FILE": "/fixture/volt-device.key",
    "VOLT_ACCESS_KEY_FILE": "/fixture/volt-access", "VOLT_KERNEL_TOKEN_FILE": "/fixture/volt-kernel.token",
    "VOLT_LISTEN_HOST": "0.0.0.0", "VOLT_PORT": "18184", "VOLT_SECURE_COOKIES": "true",
    "VOLT_KERNEL_URL": "https://kernel.mastermind.test", "VOLT_TRUSTED_PROXIES": "10.194.0.10",
    "NODE_EXTRA_CA_CERTS": "/fixture/ca.crt"}))
token("neptune-control.token")
token("neptune-export.token")
token("chronos-reader.token")
save("chronos-env.json", json.dumps({
    "DATABASE_URL": saturn["DATABASE_URL"].removesuffix("/vault") + "/chronos",
    "CHRONOS_ACCESS_KEY": token("chronos-access"), "CHRONOS_SESSION_SECRET": token("chronos-session"),
    "CHRONOS_COOKIE_SECURE": "true", "CHRONOS_TRUST_PROXY": "true", "CHRONOS_DATA_DIR": "/app/data",
    "CHRONOS_LISTEN_PORT": "18280", "CHRONOS_PUBLIC_URL": "https://chronos.mastermind.test",
    "KERNEL_URL": "https://kernel.mastermind.test", "KERNEL_SERVICE_TOKEN": token("kernel.token"),
    "SSL_CERT_FILE": "/fixture/ca.crt", "MASTERMIND_READER_TOKEN_FILE": "/fixture/chronos-reader.token"}))
save("python-entry.py", "import json,os,sys; name=sys.argv[1]; os.environ.update(json.load(open('/fixture/'+name+'-env.json'))); os.execvp(sys.argv[2],sys.argv[2:])\n")
if (FIXTURE / "enrollment.json").exists():
    enrollment = json.loads((FIXTURE / "enrollment.json").read_text())
    save("neptune-project.env", "\n".join(name + "=" + value for name, value in {
        "NEPTUNE_BACKUP_EXPORT_URL": "http://127.0.0.1:18390/api/internal/neptune/backup",
        "NEPTUNE_CONTROL_TOKEN_FILE": "/fixture/neptune-control.token", "NEPTUNE_EXPORT_TOKEN_FILE": "/fixture/neptune-export.token",
        "NEPTUNE_SATURN_TOKEN_FILE": "/fixture/saturn-archive.token", "NEPTUNE_SATURN_SLUG": enrollment["slug"],
        "NEPTUNE_MIRROR_ROOT": "mastermind", "NEPTUNE_MIRROR_MODE": "zip-tree",
        "NEPTUNE_MIRROR_EXPORT_URL": "http://127.0.0.1:18390/api/internal/neptune/mirror",
        "NEPTUNE_MIRROR_TOKEN_FILE": "/fixture/saturn-mirror.token", "NEPTUNE_READER_TOKEN_FILE": "/fixture/saturn-reader.token",
        "NEPTUNE_READER_ROOT": "root", "NEPTUNE_BACKUP_ENABLED": "false", "NEPTUNE_MIRROR_ENABLED": "false"}.items()) + "\n")
save("neptune-entry.sh", "#!/bin/sh\nset -eu\ncp /fixture/ca.crt /usr/local/share/ca-certificates/mastermind-integration.crt\n"
     "update-ca-certificates >/dev/null\nmkdir -p /var/lib/neptune /run/neptune\n"
     "dotnet /app/Neptune.Linux.dll register-project mastermind /fixture/neptune-project.env\nexec dotnet /app/Neptune.Linux.dll\n")
save("entry.mjs", "import fs from 'node:fs'; import {spawn} from 'node:child_process';\n"
     "const [name,...command]=process.argv.slice(2); const env={...process.env,...JSON.parse(fs.readFileSync('/fixture/'+name+'-env.json','utf8'))};\n"
     "const child=spawn(command[0],command.slice(1),{env,stdio:'inherit'}); for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>child.kill(signal)); "
     "child.on('exit',code=>process.exit(code??1));\n")
save("nginx.conf", "user nginx;\nevents {}\nhttp { access_log off; error_log /dev/stderr warn; client_max_body_size 8g; "
     "proxy_buffering off; proxy_request_buffering off; proxy_read_timeout 900s; proxy_send_timeout 120s;\n" + "\n".join(
         "server { listen 443 ssl; server_name " + name + ".mastermind.test; ssl_certificate /fixture/tls.crt; "
         "ssl_certificate_key /fixture/tls.key; location / { proxy_pass http://" + name + ":" + str(port) + "; "
         "proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto https; proxy_set_header X-Forwarded-For $remote_addr; }}"
         for name, port in [("kernel", 18180), ("volt", 18184), ("saturn", 3000), ("chronos", 18280)]) +
     "\nserver { listen 443 ssl; server_name neptune.mastermind.test; ssl_certificate /fixture/tls.crt; ssl_certificate_key /fixture/tls.key; "
     "location / { proxy_pass http://unix:/run/neptune/neptuned.sock:; }}\n}\n")

common = {"restart": "no", "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}},
          "networks": ["private"], "security_opt": ["no-new-privileges:true"], "pids_limit": 256}
services = {}
for name in ("kernel", "volt", "saturn"):
    services[name] = {**common, "image": f"mastermind-{name}:integration", "init": True, "read_only": True,
                      "cap_drop": ["ALL"], "mem_limit": "768m", "cpus": 2,
                      "volumes": ["./:/fixture:ro", f"{name}-data:/app/data"],
                      "tmpfs": ["/tmp:rw,nosuid,nodev,size=128m,mode=1777"],
                      "command": ["node", "/fixture/entry.mjs", name, "node",
                                  "/app/api/dist/main.js" if name == "saturn" else "/app/server/index.js"],
                      "depends_on": {"initialize": {"condition": "service_completed_successfully"}}}
services["initialize"] = {**common, "image": "python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254",
    "user": "0:0", "cap_drop": ["ALL"], "cap_add": ["CHOWN", "FOWNER"],
    "volumes": [f"{name}-data:/{name}" for name in ("kernel", "volt", "saturn", "sftp")],
    "command": ["python", "-c", "import os; [(os.chown('/'+n,1000,1000),os.chmod('/'+n,0o700)) for n in ['kernel','volt','saturn']]; os.chown('/sftp',1001,1001)"]}
services["postgres"] = {**common,
    "image": "postgres:18.1-alpine@sha256:aa6eb304ddb6dd26df23d05db4e5cb05af8951cda3e0dc57731b771e0ef4ab29",
    "environment": {"POSTGRES_DB": "vault", "POSTGRES_USER": "vault", "POSTGRES_PASSWORD_FILE": "/fixture/saturn/dev-postgres-password"},
    "volumes": ["./:/fixture:ro", "postgres-data:/var/lib/postgresql"], "mem_limit": "768m",
    "healthcheck": {"test": ["CMD", "pg_isready", "-U", "vault", "-d", "vault"], "interval": "2s", "timeout": "3s", "retries": 30}}
# The generated DB password is part of DATABASE_URL, not one of Saturn's *_FILE environment values.
save("saturn/dev-postgres-password", (SERVICES / "saturn/.secrets/dev-postgres-password").read_text())
sftp = SERVICES / "saturn/.tmp/mastermind-integration/sftp"
save("sftp-entrypoint.sh", (SERVICES / "saturn/infra/dev/sftp-entrypoint.sh").read_text())
services["sftp"] = {**common,
    "image": "atmoz/sftp:alpine@sha256:81fa92512bf8ead4849f33c1c153907b86d32d77704d1c62a9c70b4316ae9e50",
    "entrypoint": ["/bin/sh", "/bootstrap/entrypoint.sh"], "mem_limit": "192m",
    "volumes": [str(sftp / "users.conf") + ":/etc/sftp/users.conf:ro",
                "./sftp-entrypoint.sh:/bootstrap/entrypoint.sh:ro",
                str(sftp / "ssh_host_ed25519_key") + ":/hostkeys/ssh_host_ed25519_key:ro",
                str(sftp / "dev_client_ed25519.pub") + ":/home/vault/.ssh/keys/dev_client_ed25519.pub:ro",
                "sftp-data:/home/vault/gateway"]}
services["neptune"] = {**common, "image": "mastermind-neptune:integration", "user": "0:101", "mem_limit": "512m", "cpus": 2,
    "environment": {"Neptune__KernelOrigin": "https://kernel.mastermind.test", "Neptune__KernelTokenFile": "/fixture/kernel.token"},
    "volumes": ["./:/fixture:ro", "neptune-data:/var/lib/neptune", "neptune-socket:/run/neptune"],
    "depends_on": ["kernel", "saturn"]}
# The host daemon normally calls the loopback-only Core export endpoint. In this
# isolated Docker fixture it shares Core's network namespace, retaining that boundary.
services["neptune"].pop("networks")
services["neptune"]["network_mode"] = "container:mastermind-development-core-1"
services["chronos"] = {**common, "image": "mastermind-chronos:integration", "mem_limit": "512m", "cpus": 2,
    "read_only": True, "cap_drop": ["ALL"], "volumes": ["./:/fixture:ro", "chronos-data:/app/data"],
    "tmpfs": ["/tmp:rw,nosuid,nodev,size=64m,mode=1777"],
    "command": ["python", "/fixture/python-entry.py", "chronos", "python", "-m", "app"],
    "depends_on": {"postgres": {"condition": "service_healthy"}}}
services["gateway"] = {**common,
    "image": "nginx:1.29.4-alpine@sha256:4870c12cd2ca986de501a804b4f506ad3875a0b1874940ba0a2c7f763f1855b2",
    "entrypoint": ["nginx", "-g", "daemon off;", "-c", "/fixture/nginx.conf"], "mem_limit": "128m",
    "volumes": ["./:/fixture:ro", "neptune-socket:/run/neptune:ro"], "ports": ["127.0.0.1:19441:443"],
    "networks": {"private": {"ipv4_address": "10.194.0.10", "aliases": [name + ".mastermind.test" for name in ["kernel", "volt", "saturn", "chronos"]]}, "edge": {}},
    "depends_on": ["kernel", "volt", "saturn", "chronos", "neptune"]}
services["saturn"]["depends_on"].update(postgres={"condition": "service_healthy"}, sftp={"condition": "service_started"})
save("compose.yml", yaml.safe_dump({"name": "mastermind-integration", "services": services,
    "volumes": {**{name + "-data": {} for name in ["kernel", "volt", "saturn", "postgres", "sftp", "neptune", "chronos"]}, "neptune-socket": {}},
    "networks": {"private": {"internal": True, "ipam": {"config": [{"subnet": "10.194.0.0/24"}]}}, "edge": {}}}, sort_keys=False))
save("core-override.yml", yaml.safe_dump({"services": {"core": {
    "group_add": ["101"],
    "environment": {"MASTERMIND_KERNEL_URL": "https://kernel.mastermind.test", "MASTERMIND_SECRET_BACKEND": "kernel",
        "MASTERMIND_KERNEL_TOKEN_FILE": "/run/integration/kernel.token", "MASTERMIND_TRUST_CA_FILE": "/run/integration/ca.crt",
        "MASTERMIND_NEPTUNE_SOCKET": "/run/neptune/neptuned.sock",
        "MASTERMIND_NEPTUNE_TOKEN_FILE": "/run/integration/neptune-control.token",
        "MASTERMIND_NEPTUNE_EXPORT_TOKEN_FILE": "/run/integration/neptune-export.token"},
    "volumes": [str(FIXTURE) + ":/run/integration:ro", "integration-neptune-socket:/run/neptune:ro"],
    "networks": ["integration-private"]}},
    "networks": {"integration-private": {"external": True, "name": "mastermind-integration_private"}},
    "volumes": {"integration-neptune-socket": {"external": True, "name": "mastermind-integration_neptune-socket"}}}, sort_keys=False))
print("Generated isolated integration fixture, TLS trust and protected test identities.")
