"""Serve the built Studio SPA and proxy same-origin API calls to Django."""

from __future__ import annotations

from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
DIST = FRONTEND / "dist"
API_HOST = "127.0.0.1"
API_PORT = 8001
HOST = "127.0.0.1"
PORT = 5178
SPA_ROOTS = {
    "screens", "stock", "charts", "strategies", "market", "monitor",
    "deploy", "watchlists", "optimize", "backtests", "settings", "profile",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _respond(self, status: int, content: bytes, content_type: str, headers=()) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers:
            if name.lower() not in {"connection", "transfer-encoding", "content-length", "content-encoding"}:
                self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)

    def _proxy_api(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        headers = [(k, v) for k, v in self.headers.items() if k.lower() not in {
            "connection", "transfer-encoding", "content-length", "host", "accept-encoding"
        }]
        # Preserve the browser origin host for the local account-management
        # origin check. The backend transport itself stays on loopback.
        headers.append(("Host", self.headers.get("Host", "localhost")))
        conn = HTTPConnection(API_HOST, API_PORT, timeout=120)
        try:
            conn.request(self.command, self.path, body=body or None, headers=dict(headers))
            response = conn.getresponse()
            content = response.read()
            self._respond(response.status, content, response.getheader("Content-Type", "application/json"), response.getheaders())
        except (OSError, HTTPException) as exc:
            message = f"Studio API unavailable: {exc}".encode()
            self._respond(502, message, "text/plain; charset=utf-8")
        finally:
            conn.close()

    def _static(self) -> None:
        path = urlsplit(self.path).path
        if path.startswith("/api/") or path == "/api":
            self._proxy_api()
            return
        if self.command not in {"GET", "HEAD"}:
            self.send_error(405)
            return
        if path in {"/tests", "/tests/", "/tests/index.html"}:
            target = FRONTEND / "playwright-ui-report" / "index.html"
        elif path == "/" or path.strip("/").split("/", 1)[0] in SPA_ROOTS:
            target = DIST / "index.html"
        else:
            target = (DIST / path.lstrip("/")).resolve()
            if DIST not in target.parents or not target.is_file():
                self.send_error(404)
                return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        self._respond(200, target.read_bytes(), content_type)

    do_GET = _static
    do_HEAD = _static
    do_POST = _static
    do_PUT = _static
    do_PATCH = _static
    do_DELETE = _static
    do_OPTIONS = _static


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
