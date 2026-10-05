"""اختبارات لوحة Streamlit بواسطة AppTest (لا تُغني عن مراجعة المتصفح). التشغيل:

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p test_app.py -v

التوقعات تُحسب هنا من csv المعالج بحساب بايثون مباشر، لا بدوال analyze.
الحالات المعدّلة تعمل على نسخ مؤقتة؛ لا تُكتب ملفات في المشروع.
"""

import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

import app as app_module
from labor_market import analyze

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"
REAL_PROCESSED = analyze.PROCESSED_DIR
NA = "غير متاح"
PENDING = "تحت المعالجة"
PUBLIC_ADMIN = "الإدارة العامة والدفاع , الضمان الاجتماعي الالزامي"
LRI, PDI = "\u2066", "\u2069"

# البطاقات بترتيب ظهورها، وتسمياتها المختصرة (السنة والفترة في عنوان القسم).
Q1, Q2, CHANGE, RATE = "الربع الأول", "الربع الثاني", "التغير العددي", "نسبة التغير"
GROUPS = {
    "national": (slice(0, 4), [Q1, Q2, CHANGE, RATE]),
    "region": (slice(4, 8), [Q1, Q2, CHANGE, RATE]),
    "activity": (slice(8, 14), [Q1, Q2, CHANGE, RATE, Q1, Q2]),
    "pending": (slice(14, 18), ["عدد الربع الأول", "عدد الربع الثاني", "حصة الربع الأول", "حصة الربع الثاني"]),
}
TOTAL_CARDS = 18


# --- توقعات مستقلة ------------------------------------------------------------

