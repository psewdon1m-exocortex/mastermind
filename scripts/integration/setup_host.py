"""Run only inside the disposable mastermind-qualification-host container."""
import json
import os
import socket
import subprocess
from pathlib import Path


def main():
    if socket.gethostname() != "mastermind-qualification-host" or os.geteuid() != 0:
        raise SystemExit("This fixture is restricted to its dedicated disposable host")
    fixture = Path("/opt/qualification")
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
    dns = "bind-interfaces\nlisten-address=127.0.0.1,10.245.0.1\nno-resolv\nserver=1.1.1.1\n"
    for host in ("kernel", "volt", "saturn", "chronos"):
        dns += f"address=/{host}.mastermind.test/172.31.0.{5 if host == 'saturn' else 2}\n"
    for host in ("github.com", "api.github.com", "mastermind.qualification.test"):
        dns += f"address=/{host}/10.245.0.1\n"
    dns += "address=/registry.mastermind.test/172.31.0.4\n"
    Path("/etc/dnsmasq.d/mastermind-qualification.conf").write_text(dns)
    subprocess.run(["systemctl", "restart", "dnsmasq"], check=True)
    hosts = Path("/etc/hosts")
    values = hosts.read_text()
    for line in ("127.0.0.1 github.com api.github.com mastermind.qualification.test",
                 "172.31.0.2 kernel.mastermind.test volt.mastermind.test chronos.mastermind.test",
                 "172.31.0.5 saturn.mastermind.test",
                 "172.31.0.4 registry.mastermind.test"):
        if line not in values:
            values += "\n"+line+"\n"
    hosts.write_text(values)
    daemon = Path("/etc/docker/daemon.json")
    config = json.loads(daemon.read_text())
    config.update({"dns": ["10.245.0.1"], "insecure-registries": ["registry.mastermind.test:5000"]})
    daemon.write_text(json.dumps(config))
    subprocess.run(["systemctl", "restart", "docker"], check=True)
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
    subprocess.run(["systemctl", "restart", "nginx"], check=True)
    print("PASS: isolated host DNS, private CA and real Nginx syntax/listeners; application not installed yet")


if __name__ == "__main__":
    main()
