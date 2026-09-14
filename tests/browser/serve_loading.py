"""Serve the isolated browser regression fixture on localhost (no application data)."""

import argparse
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from rcssmin import cssmin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", help="Optional git ref for comparison at /?before=1")
    parser.add_argument("--port", default=8796, type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    baseline = (
        subprocess.check_output(["git", "show", f"{args.baseline}:static/js/core/rich-notes.js"], cwd=root)
        if args.baseline else None
    )
    routes = {
        "/": ("text/html; charset=utf-8", (root / "tests/browser/loading.html").read_bytes()),
        "/rich-notes.js": ("text/javascript", (root / "static/js/core/rich-notes.js").read_bytes()),
        "/style.css": ("text/css", cssmin((root / "static/css/style.css").read_text(encoding="utf-8")).encode()),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path not in routes:
                self.send_error(404)
                return
            content_type, data = routes[path]
            if path == "/rich-notes.js" and "before=1" in self.path and baseline is not None:
                data = baseline
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    print(f"Browser regression fixture: http://127.0.0.1:{args.port}/", flush=True)
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