def read_rows(name):
    with open(REAL_PROCESSED / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _val(text):
    return int(text) if text != "" else None


CELLS = {(r["region"], r["economic_activity"], int(r["quarter"])): _val(r["workers"])
         for r in read_rows("workers.csv")}
TOTALS = {(r["total_type"], r["name"], int(r["quarter"])): _val(r["value"])
          for r in read_rows("source_totals.csv")}


def count(v):
    return NA if v is None else f"{v:,}"


def signed(v):
    return NA if v is None else ("0" if v == 0 else f"{v:+,}")


def pct(x, sign=False):
    if x is None:
        return NA
    if 0 < abs(x) < 0.0001:  # قيمة متاحة أصغر من 0.01% لا تُعرض 0.00%
        return "أقل من 0.01%" + ((" (زيادة)" if x > 0 else " (انخفاض)") if sign else "")
    text = f"{x * 100:.2f}%"
    return "+" + text if sign and x > 0 else text


def ratio(num, den):
    return None if num is None or den in (None, 0) else num / den


def change(q1, q2):
    return None if q1 is None or q2 is None else q2 - q1


def four(q1, q2):
    ch = change(q1, q2)
    return [count(q1), count(q2), signed(ch), pct(ratio(ch, q1), sign=True)]


def expected_national():
    return four(TOTALS[("grand_total", "Grand Total", 1)], TOTALS[("grand_total", "Grand Total", 2)])


def expected_region(region):
    return four(TOTALS[("region", region, 1)], TOTALS[("region", region, 2)])


def expected_activity(region, activity):
    q1, q2 = CELLS[(region, activity, 1)], CELLS[(region, activity, 2)]
    d1, d2 = TOTALS[("region", region, 1)], TOTALS[("region", region, 2)]
    return four(q1, q2) + [pct(ratio(q1, d1)), pct(ratio(q2, d2))]


def expected_pending(region):
    q1, q2 = CELLS[(region, PENDING, 1)], CELLS[(region, PENDING, 2)]
    d1, d2 = TOTALS[("region", region, 1)], TOTALS[("region", region, 2)]
    return [count(q1), count(q2), pct(ratio(q1, d1)), pct(ratio(q2, d2))]


# --- أدوات الاختبار -----------------------------------------------------------

def cards(at, group):
    """قيم مجموعة بطاقات بعد التحقق من عدد البطاقات وتسمياتها المختصرة."""
    metrics = list(at.metric)
    assert len(metrics) == TOTAL_CARDS, [m.label for m in metrics]
    part, labels = GROUPS[group]
    assert [m.label for m in metrics[part]] == labels, (group, [m.label for m in metrics[part]])
    return [m.value for m in metrics[part]]


def visible_text(at):
    """كل نص ظاهر للمستخدم، دون كتلة CSS."""
    parts = [e.value for e in list(at.title) + list(at.subheader) + list(at.caption) + list(at.warning)
             + list(at.info) + list(at.error) + list(at.markdown) if not str(e.value).lstrip().startswith("<style>")]
    parts += [m.label for m in at.metric] + [m.value for m in at.metric] + [e.label for e in at.expander]
    return "\n".join(str(p) for p in parts)


def css(at):
    blocks = [m.value for m in at.markdown if str(m.value).lstrip().startswith("<style>")]
    assert len(blocks) == 1
    return blocks[0]


def chart_titles(at):
    return [json.loads(chart.proto.spec)["layout"]["title"]["text"] for chart in at.get("plotly_chart")]


def chart_trace_names(at, index):
    """أسماء سلاسل الرسم (محتوى البيانات، لا صياغة العنوان التي تملكها charts)."""
    spec = json.loads(at.get("plotly_chart")[index].proto.spec)
    return " ".join(str(trace.get("name", "")) for trace in spec["data"])


def page_markdown(at, needle):
    """أول عنصر Markdown ظاهر يحتوي النص، دون كتلة CSS."""
    return next(m.value for m in at.markdown
                if needle in str(m.value) and not str(m.value).lstrip().startswith("<style>"))


def tree_hashes(*roots):
    out = {}
    for root in roots:
        for path in sorted(Path(root).rglob("*")):
            if path.is_file():
                out[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


class AppCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def use_dir(self, path):
        patcher = mock.patch.object(analyze, "PROCESSED_DIR", Path(path))
        patcher.start()
        self.addCleanup(patcher.stop)

    def processed_copy(self):
        target = self.tmp / "processed"
        shutil.copytree(REAL_PROCESSED, target)
        self.use_dir(target)
        return target

    def run_app(self):
        at = AppTest.from_file(str(APP), default_timeout=60)
        return at.run()

    def assertNoException(self, at):
        self.assertEqual([e.value for e in at.exception], [])


class OpeningTest(AppCase):
    def setUp(self):
        super().setUp()
        self.at = self.run_app()

    def test_header_title_description_and_period(self):
        at = self.at
        self.assertNoException(at)
        self.assertEqual([t.value for t in at.title], ["مرصد سوق العمل السعودي"])
        header = page_markdown(at, "hero-sub")
        self.assertIn(app_module.SUBTITLE, header)
        self.assertIn("الربع الأول والثاني 2026", header)
        self.assertIn('dir="rtl"', header)
        self.assertEqual(len(at.error), 0)

    def test_sections_and_chart_subtabs(self):
        labels = [t.label for t in self.at.tabs]
        for label in ("نظرة عامة", "المناطق والأنشطة", "أعداد المناطق", "تغير المناطق", "أكبر الأنشطة"):
            self.assertIn(label, labels)
        self.assertEqual(len(labels), 5)
        subheaders = [s.value for s in self.at.subheader]
        self.assertIn("إجمالي المملكة — الربع الأول والثاني 2026", subheaders)
        self.assertIn("إجمالي نجران — الربع الأول والثاني 2026", subheaders)

    def test_all_cards_have_short_labels_without_repeated_year(self):
        labels = [m.label for m in self.at.metric]
        self.assertEqual(len(labels), TOTAL_CARDS)
        for label in labels:
            self.assertNotIn("2026", label)
            self.assertNotIn("Q1", label)
            self.assertNotIn("Q2", label)
            self.assertLessEqual(len(label), 16, label)
        for group in GROUPS:
            cards(self.at, group)

    def test_css_rtl_is_scoped_and_plotly_isolated(self):
        style = css(self.at)
        self.assertIn('[data-testid="stMainBlockContainer"]', style)
        self.assertIn("direction: rtl", style)
        # لا محدد عام «*» بمفرده؛ المحددات الفرعية داخل عنصر محدد (مثل بطاقة القيمة) مقبولة.
        self.assertNotRegex(style, r"(^|[,{}])\s*\*\s*[{,]")
        self.assertNotRegex(style, r"(^|\n)\s*(html|body)\b[^{]*\{[^}]*direction")
        self.assertRegex(style, r'\[data-testid="stPlotlyChart"\]\s*\{\s*direction:\s*ltr')
        self.assertRegex(style, r"unicode-bidi:\s*plaintext")
        self.assertNotIn("@import", style)
        self.assertNotIn("fonts.googleapis", style)

    def test_css_period_chip_spacing_and_rtl_dropdown_options(self):
        # التحقق البصري في المتصفح؛ هنا نحمي القاعدتين من الحذف أو الرجوع إلى محدد قديم.
        style = css(self.at)
        self.assertRegex(style, r"\.hero\s*\{[^}]*padding-bottom:\s*1rem")
        self.assertRegex(style, r'\[data-testid="stSelectboxVirtualDropdown"\] \[role="option"\]\s*\{[^}]*direction:\s*rtl')
        self.assertNotIn('data-baseweb="popover"', style)

    def test_defaults_are_najran_and_eastern(self):
        self.assertEqual(self.at.selectbox(key="region").value, "نجران")
        self.assertEqual(self.at.selectbox(key="compare_region").value, "الشرقية")

    def test_national_cards_match_independent_expectations(self):
        self.assertEqual(cards(self.at, "national"), expected_national())
        self.assertEqual(cards(self.at, "national")[2:], ["+40,680", "+0.30%"])

    def test_four_charts_in_expected_places(self):
        # عناوين الرسوم ملك charts وقد تتغير صياغتها؛ نتحقق من وجود الرسوم وترتيبها ومحتوى المقارنة.
        charts_ = self.at.get("plotly_chart")
        self.assertEqual([c.proto.id.rsplit("-", 1)[-1] for c in charts_],
                         ["chart_region_counts", "chart_region_changes", "chart_activity_counts",
                          "chart_region_comparison"])
        self.assertTrue(all(chart_titles(self.at)))
        names = chart_trace_names(self.at, 3)
        self.assertIn("نجران", names)
        self.assertIn("الشرقية", names)

    def test_charts_keep_their_own_template(self):
        for chart in self.at.get("plotly_chart"):
            self.assertNotEqual(chart.proto.theme, "streamlit")

    def test_default_region_activity_and_pending_cards(self):
        self.assertEqual(cards(self.at, "region"), expected_region("نجران"))
        self.assertEqual(cards(self.at, "pending"), expected_pending("نجران"))
        self.assertEqual(cards(self.at, "pending")[0], "39,535")
        self.assertEqual(self.at.selectbox(key="activity").value, "التشييد")
        self.assertEqual(cards(self.at, "activity"), expected_activity("نجران", "التشييد"))
        self.assertEqual(cards(self.at, "activity")[3], "+7.91%")

    def test_region_share_caption_isolates_percentages(self):
        caption = next(c.value for c in self.at.caption if "حصتها من إجمالي المملكة" in c.value)
        share_q1 = pct(ratio(TOTALS[("region", "نجران", 1)], TOTALS[("grand_total", "Grand Total", 1)]))
        share_q2 = pct(ratio(TOTALS[("region", "نجران", 2)], TOTALS[("grand_total", "Grand Total", 2)]))
        self.assertIn(f"{LRI}{share_q1}{PDI}", caption)
        self.assertIn(f"{LRI}{share_q2}{PDI}", caption)

    def test_pending_note_is_short_and_states_scope(self):
        text = visible_text(self.at)
        self.assertIn("غير محسوم", text)
        self.assertIn("مشمول في إجمالي المنطقة ومقام الحصص", text)

    def test_overview_text_states_national_scope(self):
        self.assertIn("مؤشرات المملكة كلها، ولا تتغير باختيار المنطقة", visible_text(self.at))

    def test_brief_limits_notice_is_visible_and_details_are_collapsible(self):
        notice = page_markdown(self.at, "حدود البيانات")
        self.assertIn("لا تقيس الشواغر", notice)
        self.assertIn("3 قيم فارغة", notice)
        self.assertEqual(len(self.at.expander), 1)
        expander = self.at.expander[0]
        self.assertIn("المصادر والمنهجية", expander.label)
        self.assertIn("3", expander.label)
        body = "\n".join(m.value for m in expander.markdown)
        for needle in ("وزارة الموارد البشرية والتنمية الاجتماعية", "open.data.gov.sa", "hrsd.gov.sa",
                       "لا تقيس الشواغر", PUBLIC_ADMIN, "لم تُعامل كأصفار"):
            self.assertIn(needle, body)

    def test_links_are_a_plain_markdown_list(self):
        body = "\n".join(m.value for m in self.at.expander[0].markdown)
        self.assertEqual(len(re.findall(r"(?m)^- \[[^\]]+\]\(https://", body)), 3)

    def test_no_internal_details_in_visible_text(self):
        text = re.sub(r"https?://\S+", "", visible_text(self.at))  # روابط المصدر مسموحة
        for banned in ("git", "Git", "unittest", ".csv", ".py", "data/", "data\\", "C:\\", "analyze", "charts",
                       "commit", "AppTest"):
            self.assertNotIn(banned, text)

    def test_no_nan_or_raw_fraction_text(self):
        text = visible_text(self.at)
        for bad in ("nan", "NaN", "<NA>", "None", "0.0029979", "0.002997"):
            self.assertNotIn(bad, text)


class InteractionTest(AppCase):
    def test_changing_region_updates_regional_cards_not_national(self):
        at = self.run_app()
        national_before = cards(at, "national")
        at.selectbox(key="region").select("الرياض").run()
        self.assertNoException(at)
        self.assertEqual(cards(at, "region"), expected_region("الرياض"))
        self.assertEqual(cards(at, "pending"), expected_pending("الرياض"))
        self.assertEqual(cards(at, "national"), national_before)
        self.assertEqual(cards(at, "region")[2:], ["-26,592", "-0.42%"])
        self.assertIn("إجمالي الرياض — الربع الأول والثاني 2026", [s.value for s in at.subheader])

    def test_changing_activity_updates_activity_cards(self):
        at = self.run_app()
        at.selectbox(key="activity").select("الصناعة التحويلية").run()
        self.assertNoException(at)
        self.assertEqual(cards(at, "activity"), expected_activity("نجران", "الصناعة التحويلية"))
        at.selectbox(key="region").select("الشرقية").run()
        self.assertEqual(cards(at, "activity"), expected_activity("الشرقية", "الصناعة التحويلية"))

    def test_changing_comparison_region_updates_comparison_chart(self):
        at = self.run_app()
        at.selectbox(key="compare_region").select("الرياض").run()
        self.assertNoException(at)
        self.assertIn("الرياض", chart_trace_names(at, 3))
        self.assertNotIn("الشرقية", chart_trace_names(at, 3))
        self.assertIn("حصص الأنشطة: نجران والرياض", [s.value for s in at.subheader])
        self.assertEqual(len(at.warning), 0)

    def test_same_region_comparison_shows_warning_and_no_comparison_chart(self):
        at = self.run_app()
        at.selectbox(key="compare_region").select("نجران").run()
        self.assertNoException(at)
        self.assertEqual(len(at.error), 0)
        self.assertEqual(len(at.warning), 1)
        self.assertIn("المنطقة نفسها", at.warning[0].value)
        self.assertEqual(len(chart_titles(at)), 3)
        self.assertEqual(cards(at, "region"), expected_region("نجران"))

    def test_missing_value_is_unavailable_never_zero(self):
        at = self.run_app()
        at.selectbox(key="region").select("الباحة").run()
        at.selectbox(key="activity").select(PUBLIC_ADMIN).run()
        self.assertNoException(at)
        expected = expected_activity("الباحة", PUBLIC_ADMIN)
        self.assertEqual(expected, [NA] * 6)
        self.assertEqual(cards(at, "activity"), expected)
        self.assertEqual(len(at.info), 1)
        self.assertIn("الفراغ لا يعني صفرًا", at.info[0].value)

    def test_partially_missing_activity_keeps_available_quarter(self):
        at = self.run_app()
        at.selectbox(key="activity").select(PUBLIC_ADMIN).run()
        values = cards(at, "activity")
        self.assertEqual(values, expected_activity("نجران", PUBLIC_ADMIN))
        self.assertEqual(values[:4], [NA, "2", NA, NA])
        self.assertEqual(values[4:], [NA, "أقل من 0.01%"])

    def test_every_region_opens_without_errors(self):
        at = self.run_app()
        for region in at.selectbox(key="region").options:
            at.selectbox(key="region").select(region).run()
            self.assertNoException(at)
            self.assertEqual(len(at.error), 0, region)
            self.assertEqual(cards(at, "region"), expected_region(region))
            self.assertEqual(cards(at, "pending"), expected_pending(region))

    def test_pending_is_not_an_activity_option(self):
        at = self.run_app()
        options = at.selectbox(key="activity").options
        self.assertEqual(len(options), 19)
        self.assertNotIn(PENDING, options)


class MissingOrCorruptDataTest(AppCase):
    def assertStopped(self, at, fragment):
        self.assertNoException(at)
        self.assertEqual(len(at.error), 1)
        self.assertIn(fragment, at.error[0].value)
        self.assertEqual(len(at.metric), 0)
        self.assertEqual(len(at.get("plotly_chart")), 0)
        self.assertEqual(len(at.selectbox), 0)
        self.assertEqual([t.value for t in at.title], ["مرصد سوق العمل السعودي"])
        for banned in ("Traceback", "C:\\", str(self.tmp)):
            self.assertNotIn(banned, at.error[0].value)

    def test_data_files_missing(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        self.use_dir(empty)
        self.assertStopped(self.run_app(), "غير موجودة")

    def test_data_directory_missing(self):
        self.use_dir(self.tmp / "does-not-exist")
        self.assertStopped(self.run_app(), "غير موجودة")

    def test_one_file_missing(self):
        target = self.processed_copy()
        (target / "source_totals.csv").unlink()
        self.assertStopped(self.run_app(), "غير موجودة")

    def test_duplicate_key_is_rejected_with_clear_message(self):
        target = self.processed_copy()
        lines = (target / "workers.csv").read_text(encoding="utf-8").splitlines(keepends=True)
        (target / "workers.csv").write_text("".join(lines + [lines[1]]), encoding="utf-8")
        self.assertStopped(self.run_app(), "غير صالحة")

    def test_missing_column_is_rejected(self):
        target = self.processed_copy()
        text = (target / "workers.csv").read_text(encoding="utf-8")
        (target / "workers.csv").write_text(text.replace("economic_activity", "activity", 1), encoding="utf-8")
        self.assertStopped(self.run_app(), "غير صالحة")

    def test_invalid_bytes_are_reported_as_corrupt(self):
        target = self.processed_copy()
        (target / "workers.csv").write_bytes(b"\xff\xfe\x00\x81\x82")
        self.assertStopped(self.run_app(), "تالفة")

    def test_empty_file_is_reported_as_corrupt(self):
        target = self.processed_copy()
        (target / "source_totals.csv").write_bytes(b"")
        self.assertStopped(self.run_app(), "تالفة")

    def test_non_numeric_value_is_rejected(self):
        target = self.processed_copy()
        text = (target / "workers.csv").read_text(encoding="utf-8")
        (target / "workers.csv").write_text(text.replace(",6569,", ",abc,", 1), encoding="utf-8")
        at = self.run_app()
        self.assertNoException(at)
        self.assertEqual(len(at.error), 1)
        self.assertEqual(len(at.metric), 0)


class FreshnessAndSideEffectsTest(AppCase):
    def test_cache_does_not_serve_stale_results_after_input_change(self):
        target = self.processed_copy()
        at = self.run_app()
        self.assertEqual(cards(at, "national")[1], "13,610,026")
        path = target / "source_totals.csv"
        text = path.read_text(encoding="utf-8")
        self.assertIn("Grand Total,13610026,", text)
        path.write_text(text.replace("Grand Total,13610026,", "Grand Total,13610027,", 1), encoding="utf-8")
        at.run()
        self.assertNoException(at)
        self.assertEqual(cards(at, "national")[1:3], ["13,610,027", "+40,681"])

    def test_opening_and_interacting_writes_no_files(self):
        data_dir = ROOT / "data"
        before = tree_hashes(data_dir)
        self.assertTrue(before)
        at = self.run_app()
        at.selectbox(key="region").select("الرياض").run()
        at.selectbox(key="activity").select("التعليم").run()
        at.selectbox(key="compare_region").select("نجران").run()
        self.assertEqual(tree_hashes(data_dir), before)

    def test_stale_analysis_files_are_not_used(self):
        # data/analysis قد يكون قديمًا؛ اللوحة تحسب من data/processed فقط.
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("data/analysis", source)
        self.assertNotIn("ANALYSIS_DIR", source)

    def test_independent_of_working_directory(self):
        cwd = os.getcwd()
        os.chdir(self.tmp)
        try:
            at = self.run_app()
        finally:
            os.chdir(cwd)
        self.assertNoException(at)
        self.assertEqual(cards(at, "national"), expected_national())


class ThemeTest(unittest.TestCase):
    def test_theme_matches_shared_appearance_agreement(self):
        with open(ROOT / ".streamlit" / "config.toml", "rb") as f:
            config = tomllib.load(f)
        self.assertEqual(set(config), {"theme"})  # إعداد المظهر فقط
        theme = config["theme"]
        self.assertEqual(theme["base"], "light")
        self.assertEqual(theme["backgroundColor"], "#F5F7FB")
        self.assertEqual(theme["secondaryBackgroundColor"], "#FFFFFF")
        self.assertEqual(theme["textColor"], "#12263A")
        self.assertEqual(theme["primaryColor"], "#0F766E")
        self.assertEqual(theme["greenColor"], "#0F766E")
        self.assertEqual(theme["redColor"], "#B45353")
        self.assertEqual([f.strip() for f in theme["font"].split(",")][:3], ["Segoe UI", "Tahoma", "Arial"])

    def test_css_uses_agreed_colors(self):
        for color in ("#F5F7FB", "#FFFFFF", "#12263A", "#64748B", "#0F766E", "#B45353"):
            self.assertIn(color, app_module.RTL_CSS)


class FormattingTest(unittest.TestCase):
    def test_count_and_signed(self):
        self.assertEqual(app_module.fmt_count(13569346), "13,569,346")
        self.assertEqual(app_module.fmt_count(None), NA)
        self.assertEqual(app_module.fmt_count(float("nan")), NA)
        self.assertEqual(app_module.fmt_signed(40680), "+40,680")
        self.assertEqual(app_module.fmt_signed(-26592), "-26,592")
        self.assertEqual(app_module.fmt_signed(0), "0")
        self.assertEqual(app_module.fmt_signed(None), NA)

    def test_percent_is_converted_exactly_once(self):
        self.assertEqual(app_module.fmt_percent(0.0029979337), "0.30%")
        self.assertEqual(app_module.fmt_percent(0.3117), "31.17%")
        self.assertEqual(app_module.fmt_percent(1.0), "100.00%")
        self.assertEqual(app_module.fmt_percent(0.0), "0.00%")
        self.assertEqual(app_module.fmt_percent(0.0029979337, signed=True), "+0.30%")
        self.assertEqual(app_module.fmt_percent(-0.0042, signed=True), "-0.42%")
        self.assertEqual(app_module.fmt_percent(float("nan")), NA)
        self.assertEqual(app_module.fmt_percent(None), NA)

    def test_tiny_percent_is_not_shown_as_zero(self):
        self.assertEqual(app_module.fmt_percent(0.0000075), "أقل من 0.01%")
        self.assertEqual(app_module.fmt_percent(0.0000075, signed=True), "أقل من 0.01% (زيادة)")
        self.assertEqual(app_module.fmt_percent(-0.0000075, signed=True), "أقل من 0.01% (انخفاض)")

    def test_sign_stays_with_number_in_values(self):
        # الإشارة جزء من نص القيمة قبل الرقم؛ العرض LTR يتم عبر CSS أو عزل LRI/PDI لا بتغيير القيمة.
        self.assertTrue(app_module.fmt_signed(40680).startswith("+"))
        self.assertTrue(app_module.fmt_percent(0.003, signed=True).startswith("+"))
        self.assertEqual(app_module.ltr("+0.30%"), f"{LRI}+0.30%{PDI}")

    def test_direction_for_coloring_only(self):
        self.assertEqual(app_module.direction_of(40680), "up")
        self.assertEqual(app_module.direction_of(-1), "down")
        self.assertEqual(app_module.direction_of(0), "flat")
        self.assertEqual(app_module.direction_of(None), "na")
        self.assertEqual(app_module.direction_of(float("nan")), "na")


if __name__ == "__main__":
    unittest.main()
