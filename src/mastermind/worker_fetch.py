"""Public-source HTTP transport with DNS pinning at the actual socket boundary."""
import hashlib
import http.client
import ipaddress
import os
import queue
import socket
import ssl
import threading
import time
from urllib.parse import urljoin, urlsplit

from . import __version__
from .crusher_access import public_url
from .errors import DomainError

DNS_SLOTS = threading.BoundedSemaphore(4)


def resolve_public(host, port, **kwargs):
    # libc DNS can outlive a socket timeout. Bound waiting and abandoned work;
    # an unavailable resolver cannot accumulate unbounded threads.
    if not DNS_SLOTS.acquire(blocking=False):
        raise DomainError("SOURCE_NETWORK", "The bounded DNS resolver is busy.", 503)
    result = queue.Queue(maxsize=1)
    def lookup():
        try:
            result.put((socket.getaddrinfo(host, port, **kwargs), None))
        except OSError as error:
            result.put((None, error))
        finally:
            DNS_SLOTS.release()
    threading.Thread(target=lookup, daemon=True, name="public-dns").start()
    try:
        records, failure = result.get(timeout=5)
    except queue.Empty:
        raise DomainError("SOURCE_NETWORK", "The public DNS lookup timed out.", 503) from None
    if failure:
        raise DomainError("SOURCE_NETWORK", "The public DNS lookup failed.", 503) from None
    return records


def allowed_address(value):
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
        if not address.is_global or address.is_multicast or address.is_reserved or address.is_unspecified:
            return False
        if isinstance(address, ipaddress.IPv6Address):
            return not (address.ipv4_mapped or address.sixtofour or address.teredo or address.is_site_local)
        return True
    except ValueError:
        return False


def connect_public(host, port, *, resolver=resolve_public, factory=socket.socket, deadline=None):
    deadline = deadline or time.monotonic()+60
    try:
        records = resolver(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        if not records or len(records) > 32 or any(not allowed_address(record[4][0]) for record in records):
            raise DomainError("SSRF_REJECTED", "The source destination is not public.", 422)
        attempted = set()
        for family, kind, protocol, _, address in records:
            if time.monotonic() >= deadline:
                raise DomainError("SOURCE_TIMEOUT", "The public connection exceeded its deadline.", 408)
            if address in attempted:
                continue
            attempted.add(address)
            stream = factory(family, kind, protocol)
            stream.settimeout(max(0.01, min(5, deadline-time.monotonic())))
            try:
                # No second hostname lookup: connect to the already validated numeric address.
                stream.connect(address)
                peer = stream.getpeername()[0]
                if ipaddress.ip_address(peer) != ipaddress.ip_address(address[0]) or not allowed_address(peer):
                    raise DomainError("SSRF_REJECTED", "The source connection changed its destination.", 422)
                stream.settimeout(max(0.01, min(60, deadline-time.monotonic())))
                return stream
            except (OSError, DomainError):
                stream.close()
        raise OSError("All public addresses were unreachable")
    except OSError:
        raise DomainError("SOURCE_NETWORK", "The public source could not be reached.", 503) from None


class BoundedResponse(http.client.HTTPResponse):
    def begin(self):
        original = self.fp
        class Headers:
            remaining = 16*1024

            def readline(self, size=-1):
                value = original.readline(min(size if size >= 0 else self.remaining+1, self.remaining+1))
                self.remaining -= len(value)
                if self.remaining < 0:
                    raise DomainError("SOURCE_HEADERS_INVALID", "Source headers exceed 16 KiB.", 422)
                return value

            def close(self):
                original.close()
        self.fp = Headers()
        try:
            super().begin()
        finally:
            if self.fp is not None:
                self.fp = original


class PublicHTTP(http.client.HTTPConnection):
    response_class = BoundedResponse

    def connect(self):
        self.sock = connect_public(self.host, self.port, deadline=getattr(self, "hard_deadline", None))


class PublicHTTPS(http.client.HTTPSConnection):
    response_class = BoundedResponse

    def connect(self):
        self.sock = connect_public(self.host, self.port, deadline=getattr(self, "hard_deadline", None))
        try:
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)
        except BaseException:
            self.sock.close()
            raise


