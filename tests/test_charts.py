"""اختبارات مستقلة لسلاسل Plotly من جداول صغيرة، دون استيراد analyze."""

import json
import unittest

import pandas as pd
import plotly.graph_objects as go
from pandas.testing import assert_frame_equal

from labor_market.charts import (
    make_activity_counts,
    make_region_activity_comparison,
    make_region_changes,
    make_region_counts,
)


def row(q1, q2, change, rate, share1, share2, **labels):
    return dict(year=2026, workers_q1=q1, workers_q2=q2, change=change,
                change_rate=rate, share_q1=share1, share_q2=share2, **labels)


def regions():
    return pd.DataFrame([
        row(1000, 1200, 200, .2, .1, .12, region="نجران"),
        row(3000, 2700, -300, -.1, .3, .27, region="الشرقية"),
        row(500, 500, 0, 0, .05, .05, region="الباحة"),
        row(pd.NA, pd.NA, pd.NA, pd.NA, pd.NA, pd.NA, region="الجوف"),
    ])


LONG_NAME = "إمدادات المياه وأنشطة الصرف الصحي وإدارة النفايات ومعالجتها"


def activities():
    return pd.DataFrame([
        row(400, 500, 100, .25, .04, .05, economic_activity="نشاط ب", is_pending=False),
        row(300, 450, 150, .5, .03, .045, economic_activity=LONG_NAME, is_pending=False),
        row(8000, 9000, 1000, .125, .8, .9, economic_activity="تحت المعالجة", is_pending=True),
        row(200, 500, 300, 1.5, .02, .05, economic_activity="نشاط أ", is_pending=False),
        row(pd.NA, pd.NA, pd.NA, pd.NA, pd.NA, pd.NA, economic_activity="نشاط مفقود", is_pending=False),
    ])


def region_activities():
    return pd.DataFrame([
        row(40, 50, 10, .25, .04, .05, region="نجران", economic_activity="التعليم", is_pending=False),
        row(100, 200, 100, 1, .1, .2, region="نجران", economic_activity="التشييد", is_pending=False),
        row(500, 600, 100, .2, .5, .6, region="نجران", economic_activity="تحت المعالجة", is_pending=True),
        row(100, 120, 20, .2, .05, .06, region="الشرقية", economic_activity="التعليم", is_pending=False),
        row(150, 200, 50, 1/3, .075, .1, region="الشرقية", economic_activity="التشييد", is_pending=False),
        row(1200, 1600, 400, 1/3, .6, .8, region="الشرقية", economic_activity="تحت المعالجة", is_pending=True),
        row(100, 150, 50, .5, .1, .15, region="الرياض", economic_activity="التعليم", is_pending=False),
        row(50, 100, 50, 1, .05, .1, region="الرياض", economic_activity="التشييد", is_pending=False),
    ])


def notes(fig):
    return " ".join(a.text.replace("<br>", " ") for a in fig.layout.annotations or ())


# قيم التحويم معزولة الاتجاه: الرقم مع إشارته و% داخل LRI…PDI، والنص العربي داخل RLI…PDI.
LRI, RLI, PDI = "⁦", "⁧", "⁩"
NA = RLI + "غير متاح" + PDI


def ltr(text):
    return LRI + text + PDI


def rtl(text):
    return RLI + text + PDI


def plain(text):
    return "".join(ch for ch in text if ch not in (LRI, RLI, PDI))


def hover_lines(trace):
    template = trace.hovertemplate
    assert template.endswith("<extra></extra>"), template
    return template[:-len("<extra></extra>")].split("<br>")


