import io
import socket
import threading
import time

import pytest

from mastermind.errors import DomainError
from mastermind.worker_fetch import PublicFetch, PublicHTTP, allowed_address, connect_public


@pytest.mark.parametrize("value", ["127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.0.1", "169.254.169.254",
                                  "0.0.0.0", "100.64.0.1", "224.0.0.1", "255.255.255.255", "::1", "::",
                                  "fe80::1", "fc00::1", "::ffff:127.0.0.1", "2002:7f00:1::", "ff02::1"])
def test_private_special_and_transition_destinations_are_rejected(value):
    assert not allowed_address(value)


def test_dns_result_is_pinned_and_mixed_private_answer_fails_closed():
    calls = []

    class FakeSocket:
        def settimeout(self, value):
            pass

        def connect(self, address):
            calls.append(address)

        def getpeername(self):
            return ("8.8.8.8", 443)

        def close(self):
            pass

    def resolver(host, port, **kwargs):
        assert host == "public.example" and port == 443
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443))]

    connect_public("public.example", 443, resolver=resolver, factory=lambda *args: FakeSocket())
    assert calls == [("8.8.8.8", 443)]
    with pytest.raises(DomainError) as mixed:
        connect_public("public.example", 443, resolver=lambda *args, **kwargs: resolver(*args, **kwargs) + [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443))], factory=lambda *args: FakeSocket())
    assert mixed.value.code == "SSRF_REJECTED" and len(calls) == 1


class FakeResponse:
    def __init__(self, status=200, body=b"document", **headers):
        self.status, self.headers, self.body = status, headers, io.BytesIO(body)

    def getheader(self, key, default=None):
        return self.headers.get(key, default)

    def getheaders(self):
        return list(self.headers.items())

    def read(self, count):
        return self.body.read(count)

    def close(self):
        pass


class FakeConnection:
    def __init__(self, result):
        self.result = result

    def request(self, *args, **kwargs):
        assert kwargs["headers"]["Accept-Encoding"] == "identity"

    def getresponse(self):
        return self.result

    def close(self):
        pass


@pytest.mark.parametrize("phase", ["headers", "body"])
def test_actual_socket_drip_cannot_extend_wall_clock_deadline(monkeypatch, phase):
    client, server = socket.socketpair()
    def connect(connection):
        connection.sock = client
    monkeypatch.setattr(PublicHTTP, "connect", connect)
    def send():
        try:
            server.recv(8192)
            server.sendall(b"HTTP/1.1 200 OK\r\n")
            if phase == "body":
                server.sendall(b"Content-Length: 100\r\nConnection: close\r\n\r\n")
            else:
                server.sendall(b"X-Drip: ")
            for _ in range(100):
                server.sendall(b"a")
                time.sleep(0.03)
        except OSError:
            pass
        finally:
            server.close()
    sender = threading.Thread(target=send, daemon=True)
    sender.start()
    began = time.monotonic()
    try:
        with pytest.raises(DomainError) as failure:
            PublicFetch().get("http://example.test/", io.BytesIO(), deadline=began+0.2)
        assert failure.value.code == "SOURCE_TIMEOUT"
        assert time.monotonic()-began < 1
    finally:
        client.close()
        server.close()
        sender.join(timeout=1)


def test_header_parser_stops_at_the_wire_limit(monkeypatch):
    client, server = socket.socketpair()
    monkeypatch.setattr(PublicHTTP, "connect", lambda connection: setattr(connection, "sock", client))
    def send():
        try:
            server.recv(8192)
            server.sendall(b"HTTP/1.1 200 OK\r\nX-Large: " + b"a"*20000 + b"\r\n\r\n")
        except OSError:
            pass
        finally:
            server.close()
    sender = threading.Thread(target=send, daemon=True)
    sender.start()
    try:
        with pytest.raises(DomainError) as failure:
            PublicFetch().get("http://example.test/", io.BytesIO())
        assert failure.value.code == "SOURCE_HEADERS_INVALID"
    finally:
        client.close()
        sender.join(timeout=1)


def test_every_redirect_reenters_the_socket_policy_and_redirect_count_is_bounded():
    seen = []

    def connection(parsed):
        seen.append(parsed.hostname)
        if parsed.hostname == "127.0.0.1":
            raise DomainError("SSRF_REJECTED", "private", 422)
        return FakeConnection(FakeResponse(302, Location="http://127.0.0.1/private"))

    with pytest.raises(DomainError) as denied:
        PublicFetch(factory=connection).get("https://example.test", io.BytesIO())
    assert seen == ["example.test", "127.0.0.1"] and denied.value.code == "SSRF_REJECTED"
    with pytest.raises(DomainError) as loop:
        PublicFetch(factory=lambda url: FakeConnection(FakeResponse(302, Location="/again"))).get(
            "https://example.test", io.BytesIO())
    assert loop.value.code == "SOURCE_REDIRECT_LIMIT"


@pytest.mark.parametrize("response,limit,code", [
    (FakeResponse(**{"Content-Length": "10000"}), 100, "SOURCE_SIZE_INVALID"),
    (FakeResponse(body=b"a"*200), 100, "SOURCE_SIZE_INVALID"),
    (FakeResponse(**{"Content-Length": "99"}), 100, "SOURCE_INTEGRITY"),
    (FakeResponse(**{"Content-Encoding": "gzip"}), 100, "SOURCE_ENCODING"),
    (FakeResponse(**{"X-Large": "a"*17000}), 100, "SOURCE_HEADERS_INVALID"),
    (FakeResponse(503), 100, "SOURCE_NETWORK"),
])
def test_fetch_bounds_are_enforced_on_actual_bytes(response, limit, code):
    with pytest.raises(DomainError) as failure:
        PublicFetch(factory=lambda parsed: FakeConnection(response)).get("https://example.test", io.BytesIO(), limit=limit)
    assert failure.value.code == code
