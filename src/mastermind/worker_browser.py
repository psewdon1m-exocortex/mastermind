"""JS article extraction. Browser sockets are denied; the parent brokers every GET."""
import io
import time

from .errors import DomainError
from .extractors import Text, html_document
from .fs import open_under


def render(folder, record, fetcher):
    from playwright.sync_api import sync_playwright
    if not record.get("source_url") or record.get("mime") != "text/html":
        raise DomainError("BROWSER_SOURCE_INVALID", "JavaScript rendering is available only for public webpage sources.", 422)
    with open_under(folder, "source") as stream:
        source = stream.read(8*1024**2+1)
    if len(source) > 8*1024**2:
        raise DomainError("EXTRACTION_LIMIT", "The browser document exceeds its bounded HTML profile.", 413)
    origin = record.get("url", record["source_url"])
    deadline, requests, transferred = time.monotonic()+60, 0, len(source)
    denied = []
    try:
        with sync_playwright() as playwright:
            environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONPATH": "/app/src", "PYTHONDONTWRITEBYTECODE": "1",
                "LANG": "C.UTF-8", "HOME": str(folder), "TMPDIR": str(folder), "XDG_CACHE_HOME": str(folder / "cache"),
                "MASTERMIND_BROWSER_JOB": str(folder), "MASTERMIND_CHROMIUM_EXECUTABLE": "/opt/mastermind/browser/chrome-linux64/chrome"}
            context = playwright.chromium.launch_persistent_context(str(folder / "browser-profile"),
                executable_path="/app/runtime/worker-chromium", headless=True, env=environment,
                service_workers="block", accept_downloads=False, viewport={"width": 1200, "height": 800},
                args=["--disable-dev-shm-usage", "--disable-gpu", "--disable-quic", "--disable-extensions",
                      "--single-process", "--no-zygote", "--in-process-gpu", "--disable-crash-reporter",
                      "--disable-background-networking", "--disable-component-update", "--disable-sync"], timeout=15000)
            try:
                context.route_web_socket("**", lambda route: route.close())
                page = context.pages[0] if context.pages else context.new_page()
                context.on("page", lambda popup: popup.close() if popup != page else None)
                page.on("dialog", lambda dialog: dialog.dismiss())

                def broker(route):
                    nonlocal requests, transferred
                    request = route.request
                    requests += 1
                    if requests > 64 or time.monotonic() >= deadline or request.method != "GET" \
                            or request.resource_type not in ("document", "script", "stylesheet", "fetch", "xhr") \
                            or request.resource_type == "document" and request.frame.parent_frame is not None:
                        route.abort()
                        return
                    try:
                        if request.url == origin and request.resource_type == "document":
                            body, mime = source, "text/html"
                        else:
                            output = io.BytesIO()
                            metadata = fetcher.get(request.url, output, limit=min(4*1024**2, max(1, 32*1024**2-transferred)), deadline=deadline)
                            body, mime = output.getvalue(), metadata["mime"]
                            transferred += len(body)
                        if transferred > 32*1024**2:
                            raise DomainError("EXTRACTION_LIMIT", "Browser resource budget exhausted.", 413)
                        route.fulfill(status=200, body=body, content_type=mime)
                    except DomainError as error:
                        denied.append(error.code)
                        route.abort()

                context.route("**/*", broker)
                page.goto(origin, wait_until="domcontentloaded", timeout=25000)
                # Bounded settling, not an unbounded networkidle wait on trackers.
                previous, stable = "", 0
                for _ in range(12):
                    page.wait_for_timeout(500)
                    current = page.locator("body").inner_text(timeout=2000)[:512*1024]
                    stable = stable+1 if current == previous else 0
                    previous = current
                    if stable >= 3 and len(current.strip()) >= 20 or time.monotonic() >= deadline:
                        break
                markup = page.content()
                if len(markup.encode("utf-8")) > 8*1024**2:
                    raise DomainError("EXTRACTION_LIMIT", "Rendered DOM exceeded its bound.", 413)
                title, content, metadata, _ = html_document(markup)
                if not content.strip():
                    raise DomainError("SOURCE_EMPTY", "The rendered page did not expose readable content.", 422)
                text = Text()
                text.add(content)
                return {"schema": "mastermind.extraction.v1", "type": "webpage", "mime": "text/html", "title": title,
                        "text": text.value(), "metadata": metadata, "truncated": text.truncated,
                        "needs_media": False, "needs_browser": False,
                        "diagnostics": {"requests": requests, "resource_bytes": transferred, "denied": sorted(set(denied))}}
            finally:
                context.close()
    except DomainError:
        raise
    except Exception:  # noqa: BLE001 - browser errors can include source URLs or page content
        raise DomainError("BROWSER_EXTRACTION_FAILED", "The isolated browser could not extract this public page.", 422) from None