class RegionCountsTest(unittest.TestCase):
    def test_values_order_periods_and_number_format(self):
        fig = make_region_counts(regions())
        self.assertIsInstance(fig, go.Figure)
        self.assertEqual(len(fig.data), 2)
        self.assertEqual(list(fig.data[0].y), ["الشرقية", "نجران", "الباحة", "الجوف"])
        self.assertEqual(list(fig.data[0].x), [3000, 1000, 500, None])
        self.assertEqual(list(fig.data[1].x), [2700, 1200, 500, None])
        self.assertEqual(fig.data[0].name, "الربع الأول")
        self.assertEqual(fig.data[1].name, "الربع الثاني")
        self.assertIn("2026", fig.layout.title.text)
        self.assertEqual(fig.data[0].customdata[0][1], ltr("3,000"))
        self.assertEqual(fig.layout.xaxis.tickformat, ",.0f")
        self.assertTrue(all(trace.orientation == "h" for trace in fig.data))

    def test_nullable_integer_missing_is_not_zero(self):
        frame = regions().astype({"workers_q1": "Int64", "workers_q2": "Int64"})
        fig = make_region_counts(frame)
        self.assertIsNone(fig.data[0].x[-1])
        self.assertEqual(fig.data[0].customdata[-1][1], NA)
        self.assertIn("غير متاح", notes(fig))
        self.assertIn("الجوف", notes(fig))
        self.assertIn("الربع الأول", notes(fig))
        self.assertIn("الربع الثاني", notes(fig))
        self.assertIsNone(json.loads(fig.to_json())["data"][0]["x"][-1])


class RegionChangesTest(unittest.TestCase):
    def test_change_values_sort_colors_zero_line_and_hover(self):
        fig = make_region_changes(regions())
        trace = fig.data[0]
        self.assertEqual(list(trace.y), ["الشرقية", "الباحة", "نجران", "الجوف"])
        self.assertEqual(list(trace.x), [-300, 0, 200, None])
        self.assertEqual(list(trace.marker.color), ["#B45353", "#64748B", "#0F766E", "#64748B"])
        self.assertTrue(any(s.x0 == s.x1 == 0 for s in fig.layout.shapes))
        # التغير ونسبته موقعان في التحويم؛ الصفر بلا إشارة والمفقود «غير متاح».
        self.assertEqual([row[1] for row in trace.customdata], [ltr("−300"), ltr("0"), ltr("+200"), NA])
        self.assertEqual([row[2] for row in trace.customdata], [ltr("−10.0%"), ltr("0.0%"), ltr("+20.0%"), NA])
        self.assertEqual([row[3] for row in trace.customdata], [ltr("3,000"), ltr("500"), ltr("1,000"), NA])
        self.assertEqual([row[4] for row in trace.customdata], [ltr("2,700"), ltr("500"), ltr("1,200"), NA])
        self.assertIn("مقام", notes(fig))
        self.assertIn("الربع الأول", notes(fig))
        self.assertIn("إلى الثاني", fig.layout.title.text)
        self.assertIn("الربع الأول", trace.hovertemplate)
        self.assertIn("الربع الثاني", trace.hovertemplate)

    def test_uses_supplied_change_and_rate_without_recalculating(self):
        frame = regions()
        # Sentinels isolate the chart boundary from any hypothetical calculation.
        frame.loc[frame.region == "نجران", ["change", "change_rate"]] = [17, .123]
        fig = make_region_changes(frame)
        trace = fig.data[0]
        idx = list(trace.y).index("نجران")
        self.assertEqual(trace.x[idx], 17)
        self.assertEqual(trace.customdata[idx][1], ltr("+17"))
        self.assertEqual(trace.customdata[idx][2], ltr("+12.3%"))

    def test_missing_change_and_missing_rate_remain_unavailable(self):
        frame = regions()
        frame.loc[frame.region == "نجران", "change_rate"] = float("nan")
        fig = make_region_changes(frame)
        idx = list(fig.data[0].y).index("نجران")
        self.assertEqual(fig.data[0].customdata[idx][2], NA)
        self.assertEqual(fig.data[0].customdata[idx][1], ltr("+200"))
        self.assertIsNone(fig.data[0].x[-1])
        self.assertEqual(fig.data[0].customdata[-1][1:3], [NA, NA])
        self.assertIn("الجوف", notes(fig))


