"""Separate Saturn registration/database/storage root for clean-host acceptance."""
import json
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/".local/integration"
CLEAN = "--clean-host" in sys.argv
TARGET = ROOT/(".local/clean-install/saturn-api" if CLEAN else ".local/host-fixture/saturn-api")
DATABASE = "vault_clean" if CLEAN else "vault_host"
STORAGE = "gateway-clean" if CLEAN else "gateway-host"
API_NAME = "saturn-clean" if CLEAN else "saturn-host"
TARGET.mkdir(parents=True, exist_ok=True)
shutil.copytree(SOURCE/"saturn", TARGET/"saturn", dirs_exist_ok=True)
for name in ("entry.mjs", "tls.crt", "tls.key"):
    shutil.copyfile(SOURCE/name, TARGET/name)
env = json.loads((SOURCE/"saturn-env.json").read_text())
url = urllib.parse.urlsplit(env["DATABASE_URL"])
env["DATABASE_URL"] = urllib.parse.urlunsplit(url._replace(path="/"+DATABASE))
env["STORAGE_ROOT"] = STORAGE
(TARGET/"saturn-env.json").write_text(json.dumps(env))
(TARGET/"saturn-env.json").chmod(0o600)
nginx = (SOURCE/"nginx.conf").read_text()
server = next(line for line in nginx.splitlines() if "server_name saturn.mastermind.test;" in line)
(TARGET/"nginx.conf").write_text("user nginx; events {} http {access_log off; error_log /dev/null emerg; client_max_body_size 8g; proxy_buffering off; proxy_request_buffering off; proxy_read_timeout 900s; proxy_send_timeout 120s;\n"+server.replace("http://saturn:3000", "http://"+API_NAME+":3000")+"\n}\n")
service = {"image": "mastermind-saturn:integration", "init": True, "read_only": True, "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges:true"], "pids_limit": 256, "mem_limit": "768m", "cpus": 2,
    "volumes": ["./:/fixture:ro", "saturn-host-data:/app/data"], "tmpfs": ["/tmp:rw,nosuid,nodev,size=128m,mode=1777"],
    "networks": ["private"], "logging": {"driver": "json-file", "options": {"max-size": "5m", "max-file": "2"}},
    "depends_on": {"initialize": {"condition": "service_completed_successfully"}},
    "command": ["node", "/fixture/entry.mjs", "saturn", "node", "/app/api/dist/main.js"]}
initialize = {"image": "mastermind-saturn:integration", "user": "0:0", "read_only": True,
    "cap_drop": ["ALL"], "cap_add": ["CHOWN"], "security_opt": ["no-new-privileges:true"],
    "network_mode": "none", "volumes": ["saturn-host-data:/data"],
    "entrypoint": ["node", "-e", "require('node:fs').chownSync('/data',1000,1000)"]}
worker = {**service, "command": ["node", "/fixture/entry.mjs", "saturn", "node", "/app/worker/dist/main.js"]}
migrate = {**service, "command": ["node", "/fixture/entry.mjs", "saturn", "node", "/app/scripts/migrate-runtime.mjs"]}
service["depends_on"] = worker["depends_on"] = {"migrate": {"condition": "service_completed_successfully"}}
gateway = {"image": "nginx:1.29.4-alpine@sha256:4870c12cd2ca986de501a804b4f506ad3875a0b1874940ba0a2c7f763f1855b2",
    "entrypoint": ["nginx", "-g", "daemon off;", "-c", "/fixture/nginx.conf"], "volumes": ["./:/fixture:ro"],
    "networks": {"private": {}, "edge": {"ipv4_address": "172.31.0.7" if CLEAN else "172.31.0.5"}}, "ports": ["127.0.0.1:"+("19443" if CLEAN else "19442")+":443"],
    "mem_limit": "128m", "depends_on": [API_NAME]}
compose = {"name": "mastermind-clean-services" if CLEAN else "mastermind-host-services", "services": {"initialize": initialize, "migrate": migrate, API_NAME: service, ("saturn-clean-worker" if CLEAN else "saturn-worker"): worker, "gateway": gateway},
    "volumes": {"saturn-host-data": {}}, "networks": {name: {"external": True, "name": "mastermind-integration_"+name} for name in ("private", "edge")}}
(TARGET/"compose.yml").write_text(yaml.safe_dump(compose, sort_keys=False))
query = subprocess.run(["docker", "exec", "mastermind-integration-postgres-1", "psql", "-U", "vault", "-d", "vault", "-tA", "-c", "SELECT 1 FROM pg_database WHERE datname='"+DATABASE+"'"], check=True, capture_output=True, text=True)
if not query.stdout.strip():
    subprocess.run(["docker", "exec", "mastermind-integration-postgres-1", "createdb", "-U", "vault", DATABASE], check=True)
subprocess.run(["docker", "exec", "mastermind-integration-sftp-1", "mkdir", "-p", "/home/vault/"+STORAGE], check=True)
subprocess.run(["docker", "exec", "mastermind-integration-sftp-1", "chown", "1001:1001", "/home/vault/"+STORAGE], check=True)
print("Prepared an independent Saturn database and storage root; existing registration retained")
