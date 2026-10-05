"""خادم بوصلة المحلي الرئيسي على 127.0.0.1:8620. يقدم web/ ومسارات /framework للبيانات المنشورة وآخر نسخة سليمة وحالة الجدولة. التشغيل: python -m compass launch."""

from __future__ import annotations

import argparse
import json
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from compass.serve import Handler  # noqa: E402  (رؤوس الأمان ونوع المحتوى نفسها)
from compass.local_update import PUBLISH_DIR, RUNTIME_DIR, freshness, publication_dir  # noqa: E402

WEB = ROOT / "web"
FONTS = WEB / "assets" / "fonts"


def make_server(port: int = 8620, host: str = "127.0.0.1", publish_dir=PUBLISH_DIR, runtime_dir=RUNTIME_DIR,
                fallback_dir=WEB / "data") -> ThreadingHTTPServer:
    publish_dir, runtime_dir, fallback_dir = Path(publish_dir), Path(runtime_dir), Path(fallback_dir)

    class ExplorerHandler(Handler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(WEB), **kw)

        def translate_path(self, path):
            clean = path.split("?", 1)[0].split("#", 1)[0]
            if clean in ("/framework/compass.json", "/framework/manifest.json", "/data/compass.json", "/data/manifest.json"):
                name = clean.rsplit("/", 1)[1]
                directory = publication_dir(publish_dir)
                return str(directory / name if (directory / "compass.json").is_file() else fallback_dir / name)
            if clean == "/framework/logic.js":
                return str(WEB / "assets" / "js" / "logic.js")
            if clean.startswith("/fonts/"):
                name = clean[len("/fonts/"):]
                if "/" not in name and "\\" not in name and name.endswith(".ttf"):
                    return str(FONTS / name)
            if clean.startswith(("/published/", "/runtime/")):   # لا تُقدَّم ملفات التشغيل والنشر الداخلية مباشرة
                return str(WEB / "__not_found__")
            return super().translate_path(path)

        def do_GET(self):
            if self.path.split("?", 1)[0] == "/framework/status.json":
                body = json.dumps(freshness(publish_dir, runtime_dir, fallback_dir), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

    return ThreadingHTTPServer((host, port), ExplorerHandler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="خادم بوصلة المحلي (دون تحديث تلقائي)")
    parser.add_argument("--port", type=int, default=8620)
    args = parser.parse_args(argv)
    server = make_server(args.port)
    print(f"بوصلة: http://127.0.0.1:{server.server_address[1]}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
