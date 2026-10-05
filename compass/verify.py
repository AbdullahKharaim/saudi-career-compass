"""تحقق الإصدار: python -m compass verify --quick أو --deep. السريع: المستكشف والمحدث وحفظ الإصدار. العميق: tests/ كاملة مرة واحدة دون تكرار السريع. التجارب معزولة ولا جلب حي."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable

SUITES = {
    "quick": [("المستكشف والتحديث والحفظ المتكامل", ["-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-p", "test_explorer.py"]),
              ("المحدث المحلي", ["-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-p", "test_local_updater.py"]),
              ("حفظ الإصدار والتوافق", ["-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-p", "test_release.py"])],
    "deep": [("مجموعة بوصلة والتحليل كاملة (tests/)", ["-m", "unittest", "discover", "-s", str(ROOT / "tests")])],
}


def run(label, args) -> bool:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    start = time.time()
    proc = subprocess.run([PY, "-B", *args], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    tail = [l for l in proc.stderr.splitlines() if l.startswith(("Ran ", "OK", "FAILED"))]
    print(f"• {label}: {' — '.join(tail) or 'لا مخرجات'} — {time.time() - start:.1f} ثانية — رمز الخروج {proc.returncode}", flush=True)
    if proc.returncode:
        print(proc.stderr[-4000:], flush=True)
    return proc.returncode == 0


def main(argv=None):
    p = argparse.ArgumentParser(description="تحقق مستكشف بوصلة")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--quick", action="store_true")
    g.add_argument("--deep", action="store_true")
    args = p.parse_args(argv)
    plan = SUITES["deep"] if args.deep else SUITES["quick"]
    start = time.time()
    ok = all([run(label, a) for label, a in plan])
    print(f"المجموع: {'نجح' if ok else 'فشل'} — {time.time() - start:.1f} ثانية", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
