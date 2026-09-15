"""Real Chromium/JS with controlled public responses and real private-address rejection."""
import json
from pathlib import Path

from mastermind.fs import atomic_json, sha_file
from mastermind.worker import Worker
from mastermind.worker_fetch import PublicFetch


class FixtureFetch(PublicFetch):
    def get(self, url, output, **kwargs):
        if url == "https://example.test/app.js":
            body = b"document.querySelector('main').innerHTML='<h1>Generated heading</h1><p>Readable article created by real JavaScript.</p>'; fetch('http://127.0.0.1/healthz').catch(()=>{});"
            output.write(body)
            return {"size": len(body), "mime": "application/javascript"}
        return super().get(url, output, **kwargs)


def main():
    worker = Worker(Path("/work"), Path("/opt/mastermind/model"), Path("/app/embedding-model.lock.json"),
                    Path("/run/mastermind/worker_token"))
    worker.start()
    assert worker.embeddings.session is not None
    identifier = "d"*32
    folder = worker.reserve(identifier, 4096)
    worker.active = None
    worker.fetcher = FixtureFetch()
    (folder / "source").write_text("<!doctype html><html><head><title>Fixture article</title></head><body><main></main><script src='/app.js'></script></body></html>")
    atomic_json(folder / "source.json", {"source_url": "https://example.test/", "url": "https://example.test/",
        "mime": "text/html", "name": "source.html", "size": (folder / "source").stat().st_size, "sha256": sha_file(folder / "source")})
    try:
        output = worker.render(identifier)
    except Exception as error:
        # This fixture contains only generated public data; show the bounded
        # underlying launcher diagnostic for qualification, never production logs.
        print(str(error.__context__)[:6000])
        raise
    assert "Readable article created by real JavaScript" in output["text"]
    assert "SSRF_REJECTED" in output["diagnostics"]["denied"], output["diagnostics"]
    assert not output["needs_browser"]
    worker.cleanup(identifier)
    import psutil
    print(json.dumps({"real_chromium": "PASS", "javascript_article": "PASS", "private_fetch": "DENIED",
                      "model_loaded": True, "worker_rss_bytes": psutil.Process().memory_info().rss,
                      "cgroup_peak_bytes": int(Path("/sys/fs/cgroup/memory.peak").read_text()),
                      "diagnostics": output["diagnostics"]}))


if __name__ == "__main__":
    main()
