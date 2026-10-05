"""التحديث المحلي المجدول لبوصلة: يعيد استخدام update_all وbuild. نشر مرحلي في web/published مع مؤشر جيل ذري، وجدولة 168 ساعة وإعادة محاولة 12 ساعة وفحص محلي كل 30 دقيقة. يعمل أثناء تشغيل المشغّل والحاسوب فقط؛ الفترات الجديدة مرشحة لمراجعة بشرية."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compass.build import OK_STATUSES, build as compass_build  # noqa: E402
from compass.config import HRSD_SOURCES, SOURCES_DIR, WEB_DATA_DIR, WORKERS_DATASETS  # noqa: E402
from compass.fetch import SourceStore, _write_atomic  # noqa: E402
from compass.update import update_all  # noqa: E402

PUBLISH_DIR = ROOT / "web" / "published"
RUNTIME_DIR = ROOT / "runtime"
SOURCE_IDS = [s.id for s in HRSD_SOURCES] + [d.source_id for d in WORKERS_DATASETS]


@dataclass
class Schedule:
    interval_hours: float = 168.0   # أسبوعيًا: ملفات الإطار نادرة التغير، وبيانات العاملين ربعية (ARCHITECTURE.md)
    retry_hours: float = 12.0       # بعد فشل أو تحديث جزئي: محاولة أقرب، دون طلبات متكررة
    check_minutes: float = 30.0     # فحص محلي للموعد بلا شبكة


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def publication_dir(root: Path) -> Path:
    """مؤشر ذري لزوج البيانات/البيان؛ يدعم النسخة المسطحة السابقة دون ترحيل هدّام."""
    root = Path(root)
    current = _read_json(root / "current.json") or {}
    name = current.get("generation")
    if isinstance(name, str) and len(name) == 32 and all(c in "0123456789abcdef" for c in name):
        directory = root / "generations" / name
        if all((directory / n).is_file() for n in ("compass.json", "manifest.json", "publish.json")):
            return directory
    return root


class Updater:
    def __init__(self, sources_root=SOURCES_DIR, publish_dir=PUBLISH_DIR, runtime_dir=RUNTIME_DIR, schedule=None,
                 fetcher=None, update_fn=update_all, build_fn=compass_build, processed_dir=None, raw_dir=None,
                 clock=utcnow, lock_stale_hours=3.0):
        self.sources_root, self.publish_dir, self.runtime_dir = Path(sources_root), Path(publish_dir), Path(runtime_dir)
        self.schedule = schedule or Schedule()
        self.fetcher, self.update_fn, self.build_fn = fetcher, update_fn, build_fn
        self.processed_dir, self.raw_dir, self.clock = processed_dir, raw_dir, clock
        self.lock_stale = timedelta(hours=lock_stale_hours)
        self._mutex = threading.Lock()
        self._state_mutex = threading.Lock()

    # --- الحالة ------------------------------------------------------------
    @property
    def state_path(self):
        return self.runtime_dir / "state.json"

    @property
    def lock_path(self):
        return self.runtime_dir / "update.lock"

    def state(self) -> dict:
        return _read_json(self.state_path) or {}

    def _patch_state(self, **changes):
        with self._state_mutex:
            st = self.state()
            for k, v in changes.items():
                if v is None:
                    st.pop(k, None)
                else:
                    st[k] = v
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            _write_atomic(self.state_path, json.dumps(st, ensure_ascii=False, indent=1).encode("utf-8"))
            return st

    def last_verified(self) -> datetime | None:
        """أقدم «آخر تحقق ناجح» بين المصادر: الموعد التالي يُحسب منه حين لا توجد محاولة سابقة للمشغّل."""
        times = []
        for sid in SOURCE_IDS:
            cur = SourceStore(self.sources_root, sid).current()
            if not cur:
                return None
            times.append(parse(cur.get("verified_at") or cur.get("fetched_at")))
        return min(t for t in times if t) if all(times) else None

    def next_due(self) -> datetime:
        last = self.state().get("last_attempt") or {}
        at = parse(last.get("at"))
        if at:
            hours = self.schedule.interval_hours if last.get("status") == "ok" else self.schedule.retry_hours
            return at + timedelta(hours=hours)
        verified = self.last_verified()
        return verified + timedelta(hours=self.schedule.interval_hours) if verified else self.clock()

    def is_due(self, now=None) -> bool:
        return (now or self.clock()) >= self.next_due()

    # --- القفل ---------------------------------------------------------------
    def _acquire(self) -> bool:
        if not self._mutex.acquire(blocking=False):
            return False
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(json.dumps({"pid": os.getpid(), "since": iso(self.clock())}))
                return True
            except FileExistsError:
                # قفل من مشغّل آخر: لا يُكسر إلا إن كان قديمًا جدًا (عملية انتهت دون تنظيف). لا تُفحص هوية عملية بإشارات.
                age = datetime.now(timezone.utc) - datetime.fromtimestamp(self.lock_path.stat().st_mtime, timezone.utc)
                if age < self.lock_stale:
                    break
                self.lock_path.unlink(missing_ok=True)
        self._mutex.release()
        return False

    def _release(self):
        self.lock_path.unlink(missing_ok=True)
        self._mutex.release()

    # --- البناء والنشر -------------------------------------------------------
    def publish(self, now=None) -> dict:
        """يبني إلى مجلد مرحلي، ويتحقق، ثم ينشر. أي فشل يترك آخر بيانات منشورة كما هي."""
        now = now or self.clock()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="staging-", dir=self.runtime_dir))
        generation = None
        try:
            manifest = self.build_fn(self.sources_root, staging, self.processed_dir, iso(now))
            data_path = staging / "compass.json"
            if (manifest or {}).get("status") not in ("ok", "degraded") or not data_path.is_file():
                return {"status": "failed", "error": (manifest or {}).get("message") or "تعذر البناء", "at": iso(now)}
            raw = data_path.read_bytes()
            data = json.loads(raw.decode("utf-8"))
            staged_manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
            if staged_manifest.get("status") != manifest["status"] or staged_manifest.get("generated_at") != data.get("generated_at"):
                return {"status": "failed", "error": "البيان لا يطابق البيانات المرحلية؛ لم تُنشر", "at": iso(now)}
            if not (data.get("subsectors") and data.get("skills") and (data.get("framework") or {}).get("skills_sha256")):
                return {"status": "failed", "error": "بيانات البناء ناقصة البنية؛ لم تُنشر", "at": iso(now)}
            self.publish_dir.mkdir(parents=True, exist_ok=True)
            info = {"published_at": iso(now), "generated_at": data.get("generated_at"), "build_status": manifest["status"]}
            _write_atomic(staging / "publish.json", json.dumps(info, ensure_ascii=False).encode("utf-8"))
            name = uuid.uuid4().hex
            generation = self.publish_dir / "generations" / name
            generation.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, generation)
            # خطوة الاعتماد الوحيدة: فشلها يُبقي الزوج السابق كما هو.
            _write_atomic(self.publish_dir / "current.json", json.dumps({"generation": name}).encode("utf-8"))
            return {"status": "published", **info}
        except Exception as exc:  # خطأ بناء غير متوقع: لا نشر، وتبقى البيانات السابقة
            if generation is not None:
                shutil.rmtree(generation, ignore_errors=True)
            return {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "at": iso(now)}
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def bootstrap(self) -> dict | None:
        """أول تشغيل: ينشر نسخة للتطبيق من آخر نسخ سليمة (بناء دون شبكة) إن لم توجد نسخة منشورة."""
        if (publication_dir(self.publish_dir) / "compass.json").is_file():
            return None
        if not self._acquire():
            return {"status": "skipped", "error": "تحديث آخر يجري الآن"}
        try:
            result = self.publish()
            self._patch_state(last_publish=result)
            return result
        finally:
            self._release()

    # --- التحديث ------------------------------------------------------------
    def run_once(self, now=None, force=False) -> dict:
        now = now or self.clock()
        if not force and not self.is_due(now):
            return {"status": "not_due", "next_due_at": iso(self.next_due())}
        if not self._acquire():
            return {"status": "skipped", "reason": "تحديث آخر يجري الآن"}
        started = iso(now)
        try:
            self._patch_state(running={"since": started, "pid": os.getpid()})
            try:
                report = self.update_fn(self.sources_root, self.fetcher, None, self.raw_dir)
            except Exception as exc:  # الجلب كله تعذر (شبكة أو خطأ غير متوقع): لا بناء ولا نشر
                result = {"at": started, "status": "failed", "stage": "fetch", "error": f"{type(exc).__name__}: {exc}", "sources": []}
                self._patch_state(last_attempt=result)
                return result
            sources = [{"id": i["source_id"], "status": i.get("status"), "error": i.get("error")}
                       for i in (report.get("hrsd") or []) + (report.get("workers") or [])]
            discovery = report.get("discovery") or {}
            pub = self.publish(now)
            if pub["status"] != "published":
                status, stage, error = "failed", "build", pub.get("error")
            else:
                clean = all(s["status"] in OK_STATUSES for s in sources) and discovery.get("status") == "ok" and pub["build_status"] == "ok"
                status, stage, error = ("ok" if clean else "degraded"), None, None
            result = {"at": started, "status": status, "stage": stage, "error": error, "sources": sources,
                      "discovery": {"status": discovery.get("status"), "candidates": len(discovery.get("candidates") or [])},
                      "publish": pub}
            self._patch_state(last_attempt=result, **({"last_publish": pub} if pub["status"] == "published" else {}))
            return result
        finally:
            self._patch_state(running=None)
            self._release()

    def tick(self, now=None, force=False) -> dict:
        """نبضة المشغّل: تسجيل أنه يعمل، ثم تحديث إن حان الموعد."""
        now = now or self.clock()
        result = self.run_once(now, force=force)
        self._patch_state(heartbeat_at=iso(self.clock()), launcher_pid=os.getpid(), schedule=asdict(self.schedule),
                          next_due_at=iso(self.next_due()))
        return result

    def stopped(self):
        self._patch_state(heartbeat_at=None, launcher_pid=None, running=None)


# --- ملخص الحداثة للواجهة -------------------------------------------------------

def _version(card: dict) -> str:
    edition = card.get("edition") or ""
    lm = card.get("last_modified")
    try:
        when = datetime.strptime(lm, "%a, %d %b %Y %H:%M:%S GMT").strftime("%Y-%m-%d") if lm else None
    except ValueError:
        when = None
    return f"{edition} · ملف بتاريخ {when}" if when else edition


def freshness(publish_dir=PUBLISH_DIR, runtime_dir=RUNTIME_DIR, fallback_dir=WEB_DATA_DIR, now=None, lock_stale_hours=3.0) -> dict:
    """ما يعرضه مؤشر «البيانات»: مصدر البيانات المعروضة، وآخر تحقق لكل مصدر ونسخته، وحالة التحديث التلقائي."""
    now = now or utcnow()
    publish_dir, runtime_dir = Path(publish_dir), Path(runtime_dir)
    published = publication_dir(publish_dir)
    origin = "published" if (published / "compass.json").is_file() else "fallback"
    manifest = _read_json((published if origin == "published" else Path(fallback_dir)) / "manifest.json") or {}
    st = _read_json(runtime_dir / "state.json") or {}
    sched = Schedule(**{k: v for k, v in (st.get("schedule") or {}).items() if k in Schedule.__dataclass_fields__})
    heartbeat = parse(st.get("heartbeat_at"))
    active = bool(heartbeat) and now - heartbeat <= timedelta(minutes=2 * sched.check_minutes + 5)
    lock = runtime_dir / "update.lock"
    running = lock.is_file() and now - datetime.fromtimestamp(lock.stat().st_mtime, timezone.utc) < timedelta(hours=lock_stale_hours)
    last = st.get("last_attempt") or {}
    due = parse(st.get("next_due_at"))
    cards = manifest.get("sources") or []
    if running:
        state = "running"
    elif not active:
        state = "inactive"
    elif last.get("status") == "failed":
        state = "failed"
    elif due and now > due + timedelta(hours=1):
        state = "overdue"
    elif last.get("status") == "degraded" or any(c.get("status") != "ok" for c in cards):
        state = "partial"
    else:
        state = "ok"
    return {
        "data": {"origin": origin, "generated_at": manifest.get("generated_at")},
        "sources": [{"id": c.get("id"), "title": c.get("title"), "status": c.get("status"), "verified_at": c.get("verified_at"),
                     "fetched_at": c.get("fetched_at"), "version": _version(c)} for c in cards],
        "update": {"state": state, "launcher_active": active, "last_attempt_at": last.get("at"), "last_attempt_status": last.get("status"),
                   "error": last.get("error"), "next_due_at": st.get("next_due_at"), "interval_hours": sched.interval_hours},
        "discovery": {"status": (manifest.get("discovery") or {}).get("status"),
                      "at": (manifest.get("discovery") or {}).get("last_success_at"),
                      "needs_review": len((manifest.get("discovery") or {}).get("candidates") or [])},
    }
