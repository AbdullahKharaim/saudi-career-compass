"""تجهيز بيانات العاملين في القطاع الخاص (الربعان الأول والثاني 2026).

التشغيل من جذر المشروع:
    .venv\\Scripts\\python.exe -m labor_market.prepare

يقرأ ملفي data/raw، ويتحقق من هاشيهما وبنيتهما وإجمالياتهما، وبعد نجاح كل
التحققات فقط يكتب data/processed/{workers.csv, source_totals.csv,
quality_report.json}. لا يعدّل data/raw ولا يحسب نسب نمو.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# ثوابت بنية المصدر كما هي في الملفين (تُحفظ بأسمائها الأصلية).
TITLE_CELL = "المنطقة الإدارية"
ACTIVITY_HEADER = "النشاط الاقتصادي"
GRAND_TOTAL_LABEL = "Grand Total"
UNCLASSIFIED_ACTIVITY = "تحت المعالجة"
PUBLIC_ADMIN_ACTIVITY = "الإدارة العامة والدفاع , الضمان الاجتماعي الالزامي"
N_REGIONS = 13
N_ACTIVITIES = 20
N_COLUMNS = N_REGIONS + 2
N_ROWS = 2 + N_ACTIVITIES + 1
RECORDS_PER_QUARTER = N_REGIONS * N_ACTIVITIES

WORKERS_COLUMNS = ("year", "quarter", "region", "economic_activity", "workers", "source_file")
TOTALS_COLUMNS = ("year", "quarter", "total_type", "name", "value", "source_file")

_NUMBER = re.compile(r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)")


@dataclass(frozen=True)
class SourceSpec:
    """ربط صريح بين ملف مصدر وسنته وربعه وهاشه المسجل (docs/DATA-SOURCES.md)."""

    file_name: str
    year: int
    quarter: int
    size: int
    sha256: str
    grand_total: int
    missing: tuple  # ((region, economic_activity), ...)


SOURCES = (
    SourceSpec(
        file_name="Workers in the private sector Q12026CSV.csv",
        year=2026,
        quarter=1,
        size=3660,
        sha256="BC7985DDBF19E894E61DF921D7E24650D5C4AB6587D913C45ADAF6F20505EB26",
        grand_total=13_569_346,
        missing=(("الباحة", PUBLIC_ADMIN_ACTIVITY), ("نجران", PUBLIC_ADMIN_ACTIVITY)),
    ),
    SourceSpec(
        file_name="Employees private sector Q22026CSV.csv",
        year=2026,
        quarter=2,
        size=3659,
        sha256="BFED560E1CDC95E29EA9327EDC9BD136B60EFC09A7FF93F69080DE0C6EEC7FCA",
        grand_total=13_610_026,
        missing=(("الباحة", PUBLIC_ADMIN_ACTIVITY),),
    ),
)


class PrepareError(Exception):
    """أخطاء تمنع إنتاج البيانات؛ تحمل قائمة رسائل."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


@dataclass
class ParsedSource:
    spec: SourceSpec
    size_bytes: int
    sha256: str
    regions: list
    activities: list
    cells: dict  # activity -> [workers | None] بترتيب المناطق
    region_totals: list
    activity_totals: list
    grand_total: int


def parse_number(text):
    """يحوّل خلية إلى عدد صحيح غير سالب، أو None إن كانت فارغة؛ وإلا ValueError."""
    if text == "":
        return None
    if not _NUMBER.fullmatch(text):
        raise ValueError(f"قيمة غير رقمية: {text!r}")
    return int(text.replace(",", ""))


