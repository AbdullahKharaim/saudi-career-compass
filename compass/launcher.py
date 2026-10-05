"""مشغّل «مستكشف بوصلة» المحلي: الخادم + التحديث التلقائي المجدول.

    .venv\\Scripts\\python.exe -B -m compass launch
        [--port 8620] [--interval-hours 168] [--retry-hours 12] [--check-minutes 30] [--update-now] [--no-update]

- يبدأ الخادم فورًا، ثم في خيط خلفي: ينشر نسخة للنموذج من آخر نسخ سليمة إن لم توجد (دون شبكة)،
  ثم يفحص كل check_minutes هل حان موعد التحديث، ويحدّث إن حان (updater.py). الواجهة لا تنتظر التحديث.
- يعمل فقط ما دام هذا المشغّل والحاسوب يعملان. عند إغلاقه يتوقف التحديث، ويعرض المؤشر «التحديث التلقائي متوقف».
- لا يوقف أي عملية أخرى: إن كان المنفذ مشغولًا يخرج برسالة، ويُترك القرار للمستخدم.
- السجل: runtime/launcher.log
"""

from __future__ import annotations

import argparse
import sys
import threading
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from compass.local_server import make_server  # noqa: E402
from compass.local_update import RUNTIME_DIR, Schedule, Updater  # noqa: E402


def log(line: str):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"[{stamp}] {line}"
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    sys.stdout.flush()
    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        with open(RUNTIME_DIR / "launcher.log", "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass


def describe(result: dict) -> str:
    status = result.get("status")
    if status == "not_due":
        return f"لا تحديث الآن؛ الموعد التالي {result.get('next_due_at')}"
    if status == "skipped":
        return f"تُخطّي: {result.get('reason')}"
    parts = [f"تحديث: {status}"]
    if result.get("error"):
        parts.append(f"خطأ: {result['error']}")
    for s in result.get("sources") or []:
        parts.append(f"{s['id']}={s['status']}")
    pub = result.get("publish") or {}
    if pub:
        parts.append(f"نشر: {pub.get('status')}")
    return " | ".join(parts)


def worker(updater: Updater, stop: threading.Event, update: bool, force_first: bool):
    try:
        boot = updater.bootstrap()
    except Exception as exc:
        boot = {"status": "failed", "error": str(exc)}
    if boot:
        log(f"نشر أولي من آخر نسخ سليمة (دون شبكة): {boot.get('status')} {boot.get('error') or ''}".strip())
    first = True
    while not stop.is_set():
        try:
            if update:
                log(describe(updater.tick(force=force_first and first)))
            else:
                updater._patch_state(heartbeat_at=None)
        except Exception as exc:  # لا يسقط المشغّل بسبب خطأ غير متوقع؛ يُسجَّل ويُعاد الفحص لاحقًا
            log(f"خطأ غير متوقع في التحديث: {type(exc).__name__}: {exc}")
        first = False
        stop.wait(updater.schedule.check_minutes * 60)


def main(argv=None):
    p = argparse.ArgumentParser(description="مشغّل مستكشف بوصلة مع التحديث التلقائي المحلي")
    p.add_argument("--port", type=int, default=8620)
    p.add_argument("--interval-hours", type=float, default=168.0, help="الفاصل بين التحديثات الناجحة (افتراضيًا أسبوع)")
    p.add_argument("--retry-hours", type=float, default=12.0, help="إعادة المحاولة بعد فشل أو تحديث جزئي")
    p.add_argument("--check-minutes", type=float, default=30.0, help="كل كم دقيقة يُفحص الموعد محليًا (دون شبكة)")
    p.add_argument("--update-now", action="store_true", help="حدّث فور التشغيل حتى لو لم يحن الموعد")
    p.add_argument("--no-update", action="store_true", help="الخادم فقط، دون تحديث تلقائي")
    args = p.parse_args(argv)

    try:
        server = make_server(args.port)
    except OSError as exc:
        log(f"المنفذ {args.port} مشغول أو غير متاح ({exc}). لم يُوقف أي شيء. تحقق من العملية التي تستخدمه، أو اختر --port آخر.")
        return 2
    updater = Updater(schedule=Schedule(args.interval_hours, args.retry_hours, args.check_minutes))
    stop = threading.Event()
    threading.Thread(target=server.serve_forever, daemon=True, name="explorer-server").start()
    log(f"مستكشف بوصلة: http://127.0.0.1:{server.server_address[1]}/  (التحديث التلقائي: {'متوقف' if args.no_update else f'كل {args.interval_hours:g} ساعة عند حلول الموعد'})")
    t = threading.Thread(target=worker, args=(updater, stop, not args.no_update, args.update_now), daemon=True, name="explorer-updater")
    t.start()
    try:
        while t.is_alive():
            t.join(1.0)
    except KeyboardInterrupt:
        log("إيقاف المشغّل…")
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        try:
            updater.stopped()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
