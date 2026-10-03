"""اختبارات تجهيز البيانات. التشغيل من جذر المشروع:

    .venv\\Scripts\\python.exe -m unittest discover -s tests -v

الحالات المعدّلة تعمل على نسخ مؤقتة؛ data/raw لا يُعدَّل أبدًا.
"""

import csv
import dataclasses
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from labor_market import prepare as prep

Q1, Q2 = prep.SOURCES
RAW = prep.RAW_DIR


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class TempCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.raw = self.tmp / "raw"
        self.out = self.tmp / "out"
        shutil.copytree(RAW, self.raw)

    def modify(self, spec, old, new):
        """يعدّل نسخة مؤقتة من مصدر ويعيد SourceSpec بهاش النسخة المعدّلة."""
        path = self.raw / spec.file_name
        text = path.read_bytes().decode("utf-8")
        self.assertIn(old, text)
        data = text.replace(old, new, 1).encode("utf-8")
        path.write_bytes(data)
        return dataclasses.replace(
            spec, size=len(data), sha256=hashlib.sha256(data).hexdigest().upper()
        )

    def run_prepare(self, sources=prep.SOURCES):
        return prep.prepare(self.raw, self.out, sources)

    def assertFails(self, sources, fragment):
        with self.assertRaises(prep.PrepareError) as ctx:
            self.run_prepare(sources)
        self.assertTrue(
            any(fragment in e for e in ctx.exception.errors), ctx.exception.errors
        )
        self.assertFalse(self.out.exists(), "يجب ألا تُكتب مخرجات عند الفشل")


