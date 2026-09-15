"""Loopback-only Git HTTP proxy. Every upstream socket uses the public-address guard."""
import select
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .crusher_access import public_url
from .worker_fetch import PublicFetch, connect_public


class PublicProxy(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 8

    def __init__(self, *, limit=2*1024**3, seconds=900):
        super().__init__(("127.0.0.1", 0), ProxyHandler)
        self.limit, self.deadline, self.transferred = limit, time.monotonic()+seconds, 0
        self.guard = threading.Lock()
        self.slots = threading.BoundedSemaphore(4)
        self.stopped = threading.Event()

    def account(self, amount):
        with self.guard:
            self.transferred += amount
            if self.transferred > self.limit or time.monotonic() >= self.deadline or self.stopped.is_set():
                raise OSError("Proxy byte or time budget exhausted")

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # Public source diagnostics never enter service logs.


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass

    def do_CONNECT(self):
        upstream = None
        try:
            parsed = urlsplit("https://" + self.path)
            if parsed.port != 443 or parsed.username is not None or parsed.password is not None \
                    or parsed.path or parsed.query or parsed.fragment or len(self.path) > 512:
                raise ValueError
            upstream = connect_public(parsed.hostname, 443)
            self.send_response(200)
            self.end_headers()
            self.wfile.flush()
            self.connection.setblocking(False)
            upstream.setblocking(False)
            pending = {self.connection: bytearray(), upstream: bytearray()}
            peers = {self.connection: upstream, upstream: self.connection}
            closed = set()
            last_progress = time.monotonic()
            while not self.server.stopped.is_set():
                self.server.account(0)
                if time.monotonic()-last_progress > 60:
                    raise TimeoutError
                if upstream in closed and not pending[self.connection]:
                    return
                readable = [stream for stream in peers if stream not in closed and len(pending[peers[stream]]) < 256*1024]
                writable = [stream for stream, buffer in pending.items() if buffer]
                reads, writes, _ = select.select(readable, writable, [], 0.5)
                for stream in reads:
                    data = stream.recv(64*1024)
                    if not data:
                        if stream is self.connection:
                            return
                        closed.add(stream)
                        continue
                    self.server.account(len(data))
                    pending[peers[stream]].extend(data)
                    last_progress = time.monotonic()
                for stream in writes:
                    sent = stream.send(pending[stream])
                    del pending[stream][:sent]
                    if sent:
                        last_progress = time.monotonic()
        except Exception:  # noqa: BLE001, S110 - close failed tunnels without source-controlled diagnostics
            pass
        finally:
            if upstream:
                upstream.close()
            self.close_connection = True

    def relay(self):
        connection = response = None
        try:
            parsed = urlsplit(public_url(self.path))
            if parsed.scheme != "http":
                raise ValueError
            if sum(len(key)+len(value)+4 for key, value in self.headers.items()) > 16*1024:
                raise ValueError
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 1024**2 or self.headers.get("Transfer-Encoding"):
                raise ValueError
            data = self.rfile.read(size) if size else None
            self.server.account(size)
            connection = PublicFetch().connection(parsed)
            connection.request(self.command, parsed.path + ("?"+parsed.query if parsed.query else ""), body=data,
                headers={"Content-Type": self.headers.get("Content-Type", "application/octet-stream"),
                         "Accept-Encoding": "identity", "Git-Protocol": self.headers.get("Git-Protocol", "version=2")})
            response = connection.getresponse()
            self.send_response(response.status)
            for name in ("Content-Type", "Content-Length", "Location"):
                value = response.getheader(name)
                if value and len(value) < 8192:
                    self.send_header(name, value)
            self.send_header("Connection", "close")
            self.end_headers()
            while chunk := response.read1(64*1024):
                self.server.account(len(chunk))
                self.wfile.write(chunk)
        except Exception:  # noqa: BLE001 - no raw upstream errors/URLs are exposed
            self.close_connection = True
        finally:
            if response:
                response.close()
            if connection:
                connection.close()

    do_GET = relay
    do_POST = relay


@contextmanager
def public_proxy():
    server = PublicProxy()
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.stopped.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