class ActivityCountsTest(unittest.TestCase):
    def test_top_n_order_ties_period_and_pending_exclusion(self):
        fig = make_activity_counts(activities(), top_n=2)
        self.assertEqual(list(fig.data[0].y), ["نشاط أ", "نشاط ب"])
        self.assertEqual(list(fig.data[0].x), [500, 500])
        self.assertNotIn("تحت المعالجة", fig.data[0].y)
        self.assertIn("مستبعد من العرض", notes(fig))
        self.assertIn("تحت المعالجة", notes(fig))
        self.assertEqual(fig.data[0].name, "الربع الثاني")
        self.assertIn("2026", fig.layout.title.text)

    def test_long_source_names_wrapped_and_missing_kept(self):
        fig = make_activity_counts(activities())
        self.assertEqual(list(fig.data[0].y), ["نشاط أ", "نشاط ب", LONG_NAME, "نشاط مفقود"])
        self.assertEqual(list(fig.data[0].x), [500, 500, 450, None])
        idx = list(fig.layout.yaxis.tickvals).index(LONG_NAME)
        self.assertIn("<br>", fig.layout.yaxis.ticktext[idx])
        self.assertEqual(fig.layout.yaxis.ticktext[idx].replace("<br>", " "), LONG_NAME)
        self.assertEqual(fig.data[0].customdata[idx][0], LONG_NAME)
        self.assertLessEqual(fig.layout.margin.l, 40)
        self.assertLessEqual(fig.layout.margin.r, 180)
        self.assertIn("نشاط مفقود", notes(fig))

    def test_share_is_percentage_with_national_denominator(self):
        fig = make_activity_counts(activities())
        self.assertEqual(fig.data[0].customdata[0][2], ltr("5.0%"))
        self.assertIn("مصدر المملكة", notes(fig))
        self.assertIn("يشمل تصنيف تحت المعالجة", notes(fig))
        self.assertIn("إجمالي مصدر المملكة", fig.data[0].hovertemplate)

    def test_all_pending_returns_figure_with_explanation(self):
        fig = make_activity_counts(activities().query("is_pending"))
        self.assertEqual(list(fig.data[0].x), [])
        self.assertIn("لا توجد أنشطة", notes(fig))

    def test_invalid_top_n_fails_clearly(self):
        for value in (0, -1, True, 1.5, "2"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "top_n"):
                make_activity_counts(activities(), value)


class RegionActivityComparisonTest(unittest.TestCase):
    def test_default_regions_values_order_and_denominators(self):
        fig = make_region_activity_comparison(region_activities())
        self.assertEqual(len(fig.data), 2)
        self.assertEqual(list(fig.data[0].y), ["التشييد", "التعليم"])
        self.assertEqual(list(fig.data[0].x), [.2, .05])
        self.assertEqual(list(fig.data[1].x), [.1, .06])
        self.assertIn("نجران", fig.data[0].name)
        self.assertIn("الشرقية", fig.data[1].name)
        self.assertEqual([t.name for t in fig.data], ["نجران", "الشرقية"])
        self.assertIn("الربع الثاني", fig.layout.title.text)
        self.assertEqual(fig.layout.xaxis.tickformat, ".0%")
        self.assertEqual(fig.data[0].customdata[1][1], ltr("5.0%"))
        self.assertIn("إجمالي مصدر كل منطقة", notes(fig))
        self.assertIn("يشمل تصنيف تحت المعالجة", notes(fig))
        self.assertIn("مستبعد من العرض", notes(fig))
        for trace in fig.data:
            self.assertNotIn("تحت المعالجة", trace.y)
            self.assertIn("المقام: إجمالي مصدر المنطقة", trace.hovertemplate)

    def test_custom_regions_exclude_unselected_and_do_not_normalize(self):
        fig = make_region_activity_comparison(region_activities(), "الرياض", "نجران")
        self.assertIn("الرياض", fig.data[0].name)
        self.assertIn("نجران", fig.data[1].name)
        self.assertEqual(list(fig.data[0].x), [.1, .15])
        self.assertEqual(list(fig.data[1].x), [.2, .05])
        self.assertNotIn("الشرقية", fig.layout.title.text)

    def test_missing_share_and_absent_activity_do_not_become_zero(self):
        frame = region_activities()
        frame.loc[(frame.region == "نجران") & (frame.economic_activity == "التعليم"), "share_q2"] = pd.NA
        frame = frame.loc[~((frame.region == "الشرقية") & (frame.economic_activity == "التشييد"))]
        fig = make_region_activity_comparison(frame)
        self.assertEqual(list(fig.data[0].x), [.2, None])
        self.assertEqual(list(fig.data[1].x), [None, .06])
        self.assertEqual(fig.data[0].customdata[1][1], NA)
        self.assertIn("غير متاح", notes(fig))
        self.assertIn("نجران", notes(fig))
        self.assertIn("الشرقية", notes(fig))
        self.assertIn("التعليم", notes(fig))
        self.assertIn("التشييد", notes(fig))

    def test_nullable_shares_and_all_missing_activity_are_preserved(self):
        frame = region_activities().astype({"share_q2": "Float64"})
        frame.loc[frame.economic_activity == "التعليم", "share_q2"] = pd.NA
        fig = make_region_activity_comparison(frame)
        self.assertEqual(list(fig.data[0].y), ["التشييد", "التعليم"])
        self.assertEqual(list(fig.data[0].x), [.2, None])
        self.assertEqual(list(fig.data[1].x), [.1, None])
        self.assertEqual(fig.data[0].customdata[1][1], NA)
        self.assertIn("التعليم", notes(fig))
        self.assertIsNone(json.loads(fig.to_json())["data"][1]["x"][1])

    def test_unavailable_region_and_same_region_fail_clearly(self):
        with self.assertRaisesRegex(ValueError, "غير موجودة"):
            make_region_activity_comparison(region_activities(), "الجوف", "نجران")
        with self.assertRaisesRegex(ValueError, "مختلفتين"):
            make_region_activity_comparison(region_activities(), "نجران", "نجران")

    def test_input_row_order_does_not_change_series(self):
        frame = region_activities()
        first = make_region_activity_comparison(frame)
        second = make_region_activity_comparison(frame.iloc[::-1])
        self.assertEqual(first.to_json(), second.to_json())


