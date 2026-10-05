"""حسابات المقارنة بين الربعين الأول والثاني (الاتفاق: docs/ANALYSIS-CONTRACT.md).

التشغيل من جذر المشروع:
    .venv\\Scripts\\python.exe -m labor_market.analyze

يقرأ data/processed ويكتب أربعة جداول في data/analysis دون تعديل مخرجات
التجهيز. لا يجمع الربعين، ولا يحوّل المفقودات إلى أصفار، ولا يرسم شيئًا.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
ANALYSIS_DIR = PROJECT_ROOT / "data" / "analysis"

PENDING_ACTIVITY = "تحت المعالجة"
GRAND_TOTAL_NAME = "Grand Total"

# المخطط الموثق للمدخلين (docs/ANALYSIS-CONTRACT.md)، ويشمل source_file.
WORKERS_REQUIRED = ("year", "quarter", "region", "economic_activity", "workers", "source_file")
TOTALS_REQUIRED = ("year", "quarter", "total_type", "name", "value", "source_file")
TOTAL_TYPES = ("region", "economic_activity", "grand_total")

TABLE_COLUMNS = {
    "national": ["year", "workers_q1", "workers_q2", "change", "change_rate"],
    "regions": ["year", "region", "workers_q1", "workers_q2", "change", "change_rate",
                "share_q1", "share_q2"],
    "activities": ["year", "economic_activity", "workers_q1", "workers_q2", "change",
                   "change_rate", "share_q1", "share_q2", "is_pending"],
    "region_activities": ["year", "region", "economic_activity", "workers_q1", "workers_q2",
                          "change", "change_rate", "share_q1", "share_q2", "is_pending"],
}


class AnalysisError(Exception):
    """مدخلات غير صالحة للتحليل؛ الرسالة تشرح السبب."""


def _check_columns(df, required, label):
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise AnalysisError(f"{label}: أعمدة ناقصة {missing}")


def _check_duplicates(df, keys, label):
    dup = df[df.duplicated(keys, keep=False)]
    if len(dup):
        sample = dup[keys].drop_duplicates().head(3).values.tolist()
        raise AnalysisError(f"{label}: مفاتيح مكررة، مثل {sample}")


def _integers(series, column, label, allow_missing, non_negative=False):
    """يتحقق أن العمود أعداد صحيحة قبل أي تحويل، فلا يُقطع كسر ولا يُغيَّر شيء بصمت.

    يرفض: غير الرقمي، والكسري، وغير المنتهي (inf)، والمنطقي، والمفقود إن لم يُسمح به،
    والسالب إن طُلب عدم السالب. يعيد Int64 (مع المفقود حيث يُسمح).
    """
    bad = f"{label}: العمود {column} يحتوي قيمًا غير صحيحة"
    if pd.api.types.is_bool_dtype(series):
        raise AnalysisError(f"{bad} (منطقية)")
    try:
        numeric = pd.to_numeric(series, errors="raise")
    except (ValueError, TypeError) as exc:
        raise AnalysisError(f"{bad} ({exc})")
    present = numeric.dropna()
    if len(present) != len(numeric) and not allow_missing:
        raise AnalysisError(f"{bad} (مفقودة)")
    floats = present.astype("float64").to_numpy()
    if not np.isfinite(floats).all() or (floats != np.floor(floats)).any():
        raise AnalysisError(f"{bad} (كسرية أو غير منتهية)")
    if non_negative and (floats < 0).any():
        raise AnalysisError(f"{label}: العمود {column} يحتوي قيمًا سالبة")
    return numeric.astype("Int64")


def _check_keys(df, columns, label):
    """يرفض أسماء المفاتيح المفقودة أو الفارغة أو المسافات فقط، قبل الربط والحساب."""
    for column in columns:
        valid = [isinstance(v, str) and v.strip() != "" for v in df[column]]
        if not all(valid):
            rows = "، ".join(str(i + 1) for i, ok in enumerate(valid) if not ok)
            raise AnalysisError(
                f"{label}: العمود {column} يحتوي أسماء مفقودة أو فارغة أو مسافات فقط "
                f"(الصفوف بترتيبها في الجدول: {rows[:60]})"
            )


def _prepare_inputs(workers, source_totals):
    _check_columns(workers, WORKERS_REQUIRED, "workers")
    _check_columns(source_totals, TOTALS_REQUIRED, "source_totals")
    w = workers[list(WORKERS_REQUIRED)].copy()
    t = source_totals[list(TOTALS_REQUIRED)].copy()
    _check_keys(w, ("region", "economic_activity"), "workers")
    _check_keys(t, ("total_type", "name"), "source_totals")
    w["workers"] = _integers(w["workers"], "workers", "workers", allow_missing=True, non_negative=True)
    t["value"] = _integers(t["value"], "value", "source_totals", allow_missing=True, non_negative=True)
    for frame, label in ((w, "workers"), (t, "source_totals")):
        for col in ("year", "quarter"):
            frame[col] = _integers(frame[col], col, label, allow_missing=False).astype("int64")
        if set(frame["quarter"]) != {1, 2}:
            raise AnalysisError(f"{label}: الأرباع {sorted(set(frame['quarter']))} والمتوقع {{1, 2}}")
    years = set(w["year"]) | set(t["year"])
    if len(years) != 1:
        raise AnalysisError(f"السنوات {sorted(years)}؛ المقارنة داخل سنة واحدة فقط")
    bad_types = set(t["total_type"]) - set(TOTAL_TYPES)
    if bad_types:
        raise AnalysisError(f"source_totals: أنواع إجماليات غير معروفة {sorted(bad_types)}")

    _check_duplicates(w, ["year", "quarter", "region", "economic_activity"], "workers")
    _check_duplicates(t, ["year", "quarter", "total_type", "name"], "source_totals")

    # اكتمال الربط: نفس المناطق والتصنيفات في الربعين وفي التفاصيل والإجماليات.
    def names(frame, quarter, column):
        return set(frame.loc[frame["quarter"] == quarter, column])

    regions = names(w, 1, "region")
    activities = names(w, 1, "economic_activity")
    for q in (1, 2):
        if names(w, q, "region") != regions or names(w, q, "economic_activity") != activities:
            raise AnalysisError("الربط غير مكتمل: المناطق أو التصنيفات تختلف بين الربعين في workers")
        if int((w["quarter"] == q).sum()) != len(regions) * len(activities):
            raise AnalysisError(f"الربط غير مكتمل: الربع {q} لا يغطي كل تركيبات المنطقة والتصنيف")
        by_type = t[t["quarter"] == q]
        if set(by_type.loc[by_type["total_type"] == "region", "name"]) != regions:
            raise AnalysisError(f"الربط غير مكتمل: إجماليات المناطق في الربع {q} لا تطابق workers")
        if set(by_type.loc[by_type["total_type"] == "economic_activity", "name"]) != activities:
            raise AnalysisError(f"الربط غير مكتمل: إجماليات التصنيفات في الربع {q} لا تطابق workers")
        if list(by_type.loc[by_type["total_type"] == "grand_total", "name"]) != [GRAND_TOTAL_NAME]:
            raise AnalysisError(f"الربط غير مكتمل: الإجمالي العام مفقود أو مكرر في الربع {q}")
    return w, t


def _wide(frame, keys, value_column, label):
    """يحوّل جدولًا طويلًا (ربع في صف) إلى workers_q1 وworkers_q2 بمفاتيح صريحة."""
    parts = []
    for q in (1, 2):
        part = frame.loc[frame["quarter"] == q, keys + [value_column]]
        parts.append(part.rename(columns={value_column: f"workers_q{q}"}))
    merged = parts[0].merge(parts[1], on=keys, how="inner", validate="one_to_one")
    if not (len(merged) == len(parts[0]) == len(parts[1])):
        raise AnalysisError(f"الربط غير مكتمل في {label}")
    return merged.reset_index(drop=True)


def _rate(numerator, denominator):
    """نسبة كسرية؛ غير متاحة (NaN) عند فقد أحد الطرفين أو كون المقام صفرًا."""
    num = numerator.astype("Float64")
    den = denominator.astype("Float64")
    zero = (den == 0).fillna(False).astype(bool)
    return (num / den).mask(zero).astype("float64")


def _add_change(df):
    df["change"] = df["workers_q2"] - df["workers_q1"]
    df["change_rate"] = _rate(df["change"], df["workers_q1"])
    return df


def _add_shares(df, den_q1, den_q2):
    df["share_q1"] = _rate(df["workers_q1"], den_q1)
    df["share_q2"] = _rate(df["workers_q2"], den_q2)
    return df


def build_analysis(workers, source_totals):
    """يعيد قاموسًا من أربعة DataFrame: national, regions, activities, region_activities."""
    w, t = _prepare_inputs(workers, source_totals)
    year = int(w["year"].iloc[0])

    def totals_wide(total_type, column):
        sub = t[t["total_type"] == total_type].rename(columns={"name": column})
        return _wide(sub.assign(year=year), ["year", column], "value", f"إجماليات {total_type}")

    national = totals_wide("grand_total", "name").drop(columns="name")
    national = _add_change(national)[TABLE_COLUMNS["national"]]
    grand_q1, grand_q2 = national["workers_q1"].iloc[0], national["workers_q2"].iloc[0]

    regions = totals_wide("region", "region")
    regions = _add_change(regions)
    regions = _add_shares(regions, pd.Series(grand_q1, index=regions.index, dtype="Int64"),
                          pd.Series(grand_q2, index=regions.index, dtype="Int64"))
    regions = regions[TABLE_COLUMNS["regions"]]

    activities = totals_wide("economic_activity", "economic_activity")
    activities = _add_change(activities)
    activities = _add_shares(activities, pd.Series(grand_q1, index=activities.index, dtype="Int64"),
                             pd.Series(grand_q2, index=activities.index, dtype="Int64"))
    activities["is_pending"] = activities["economic_activity"] == PENDING_ACTIVITY
    activities = activities[TABLE_COLUMNS["activities"]]

    cells = _wide(w, ["year", "region", "economic_activity"], "workers", "تفاصيل workers")
    cells = _add_change(cells)
    region_den = regions[["region", "workers_q1", "workers_q2"]].rename(
        columns={"workers_q1": "den_q1", "workers_q2": "den_q2"})
    cells = cells.merge(region_den, on="region", how="left", validate="many_to_one")
    cells = _add_shares(cells, cells["den_q1"], cells["den_q2"])
    cells["is_pending"] = cells["economic_activity"] == PENDING_ACTIVITY
    region_activities = cells[TABLE_COLUMNS["region_activities"]]

    return {
        "national": national,
        "regions": regions,
        "activities": activities,
        "region_activities": region_activities,
    }


def read_processed(processed_dir=PROCESSED_DIR):
    """يقرأ مخرجات التجهيز دون تحويل الفراغ أو أسماء مثل NA إلى شيء آخر."""
    opts = {"encoding": "utf-8", "keep_default_na": False, "na_values": [""]}
    processed_dir = Path(processed_dir)
    workers = pd.read_csv(processed_dir / "workers.csv", dtype={"workers": "Int64"}, **opts)
    totals = pd.read_csv(processed_dir / "source_totals.csv", dtype={"value": "Int64"}, **opts)
    return workers, totals


def write_analysis(tables, out_dir=ANALYSIS_DIR):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False, encoding="utf-8", lineterminator="\n")


def run(processed_dir=PROCESSED_DIR, out_dir=ANALYSIS_DIR):
    workers, totals = read_processed(processed_dir)
    tables = build_analysis(workers, totals)
    write_analysis(tables, out_dir)
    return tables


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        tables = run()
    except AnalysisError as exc:
        print(f"فشل التحليل؛ لم تُكتب أي مخرجات: {exc}", file=sys.stderr)
        return 1
    print("كُتبت جداول التحليل في", ANALYSIS_DIR)
    for name, df in tables.items():
        print(f" - {name}: {len(df)} سجلًا")
    return 0


if __name__ == "__main__":
    sys.exit(main())
