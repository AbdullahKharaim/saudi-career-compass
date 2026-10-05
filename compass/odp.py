"""منصة البيانات المفتوحة: بيانات العاملين في القطاع الخاص حسب النشاط الاقتصادي والمنطقة الإدارية.

ما نجح فعليًا (2026-10-04) بطلب GET بمعرّف صريح:
- البيانات الوصفية: https://open.data.gov.sa/api/datasets/<datasetID> (JSON فيه timePeriod وresources).
- الملف: https://open.data.gov.sa/odp-public/<resource.url> (CSV مطابق بايتًا لنسخة data/raw).
ما لا نستخدمه: قائمة المجموعات (POST /api/datasets/list) ترفض العملاء غير المتصفحات بصفحة
«Request Rejected»؛ لا نتجاوز ذلك. اكتشاف الفترات الجديدة يتم من صفحة فهرس الوزارة العامة.
الفترة لا تُعتمد من timePeriod وحده: وُجدت مجموعة عنوانها «الربع الثالث 2025» وtimePeriod فيها 2026-07..09.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

from labor_market import prepare

from .config import ODP_API, ODP_FILES, WORKERS_DATASETS, WORKERS_TITLE_MARKER
from .fetch import FetchError, ValidationError, sha256

QUARTERS = {"الاول": 1, "الأول": 1, "الثاني": 2, "الثالث": 3, "الرابع": 4}
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def _plain(text):
    """توحيد للمقارنة: دون تشكيل، والهمزات ألفًا، والمسافات مفردة."""
    text = re.sub("[ً-ْ ]", " ", str(text))
    return " ".join(text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").split())


def metadata(dataset_id, fetcher) -> dict:
    """البيانات الوصفية بعد التحقق من بنيتها. تعذر الحصول عليها (اتصال، أو HTTP، أو جسم ليس JSON
    مثل صفحة منع وصول) FetchError؛ JSON صحيح ببنية غير متوقعة ValidationError. كلاهما فشل يُسجَّل
    لهذا المصدر وحده، لا استثناء يوقف بقية المصادر."""
    r = fetcher.get(ODP_API + dataset_id, headers={"Accept": "application/json"})
    if r.status != 200:
        raise FetchError(f"بيانات وصفية: HTTP {r.status}")
    try:
        meta = json.loads(r.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FetchError(f"بيانات وصفية ليست JSON ({r.body[:60]!r})") from exc
    problems = metadata_problems(meta, dataset_id)
    if problems:
        raise ValidationError(problems)
    return meta


def metadata_problems(meta, dataset_id) -> list:
    """اتفاق بنية البيانات الوصفية التي يستخدمها بوصلة. كل حقل يُستخدم يُتحقق من نوعه قبل قراءته."""
    if not isinstance(meta, dict):
        return [f"البيانات الوصفية ليست كائن JSON بل {type(meta).__name__}"]
    problems = []
    if meta.get("datasetID") != dataset_id:
        problems.append("البيانات الوصفية لا تحمل المعرّف المطلوب")
    for key in ("titleAr", "titleEn", "updatedAt"):
        if meta.get(key) is not None and not isinstance(meta[key], str):
            problems.append(f"الحقل {key} ليس نصًا")
    tp = meta.get("timePeriod")
    if tp is not None and not isinstance(tp, dict):
        problems.append("timePeriod ليس كائنًا")
    resources = meta.get("resources")
    if not isinstance(resources, list):
        problems.append("resources ليست قائمة ملفات")
    else:
        for i, r in enumerate(resources):
            if not isinstance(r, dict):
                problems.append(f"resources[{i}] ليس كائنًا")
                continue
            for key in ("name", "url", "format"):
                if r.get(key) is not None and not isinstance(r[key], str):
                    problems.append(f"resources[{i}].{key} ليس نصًا")
    return problems


def csv_resource(meta) -> dict:
    found = [r for r in meta["resources"] if str(r.get("format", "")).upper() == "CSV" and r.get("url")]
    if len(found) != 1:
        raise ValidationError(f"متوقع ملف CSV واحد في البيانات الوصفية، وُجد {len(found)}")
    return found[0]


def file_url(resource) -> str:
    return ODP_FILES + quote(resource["url"])


def text_signals(text):
    """كل إشارات السنة والربع في نص واحد: ({السنوات}, {الأرباع}).

    يُجمع كل ما في النص لا أوله؛ نص فيه «الربع الثاني 2026» و«Q1 2025» إشاراته متعارضة.
    """
    t = _plain(text)
    quarters = {QUARTERS[q] for q in re.findall(r"(?:ال|ل)ربع\s+(الاول|الثاني|الثالث|الرابع)", t)}
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", t)}
    for q, y in re.findall(r"Q\s*([1-4])\s*-?\s*(20\d\d)?", str(text)):
        quarters.add(int(q))
        if y:
            years.add(int(y))
    return years, quarters


def period_from_text(text):
    """(سنة، ربع) من نص عربي («الربع الثاني 2026») أو إنجليزي («Q22026»، «Q3 2025»).

    الجزء الذي له أكثر من قيمة في النص نفسه يعود None (متعارض)، كما يعود None إن غاب.
    """
    years, quarters = text_signals(text)
    return (next(iter(years)) if len(years) == 1 else None, next(iter(quarters)) if len(quarters) == 1 else None)


def period_from_dates(time_period):
    """(سنة، ربع) من timePeriod إن كان ربعًا واحدًا؛ وإلا (None, None). التشخيص في dates_problem."""
    return dates_period(time_period)[0]


_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ][0-9:.]+(?:Z|[+-]\d{2}:?\d{2})?)?")


def _calendar_date(value):
    """تاريخ تقويمي كامل من نص ISO (اليوم يُتحقق منه: 2026-04-99 و2026-02-30 مرفوضان)."""
    m = _ISO_DATE.fullmatch(value.strip()) if isinstance(value, str) else None
    if not m:
        raise ValueError(value)
    return dt.date(*map(int, m.groups()))


def dates_period(time_period):
    """((سنة، ربع)، مشكلة أو None). الغياب الكامل ليس مشكلة؛ أما التاريخ غير التقويمي، والمدى
    المعكوس، والممتد عبر أكثر من ربع، فمشكلات (دليل غير صالح لا يُعامل كدليل غائب)."""
    if time_period is None or time_period == {}:
        return (None, None), None
    try:
        start, end = _calendar_date(time_period["fromDate"]), _calendar_date(time_period["toDate"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return (None, None), f"timePeriod غير صالح أو تاريخ غير موجود في التقويم: {time_period!r}"
    span = f"({time_period['fromDate']}..{time_period['toDate']})"
    if end < start:
        return (None, None), f"timePeriod معكوس: النهاية قبل البداية {span}"
    q1, q2 = (start.month - 1) // 3 + 1, (end.month - 1) // 3 + 1
    if (start.year, q1) != (end.year, q2):
        return (None, None), f"timePeriod يمتد عبر أكثر من ربع {span}"
    return (start.year, q1), None


def resolve_period(meta) -> dict:
    """يجمع أدلة الفترة من العنوانين وأسماء الملفات وtimePeriod.

    متسقة فقط إن لم يكن في أي دليل تعارض داخلي أو قيمة غير صالحة، واتفقت الأدلة الموجودة كلها
    على سنة واحدة وربع واحد. الدليل الغائب لا يُحسب لصالح الفترة ولا ضدها.
    """
    texts = {"title_ar": meta.get("titleAr", ""), "title_en": meta.get("titleEn", "")}
    for i, r in enumerate(meta.get("resources", [])):
        texts[f"resource_{i}"] = r.get("name", "")
    evidence, problems, years, quarters = {}, [], set(), set()
    for key, text in texts.items():
        ys, qs = text_signals(text)
        if len(ys) > 1 or len(qs) > 1:
            problems.append(f"{key}: إشارات متعارضة في النص نفسه (سنوات {sorted(ys)}، أرباع {sorted(qs)})")
        years |= ys
        quarters |= qs
        evidence[key] = [next(iter(ys)) if len(ys) == 1 else None, next(iter(qs)) if len(qs) == 1 else None]
    (dy, dq), problem = dates_period(meta.get("timePeriod"))
    evidence["time_period"] = [dy, dq]
    if problem:
        problems.append(problem)
    if dy:
        years.add(dy)
        quarters.add(dq)
    if len(years) > 1 or len(quarters) > 1:
        problems.append(f"الأدلة لا تتفق: سنوات {sorted(years)}، أرباع {sorted(quarters)}")
    if not years or not quarters:
        problems.append("لا يوجد دليل كافٍ على السنة والربع")
    consistent = not problems
    return {"year": years.pop() if consistent else None, "quarter": quarters.pop() if consistent else None,
            "consistent": consistent, "evidence": evidence, "problems": problems}


def validate_workers_csv(body: bytes, file_name: str, year: int, quarter: int) -> dict:
    """تحقق البنية والإجماليات بمنطق labor_market.prepare نفسه (دون شرط هاش مسبق)."""
    spec = prepare.SourceSpec(file_name=file_name, year=year, quarter=quarter, size=len(body),
                              sha256=sha256(body), grand_total=0, missing=())
    with tempfile.TemporaryDirectory(prefix="compass-odp-") as tmp:
        (Path(tmp) / file_name).write_bytes(body)
        try:
            parsed = prepare.parse_source(tmp, spec)
        except prepare.PrepareError as exc:
            raise ValidationError(exc.errors)
    _, errors, warnings = prepare.reconcile(parsed)
    if errors:
        raise ValidationError(errors)
    return {"regions": len(parsed.regions), "activities": len(parsed.activities), "grand_total": parsed.grand_total,
            "missing": len(prepare.missing_locations(parsed)), "warnings": len(warnings)}


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._cur = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._cur = [dict(attrs).get("href") or "", ""]

    def handle_data(self, data):
        if self._cur is not None:
            self._cur[1] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._cur is not None:
            self.links.append((self._cur[0], " ".join(self._cur[1].split())))
            self._cur = None


def discover_from_index(html: str) -> list:
    """روابط مجموعات «العاملين في القطاع الخاص حسب النشاط الاقتصادي والمنطقة الإدارية» في صفحة الفهرس."""
    parser = _Links()
    parser.feed(html)
    marker = _plain(WORKERS_TITLE_MARKER)
    out = {}
    for href, text in parser.links:
        m = re.search(r"open\.data\.gov\.sa/[a-z]{2}/datasets/view/(" + _UUID + ")", href or "")
        if m and marker in _plain(text):
            out.setdefault(m.group(1), text)
    return [{"dataset_id": k, "title": v} for k, v in out.items()]


def classify_candidates(found: list, metas: dict) -> list:
    """يقارن المكتشف بالسجل المثبت: فترة جديدة، أو فترة معروفة بمعرّف آخر، أو تعارض في الفترة،
    أو عنوان في المنصة لا يطابق موضوع الرابط (وُجد فعلًا: daa44995 موسوم في الفهرس بالمنطقة الإدارية
    وعنوانه في المنصة «حسب النشاط الاقتصادي والجنس والجنسية»)."""
    known_ids = {d.dataset_id for d in WORKERS_DATASETS}
    known_periods = {(d.year, d.quarter): d.dataset_id for d in WORKERS_DATASETS}
    out = []
    for item in found:
        if item["dataset_id"] in known_ids:
            continue
        meta = metas.get(item["dataset_id"])
        if isinstance(meta, Exception) or meta is None:
            out.append(item | {"status": "metadata_failed", "error": str(meta)})
            continue
        period = resolve_period(meta)
        if _plain(WORKERS_TITLE_MARKER) not in _plain(meta.get("titleAr", "")):
            status = "title_mismatch"  # عنوان الرابط في الفهرس لا يطابق عنوان المجموعة في المنصة
        elif not period["consistent"]:
            status = "period_conflict"
        elif (period["year"], period["quarter"]) in known_periods:
            status = "known_period_other_id"
        else:
            status = "new_period"
        out.append(item | {"status": status, "period": period, "updated_at": meta.get("updatedAt"),
                           "title_ar": meta.get("titleAr")})
    return out
