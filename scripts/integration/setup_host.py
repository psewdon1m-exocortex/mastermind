"""Run only inside the disposable mastermind-qualification-host container."""
import json
import argparse
import os
import socket
import subprocess
from pathlib import Path


def assert_host():
    if socket.gethostname() != "mastermind-qualification-host" or os.geteuid() != 0:
        raise SystemExit("This fixture is restricted to its dedicated disposable host")


def main():
    assert_host()
    fixture = Path("/opt/qualification")
    saturn_address = "172.31.0.7" if (fixture/"clean-host").exists() else "172.31.0.5"
    for source, name in ((fixture/"transport-ca.crt", "mastermind-qualification.crt"),
                         (fixture/"combined-ca.crt", "mastermind-integration.crt")):
        # update-ca-certificates needs one certificate per file. The combined
        # bundle is used by Core separately; copy only the other existing CA.
        if source.name == "combined-ca.crt":
            blocks = source.read_text().split("-----END CERTIFICATE-----")
            data = blocks[1].lstrip()+"-----END CERTIFICATE-----\n"
        else:
            data = source.read_text()
        Path("/usr/local/share/ca-certificates", name).write_text(data)
    subprocess.run(["update-ca-certificates"], check=True)
    dns = "bind-dynamic\nlisten-address=127.0.0.1,10.245.0.1\nno-resolv\nserver=1.1.1.1\n"
    for host in ("kernel", "volt", "saturn", "chronos"):
        dns += f"address=/{host}.mastermind.test/{saturn_address if host == 'saturn' else '172.31.0.2'}\n"
    for host in ("github.com", "api.github.com", "mastermind.qualification.test"):
        dns += f"address=/{host}/10.245.0.1\n"
    dns += "address=/registry.mastermind.test/172.31.0.3\n"
    Path("/etc/dnsmasq.d/mastermind-qualification.conf").write_text(dns)
    subprocess.run(["systemctl", "restart", "dnsmasq"], check=True)
    hosts = Path("/etc/hosts")
    values = hosts.read_text()
    for line in ("127.0.0.1 github.com api.github.com mastermind.qualification.test",
                 "172.31.0.2 kernel.mastermind.test volt.mastermind.test chronos.mastermind.test",
                 saturn_address+" saturn.mastermind.test",
                 "172.31.0.3 registry.mastermind.test"):
        if line not in values:
            values += "\n"+line+"\n"
    hosts.write_text(values)
    daemon = Path("/etc/docker/daemon.json")
    config = json.loads(daemon.read_text())
    config.update({"dns": ["10.245.0.1"], "insecure-registries": ["registry.mastermind.test:5000"]})
    daemon.write_text(json.dumps(config))
    subprocess.run(["systemctl", "restart", "docker"], check=True)
    render_nginx()
    print("PASS: isolated host DNS, private CA and real Nginx syntax/listeners; application not installed yet")


def render_nginx():
    assert_host()
    Path("/etc/nginx/sites-enabled/default").unlink(missing_ok=True)
    config = """include /opt/nginx-qualification/mastermind-http.conf;
server { listen 443 ssl default_server; ssl_reject_handshake on; return 444; }
server {
    listen 443 ssl; server_name github.com api.github.com;
    ssl_certificate /opt/qualification/transport.crt;
    ssl_certificate_key /opt/qualification/transport.key;
    access_log off; error_log /dev/null emerg;
    location /repos/ { proxy_pass http://127.0.0.1:18881; }
    location / { root /opt/qualification/release-assets; try_files $uri =404; }
}
"""
    source = Path("/opt/nginx-qualification/mastermind-server.conf.template").read_text()
    source = source.replace("__MASTERMIND_HOST__", "mastermind.qualification.test") \
        .replace("__MASTERMIND_CERTIFICATE__", "/opt/qualification/transport.crt") \
        .replace("__MASTERMIND_CERTIFICATE_KEY__", "/opt/qualification/transport.key") \
        .replace("/opt/exocortex/mastermind/packaging/nginx", "/opt/nginx-qualification")
    Path("/etc/nginx/conf.d/mastermind-qualification.conf").write_text(config+source)
    subprocess.run(["nginx", "-t"], check=True)
    subprocess.run(["systemctl", "reload-or-restart", "nginx"], check=True)
    print("PASS: canonical qualification Nginx config rendered and loaded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--nginx-only", action="store_true")
    arguments = parser.parse_args()
    render_nginx() if arguments.nginx_only else main()
