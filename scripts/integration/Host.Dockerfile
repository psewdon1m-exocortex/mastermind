# Qualification host only: an isolated Linux OS with its own systemd and Docker.
# Never mount the outer host Docker socket or use this image as a service image.
FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90
ENV container=docker DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    systemd systemd-sysv dbus docker.io docker-compose-v2 iptables iproute2 \
    curl ca-certificates openssl python3 nano nginx tini jq xz-utils \
    && rm -rf /var/lib/apt/lists/* \
    && systemctl enable docker.service \
    && systemctl mask getty.target console-getty.service systemd-remount-fs.service \
    && mkdir -p /etc/docker \
    && printf '%s\n' '{"storage-driver":"overlay2","log-driver":"local","default-address-pools":[{"base":"10.245.0.0/16","size":24}]}' > /etc/docker/daemon.json \
    && dpkg-query -W > /qualification-packages.txt
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
