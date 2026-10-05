"""الأوامر:
    .venv\\Scripts\\python.exe -m compass update   جلب المصادر والتحقق منها ثم البناء
    .venv\\Scripts\\python.exe -m compass build    البناء من آخر نسخ سليمة دون شبكة
    .venv\\Scripts\\python.exe -m compass launch   الواجهة والتحديث المحلي على 8620
رمز الخروج: 0 نجاح كامل، 1 بناء بحالة «متدهورة» (مصدر تعذر تحديثه)، 2 تعذر البناء.
"""

from __future__ import annotations

import argparse
import sys

from .build import build
from .serve import serve
from .update import update_all


def _print(line):
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    sys.stdout.flush()


def describe(item) -> str:
    """سطر نتيجة مصدر للأمر؛ يذكر صراحة إن تعذر تسجيل المحاولة نفسها."""
    line = f"{item['source_id']}: {item['status']}" + (f" — {item['error']}" if item.get("error") else "")
    for key in ("reject_error", "log_error"):
        if item.get(key):
            line += f" [تنبيه: {item[key]}]"
    return line


def main(argv=None):
    parser = argparse.ArgumentParser(prog="compass")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("update")
    sub.add_parser("build")
    sub.add_parser("launch", help="الواجهة الرئيسية والتحديث المحلي المجدول")
    sub.add_parser("verify", help="التحقق السريع أو العميق")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8620)
    # تُفوض الخيارات للمشغّل/التحقق دون تكرار تعريفها هنا.
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in ("launch", "verify"):
        if argv[0] == "launch":
            from .launcher import main as delegated
        else:
            from .verify import main as delegated
        return delegated(argv[1:])
    args = parser.parse_args(argv)
    if args.cmd == "serve":
        from .local_server import main as server_main
        server_main(["--port", str(args.port)])
        return 0
    if args.cmd == "update":
        report = update_all()
        for item in report["hrsd"] + report["workers"]:
            _print(describe(item))
        d = report["discovery"]
        _print(f"discovery: {d['status']} — مرشحون: {[(c['dataset_id'][:8], c['status']) for c in d.get('candidates', [])]}")
    manifest = build()
    _print(f"build: {manifest['status']}" + (f" — {manifest.get('message')}" if manifest.get("message") else ""))
    return {"ok": 0, "degraded": 1}.get(manifest["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