class PublicFetch:
    def __init__(self, *, factory=None, clock=time.monotonic):
        self.factory, self.clock = factory, clock

    def connection(self, parsed):
        if self.factory:
            return self.factory(parsed)
        if parsed.scheme == "https":
            return PublicHTTPS(parsed.hostname, parsed.port or 443, timeout=60, context=ssl.create_default_context())
        return PublicHTTP(parsed.hostname, parsed.port or 80, timeout=60)

    def get(self, url, output, *, limit=2*1024**3, deadline=None):
        url = public_url(url)
        deadline = min(deadline or self.clock()+900, self.clock()+900)
        for redirect in range(4):
            connection, response, timer = None, None, None
            try:
                if self.clock() >= deadline:
                    raise DomainError("SOURCE_TIMEOUT", "Source acquisition exceeded its deadline.", 408)
                parsed = urlsplit(url)
                connection = self.connection(parsed)
                connection.hard_deadline = time.monotonic()+max(0.01, deadline-self.clock())
                connected_socket = [None]
                if not self.factory:
                    def expire(connected_socket=connected_socket, connection=connection):
                        stream = connected_socket[0] or connection.sock
                        if stream is not None:
                            try:
                                stream.shutdown(socket.SHUT_RDWR)
                            except OSError:
                                pass
                    timer = threading.Timer(max(0.01, deadline-self.clock()), expire)
                    timer.daemon = True
                    timer.start()
                connection.request("GET", parsed.path + ("?"+parsed.query if parsed.query else ""), headers={
                    "User-Agent": f"Mastermind/{__version__} source-reader", "Accept-Encoding": "identity", "Connection": "close"})
                connected_socket[0] = getattr(connection, "sock", None)
                response = connection.getresponse()
                headers = response.getheaders()
                if sum(len(key)+len(value)+4 for key, value in headers) > 16*1024:
                    raise DomainError("SOURCE_HEADERS_INVALID", "Source headers exceed their limit.", 422)
                if response.status in (301, 302, 303, 307, 308):
                    target = response.getheader("Location")
                    if redirect == 3 or not target:
                        raise DomainError("SOURCE_REDIRECT_LIMIT", "Source redirect policy rejected this response.", 422)
                    url = public_url(urljoin(url, target))
                    continue
                if response.status in (429, 500, 502, 503, 504):
                    retry_after = response.getheader("Retry-After")
                    raise DomainError("SOURCE_NETWORK", "The public source is temporarily unavailable.", 503,
                                      {"Retry-After": retry_after} if retry_after and len(retry_after) <= 64 else {})
                if response.status != 200:
                    raise DomainError("SOURCE_UNAVAILABLE", "The public source did not return a readable document.", 422)
                if response.getheader("Content-Encoding", "identity").lower() not in ("identity", ""):
                    raise DomainError("SOURCE_ENCODING", "The source ignored the bounded identity encoding request.", 422)
                lengths = [value for key, value in headers if key.lower() == "content-length"]
                if len(lengths) > 1 or lengths and (not lengths[0].isascii() or not lengths[0].isdigit() or int(lengths[0]) > limit):
                    raise DomainError("SOURCE_SIZE_INVALID", "The source length is invalid or exceeds 2 GiB.", 413)
                content_hash, count = hashlib.sha256(), 0
                reader = getattr(response, "read1", response.read)
                while block := reader(256*1024):
                    count += len(block)
                    if count > limit:
                        raise DomainError("SOURCE_SIZE_INVALID", "The source exceeds its byte limit.", 413)
                    if self.clock() >= deadline:
                        raise DomainError("SOURCE_TIMEOUT", "Source acquisition exceeded its deadline.", 408)
                    output.write(block)
                    content_hash.update(block)
                if self.clock() >= deadline:
                    raise DomainError("SOURCE_TIMEOUT", "Source acquisition exceeded its deadline.", 408)
                if lengths and count != int(lengths[0]):
                    raise DomainError("SOURCE_INTEGRITY", "The source ended before its declared length.", 422)
                output.flush()
                if hasattr(output, "fileno"):
                    import io
                    try:
                        os.fsync(output.fileno())
                    except io.UnsupportedOperation:
                        pass
                return {"size": count, "sha256": content_hash.hexdigest(),
                        "mime": response.getheader("Content-Type", "application/octet-stream").split(";", 1)[0].lower(),
                        "url": url}
            except (OSError, http.client.HTTPException):
                if self.clock() >= deadline:
                    raise DomainError("SOURCE_TIMEOUT", "Source acquisition exceeded its deadline.", 408) from None
                raise DomainError("SOURCE_NETWORK", "The public source connection failed.", 503) from None
            finally:
                if timer:
                    timer.cancel()
                if response:
                    response.close()
                if connection:
                    connection.close()
        raise AssertionError("Redirect loop is bounded")
