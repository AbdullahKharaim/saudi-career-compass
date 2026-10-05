"""اختبارات حسابات التحليل. التشغيل (ملف واحد):

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p test_analyze.py -v

التوقعات تُحسب هنا بـcsv القياسي وحساب بايثون العادي، لا بدوال analyze.
"""

import csv
import hashlib
import math
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from labor_market import analyze

PROCESSED = analyze.PROCESSED_DIR
PENDING = "تحت المعالجة"


def isna(x):
    return x is None or (isinstance(x, float) and math.isnan(x)) or x is pd.NA


def cell(x):
    """قيمة DataFrame إلى بايثون عادي: None للمفقود."""
    return None if isna(x) else (int(x) if not isinstance(x, (float, bool)) else x)


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=0)


def frac(num, den):
    """كسر مستقل: None عند فقد أحد الطرفين أو مقام صفر."""
    if num is None or den is None or den == 0:
        return None
    return num / den


def sub(a, b):
    return None if a is None or b is None else a - b


def read_rows(name):
    with open(PROCESSED / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def independent_real_expectations():
    """يحسب كل الجداول المتوقعة من csv المعالج بحساب بايثون مباشر."""
    def val(text):
        return int(text) if text != "" else None

    cells = {}
    for r in read_rows("workers.csv"):
        cells[(r["region"], r["economic_activity"], int(r["quarter"]))] = val(r["workers"])
    totals = {}
    for r in read_rows("source_totals.csv"):
        totals[(r["total_type"], r["name"], int(r["quarter"]))] = val(r["value"])
    return cells, totals


def expected_tables(cells, totals):
    regions = sorted({k[0] for k in cells})
    activities = sorted({k[1] for k in cells})
    grand = {q: totals[("grand_total", "Grand Total", q)] for q in (1, 2)}

    def row(q1, q2):
        return {"workers_q1": q1, "workers_q2": q2, "change": sub(q2, q1), "change_rate": frac(sub(q2, q1), q1)}

    national = {(): row(grand[1], grand[2])}
    reg = {}
    for r in regions:
        t1, t2 = totals[("region", r, 1)], totals[("region", r, 2)]
        reg[(r,)] = {**row(t1, t2), "share_q1": frac(t1, grand[1]), "share_q2": frac(t2, grand[2])}
    act = {}
    for a in activities:
        t1, t2 = totals[("economic_activity", a, 1)], totals[("economic_activity", a, 2)]
        act[(a,)] = {**row(t1, t2), "share_q1": frac(t1, grand[1]), "share_q2": frac(t2, grand[2]),
                     "is_pending": a == PENDING}
    ra = {}
    for r in regions:
        for a in activities:
            c1, c2 = cells[(r, a, 1)], cells[(r, a, 2)]
            ra[(r, a)] = {**row(c1, c2),
                          "share_q1": frac(c1, totals[("region", r, 1)]),
                          "share_q2": frac(c2, totals[("region", r, 2)]),
                          "is_pending": a == PENDING}
    return {"national": national, "regions": reg, "activities": act, "region_activities": ra}


KEY_COLUMNS = {"national": [], "regions": ["region"], "activities": ["economic_activity"],
               "region_activities": ["region", "economic_activity"]}


def assert_table_equals(case, name, df, expected):
    keys = KEY_COLUMNS[name]
    case.assertEqual(len(df), len(expected), name)
    seen = set()
    for _, r in df.iterrows():
        key = tuple(r[k] for k in keys)
        case.assertNotIn(key, seen, f"{name}: مفتاح مكرر {key}")
        seen.add(key)
        exp = expected[key]
        case.assertEqual(int(r["year"]), 2026)
        for col, want in exp.items():
            got = cell(r[col])
            if col == "is_pending":
                case.assertIs(bool(got), want, f"{name} {key} {col}")
            elif col in ("change_rate", "share_q1", "share_q2"):
                case.assertTrue(close(got, want), f"{name} {key} {col}: {got} != {want}")
            else:
                case.assertEqual(got, want, f"{name} {key} {col}")
    case.assertEqual(seen, set(expected))


def small_inputs(q1_cells=None, q2_cells=None, **overrides):
    """مدخلات صغيرة بتوقعات يدوية: منطقتان × تصنيفان (أحدهما تحت المعالجة)."""
    regions, acts = ["A", "B"], ["X", PENDING]
    q1 = {("A", "X"): 10, ("A", PENDING): 5, ("B", "X"): 20, ("B", PENDING): 15}
    q2 = {("A", "X"): 12, ("A", PENDING): 3, ("B", "X"): 18, ("B", PENDING): 27}
    q1.update(q1_cells or {})
    q2.update(q2_cells or {})
    workers = [(2026, q, r, a, c[(r, a)], "f") for q, c in ((1, q1), (2, q2)) for r in regions for a in acts]

    def total(c, key):
        return None if any(c[k] is None for k in key) else sum(c[k] for k in key)

    totals = []
    for q, c in ((1, q1), (2, q2)):
        for r in regions:
            totals.append((2026, q, "region", r, total(c, [(r, a) for a in acts]), "f"))
        for a in acts:
            totals.append((2026, q, "economic_activity", a, total(c, [(r, a) for r in regions]), "f"))
        totals.append((2026, q, "grand_total", "Grand Total", total(c, list(c)), "f"))
    wdf = pd.DataFrame(workers, columns=["year", "quarter", "region", "economic_activity", "workers", "source_file"])
    tdf = pd.DataFrame(totals, columns=["year", "quarter", "total_type", "name", "value", "source_file"])
    wdf["workers"] = wdf["workers"].astype("Int64")
    tdf["value"] = tdf["value"].astype("Int64")
    return wdf, tdf


def row_of(df, **match):
    mask = pd.Series(True, index=df.index)
    for k, v in match.items():
        mask &= df[k] == v
    assert mask.sum() == 1, match
    return df[mask].iloc[0]


class RealDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = analyze.build_analysis(*analyze.read_processed())
        cls.cells, cls.totals = independent_real_expectations()
        cls.expected = expected_tables(cls.cells, cls.totals)

    def test_contract_names_sizes_and_columns(self):
        self.assertEqual(list(self.tables), ["national", "regions", "activities", "region_activities"])
        self.assertEqual({k: len(v) for k, v in self.tables.items()},
                         {"national": 1, "regions": 13, "activities": 20, "region_activities": 260})
        for name, df in self.tables.items():
            self.assertEqual(list(df.columns), analyze.TABLE_COLUMNS[name])

    def test_national_change_is_40680(self):
        n = self.tables["national"].iloc[0]
        self.assertEqual((int(n["year"]), int(n["workers_q1"]), int(n["workers_q2"]), int(n["change"])),
                         (2026, 13_569_346, 13_610_026, 40_680))
        self.assertTrue(close(float(n["change_rate"]), 40_680 / 13_569_346))

    def test_every_table_matches_independent_expectations(self):
        for name, df in self.tables.items():
            with self.subTest(table=name):
                assert_table_equals(self, name, df, self.expected[name])

    def test_shares_are_fractions_and_sum_to_one(self):
        for name in ("regions", "activities"):
            df = self.tables[name]
            for col in ("share_q1", "share_q2"):
                self.assertTrue(math.isclose(df[col].sum(), 1.0, rel_tol=1e-12), (name, col))
                self.assertTrue((df[col] < 1).all())
        ra = self.tables["region_activities"]
        for region, g in ra.groupby("region"):
            for col, q in (("share_q1", "workers_q1"), ("share_q2", "workers_q2")):
                self.assertLessEqual(g[col].sum(), 1.0 + 1e-12, (region, col))

    def test_denominators_are_region_totals_including_pending(self):
        r = row_of(self.tables["region_activities"], region="الرياض", economic_activity="التشييد")
        self.assertTrue(close(float(r["share_q1"]), 1_508_328 / 6_270_023))
        p = row_of(self.tables["region_activities"], region="الرياض", economic_activity=PENDING)
        self.assertTrue(bool(p["is_pending"]))
        self.assertTrue(close(float(p["share_q1"]), 870_276 / 6_270_023))
        a = row_of(self.tables["activities"], economic_activity=PENDING)
        self.assertTrue(close(float(a["share_q1"]), 1_333_100 / 13_569_346))

    def test_pending_flag_only_on_pending_activity(self):
        self.assertEqual(int(self.tables["activities"]["is_pending"].sum()), 1)
        self.assertEqual(int(self.tables["region_activities"]["is_pending"].sum()), 13)
        for df in (self.tables["activities"], self.tables["region_activities"]):
            self.assertEqual(set(df.loc[df["is_pending"], "economic_activity"]), {PENDING})

    def test_missing_values_stay_missing(self):
        ra = self.tables["region_activities"]
        public = "الإدارة العامة والدفاع , الضمان الاجتماعي الالزامي"
        baha = row_of(ra, region="الباحة", economic_activity=public)
        for col in ("workers_q1", "workers_q2", "change", "change_rate", "share_q1", "share_q2"):
            self.assertTrue(pd.isna(baha[col]), col)
        najran = row_of(ra, region="نجران", economic_activity=public)
        self.assertTrue(pd.isna(najran["workers_q1"]))
        self.assertEqual(int(najran["workers_q2"]), 2)
        self.assertTrue(pd.isna(najran["change"]) and pd.isna(najran["change_rate"]))
        self.assertTrue(pd.isna(najran["share_q1"]))
        self.assertTrue(close(float(najran["share_q2"]), 2 / 264_876))
        self.assertEqual(int(ra["workers_q1"].isna().sum()), 2)
        self.assertEqual(int(ra["workers_q2"].isna().sum()), 1)

    def test_quarters_are_never_summed(self):
        for df in self.tables.values():
            self.assertFalse(any("total" in c or "sum" in c for c in df.columns))


class SmallHandComputedTest(unittest.TestCase):
    def test_hand_computed_values(self):
        t = analyze.build_analysis(*small_inputs())
        n = t["national"].iloc[0]
        self.assertEqual((n["workers_q1"], n["workers_q2"], n["change"]), (50, 60, 10))
        self.assertTrue(close(float(n["change_rate"]), 0.2))
        a = row_of(t["regions"], region="A")
        self.assertEqual((a["workers_q1"], a["workers_q2"], a["change"]), (15, 15, 0))
        self.assertTrue(close(float(a["change_rate"]), 0.0))
        self.assertTrue(close(float(a["share_q1"]), 15 / 50))
        self.assertTrue(close(float(a["share_q2"]), 15 / 60))
        p = row_of(t["activities"], economic_activity=PENDING)
        self.assertEqual((p["workers_q1"], p["workers_q2"], p["change"]), (20, 30, 10))
        self.assertTrue(bool(p["is_pending"]))
        self.assertTrue(close(float(p["share_q2"]), 30 / 60))
        c = row_of(t["region_activities"], region="B", economic_activity="X")
        self.assertEqual((c["workers_q1"], c["workers_q2"], c["change"]), (20, 18, -2))
        self.assertTrue(close(float(c["change_rate"]), -0.1))
        self.assertTrue(close(float(c["share_q1"]), 20 / 35))
        self.assertTrue(close(float(c["share_q2"]), 18 / 45))

    def test_zero_q1_gives_rate_na_but_keeps_change(self):
        t = analyze.build_analysis(*small_inputs(q1_cells={("A", "X"): 0}))
        c = row_of(t["region_activities"], region="A", economic_activity="X")
        self.assertEqual((c["workers_q1"], c["workers_q2"], c["change"]), (0, 12, 12))
        self.assertTrue(pd.isna(c["change_rate"]))
        self.assertTrue(close(float(c["share_q1"]), 0.0))

    def test_zero_denominator_gives_share_na(self):
        zeros = {("A", "X"): 0, ("A", PENDING): 0}
        t = analyze.build_analysis(*small_inputs(q1_cells=zeros))
        a = row_of(t["regions"], region="A")
        self.assertEqual(int(a["workers_q1"]), 0)
        self.assertTrue(pd.isna(a["change_rate"]))
        cells = t["region_activities"]
        for act in ("X", PENDING):
            self.assertTrue(pd.isna(row_of(cells, region="A", economic_activity=act)["share_q1"]))

    def test_missing_cell_is_not_zero_and_total_changes_nothing_else(self):
        wdf, tdf = small_inputs(q2_cells={("B", PENDING): None})
        t = analyze.build_analysis(wdf, tdf)
        c = row_of(t["region_activities"], region="B", economic_activity=PENDING)
        self.assertEqual(int(c["workers_q1"]), 15)
        self.assertTrue(pd.isna(c["workers_q2"]) and pd.isna(c["change"]) and pd.isna(c["change_rate"]))
        self.assertTrue(pd.isna(c["share_q2"]))
        # الإجماليات المقابلة مفقودة أيضًا في هذه المدخلات ولا تتحول إلى صفر.
        b = row_of(t["regions"], region="B")
        self.assertTrue(pd.isna(b["workers_q2"]) and pd.isna(b["share_q2"]))
        self.assertTrue(pd.isna(t["national"].iloc[0]["workers_q2"]))

    def test_inputs_not_mutated(self):
        wdf, tdf = small_inputs()
        w0, t0 = wdf.copy(deep=True), tdf.copy(deep=True)
        analyze.build_analysis(wdf, tdf)
        pd.testing.assert_frame_equal(wdf, w0)
        pd.testing.assert_frame_equal(tdf, t0)

    def test_accepts_plain_int_and_float_inputs(self):
        wdf, tdf = small_inputs()
        wdf["workers"] = wdf["workers"].astype("float64")
        tdf["value"] = tdf["value"].astype("float64")
        t = analyze.build_analysis(wdf, tdf)
        self.assertEqual(int(t["national"].iloc[0]["change"]), 10)


class ValidationTest(unittest.TestCase):
    def assertRejects(self, wdf, tdf, fragment):
        with self.assertRaises(analyze.AnalysisError) as ctx:
            analyze.build_analysis(wdf, tdf)
        self.assertIn(fragment, str(ctx.exception))

    def test_duplicate_detail_key(self):
        wdf, tdf = small_inputs()
        wdf = pd.concat([wdf, wdf.iloc[[0]]], ignore_index=True)
        self.assertRejects(wdf, tdf, "workers: مفاتيح مكررة")

    def test_duplicate_total_key(self):
        wdf, tdf = small_inputs()
        tdf = pd.concat([tdf, tdf.iloc[[0]]], ignore_index=True)
        self.assertRejects(wdf, tdf, "source_totals: مفاتيح مكررة")

    def test_incomplete_join_missing_detail_row(self):
        wdf, tdf = small_inputs()
        wdf = wdf[~((wdf["quarter"] == 2) & (wdf["region"] == "B") & (wdf["economic_activity"] == "X"))]
        self.assertRejects(wdf, tdf, "الربط غير مكتمل")

    def test_region_only_in_one_quarter(self):
        wdf, tdf = small_inputs()
        wdf = wdf.copy()
        wdf.loc[(wdf["quarter"] == 2) & (wdf["region"] == "B"), "region"] = "C"
        self.assertRejects(wdf, tdf, "الربط غير مكتمل")

    def test_totals_do_not_match_detail_names(self):
        wdf, tdf = small_inputs()
        tdf = tdf[~((tdf["total_type"] == "region") & (tdf["name"] == "B") & (tdf["quarter"] == 1))]
        self.assertRejects(wdf, tdf, "إجماليات المناطق")

    def test_missing_grand_total(self):
        wdf, tdf = small_inputs()
        tdf = tdf[~((tdf["total_type"] == "grand_total") & (tdf["quarter"] == 2))]
        self.assertRejects(wdf, tdf, "الإجمالي العام")

    def test_missing_column(self):
        wdf, tdf = small_inputs()
        self.assertRejects(wdf.drop(columns="region"), tdf, "أعمدة ناقصة")

    def test_negative_value(self):
        wdf, tdf = small_inputs()
        wdf.loc[0, "workers"] = -1
        self.assertRejects(wdf, tdf, "سالبة")

    def test_non_integer_value(self):
        wdf, tdf = small_inputs()
        wdf["workers"] = wdf["workers"].astype("float64")
        wdf.loc[0, "workers"] = 1.5
        self.assertRejects(wdf, tdf, "غير صحيحة")

    def test_unexpected_quarter(self):
        wdf, tdf = small_inputs()
        wdf.loc[wdf["quarter"] == 2, "quarter"] = 3
        self.assertRejects(wdf, tdf, "الأرباع")

    def test_more_than_one_year(self):
        wdf, tdf = small_inputs()
        wdf.loc[wdf["quarter"] == 2, "year"] = 2027
        tdf.loc[tdf["quarter"] == 2, "year"] = 2027
        self.assertRejects(wdf, tdf, "السنوات")

    def test_unknown_total_type(self):
        wdf, tdf = small_inputs()
        tdf.loc[0, "total_type"] = "city"
        self.assertRejects(wdf, tdf, "أنواع إجماليات غير معروفة")


class IntegerAndKeyBoundaryTest(unittest.TestCase):
    """حدود لم تغطها اختبارات التكامل: لا قطع للكسور، ولا مفاتيح مفقودة، ولا أعمدة ناقصة."""

    def assertRejects(self, wdf, tdf, fragment):
        with self.assertRaises(analyze.AnalysisError) as ctx:
            analyze.build_analysis(wdf, tdf)
        self.assertIn(fragment, str(ctx.exception))

    def test_fractional_year_or_quarter_is_rejected_not_truncated(self):
        for column, value in (("quarter", 1.9), ("quarter", 2.0000001), ("year", 2026.1), ("year", 2026.9)):
            with self.subTest(column=column, value=value):
                wdf, tdf = small_inputs()
                for frame in (wdf, tdf):
                    frame[column] = frame[column].astype("float64")
                wdf.loc[0, column] = value
                self.assertRejects(wdf, tdf, "غير صحيحة")

    def test_integer_valued_floats_are_still_accepted(self):
        wdf, tdf = small_inputs()
        for frame in (wdf, tdf):
            frame["year"] = frame["year"].astype("float64")
            frame["quarter"] = frame["quarter"].astype("float64")
        t = analyze.build_analysis(wdf, tdf)
        self.assertEqual((int(t["national"].iloc[0]["year"]), int(t["national"].iloc[0]["change"])), (2026, 10))

    def test_non_finite_missing_boolean_and_text_period_values_are_rejected(self):
        cases = {
            "infinite year": ("year", float("inf"), "غير صحيحة"),
            "missing year": ("year", None, "مفقودة"),
            "missing quarter": ("quarter", None, "مفقودة"),
            "fractional text quarter": ("quarter", "1.5", "غير صحيحة"),
            "non-numeric text quarter": ("quarter", "الأول", "غير صحيحة"),
        }
        for label, (column, value, fragment) in cases.items():
            with self.subTest(label):
                wdf, tdf = small_inputs()
                wdf[column] = wdf[column].astype("object")
                wdf.loc[0, column] = value
                self.assertRejects(wdf, tdf, fragment)
        wdf, tdf = small_inputs()
        wdf["quarter"] = wdf["quarter"] == 1
        self.assertRejects(wdf, tdf, "منطقية")

    def test_fractional_or_infinite_counts_are_rejected_in_both_inputs(self):
        for target, column, value in (("w", "workers", 1.5), ("w", "workers", float("inf")),
                                      ("t", "value", 2.5), ("t", "value", float("inf"))):
            with self.subTest(target=target, value=value):
                wdf, tdf = small_inputs()
                frame = wdf if target == "w" else tdf
                frame[column] = frame[column].astype("float64")
                frame.loc[0, column] = value
                self.assertRejects(wdf, tdf, "غير صحيحة")

    def test_missing_empty_or_blank_key_names_are_rejected_before_any_calculation(self):
        bad_names = {"None": None, "NaN": float("nan"), "empty": "", "spaces": "   ", "tab": "\t \n"}
        fields = (("w", "region"), ("w", "economic_activity"), ("t", "name"), ("t", "total_type"))
        for target, column in fields:
            for label, bad in bad_names.items():
                with self.subTest(column=column, bad=label):
                    wdf, tdf = small_inputs()
                    frame = wdf if target == "w" else tdf
                    frame[column] = frame[column].astype("object")
                    frame.loc[1, column] = bad
                    label_name = "workers" if target == "w" else "source_totals"
                    self.assertRejects(wdf, tdf, f"{label_name}: العمود {column} يحتوي أسماء مفقودة")

    def test_key_error_message_points_to_the_row(self):
        wdf, tdf = small_inputs()
        wdf["region"] = wdf["region"].astype("object")
        wdf.loc[2, "region"] = None
        self.assertRejects(wdf, tdf, "الصفوف بترتيبها في الجدول: 3")

    def test_bad_names_are_neither_filled_nor_dropped(self):
        wdf, tdf = small_inputs()
        wdf["region"] = wdf["region"].astype("object")
        wdf.loc[0, "region"] = None
        before, rows = wdf.copy(deep=True), len(wdf)
        with self.assertRaises(analyze.AnalysisError):
            analyze.build_analysis(wdf, tdf)
        self.assertEqual(len(wdf), rows)
        self.assertTrue(wdf["region"].isna().sum() == 1)
        pd.testing.assert_frame_equal(wdf, before)

    def test_every_documented_column_is_required_for_both_inputs(self):
        for column in analyze.WORKERS_REQUIRED:
            with self.subTest(table="workers", column=column):
                wdf, tdf = small_inputs()
                self.assertRejects(wdf.drop(columns=column), tdf, "workers: أعمدة ناقصة")
        for column in analyze.TOTALS_REQUIRED:
            with self.subTest(table="source_totals", column=column):
                wdf, tdf = small_inputs()
                self.assertRejects(wdf, tdf.drop(columns=column), "source_totals: أعمدة ناقصة")

    def test_required_columns_match_documented_schema(self):
        self.assertEqual(analyze.WORKERS_REQUIRED,
                         ("year", "quarter", "region", "economic_activity", "workers", "source_file"))
        self.assertEqual(analyze.TOTALS_REQUIRED,
                         ("year", "quarter", "total_type", "name", "value", "source_file"))

    def test_extra_columns_are_still_ignored(self):
        wdf, tdf = small_inputs()
        wdf["note"] = "x"
        t = analyze.build_analysis(wdf, tdf)
        self.assertEqual(int(t["national"].iloc[0]["change"]), 10)


class OutputTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def sha_processed(self):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(PROCESSED.iterdir())}

    def test_run_writes_four_tables_matching_expectations_and_leaves_processed_untouched(self):
        before = self.sha_processed()
        analyze.run(PROCESSED, self.tmp / "out")
        self.assertEqual(self.sha_processed(), before)
        cells, totals = independent_real_expectations()
        exp = expected_tables(cells, totals)
        for name, keys in KEY_COLUMNS.items():
            with open(self.tmp / "out" / f"{name}.csv", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(list(rows[0]), analyze.TABLE_COLUMNS[name])
            self.assertEqual(len(rows), len(exp[name]))
            for r in rows:
                want = exp[name][tuple(r[k] for k in keys)]
                for col in ("workers_q1", "workers_q2", "change"):
                    self.assertEqual(r[col], "" if want[col] is None else str(want[col]), (name, col))
                for col in ("change_rate", "share_q1", "share_q2"):
                    if col in want:
                        self.assertEqual(r[col] == "", want[col] is None, (name, col))
                        if want[col] is not None:
                            self.assertTrue(close(float(r[col]), want[col]))
        self.assertEqual(sorted(p.name for p in (self.tmp / "out").iterdir()),
                         ["activities.csv", "national.csv", "region_activities.csv", "regions.csv"])

    def test_rerun_is_byte_identical(self):
        analyze.run(PROCESSED, self.tmp / "a")
        analyze.run(PROCESSED, self.tmp / "b")
        for name in KEY_COLUMNS:
            self.assertEqual((self.tmp / "a" / f"{name}.csv").read_bytes(),
                             (self.tmp / "b" / f"{name}.csv").read_bytes())

    def test_no_output_on_failure(self):
        bad = self.tmp / "processed"
        bad.mkdir()
        for name in ("workers.csv", "source_totals.csv"):
            (bad / name).write_bytes((PROCESSED / name).read_bytes())
        lines = (bad / "workers.csv").read_text(encoding="utf-8").splitlines(keepends=True)
        (bad / "workers.csv").write_text("".join(lines + [lines[1]]), encoding="utf-8")
        with self.assertRaises(analyze.AnalysisError):
            analyze.run(bad, self.tmp / "out")
        self.assertFalse((self.tmp / "out").exists())

    def test_independent_of_working_directory(self):
        cwd = os.getcwd()
        os.chdir(self.tmp)
        try:
            analyze.run(out_dir=self.tmp / "out")
        finally:
            os.chdir(cwd)
        self.assertTrue((self.tmp / "out" / "national.csv").is_file())


if __name__ == "__main__":
    unittest.main()