def sum_available(values):
    """مجموع القيم المتاحة؛ None إذا كانت المجموعة كلها مفقودة (لا يتحول إلى صفر)."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def parse_source(raw_dir, spec):
    """يتحقق من الملف وهاشه وبنيته ويعيد ParsedSource، أو يرفع PrepareError."""
    name = spec.file_name
    path = Path(raw_dir) / name
    if not path.is_file():
        raise PrepareError([f"{name}: الملف غير موجود في {raw_dir}"])
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest().upper()
    if len(data) != spec.size or sha != spec.sha256:
        raise PrepareError(
            [
                f"{name}: اختلف الحجم أو الهاش عن المسجل "
                f"(الحجم {len(data)} مقابل {spec.size}، SHA-256 {sha} مقابل {spec.sha256})"
            ]
        )
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PrepareError([f"{name}: الملف ليس UTF-8 صالحًا ({exc})"])

    errors = []
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if len(rows) != N_ROWS:
        raise PrepareError([f"{name}: عدد الصفوف {len(rows)} والمتوقع {N_ROWS}"])
    for i, row in enumerate(rows, start=1):
        if len(row) != N_COLUMNS:
            errors.append(f"{name}: الصف {i} فيه {len(row)} عمودًا والمتوقع {N_COLUMNS}")
    if errors:
        raise PrepareError(errors)

    if rows[0] != [""] + [TITLE_CELL] + [""] * (N_COLUMNS - 2):
        errors.append(f"{name}: الصف الأول ليس عنوان المناطق المتوقع")
    header = rows[1]
    if header[0] != ACTIVITY_HEADER or header[-1] != GRAND_TOTAL_LABEL:
        errors.append(f"{name}: رأس الجدول (الصف الثاني) غير متوقع")
    regions = header[1:-1]
    if any(r == "" for r in regions) or len(set(regions)) != len(regions):
        errors.append(f"{name}: أسماء المناطق فارغة أو مكررة")
    last = rows[-1]
    if last[0] != GRAND_TOTAL_LABEL:
        errors.append(f"{name}: الصف الأخير ليس صف {GRAND_TOTAL_LABEL}")
    body = rows[2:-1]
    activities = [r[0] for r in body]
    if any(a == "" or a == GRAND_TOTAL_LABEL for a in activities) or len(set(activities)) != len(activities):
        errors.append(f"{name}: أسماء التصنيفات فارغة أو مكررة أو تتضمن الإجمالي")
    if errors:
        raise PrepareError(errors)

    def cell(text_, where, allow_missing):
        try:
            value = parse_number(text_)
        except ValueError as exc:
            errors.append(f"{name}: {where}: {exc}")
            return None
        if value is None and not allow_missing:
            errors.append(f"{name}: {where}: خلية إجمالي فارغة")
        return value

    cells = {}
    activity_totals = []
    for row in body:
        activity = row[0]
        cells[activity] = [
            cell(v, f"({regions[j]} | {activity})", True) for j, v in enumerate(row[1:-1])
        ]
        activity_totals.append(cell(row[-1], f"إجمالي التصنيف {activity}", False))
    region_totals = [cell(v, f"إجمالي المنطقة {regions[j]}", False) for j, v in enumerate(last[1:-1])]
    grand_total = cell(last[-1], "الإجمالي العام", False)
    if errors:
        raise PrepareError(errors)

    return ParsedSource(spec, len(data), sha, regions, activities, cells,
                        region_totals, activity_totals, grand_total)


def missing_locations(parsed):
    return [
        (region, activity)
        for activity in parsed.activities
        for region, value in zip(parsed.regions, parsed.cells[activity])
        if value is None
    ]


def reconcile(parsed):
    """مطابقة الإجماليات بالقيم المتاحة. تعيد (checks, errors, warnings)."""
    spec = parsed.spec
    checks, errors, warnings = [], [], []

    def add(kind, name, source_total, values):
        available = sum_available(values)
        missing = sum(1 for v in values if v is None)
        if available is None:
            status = "unverifiable"
        elif available == source_total:
            status = "match" if missing == 0 else "match_with_missing"
        else:
            status = "mismatch"
        checks.append({
            "year": spec.year, "quarter": spec.quarter, "kind": kind, "name": name,
            "source_total": source_total, "sum_available": available,
            "missing_count": missing, "status": status,
        })
        label = f"الربع {spec.quarter} {kind} {name}"
        if status == "mismatch":
            errors.append(
                f"إجمالي غير مطابق: {label}: إجمالي المصدر {source_total} "
                f"ومجموع المتاح {available} ومفقودات {missing}"
            )
        elif status == "match_with_missing":
            warnings.append({
                "code": "match_with_missing",
                "message": f"{label}: المطابقة نجحت مع {missing} مفقودات؛ لا تعني اكتمال البيانات",
            })
        elif status == "unverifiable":
            warnings.append({
                "code": "unverifiable",
                "message": f"{label}: كل القيم مفقودة، لا يمكن التحقق من الإجمالي {source_total}",
            })

    for j, region in enumerate(parsed.regions):
        add("region", region, parsed.region_totals[j], [parsed.cells[a][j] for a in parsed.activities])
    for i, activity in enumerate(parsed.activities):
        add("economic_activity", activity, parsed.activity_totals[i], parsed.cells[activity])
    every = [v for a in parsed.activities for v in parsed.cells[a]]
    add("grand_total", GRAND_TOTAL_LABEL, parsed.grand_total, every)
    add("region_totals_vs_grand_total", GRAND_TOTAL_LABEL, parsed.grand_total, [sum(parsed.region_totals)])
    add("activity_totals_vs_grand_total", GRAND_TOTAL_LABEL, parsed.grand_total, [sum(parsed.activity_totals)])
    return checks, errors, warnings


def check_expectations(parsed):
    """مقارنة بتوقعات المصادر المسجلة (العدد، الإجمالي العام، مواقع المفقودات)."""
    spec = parsed.spec
    errors = []
    if len(parsed.regions) * len(parsed.activities) != RECORDS_PER_QUARTER:
        errors.append(f"الربع {spec.quarter}: عدد السجلات غير {RECORDS_PER_QUARTER}")
    if parsed.grand_total != spec.grand_total:
        errors.append(
            f"الربع {spec.quarter}: الإجمالي العام {parsed.grand_total} والمتوقع {spec.grand_total}"
        )
    if set(missing_locations(parsed)) != set(spec.missing):
        errors.append(
            f"الربع {spec.quarter}: مواقع المفقودات {missing_locations(parsed)} "
            f"تختلف عن المتوقع {list(spec.missing)}"
        )
    return errors


def build_tables(parsed_sources):
    workers, totals = [], []
    for p in parsed_sources:
        s = p.spec
        for activity in p.activities:
            for region, value in zip(p.regions, p.cells[activity]):
                workers.append((s.year, s.quarter, region, activity, value, s.file_name))
        for region, value in zip(p.regions, p.region_totals):
            totals.append((s.year, s.quarter, "region", region, value, s.file_name))
        for activity, value in zip(p.activities, p.activity_totals):
            totals.append((s.year, s.quarter, "economic_activity", activity, value, s.file_name))
        totals.append((s.year, s.quarter, "grand_total", GRAND_TOTAL_LABEL, p.grand_total, s.file_name))
    return workers, totals


def _csv_bytes(columns, rows):
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(["" if v is None else v for v in row])
    return buf.getvalue().encode("utf-8")


def prepare(raw_dir=RAW_DIR, out_dir=PROCESSED_DIR, sources=SOURCES):
    """يشغّل التجهيز كاملًا. لا يكتب أي مخرجات إلا بعد نجاح كل التحققات."""
    errors, parsed_list = [], []
    for spec in sources:
        try:
            parsed_list.append(parse_source(raw_dir, spec))
        except PrepareError as exc:
            errors.extend(exc.errors)
    if errors:
        raise PrepareError(errors)

    warnings, reconciliation = [], []
    for p in parsed_list:
        errors.extend(check_expectations(p))
        checks, errs, warns = reconcile(p)
        reconciliation.extend(checks)
        errors.extend(errs)
        warnings.extend(warns)
        for region, activity in missing_locations(p):
            warnings.append({
                "code": "missing_value",
                "message": f"الربع {p.spec.quarter}: قيمة مفقودة ({region} | {activity}) محتفظ بها كمفقودة",
            })

    first = parsed_list[0]
    same_order = True
    for other in parsed_list[1:]:
        if set(other.regions) != set(first.regions):
            errors.append("أسماء المناطق غير متطابقة بين الملفين")
        if set(other.activities) != set(first.activities):
            errors.append("أسماء التصنيفات غير متطابقة بين الملفين")
        same_order = same_order and other.regions == first.regions and other.activities == first.activities

    workers, totals = build_tables(parsed_list)
    keys = [(w[0], w[1], w[2], w[3]) for w in workers]
    if len(set(keys)) != len(keys):
        errors.append("مفتاح مكرر في التفاصيل (سنة، ربع، منطقة، تصنيف)")
    if len(workers) != RECORDS_PER_QUARTER * len(sources):
        errors.append(f"عدد سجلات التفاصيل {len(workers)} والمتوقع {RECORDS_PER_QUARTER * len(sources)}")
    if errors:
        raise PrepareError(errors)

    warnings.append({
        "code": "unclassified_activity",
        "message": f"«{UNCLASSIFIED_ACTIVITY}» تصنيف غير مفسر محتفظ به كما هو، وضمن الإجمالي العام، ولم يُوزَّع على الأنشطة",
    })
    workers_bytes = _csv_bytes(WORKERS_COLUMNS, workers)
    totals_bytes = _csv_bytes(TOTALS_COLUMNS, totals)

    def source_entry(p):
        s = p.spec
        return {
            "file": s.file_name, "year": s.year, "quarter": s.quarter,
            "size_bytes": p.size_bytes, "expected_size_bytes": s.size,
            "sha256": p.sha256, "expected_sha256": s.sha256, "hash_match": p.sha256 == s.sha256,
            "records": len(p.regions) * len(p.activities),
            "regions": len(p.regions), "economic_activities": len(p.activities),
            "missing_count": len(missing_locations(p)),
            "grand_total_source": p.grand_total, "grand_total_expected": s.grand_total,
        }

    report = {
        "status": "passed",
        "errors": [],
        "warnings": warnings,
        "sources": [source_entry(p) for p in parsed_list],
        "cross_source": {
            "regions_match": True, "economic_activities_match": True,
            "same_order": same_order, "total_records": len(workers),
        },
        "missing_values": [
            {"year": p.spec.year, "quarter": p.spec.quarter, "region": r, "economic_activity": a}
            for p in parsed_list for r, a in missing_locations(p)
        ],
        "reconciliation": reconciliation,
        "unclassified_activity": {
            "name": UNCLASSIFIED_ACTIVITY,
            "interpretation": "غير محسوم",
            "included_in_grand_total": True,
            "source_totals": [
                {"year": p.spec.year, "quarter": p.spec.quarter,
                 "value": p.activity_totals[p.activities.index(UNCLASSIFIED_ACTIVITY)]}
                for p in parsed_list if UNCLASSIFIED_ACTIVITY in p.activities
            ],
        },
        "notes": [
            "نجاح مطابقة الإجماليات بالقيم المتاحة لا يعني اكتمال البيانات؛ معنى الفراغات غير محسوم.",
            "الفراغات محفوظة كقيم مفقودة وليست أصفارًا.",
        ],
        "outputs": {
            "workers.csv": {"rows": len(workers), "sha256": hashlib.sha256(workers_bytes).hexdigest().upper()},
            "source_totals.csv": {"rows": len(totals), "sha256": hashlib.sha256(totals_bytes).hexdigest().upper()},
        },
    }
    report_bytes = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "workers.csv").write_bytes(workers_bytes)
    (out / "source_totals.csv").write_bytes(totals_bytes)
    (out / "quality_report.json").write_bytes(report_bytes)
    return report


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        report = prepare()
    except PrepareError as exc:
        print("فشل التجهيز؛ لم تُكتب أي مخرجات:", file=sys.stderr)
        for message in exc.errors:
            print(f" - {message}", file=sys.stderr)
        return 1
    print("نجح التجهيز وكُتبت المخرجات في", PROCESSED_DIR)
    print("السجلات:", report["cross_source"]["total_records"],
          "| المفقودات:", len(report["missing_values"]),
          "| التحذيرات:", len(report["warnings"]))
    for source in report["sources"]:
        print(f" - الربع {source['quarter']}: {source['records']} سجلًا، "
              f"{source['missing_count']} مفقودات، الإجمالي {source['grand_total_source']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
