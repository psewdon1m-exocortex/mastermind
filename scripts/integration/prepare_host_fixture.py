"""Build private transport/signing fixtures for a real isolated Linux host.

GitHub release HTTP is controlled only inside that host. Real signature checks,
Docker registry pulls, systemd/Updater and related service APIs remain enabled.
This script neither publishes a release nor changes workstation trust or DNS.
"""
import datetime
import ipaddress
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT/".local/host-fixture"


def private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(value)
    path.chmod(0o600)


def main():
    FIXTURE.mkdir(parents=True, exist_ok=True, mode=0o700)
    key_path = FIXTURE/"transport-ca.key"
    if not key_path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        private(key_path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Mastermind isolated qualification CA")])
        now = datetime.datetime.now(datetime.UTC)
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=5))
              .not_valid_after(now+datetime.timedelta(days=30)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .sign(key, hashes.SHA256()))
        (FIXTURE/"transport-ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        private(FIXTURE/"transport.key", leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mastermind.qualification.test")]))
                .issuer_name(name).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-datetime.timedelta(minutes=5)).not_valid_after(now+datetime.timedelta(days=30))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(host) for host in
                  ("github.com", "api.github.com", "mastermind.qualification.test")]+[x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
                .sign(key, hashes.SHA256()))
        (FIXTURE/"transport.crt").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    for service in ("mastermind", "updater", "neptune"):
        path = FIXTURE/(service+"-signing.key")
        if not path.exists():
            key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
            private(path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            (FIXTURE/(service+".pem")).write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    (FIXTURE/"combined-ca.crt").write_bytes((FIXTURE/"transport-ca.crt").read_bytes()+(ROOT/".local/integration/ca.crt").read_bytes())
    private(FIXTURE/"kernel.token", (ROOT/".local/integration/kernel.token").read_bytes())
    vendor = FIXTURE/"updater"
    for relative in ("install.sh", "systemd/updater.service", "release-trust/gryphon.pem"):
        destination = vendor/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/".local/services/updater"/relative, destination)
    shutil.copyfile(ROOT/".local/services/updater/updater", vendor/"updater-linux-amd64")
    for service in ("updater", "neptune"):
        shutil.copyfile(FIXTURE/(service+".pem"), vendor/"release-trust"/(service+".pem"))
    (FIXTURE/"README.txt").write_text("Private local qualification transport/signers; never install this CA on a real host or publish these keys.\n")
    print("Prepared private host qualification transport and signed-candidate identities; no secrets printed")


if __name__ == "__main__":
    main()
