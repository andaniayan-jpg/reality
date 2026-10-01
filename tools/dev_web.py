"""Serve the static Reality website locally with its production SPA fallback."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class RealityWebHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        pathname = self.path.split("?", 1)[0]
        if not (Path(self.directory) / pathname.lstrip("/")).is_file():
            self.path = "/index.html"
        super().do_GET()


if __name__ == "__main__":
    web_root = Path(__file__).resolve().parents[1] / "apps" / "web"
    handler = partial(RealityWebHandler, directory=str(web_root))
    server = ThreadingHTTPServer(("127.0.0.1", 3000), handler)
    print("Reality web development server: http://127.0.0.1:3000", flush=True)
    server.serve_forever()