class InputContractTest(unittest.TestCase):
    def test_functions_leave_input_unchanged(self):
        for function, frame in [(make_region_counts, regions()), (make_region_changes, regions()),
                                (make_activity_counts, activities()), (make_region_activity_comparison, region_activities())]:
            with self.subTest(function=function.__name__):
                before = frame.copy(deep=True)
                self.assertIsInstance(function(frame), go.Figure)
                assert_frame_equal(frame, before)

    def test_required_columns_empty_and_multiple_years(self):
        with self.assertRaisesRegex(ValueError, "share_q2"):
            make_region_counts(regions().drop(columns="share_q2"))
        with self.assertRaisesRegex(ValueError, "فارغ"):
            make_activity_counts(activities().iloc[:0])
        frame = regions()
        frame.loc[0, "year"] = 2025
        with self.assertRaisesRegex(ValueError, "سنة واحدة"):
            make_region_counts(frame)

    def test_duplicate_keys_and_unknown_pending_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "مكررة"):
            make_region_activity_comparison(pd.concat([region_activities(), region_activities().iloc[:1]]))
        frame = activities().astype({"is_pending": "boolean"})
        frame.loc[0, "is_pending"] = pd.NA
        with self.assertRaisesRegex(ValueError, "is_pending"):
            make_activity_counts(frame)


