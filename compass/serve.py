"""خادم ملفات ثابتة للواجهة على 127.0.0.1 فقط (للتشغيل المحلي، لا للنشر)."""

from __future__ import annotations

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import WEB_DIR


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript; charset=utf-8",
                      ".mjs": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
                      ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8",
                      ".svg": "image/svg+xml", ".woff2": "font/woff2"}

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        # البيانات قد تتحدث؛ لا تُخزَّن مؤقتًا حتى يرى المستخدم حالة المصادر الحالية.
        self.send_header("Cache-Control", "no-store" if self.path.split("?")[0].endswith(".json") else "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


def make_server(port=8502, directory=WEB_DIR, host="127.0.0.1"):
    handler = functools.partial(Handler, directory=str(Path(directory)))
    return ThreadingHTTPServer((host, port), handler)


def serve(port=8502, directory=WEB_DIR):
    server = make_server(port, directory)
    print(f"بوصلة: http://127.0.0.1:{server.server_address[1]}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
