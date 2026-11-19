"""Brant Test app: local web server for the interface in web/.

    python server.py                 opens http://localhost:8766 in the browser
    python server.py --no-browser    serves only

The desktop app (desktop/launcher.py) starts the same server and shows the page in its own window.
All analysis runs on this computer; nothing is sent over the network.
"""
import argparse
import json
import os
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

from engine import api

ROOT = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
LOCK = threading.Lock()        # matplotlib and the shared data are not thread-safe
MAX_BODY = 50 * 1024 * 1024
PORT = 8766


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(ROOT, "web"), **k)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        if n > MAX_BODY:
            return self._raw(json.dumps({"ok": False, "error": "The file is too large (limit 50 MB)."}))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._raw(json.dumps({"ok": False, "error": "Malformed request."}))
        route = self.path.split("?")[0]
        routes = {
            "/api/datasets": lambda: api.datasets(),
            "/api/load": lambda: api.load(req["name"]),
            "/api/register": lambda: api.register(req["name"], req["csv"]),
            "/api/preview": lambda: api.preview(req["name"], req.get("n", 20)),
            "/api/run": lambda: api.run(json.dumps(req["spec"])),
            "/api/pycode": lambda: api.python_code(json.dumps(req["spec"])),
            "/api/csv": lambda: json.dumps({"ok": True, "csv": api.get_csv(req["name"])}),
        }
        if route not in routes:
            return self._raw(json.dumps({"ok": False, "error": "Unknown route."}))
        try:
            with LOCK:
                out = routes[route]()
        except KeyError as e:
            out = json.dumps({"ok": False, "error": f"Dataset not loaded ({e}). Choose it again."})
        self._raw(out)

    def _raw(self, s):
        body = s.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(host="127.0.0.1", port=PORT):
    """Bind to the requested port, or the next free one."""
    last = None
    for p in [port] + list(range(port + 1, port + 20)) + [0]:
        try:
            return ThreadingHTTPServer((host, p), Handler)
        except OSError as e:
            last = e
    raise last


def main():
    ap = argparse.ArgumentParser(description="Brant Test")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    srv = make_server(a.host, a.port)
    url = f"http://localhost:{srv.server_address[1]}"
    print(f"Brant Test is running at {url}  (press Ctrl+C to stop)", flush=True)
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