class PresentationTest(unittest.TestCase):
    def test_palette_white_background_font_and_responsive_size(self):
        for function, frame in [(make_region_counts, regions()), (make_region_changes, regions()),
                                (make_activity_counts, activities()), (make_region_activity_comparison, region_activities())]:
            with self.subTest(function=function.__name__):
                fig = function(frame)
                self.assertEqual(fig.layout.paper_bgcolor, "white")
                self.assertEqual(fig.layout.plot_bgcolor, "white")
                self.assertEqual(fig.layout.font.color, "#12263A")
                self.assertEqual(fig.layout.font.family, "Segoe UI, Tahoma, Arial, sans-serif")
                self.assertTrue(fig.layout.autosize)
                self.assertIsNone(fig.layout.width)
                self.assertFalse(fig.layout.yaxis.title.text)
                self.assertLessEqual(fig.layout.margin.l, 40)
                self.assertFalse(fig.layout.margin.autoexpand)
                self.assertEqual(fig.layout.xaxis.gridcolor, "#E2E8F0")
        counts = make_region_counts(regions())
        self.assertEqual([trace.marker.color for trace in counts.data], ["#64748B", "#0F766E"])

    def test_short_titles_and_legends_do_not_repeat_periods(self):
        counts = make_region_counts(regions())
        comparison = make_region_activity_comparison(region_activities())
        self.assertEqual(counts.layout.title.text.split("<br>")[0], "العاملون حسب المنطقة")
        self.assertEqual(comparison.layout.title.text.split("<br>")[0], "حصص الأنشطة داخل المنطقتين")
        self.assertFalse(counts.layout.legend.title.text)
        self.assertEqual(counts.layout.legend.xref, "container")
        self.assertEqual(comparison.layout.legend.y, 1)
        self.assertEqual([trace.name for trace in comparison.data], ["نجران", "الشرقية"])
        self.assertNotIn("Q1", counts.layout.title.text)
        self.assertNotIn("Q2", comparison.layout.title.text)
        self.assertEqual(comparison.layout.title.text.count("الربع الثاني"), 1)

    def test_million_axis_keeps_raw_series_and_exact_hover_counts(self):
        frame = regions()
        frame.loc[frame.region == "الشرقية", ["workers_q1", "workers_q2"]] = [3_200_005, 3_700_011]
        fig = make_region_counts(frame)
        self.assertEqual(fig.data[0].x[0], 3_200_005)
        self.assertEqual(fig.data[1].x[0], 3_700_011)
        self.assertEqual(fig.data[1].customdata[0][1], ltr("3,700,011"))
        self.assertEqual(fig.layout.xaxis.title.text, "مليون عامل")
        self.assertEqual(fig.layout.xaxis.tickmode, "array")
        self.assertIn(1_000_000, fig.layout.xaxis.tickvals)
        self.assertIn("1", fig.layout.xaxis.ticktext)

    def test_signed_changes_have_arrows_patterns_and_unavailable_is_not_zero(self):
        fig = make_region_changes(regions())
        trace = fig.data[0]
        # التسمية تحت اسم المنطقة بلون العمود، ولا نص على الأعمدة يضيق عنه العمود القصير.
        ticks = dict(zip(fig.layout.yaxis.tickvals, fig.layout.yaxis.ticktext))
        for name, label, color in [("الشرقية", "↓ −300", "#B45353"), ("الباحة", "0", "#64748B"),
                                   ("نجران", "↑ +200", "#0F766E"), ("الجوف", "غير متاح", "#64748B")]:
            self.assertEqual(ticks[name], f'{name}<br><span style="color:{color}">{label}</span>')
        self.assertIsNone(trace.text)
        self.assertIsNone(trace.textposition)
        self.assertEqual(list(trace.marker.pattern.shape), ["\\", "", "/", ""])
        self.assertEqual(list(trace.x), [-300, 0, 200, None])
        self.assertEqual(fig.layout.shapes[0].line.color, "#12263A")
        self.assertIn("−", " ".join(fig.layout.xaxis.ticktext))
        self.assertIn("+", " ".join(fig.layout.xaxis.ticktext))

    def test_small_available_shares_are_not_displayed_as_zero(self):
        frame = region_activities()
        idx = (frame.region == "نجران") & (frame.economic_activity == "التعليم")
        frame.loc[idx, "share_q2"] = 2 / 264876
        frame.loc[idx, "workers_q2"] = 2
        fig = make_region_activity_comparison(frame)
        trace = fig.data[0]
        position = list(trace.y).index("التعليم")
        self.assertEqual(trace.x[position], 2 / 264876)
        self.assertEqual(trace.customdata[position][1], ltr("0.0008%"))
        self.assertEqual(trace.customdata[position][2], ltr("2"))
        frame.loc[idx, "share_q2"] = 1e-12
        smaller = make_region_activity_comparison(frame)
        # النص العربي RTL والرقم داخله LTR، فلا تنفصل % عن الرقم.
        self.assertEqual(smaller.data[0].customdata[position][1], rtl("أقل من " + ltr("0.0001%")))

    def test_comparison_uses_distinct_symbols_and_keeps_every_named_activity(self):
        fig = make_region_activity_comparison(region_activities())
        self.assertEqual([trace.type for trace in fig.data], ["scatter", "scatter"])
        self.assertEqual([trace.marker.symbol for trace in fig.data], ["circle", "diamond"])
        self.assertEqual(set(fig.data[0].y), {"التعليم", "التشييد"})
        self.assertEqual(set(fig.data[1].y), {"التعليم", "التشييد"})

    def test_long_hover_names_wrap_without_losing_original_keys(self):
        activity_frame = activities()
        comparison_frame = region_activities()
        comparison_frame.loc[comparison_frame.economic_activity == "التعليم", "economic_activity"] = LONG_NAME
        for fig in [make_activity_counts(activity_frame), make_region_activity_comparison(comparison_frame)]:
            with self.subTest(title=fig.layout.title.text):
                trace = fig.data[0]
                position = list(trace.y).index(LONG_NAME)
                self.assertEqual(trace.customdata[position][0], LONG_NAME)
                wrapped = trace.customdata[position][3]
                self.assertIn("<br>", wrapped)
                # كل سطر من الاسم يُغلق عزله ويُفتح من جديد؛ دون حذف أو تغيير في الاسم.
                self.assertEqual(wrapped.count("<br>"), wrapped.count(PDI + "<br>" + RLI))
                self.assertEqual(plain(wrapped).replace("<br>", " "), LONG_NAME)
                self.assertIn(rtl("النشاط: %{customdata[3]}"), trace.hovertemplate)
                self.assertIn("<br>" + rtl("(يشمل تحت المعالجة)"), trace.hovertemplate)

    def test_header_reserves_space_for_two_legend_rows(self):
        frame = region_activities().replace({"نجران": "الحدود الشمالية", "الشرقية": "مكة المكرمة"})
        fig = make_region_activity_comparison(frame, "الحدود الشمالية", "مكة المكرمة")
        self.assertGreaterEqual(fig.layout.margin.t, 110)
        self.assertEqual(fig.layout.title.yref, "container")
        self.assertEqual(fig.layout.title.yanchor, "top")
        self.assertEqual(fig.layout.legend.yanchor, "bottom")
        self.assertEqual(fig.layout.legend.entrywidthmode, "fraction")
        self.assertEqual([trace.name for trace in fig.data], ["الحدود الشمالية", "مكة المكرمة"])

    def test_large_signed_labels_are_short_and_exact_counts_remain_in_hover(self):
        frame = regions()
        frame.loc[frame.region == "نجران", ["region", "change"]] = ["مكة المكرمة", 26013]
        frame.loc[frame.region == "الشرقية", "change"] = -26592
        frame.loc[frame.region == "الباحة", "change"] = 18646  # عمود أقصر من نصه على الجوال سابقًا
        fig = make_region_changes(frame)
        trace = fig.data[0]
        ticks = dict(zip(fig.layout.yaxis.tickvals, fig.layout.yaxis.ticktext))
        for name, value, label, count in [("مكة المكرمة", 26013, "↑ +26.0 ألف", "+26,013"),
                                         ("الباحة", 18646, "↑ +18.6 ألف", "+18,646"),
                                         ("الشرقية", -26592, "↓ −26.6 ألف", "−26,592")]:
            idx = list(trace.y).index(name)
            self.assertEqual(trace.x[idx], value)
            self.assertEqual(ticks[name].split("<br>")[1].split(">")[1].split("<")[0], label)
            self.assertEqual(trace.customdata[idx][1], ltr(count))
        self.assertIsNone(trace.text)

    def test_value_labels_in_name_column_add_row_height_not_bar_text(self):
        fig = make_region_changes(regions())
        counts = make_region_counts(regions())
        self.assertTrue(all(label.count("<br>") == 1 for label in fig.layout.yaxis.ticktext))
        # الهامش الأيمن لعمود الأسماء ثابت بالبكسل، فلا يعتمد مكان التسمية على طول العمود.
        self.assertEqual(fig.layout.margin.r, counts.layout.margin.r)
        self.assertEqual(list(fig.layout.yaxis.tickvals), list(fig.data[0].y))

    def test_comparison_full_width_rows_show_tiny_zero_and_missing_shares(self):
        frame = region_activities()
        frame.loc[(frame.region == "نجران") & (frame.economic_activity == "التعليم"), "share_q2"] = 2 / 264876
        frame.loc[(frame.region == "الشرقية") & (frame.economic_activity == "التعليم"), "share_q2"] = pd.NA
        frame.loc[(frame.region == "نجران") & (frame.economic_activity == "التشييد"), "share_q2"] = 0
        fig = make_region_activity_comparison(frame)
        self.assertLessEqual(fig.layout.margin.r, 24)
        self.assertFalse(fig.layout.yaxis.showticklabels)
        labels = {a.y: a.text for a in fig.layout.annotations if a.yref == "y"}
        self.assertEqual(set(labels), {"التعليم", "التشييد"})
        self.assertIn("0.0008%", labels["التعليم"])
        self.assertIn("غير متاح", labels["التعليم"])
        self.assertIn("0.0%", labels["التشييد"])
        self.assertIn("●", labels["التعليم"])
        self.assertIn("◆", labels["التعليم"])
        self.assertEqual(list(fig.data[0].x), [0, 2 / 264876])
        self.assertEqual(list(fig.data[1].x), [.1, None])
        self.assertEqual(fig.layout.xaxis.type, None)  # لا مقياس لوغاريتمي أو كسر للمحور.

    def test_footnotes_use_isolated_arabic_lines_without_fragile_punctuation(self):
        for fig in [make_region_changes(regions()), make_activity_counts(activities()),
                    make_region_activity_comparison(region_activities())]:
            footers = [a.text for a in fig.layout.annotations if a.yref == "paper"]
            self.assertTrue(footers)
            for footer in footers:
                for line in footer.split("<br>"):
                    self.assertTrue(line.startswith("\u2067"))
                    self.assertTrue(line.endswith("\u2069"))
                for char in ("«", "»", "؛"):
                    self.assertNotIn(char, footer)
        self.assertIn("معنى هذا التصنيف غير محسوم", notes(make_activity_counts(activities())))

    def test_heights_follow_rows_and_full_wrapped_labels_without_large_minimum(self):
        short = make_region_counts(regions().iloc[:1])
        extra = regions().copy()
        extra["region"] = extra["region"] + " إضافية"
        longer = make_region_counts(pd.concat([regions(), extra], ignore_index=True))
        self.assertLess(short.layout.height, longer.layout.height)
        self.assertLessEqual(short.layout.height, 320)
        fig = make_activity_counts(activities())
        self.assertEqual(set(fig.layout.yaxis.tickvals), set(fig.data[0].y))
        for original, displayed in zip(fig.layout.yaxis.tickvals, fig.layout.yaxis.ticktext):
            self.assertEqual(displayed.replace("<br>", " "), original)


