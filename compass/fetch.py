"""جلب ملفات المصادر وتخزينها مع سجل وبصمات، دون استبدال آخر بيانات سليمة.

لكل مصدر مجلد في data/sources/<id>/:
    files/<أول 12 من sha256>_<اسم الملف>   نسخ أصلية لا تُكتب فوقها أبدًا
    rejected/<وقت>_<اسم الملف>             ملفات فشل التحقق منها (للفحص فقط)
    fetch_log.jsonl                        سجل إلحاقي لكل محاولة ونتيجتها
    current.json                           مؤشر آخر نسخة سليمة؛ يتغير ذريًا بعد نجاح التحقق فقط
نجاح HTTP وحده لا يكفي: صفحة «Request Rejected» من جدار الحماية تعود برمز 200، لذلك
يُتحقق من نوع المحتوى وتوقيع الملف ثم من بنيته قبل القبول.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .config import TIMEOUT, USER_AGENT


class FetchError(Exception):
    """تعذر الاتصال أو قراءة الاستجابة."""


class ValidationError(Exception):
    def __init__(self, errors):
        self.errors = [str(e) for e in (errors if isinstance(errors, (list, tuple)) else [errors])]
        super().__init__("؛ ".join(self.errors))


@dataclass
class Response:
    status: int
    body: bytes
    url: str
    headers: dict = field(default_factory=dict)  # مفاتيح بأحرف صغيرة


class HttpFetcher:
    """GET بمعرّف صريح ومهلة؛ أخطاء HTTP تعود Response، وأخطاء الشبكة FetchError."""

    def __init__(self, user_agent=USER_AGENT, timeout=TIMEOUT):
        self.user_agent, self.timeout = user_agent, timeout

    def get(self, url, headers=None) -> Response:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return Response(r.status, r.read(), r.geturl(), {k.lower(): v for k, v in r.headers.items()})
        except urllib.error.HTTPError as exc:
            return Response(exc.code, exc.read() if exc.fp else b"", url, {k.lower(): v for k, v in (exc.headers or {}).items()})
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FetchError(f"{type(exc).__name__}: {exc}") from exc


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _write_atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "file"


class SourceStore:
    def __init__(self, root: Path, source_id: str):
        self.id = source_id
        self.dir = Path(root) / source_id
        self.files = self.dir / "files"
        self.rejected = self.dir / "rejected"
        self.log_path = self.dir / "fetch_log.jsonl"
        self.current_path = self.dir / "current.json"

    def current(self):
        try:
            pointer = json.loads(self.current_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        path = self.dir / pointer.get("file", "")
        if not path.is_file() or sha256(path.read_bytes()) != pointer.get("sha256"):
            return None  # مؤشر يشير إلى ملف مفقود أو معدّل لا يُعتمد
        return pointer

    def current_bytes(self):
        pointer = self.current()
        return (self.dir / pointer["file"]).read_bytes() if pointer else None

    def log(self, entry: dict):
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def history(self) -> list:
        if not self.log_path.is_file():
            return []
        out = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def last_attempt(self):
        h = self.history()
        return h[-1] if h else None

    def _set_current(self, pointer):
        _write_atomic(self.current_path, json.dumps(pointer, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8"))

    def accept(self, body, filename, at, meta) -> dict:
        """يحفظ نسخة سليمة ويوجه المؤشر إليها. يتحقق من محتوى الأرشيف لا من وجود اسمه:
        إن وُجد ملف بالاسم نفسه ومحتواه لا يطابق البصمة (تالف)، يُستبدل بالبايتات السليمة."""
        digest = sha256(body)
        rel = Path("files") / f"{digest[:12]}_{_safe(filename)}"
        target = self.dir / rel
        repaired = False
        if target.exists() and sha256(target.read_bytes()) != digest:
            repaired = True
        if repaired or not target.exists():
            _write_atomic(target, body)
        if sha256(target.read_bytes()) != digest:
            raise OSError(f"تعذر حفظ نسخة مطابقة للبصمة في {rel.as_posix()}")
        previous = self.current()
        pointer = {"source_id": self.id, "file": rel.as_posix(), "sha256": digest, "size": len(body),
                   "fetched_at": at, "verified_at": at, **meta}
        if previous and previous["sha256"] != digest:
            pointer["previous_sha256"] = previous["sha256"]
        self._set_current(pointer)
        if self.current() is None:
            raise OSError("المؤشر الحالي لا يشير إلى نسخة صالحة بعد الحفظ")
        return pointer | ({"repaired_archive": True} if repaired else {})

    def mark_verified(self, at, meta=None):
        pointer = self.current()
        if pointer:
            pointer["verified_at"] = at
            pointer.update(meta or {})
            self._set_current(pointer)
        return pointer

    def reject(self, body, filename, at) -> str:
        rel = Path("rejected") / f"{at.replace(':', '')}_{_safe(filename)}"
        _write_atomic(self.dir / rel, body)
        return rel.as_posix()


SIGNATURES = {"xlsx": b"PK\x03\x04", "pdf": b"%PDF-"}


def check_kind(kind: str, response: Response):
    """فحص أولي يرفض صفحات HTML التي تعود برمز 200 بدل الملف."""
    ctype = response.headers.get("content-type", "")
    body = response.body
    if not body:
        raise ValidationError("الاستجابة فارغة")
    if "text/html" in ctype or body.lstrip()[:15].lower().startswith((b"<html", b"<!doctype")):
        snippet = re.sub(rb"<[^>]+>", b" ", body[:200]).decode("utf-8", "replace").strip()
        raise ValidationError(f"وصلت صفحة HTML بدل الملف ({snippet[:80]})")
    if kind in SIGNATURES and not body.startswith(SIGNATURES[kind]):
        raise ValidationError(f"توقيع الملف لا يطابق {kind}")
    if kind == "csv":
        try:
            body.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationError(f"CSV ليس UTF-8 صالحًا: {exc}")


def log_attempt(store: SourceStore, entry: dict) -> dict:
    """يسجل المحاولة؛ إن تعذرت كتابة السجل نفسه يُذكر ذلك في النتيجة (log_error) بدل ادعاء التسجيل."""
    try:
        store.log(entry)
    except OSError as exc:
        entry["log_error"] = f"تعذر تسجيل هذه المحاولة في fetch_log.jsonl: {exc}"
    return entry


def _storage_failure(store, entry, action, exc) -> dict:
    entry.update(status="failed_storage", error=f"{action}: {exc}")
    return log_attempt(store, entry)


def update_file(store: SourceStore, url: str, *, kind: str, filename: str, validate, fetcher=None, now=None,
                context=None) -> dict:
    """يحاول تحديث مصدر واحد. لا يغيّر current.json إلا بعد نجاح التحقق. يعيد نتيجة المحاولة.

    سياسة فشل التخزين واحدة في كل الفروع (نسخة جديدة، ولم يتغير، و304، وإصلاح الأرشيف): أي OSError
    عند قراءة المؤشر أو كتابته أو حفظ النسخة يصير «failed_storage» مسجلًا، ويبقى المؤشر السابق كما هو
    (الكتابة ذرية)، ويكمل المستدعي بقية المصادر.
    """
    fetcher = fetcher or HttpFetcher()
    at = now or utcnow()
    entry = {"at": at, "url": url, "kind": kind, **(context or {})}
    try:
        current = store.current()
    except OSError as exc:
        return _storage_failure(store, entry, "تعذر قراءة المؤشر current.json", exc)
    headers = {}
    if current and current.get("http", {}).get("etag"):
        headers["If-None-Match"] = current["http"]["etag"]
    try:
        response = fetcher.get(url, headers=headers)
    except FetchError as exc:
        entry.update(status="failed_download", error=str(exc))
        return log_attempt(store, entry)
    http = {k: response.headers.get(k) for k in ("etag", "last-modified", "content-type", "content-length") if response.headers.get(k)}
    entry["http_status"], entry["http"] = response.status, http
    if response.status == 304 and current:
        try:
            store.mark_verified(at)
        except OSError as exc:
            return _storage_failure(store, entry, "تعذر تحديث المؤشر current.json بعد 304", exc)
        entry.update(status="not_modified", sha256=current["sha256"])
        return log_attempt(store, entry)
    if response.status != 200:
        entry.update(status="failed_download", error=f"HTTP {response.status}")
        return log_attempt(store, entry)
    digest = sha256(response.body)
    entry.update(sha256=digest, size=len(response.body))
    try:
        check_kind(kind, response)
        summary = validate(response.body) or {}
    except Exception as exc:  # أي خطأ قراءة (مثل XML تالف داخل xlsx) فشلُ مصدر، لا انهيار للتحديث
        reason = str(exc) if isinstance(exc, ValidationError) else f"تعذر قراءة الملف ({type(exc).__name__}: {exc})"
        entry.update(status="failed_validation", error=reason)
        try:
            entry["rejected_file"] = store.reject(response.body, filename, at)
        except OSError as rexc:
            entry["reject_error"] = f"تعذر حفظ نسخة الملف المرفوض للفحص: {rexc}"
        return log_attempt(store, entry)
    meta = {"url": url, "http": {"etag": http.get("etag"), "last_modified": http.get("last-modified"),
                                 "content_type": http.get("content-type")}, "summary": summary}
    if current and current["sha256"] == digest:
        try:
            store.mark_verified(at, {"http": meta["http"], "summary": summary})
        except OSError as exc:
            return _storage_failure(store, entry, "تعذر تحديث المؤشر current.json لملف لم يتغير", exc)
        entry["status"] = "unchanged"
    else:
        try:
            pointer = store.accept(response.body, filename, at, meta)
        except OSError as exc:
            return _storage_failure(store, entry, "تعذر حفظ النسخة الجديدة أو توجيه المؤشر current.json إليها", exc)
        if pointer.get("repaired_archive"):
            entry["status"] = "repaired"  # كانت النسخة المؤرشفة بالبصمة نفسها تالفة فاستُبدلت
        else:
            entry["status"] = "revised" if pointer.get("previous_sha256") else "updated"
        if pointer.get("previous_sha256"):
            entry["previous_sha256"] = pointer["previous_sha256"]
    entry["summary"] = summary
    return log_attempt(store, entry)