class RealSourcesTest(TempCase):
    def setUp(self):
        super().setUp()
        self.report = self.run_prepare()
        self.workers = read_csv(self.out / "workers.csv")
        self.totals = read_csv(self.out / "source_totals.csv")

    def test_record_counts(self):
        self.assertEqual(len(self.workers), 520)
        for q in ("1", "2"):
            self.assertEqual(sum(1 for r in self.workers if r["quarter"] == q), 260)
        self.assertEqual(list(self.workers[0]), list(prep.WORKERS_COLUMNS))
        keys = {(r["year"], r["quarter"], r["region"], r["economic_activity"]) for r in self.workers}
        self.assertEqual(len(keys), 520)

    def test_year_quarter_and_source_file_binding(self):
        for r in self.workers:
            spec = Q1 if r["quarter"] == "1" else Q2
            self.assertEqual(r["year"], "2026")
            self.assertEqual(r["source_file"], spec.file_name)

    def test_missing_values_preserved_not_zero(self):
        empty = {
            (r["quarter"], r["region"], r["economic_activity"])
            for r in self.workers if r["workers"] == ""
        }
        self.assertEqual(
            empty,
            {
                ("1", "الباحة", prep.PUBLIC_ADMIN_ACTIVITY),
                ("1", "نجران", prep.PUBLIC_ADMIN_ACTIVITY),
                ("2", "الباحة", prep.PUBLIC_ADMIN_ACTIVITY),
            },
        )
        self.assertEqual(len(self.report["missing_values"]), 3)

    def test_missing_values_load_as_missing_in_pandas(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas غير متاح")
        df = pd.read_csv(self.out / "workers.csv", dtype={"workers": "Int64"})
        self.assertEqual(int(df["workers"].isna().sum()), 3)

    def test_totals_excluded_from_details(self):
        self.assertTrue(all(prep.GRAND_TOTAL_LABEL not in (r["region"], r["economic_activity"])
                            for r in self.workers))
        self.assertEqual(len(self.totals), 2 * (13 + 20 + 1))
        grand = {r["quarter"]: int(r["value"]) for r in self.totals if r["total_type"] == "grand_total"}
        self.assertEqual(grand, {"1": 13_569_346, "2": 13_610_026})

    def test_unclassified_activity_kept_as_own_category(self):
        rows = [r for r in self.workers if r["economic_activity"] == prep.UNCLASSIFIED_ACTIVITY]
        self.assertEqual(len(rows), 26)
        self.assertEqual(self.report["unclassified_activity"]["interpretation"], "غير محسوم")
        self.assertTrue(any(w["code"] == "unclassified_activity" for w in self.report["warnings"]))

    def test_reconciliation_has_no_mismatch_and_reports_missing(self):
        statuses = {c["status"] for c in self.report["reconciliation"]}
        self.assertNotIn("mismatch", statuses)
        with_missing = [c for c in self.report["reconciliation"] if c["missing_count"]]
        self.assertTrue(with_missing)
        self.assertTrue(all(c["status"] == "match_with_missing" for c in with_missing))
        grand_q1 = next(c for c in self.report["reconciliation"]
                        if c["kind"] == "grand_total" and c["quarter"] == 1)
        self.assertEqual((grand_q1["sum_available"], grand_q1["missing_count"]), (13_569_346, 2))

    def test_thousands_separators_parsed(self):
        row = next(r for r in self.workers
                   if r["quarter"] == "1" and r["region"] == "الرياض"
                   and r["economic_activity"] == "التشييد")
        self.assertEqual(row["workers"], "1508328")

    def test_report_file_contents(self):
        report = json.loads((self.out / "quality_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["errors"], [])
        for entry in report["sources"]:
            self.assertTrue(entry["hash_match"])
            self.assertEqual((entry["records"], entry["regions"], entry["economic_activities"]), (260, 13, 20))
        self.assertEqual(report["outputs"]["workers.csv"]["sha256"], sha(self.out / "workers.csv"))


class RerunAndIsolationTest(TempCase):
    def test_rerun_is_identical_and_raw_unchanged(self):
        before = {s.file_name: sha(self.raw / s.file_name) for s in prep.SOURCES}
        self.run_prepare()
        first = {f: (self.out / f).read_bytes()
                 for f in ("workers.csv", "source_totals.csv", "quality_report.json")}
        shutil.rmtree(self.out)
        self.run_prepare()
        second = {f: (self.out / f).read_bytes() for f in first}
        self.assertEqual(first, second)
        after = {s.file_name: sha(self.raw / s.file_name) for s in prep.SOURCES}
        self.assertEqual(before, after)
        self.assertEqual(before, {s.file_name: s.sha256 for s in prep.SOURCES})

    def test_real_raw_files_match_recorded_hashes(self):
        for s in prep.SOURCES:
            self.assertEqual(sha(RAW / s.file_name), s.sha256)

    def test_independent_of_working_directory(self):
        cwd = os.getcwd()
        os.chdir(self.tmp)
        try:
            prep.prepare(out_dir=self.out)
        finally:
            os.chdir(cwd)
        self.assertTrue((self.out / "workers.csv").is_file())


class FailureCasesTest(TempCase):
    def test_changed_source_hash(self):
        path = self.raw / Q1.file_name
        path.write_bytes(path.read_bytes().replace(b"6,569", b"6,570", 1))
        self.assertFails(prep.SOURCES, "اختلف الحجم أو الهاش")

    def test_non_numeric_value(self):
        spec = self.modify(Q1, '"6,569"', "abc")
        self.assertFails((spec, Q2), "قيمة غير رقمية")

    def test_negative_value(self):
        spec = self.modify(Q1, '"6,569"', "-5")
        self.assertFails((spec, Q2), "قيمة غير رقمية")

    def test_malformed_thousands_separator(self):
        spec = self.modify(Q1, '"6,569"', '"65,69"')
        self.assertFails((spec, Q2), "قيمة غير رقمية")

    def test_duplicate_region_name(self):
        spec = self.modify(Q1, "الباحة,الجوف,", "الباحة,الباحة,")
        self.assertFails((spec, Q2), "أسماء المناطق فارغة أو مكررة")

    def test_duplicate_activity_name(self):
        spec = self.modify(Q1, "\nالتعليم,", "\nالتشييد,")
        self.assertFails((spec, Q2), "أسماء التصنيفات فارغة أو مكررة")

    def test_total_mismatch(self):
        spec = self.modify(Q1, '"47,882"', '"47,883"')
        self.assertFails((spec, Q2), "إجمالي غير مطابق")

    def test_unexpected_extra_row(self):
        path = self.raw / Q1.file_name
        data = path.read_bytes() + b"\r\n"
        path.write_bytes(data)
        spec = dataclasses.replace(Q1, size=len(data), sha256=hashlib.sha256(data).hexdigest().upper())
        self.assertFails((spec, Q2), "عدد الصفوف")

    def test_unexpected_missing_location(self):
        spec = dataclasses.replace(Q1, missing=Q1.missing[:1])
        self.assertFails((spec, Q2), "مواقع المفقودات")

    def test_region_names_must_match_between_quarters(self):
        spec = self.modify(Q2, "نجران,Grand Total", "نجران2,Grand Total")
        self.assertFails((Q1, spec), "غير متطابقة")

    def test_source_file_missing(self):
        (self.raw / Q2.file_name).unlink()
        self.assertFails(prep.SOURCES, "الملف غير موجود")


# --- مقارنة مستقلة كاملة --------------------------------------------------
# التوقعات تُبنى هنا بـcsv القياسي فقط، دون أي دالة تحويل أو تجميع أو ربط
# للفترات من prepare. الفترات مكتوبة صراحة في الاختبار.

EXPECTED_PERIODS = {
    "Workers in the private sector Q12026CSV.csv": (2026, 1),
    "Employees private sector Q22026CSV.csv": (2026, 2),
}


def independent_expectations(raw_dir):
    """يعيد (details, totals): مفتاح -> (قيمة أو None, ملف المصدر)."""
    details, totals = {}, {}
    for file_name, (year, quarter) in EXPECTED_PERIODS.items():
        with open(Path(raw_dir) / file_name, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))

        def num(cell):
            return int(cell.replace(",", "")) if cell != "" else None

        regions = rows[1][1:-1]
        for row in rows[2:-1]:
            activity = row[0]
            for region, cell in zip(regions, row[1:-1]):
                details[(year, quarter, region, activity)] = (num(cell), file_name)
            totals[(year, quarter, "economic_activity", activity)] = (num(row[-1]), file_name)
        last = rows[-1]
        for region, cell in zip(regions, last[1:-1]):
            totals[(year, quarter, "region", region)] = (num(cell), file_name)
        totals[(year, quarter, "grand_total", "Grand Total")] = (num(last[-1]), file_name)
    return details, totals


def load_outputs(out_dir):
    """يقرأ مخرجات prepare من القرص بمفاتيح السجلات (لا بترتيبها)."""
    def value(text):
        return int(text) if text != "" else None

    details = {}
    for r in read_csv(Path(out_dir) / "workers.csv"):
        key = (int(r["year"]), int(r["quarter"]), r["region"], r["economic_activity"])
        assert key not in details, f"مفتاح مكرر في workers.csv: {key}"
        details[key] = (value(r["workers"]), r["source_file"])
    totals = {}
    for r in read_csv(Path(out_dir) / "source_totals.csv"):
        key = (int(r["year"]), int(r["quarter"]), r["total_type"], r["name"])
        assert key not in totals, f"مفتاح مكرر في source_totals.csv: {key}"
        totals[key] = (value(r["value"]), r["source_file"])
    return details, totals


def differences(expected, actual):
    """مفاتيح تختلف بين التوقع والمخرج (مفقودة أو زائدة أو بقيمة/مصدر مختلف)."""
    return sorted(
        (k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k)),
        key=str,
    )


class IndependentComparisonTest(TempCase):
    def test_expectation_builder_sanity(self):
        details, totals = independent_expectations(RAW)
        self.assertEqual((len(details), len(totals)), (520, 68))
        self.assertEqual(sum(1 for v, _ in details.values() if v is None), 3)

    def test_all_details_and_totals_match_independent_expectations(self):
        expected_details, expected_totals = independent_expectations(RAW)
        self.run_prepare()
        actual_details, actual_totals = load_outputs(self.out)
        self.assertEqual(len(actual_details), 520)
        self.assertEqual(len(actual_totals), 68)
        self.assertEqual(differences(expected_details, actual_details), [])
        self.assertEqual(differences(expected_totals, actual_totals), [])

    def test_comparison_is_by_key_not_order(self):
        details, _ = independent_expectations(RAW)
        shuffled = dict(reversed(list(details.items())))
        self.assertEqual(differences(details, shuffled), [])

    def test_offsetting_changes_keep_sums_but_are_detected(self):
        services, construction = "أنشطة الخدمات الأخرى", "التشييد"
        riyadh, eastern = "الرياض", "الشرقية"
        deltas = {
            (services, riyadh): +1,
            (services, eastern): -1,
            (construction, riyadh): -1,
            (construction, eastern): +1,
        }

        # نسخة مؤقتة من الربع الأول بأربع خلايا غير مفقودة معدّلة.
        path = self.raw / Q1.file_name
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        regions = rows[1][1:-1]
        for row in rows[2:-1]:
            for region in (riyadh, eastern):
                delta = deltas.get((row[0], region))
                if delta:
                    j = regions.index(region) + 1
                    self.assertNotEqual(row[j], "")
                    row[j] = f"{int(row[j].replace(',', '')) + delta:,}"
        with open(path, "w", encoding="utf-8", newline="") as f:
            csv.writer(f, lineterminator="\r\n").writerows(rows)
        data = path.read_bytes()
        tampered_spec = dataclasses.replace(
            Q1, size=len(data), sha256=hashlib.sha256(data).hexdigest().upper()
        )

        # المجاميع ثابتة بحسابها المستقل من الملفين الأصلي والمعدّل.
        original, tampered = independent_expectations(RAW)[0], independent_expectations(self.raw)[0]
        self.assertNotEqual(original, tampered)
        changed = differences(original, tampered)
        self.assertEqual(
            sorted(changed, key=str),
            sorted(((2026, 1, region, activity) for (activity, region) in deltas), key=str),
        )
        def q1_sum(details, region=None, activity=None):
            return sum(
                v for (y, q, r, a), (v, _) in details.items()
                if (y, q) == (2026, 1) and v is not None
                and region in (None, r) and activity in (None, a)
            )

        for activity in (services, construction):
            self.assertEqual(q1_sum(original, activity=activity), q1_sum(tampered, activity=activity))
        for region in (riyadh, eastern):
            self.assertEqual(q1_sum(original, region=region), q1_sum(tampered, region=region))
        self.assertEqual(q1_sum(original), q1_sum(tampered))

        # فحوص prepare نفسها لا تكشف التحريف (المجاميع لم تتغير)...
        report = self.run_prepare((tampered_spec, Q2))
        self.assertNotIn("mismatch", {c["status"] for c in report["reconciliation"]})

        # ...لكن المقارنة المستقلة بالتوقعات الأصلية تكشف الخلايا الأربع بدقة.
        expected_details, expected_totals = independent_expectations(RAW)
        actual_details, actual_totals = load_outputs(self.out)
        self.assertEqual(differences(expected_totals, actual_totals), [])
        self.assertEqual(
            differences(expected_details, actual_details),
            sorted(((2026, 1, region, activity) for (activity, region) in deltas), key=str),
        )
        for (activity, region), delta in deltas.items():
            key = (2026, 1, region, activity)
            self.assertEqual(actual_details[key][0] - expected_details[key][0], delta)


class HelpersTest(unittest.TestCase):
    def test_parse_number(self):
        self.assertEqual(prep.parse_number("1,333,100"), 1333100)
        self.assertEqual(prep.parse_number("8"), 8)
        self.assertEqual(prep.parse_number("0"), 0)
        self.assertIsNone(prep.parse_number(""))
        for bad in ("abc", "-1", "1.5", " 5", "1,23", "١٢"):
            with self.assertRaises(ValueError):
                prep.parse_number(bad)

    def test_sum_available_never_turns_all_missing_into_zero(self):
        self.assertIsNone(prep.sum_available([None, None]))
        self.assertEqual(prep.sum_available([None, 3, 4]), 7)
        self.assertEqual(prep.sum_available([0, None]), 0)


if __name__ == "__main__":
    unittest.main()