class HoverDirectionTest(unittest.TestCase):
    """SVG الرسم LTR؛ دون عزل تنتقل % إلى طرف السطر ويظهر السالب بعد الرقم."""

    def figures(self):
        return [make_region_counts(regions()), make_region_changes(regions()),
                make_activity_counts(activities()), make_region_activity_comparison(region_activities())]

    def test_every_hover_line_is_an_isolated_rtl_line_aligned_right(self):
        for fig in self.figures():
            self.assertEqual(fig.layout.hoverlabel.align, "right")
            for trace in fig.data:
                with self.subTest(title=fig.layout.title.text, trace=trace.name):
                    for line in hover_lines(trace):
                        self.assertTrue(line.startswith(RLI), line)
                        self.assertTrue(line.endswith(PDI), line)

    def test_every_hover_value_is_one_isolated_segment(self):
        number = r"⁦[+−]?\d[\d,.]*%?⁩"
        for fig in self.figures():
            for trace in fig.data:
                values = [cell for row in trace.customdata for cell in row[1:3]]
                if trace.name == "التغير العددي":
                    values += [cell for row in trace.customdata for cell in row[3:5]]
                with self.subTest(title=fig.layout.title.text, trace=trace.name):
                    self.assertTrue(values)
                    for value in values:
                        if value != NA:
                            self.assertRegex(value, "^" + number + "$")

    def test_signed_change_rate_and_tiny_rate_keep_sign_with_number(self):
        frame = regions()
        frame.loc[frame.region == "نجران", "change_rate"] = 1e-9
        frame.loc[frame.region == "الشرقية", "change_rate"] = -1e-9
        trace = make_region_changes(frame).data[0]
        rates = dict(zip(trace.y, (row[2] for row in trace.customdata)))
        self.assertEqual(rates["نجران"], rtl("أقل من " + ltr("0.0001%") + " (زيادة)"))
        self.assertEqual(rates["الشرقية"], rtl("أقل من " + ltr("0.0001%") + " (انخفاض)"))
        self.assertEqual(rates["الباحة"], ltr("0.0%"))

    def test_comparison_row_labels_isolate_each_share(self):
        frame = region_activities()
        frame.loc[(frame.region == "نجران") & (frame.economic_activity == "التعليم"), "share_q2"] = 2 / 264876
        frame.loc[(frame.region == "الشرقية") & (frame.economic_activity == "التعليم"), "share_q2"] = pd.NA
        fig = make_region_activity_comparison(frame)
        labels = {a.y: a.text for a in fig.layout.annotations if a.yref == "y"}
        self.assertTrue(labels["التعليم"].endswith(f"● {ltr('0.0008%')}   ◆ {NA}"))


if __name__ == "__main__":
    unittest.main()
