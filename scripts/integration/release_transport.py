"""Controlled GitHub metadata only; actual signatures/assets are verified normally."""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path("/opt/qualification/release-assets/psewdon1m-exocortex")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        match = re.fullmatch(r"/repos/psewdon1m-exocortex/(mastermind|neptune)/releases(?:/tags/([a-z]+-v[0-9.]+))?", urlsplit(self.path).path)
        if match is None:
            self.send_error(404)
            return
        name, tag = match.groups()
        releases = []
        for folder in sorted((ROOT/name/"releases/download").iterdir()):
            if not folder.is_dir() or tag and folder.name != tag:
                continue
            releases.append({"tag_name": folder.name, "draft": False, "prerelease": False,
                "assets": [{"name": item.name, "browser_download_url": f"https://github.com/psewdon1m-exocortex/{name}/releases/download/{folder.name}/{item.name}"}
                           for item in sorted(folder.iterdir()) if item.is_file()]})
        if tag and not releases:
            self.send_error(404)
            return
        body = json.dumps(releases[0] if tag else releases).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18881), Handler).serve_forever()
