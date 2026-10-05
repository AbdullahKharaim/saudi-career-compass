"""تحديث كل المصادر: جلب، ثم تحقق، ثم قبول أو رفض، ثم اكتشاف الفترات الجديدة.

لا يكتب في data/raw ولا يغيّر مدخلات التحليل المعتمدة؛ الفترة الجديدة تُسجَّل مرشحة فقط
حتى تضاف إلى config.WORKERS_DATASETS بعد مراجعة بشرية.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from labor_market import prepare

from . import odp
from .config import HRSD_OPEN_DATA_INDEX, HRSD_SOURCES, SKILLS_DB, SOURCES_DIR, WORKERS_DATASETS
from .fetch import (FetchError, HttpFetcher, SourceStore, ValidationError, _write_atomic, log_attempt, sha256,
                    update_file, utcnow)
from .pdf import PdfError, validate_structure
from .skills import SkillsFormatError, parse_skills_workbook, summarize


def _validate_skills(body):
    try:
        return summarize(parse_skills_workbook(body))
    except SkillsFormatError as exc:
        raise ValidationError(exc.errors)
    except ValueError as exc:  # xlsx غير قابل للقراءة
        raise ValidationError(str(exc))


def _validate_pdf(body):
    try:
        return validate_structure(body)
    except PdfError as exc:
        raise ValidationError(str(exc))


def _filename(url):
    from urllib.parse import unquote
    return unquote(url.rsplit("/", 1)[-1])


def _isolated(store, at, context, run):
    """يشغّل تحديث مصدر واحد بحيث لا يوقف خطأ غير متوقع بقية المصادر المستقلة: يُسجَّل الخطأ
    بنوعه ونصه حالةَ «failed_unexpected»، ولا يُمس المؤشر الحالي."""
    try:
        return run()
    except Exception as exc:  # آخر خط دفاع؛ الأخطاء المتوقعة تعالجها update_file نفسها
        entry = {"at": at, "status": "failed_unexpected", "error": f"{type(exc).__name__}: {exc}", **context}
        return log_attempt(store, entry)


def update_hrsd(root=SOURCES_DIR, fetcher=None, now=None) -> list:
    out = []
    for src in HRSD_SOURCES:
        validate = _validate_skills if src is SKILLS_DB else _validate_pdf
        store = SourceStore(root, src.id)
        result = _isolated(store, now or utcnow(), {"url": src.url, "kind": src.kind},
                           lambda: update_file(store, src.url, kind=src.kind, filename=_filename(src.url),
                                               validate=validate, fetcher=fetcher, now=now))
        out.append({"source_id": src.id, **result})
    return out


def update_workers(root=SOURCES_DIR, fetcher=None, now=None, raw_dir=None) -> list:
    fetcher = fetcher or HttpFetcher()
    raw_dir = Path(raw_dir or prepare.RAW_DIR)
    out = []
    for ds in WORKERS_DATASETS:
        store = SourceStore(root, ds.source_id)
        at = now or utcnow()
        context = {"dataset_id": ds.dataset_id, "year": ds.year, "quarter": ds.quarter}
        result = _isolated(store, at, context, lambda ds=ds, store=store, at=at, context=context:
                           _update_dataset(ds, store, at, context, fetcher, raw_dir))
        out.append({"source_id": ds.source_id, **result})
    return out


def _update_dataset(ds, store, at, context, fetcher, raw_dir) -> dict:
    try:
        meta = odp.metadata(ds.dataset_id, fetcher)
    except FetchError as exc:
        return log_attempt(store, {"at": at, "status": "failed_download", "stage": "metadata", "error": str(exc), **context})
    except ValidationError as exc:
        return log_attempt(store, {"at": at, "status": "failed_validation", "stage": "metadata", "error": str(exc), **context})
    try:
        resource = odp.csv_resource(meta)
    except ValidationError as exc:
        return log_attempt(store, {"at": at, "status": "failed_validation", "stage": "metadata", "error": str(exc), **context})
    period = odp.resolve_period(meta)
    if not period["consistent"] or (period["year"], period["quarter"]) != (ds.year, ds.quarter):
        why = "؛ ".join(period["problems"]) or f"الفترة {period['year']} ربع {period['quarter']}"
        return log_attempt(store, {"at": at, "status": "failed_validation", "stage": "metadata",
                                   "error": f"فترة البيانات الوصفية لا تطابق المسجل ({why}): {period['evidence']}", **context})
    raw = Path(raw_dir) / ds.raw_file
    pinned = sha256(raw.read_bytes()) if raw.is_file() else None

    def validate(body):
        summary = odp.validate_workers_csv(body, ds.raw_file, ds.year, ds.quarter)
        summary["matches_pinned_raw"] = sha256(body) == pinned
        return summary

    context = context | {"metadata_updated_at": meta.get("updatedAt"), "resource_updated_at": resource.get("updatedAt")}
    return update_file(store, odp.file_url(resource), kind="csv", filename=ds.raw_file, validate=validate,
                       fetcher=fetcher, now=at, context=context)


def _check_index_page(response) -> str:
    """يعيد نص صفحة الفهرس إن كانت هي الصفحة المتوقعة؛ وإلا FetchError بسبب واضح.

    رمز 200 لا يكفي: جدار الحماية يعيد «Request Rejected» برمز 200. الصفحة المتوقعة HTML من
    موقع الوزارة فيها روابط مجموعات على منصة البيانات المفتوحة.
    """
    if response.status != 200:
        raise FetchError(f"HTTP {response.status}")
    text = response.body.decode("utf-8", "replace")
    if "request rejected" in text.lower():
        raise FetchError("وصلت صفحة منع وصول (Request Rejected) بدل صفحة الفهرس")
    if not re.search(r"open\.data\.gov\.sa/[a-z]{2}/datasets/view/", text):
        raise FetchError("الصفحة لا تحتوي روابط مجموعات بيانات؛ ليست صفحة الفهرس المتوقعة")
    return text


def discover(root=SOURCES_DIR, fetcher=None, now=None) -> dict:
    """يفحص الفهرس بحثًا عن فترات جديدة. عند الفشل يُسجَّل الفشل، وتبقى آخر نتيجة ناجحة
    محفوظة بتاريخها في last_success دون أن تُعرض فحصًا حديثًا."""
    fetcher = fetcher or HttpFetcher()
    path = Path(root) / "discovery.json"
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        previous = {}
    last_success = previous if previous.get("status") == "ok" else previous.get("last_success")
    report = {"at": now or utcnow(), "index_url": HRSD_OPEN_DATA_INDEX}
    try:
        found = odp.discover_from_index(_check_index_page(fetcher.get(HRSD_OPEN_DATA_INDEX)))
        metas = {}
        for item in found:
            try:
                metas[item["dataset_id"]] = odp.metadata(item["dataset_id"], fetcher)
            except (FetchError, ValidationError) as exc:
                metas[item["dataset_id"]] = exc
        report |= {"status": "ok", "links_found": len(found), "candidates": odp.classify_candidates(found, metas)}
    except FetchError as exc:
        report |= {"status": "failed", "error": str(exc), "candidates": [], "last_success": last_success}
    Path(root).mkdir(parents=True, exist_ok=True)
    _write_atomic(path, json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8"))
    return report


def update_all(root=SOURCES_DIR, fetcher=None, now=None, raw_dir=None) -> dict:
    fetcher = fetcher or HttpFetcher()
    return {"hrsd": update_hrsd(root, fetcher, now), "workers": update_workers(root, fetcher, now, raw_dir),
            "discovery": discover(root, fetcher, now)}
