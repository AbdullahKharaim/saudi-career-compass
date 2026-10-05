"""لوحة «مرصد سوق العمل السعودي» المحلية (عرض فقط).

التشغيل من جذر المشروع:
    .venv\\Scripts\\python.exe -m streamlit run app.py --server.address 127.0.0.1

القيم والتغيرات والحصص تأتي من labor_market.analyze.build_analysis، والرسوم من
labor_market.charts. هذا الملف يختار ويعرض وينسّق فقط، ولا يكتب أي ملف.
المظهر: .streamlit/config.toml (الألوان والخط) وRTL_CSS أدناه (التخطيط والاتجاه).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from labor_market import analyze, charts  # noqa: E402

TITLE = "مرصد سوق العمل السعودي"
SUBTITLE = "مقارنة أعداد العاملين في القطاع الخاص بين ربعين، حسب المنطقة الإدارية والنشاط الاقتصادي."
NA = "غير متاح"
PENDING_NAME = "تحت المعالجة"
DEFAULT_REGION = "نجران"
DEFAULT_COMPARE_REGION = "الشرقية"
INPUT_FILES = ("workers.csv", "source_totals.csv")

# تسميات البطاقات مختصرة؛ السنة والفترة تُذكران مرة في عنوان القسم.
Q1, Q2, CHANGE, RATE = "الربع الأول", "الربع الثاني", "التغير العددي", "نسبة التغير"

SOURCE_LINKS = (
    ("فهرس البيانات المفتوحة في الوزارة",
     "https://www.hrsd.gov.sa/knowledge-centre/data-and-statistics/open-data/758917"),
    ("بيانات الربع الأول 2026",
     "https://open.data.gov.sa/ar/datasets/view/3f25d48e-f3c4-4c02-847e-0ce6e14b6d5b"),
    ("بيانات الربع الثاني 2026",
     "https://open.data.gov.sa/ar/datasets/view/11d328f2-7c11-4a26-8bcd-e8f6bef5f706"),
)

# الاتجاه يُضبط على حاوية المحتوى وعناصر بعينها، لا على كل العناصر؛
# ورسوم Plotly تبقى معزولة باتجاهها الافتراضي.
RTL_CSS = """
<style>
:root {
  --page: #F5F7FB; --card: #FFFFFF; --text: #12263A; --muted: #64748B;
  --primary: #0F766E; --up: #0F766E; --down: #B45353; --line: #E2E8F0;
  --pending: #F1F5F9;
}
.block-container, [data-testid="stMainBlockContainer"] {
  direction: rtl; text-align: right;
  max-width: 1180px; padding: 3.75rem 1rem 3rem;  /* أعلى الصفحة تحت شريط Streamlit */
}
[data-testid="stVerticalBlock"] { gap: 0.75rem; }

/* رأس الصفحة */
[data-testid="stMainBlockContainer"] h1 {
  font-size: clamp(1.55rem, 1.1rem + 1.6vw, 2.1rem); font-weight: 700; line-height: 1.3;
  color: var(--text); text-align: right; padding: 0; margin: 0;
}
/* حاوية Markdown في Streamlit هامشها السفلي −1rem لإلغاء هامش آخر فقرة؛ الرأس ينتهي بالشارة
   لا بفقرة، فتعوّضه الحشوة كي لا تركب الشارة على بطاقة حدود البيانات */
.hero { direction: rtl; text-align: right; width: 100%; padding-bottom: 1rem; }
.hero-sub { color: var(--muted); font-size: 1rem; margin: 0.15rem 0 0.5rem; }
.period-chip {
  display: inline-block; background: #E6F4F2; color: var(--primary); font-weight: 600;
  border-radius: 999px; padding: 0.2rem 0.8rem; font-size: 0.9rem;
}
[data-testid="stMainBlockContainer"] h3 {
  font-size: 1.15rem; font-weight: 700; color: var(--text);
  padding: 0.35rem 0 0; margin: 0; text-align: right;
}
[data-testid="stHeadingWithActionElements"] a { display: none; }

/* البطاقات */
[data-testid="stMetric"] {
  background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: 0.75rem 0.95rem; box-shadow: 0 1px 2px rgba(18, 38, 58, 0.05); height: 100%;
}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {
  color: var(--muted); font-size: 0.86rem; text-align: right;
  white-space: normal; overflow: visible; text-overflow: clip;
}
[data-testid="stMetricValue"] {
  font-size: clamp(1.2rem, 0.95rem + 1vw, 1.6rem); font-weight: 650; color: var(--text);
}
/* القيمة تُعرض بحسب محتواها: الأرقام الموقعة والنسب LTR، والنص العربي RTL */
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {
  direction: ltr; unicode-bidi: plaintext; text-align: right;
  white-space: normal; overflow: visible; text-overflow: clip;
}
[class*="-chg-up"] [data-testid="stMetricValue"], [class*="-chg-up"] [data-testid="stMetricValue"] * { color: var(--up); }
[class*="-chg-down"] [data-testid="stMetricValue"], [class*="-chg-down"] [data-testid="stMetricValue"] * { color: var(--down); }
[class*="-chg-na"] [data-testid="stMetricValue"], [class*="-chg-na"] [data-testid="stMetricValue"] * { color: var(--muted); }

/* الحاويات ذات الإطار تأخذ حشوتها من Streamlit؛ حشوة إضافية هنا تقصّ المحتوى */
[class*="st-key-card-"] {
  background: var(--card); border: 1px solid var(--line) !important; border-radius: 14px;
}
[class*="st-key-card-"] [data-testid="stMetric"] { box-shadow: none; }
.st-key-card-pending { background: var(--pending); border-style: dashed !important; }
.st-key-card-pending [data-testid="stMetric"] { background: transparent; border: none; padding: 0.35rem 0.5rem; }
.st-key-card-pending [data-testid="stMetricValue"] { font-size: 1.15rem; }
.st-key-card-notice { background: #FBFCFE; }
.st-key-card-notice [data-testid="stMarkdown"], .st-key-card-notice [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
.st-key-card-notice p { color: var(--muted); font-size: 0.9rem; line-height: 1.7; margin: 0; }
.group-title { font-weight: 700; color: var(--text); margin: 0; }
.group-sub { color: var(--muted); font-size: 0.88rem; margin: 0; }

/* النصوص والقوائم والروابط */
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--muted); text-align: right; }
[data-testid="stMarkdownContainer"] ul, [data-testid="stMarkdownContainer"] ol {
  padding-inline-start: 1.1rem; padding-inline-end: 0; margin: 0.25rem 0;
}
[data-testid="stMarkdownContainer"] li { margin: 0.15rem 0; padding: 0; }
[data-testid="stMarkdownContainer"] a { color: var(--primary); overflow-wrap: anywhere; }
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p { text-align: right; font-weight: 600; }
[data-testid="stExpander"] details { background: var(--card); border-radius: 12px; }
[data-testid="stExpander"] summary { direction: rtl; }

/* التبويبات */
[data-testid="stTabs"] [role="tablist"] { gap: 0.35rem; flex-wrap: wrap; }
[data-testid="stTab"] p { font-weight: 600; }

/* قوائم الاختيار تُفتح خارج حاوية المحتوى؛ الخيار flex فيحتاج الاتجاه لا المحاذاة وحدها */
[data-testid="stSelectboxVirtualDropdown"] [role="listbox"],
[data-testid="stSelectboxVirtualDropdown"] [role="option"] { direction: rtl; text-align: right; }

/* الرسوم معزولة عن اتجاه الصفحة */
[data-testid="stPlotlyChart"] { direction: ltr; }

@media (max-width: 640px) {
  .block-container, [data-testid="stMainBlockContainer"] { padding: 3.5rem 0.75rem 2.5rem; }
  [data-testid="stMetric"] { padding: 0.6rem 0.75rem; }
}
</style>
"""


# --- تنسيق العرض (لا حسابات) -------------------------------------------------

def fmt_count(value):
    return NA if pd.isna(value) else f"{int(value):,}"


def fmt_signed(value):
    if pd.isna(value):
        return NA
    value = int(value)
    return "0" if value == 0 else f"{value:+,}"


def fmt_percent(fraction, signed=False):
    """يحوّل الكسر إلى نسبة مئوية مرة واحدة فقط (0.003 → 0.30%)."""
    if pd.isna(fraction):
        return NA
    fraction = float(fraction)
    if fraction == 0:
        return "0.00%"
    if abs(fraction) < 0.0001:
        suffix = " (زيادة)" if fraction > 0 else " (انخفاض)"
        return "أقل من 0.01%" + (suffix if signed else "")
    return f"{fraction:+.2%}" if signed else f"{fraction:.2%}"


def ltr(text):
    """يعزل رقمًا موقعًا أو نسبة داخل جملة عربية (LRI…PDI) فلا تنتقل الإشارة إلى الطرف الآخر."""
    return f"⁦{text}⁩"


def direction_of(value):
    """اتجاه القيمة المعروضة للتلوين فقط: up أو down أو flat أو na."""
    if pd.isna(value):
        return "na"
    value = float(value)
    return "up" if value > 0 else ("down" if value < 0 else "flat")


# --- تحميل البيانات ----------------------------------------------------------

def _signature():
    """بصمة محتوى ملفي الإدخال؛ تتغير بتغيرهما فلا يبقى تخزين مؤقت قديم."""
    base = Path(analyze.PROCESSED_DIR)
    parts = [str(base)]
    for name in INPUT_FILES:
        try:
            parts.append(hashlib.sha256((base / name).read_bytes()).hexdigest())
        except OSError:
            parts.append(None)
    return tuple(parts)


@st.cache_data(show_spinner=False)
def _cached_tables(signature):
    workers, totals = analyze.read_processed(Path(signature[0]))
    return analyze.build_analysis(workers, totals)


def load_tables():
    """يعيد (tables, error_message). عند الفشل tables=None ورسالة عربية مفهومة."""
    signature = _signature()
    if any(part is None for part in signature[1:]):
        return None, "ملفات البيانات المعالجة غير موجودة. شغّل خطوة تجهيز البيانات أولًا ثم أعد فتح اللوحة."
    try:
        return _cached_tables(signature), None
    except analyze.AnalysisError as exc:
        return None, f"ملفات البيانات غير صالحة للعرض: {exc}"
    except (ValueError, KeyError, UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
        return None, "ملفات البيانات تالفة أو بصيغة غير متوقعة، ولا يمكن عرض النتائج."


# --- عناصر الواجهة -----------------------------------------------------------

def kpi_row(scope, cards, columns=None):
    """صف بطاقات؛ كل بطاقة (label, text, direction أو None). الأعمدة تتكدس على الجوال."""
    cols = st.columns(columns or len(cards))
    for index, (col, (label, text, direction)) in enumerate(zip(cols, cards)):
        with col:
            if direction is None:
                st.metric(label, text)
            else:
                with st.container(key=f"{scope}-{index}-chg-{direction}"):
                    st.metric(label, text)


def change_cards(row):
    """البطاقات الأربع المعتادة لسطر فيه workers_q1 وworkers_q2 وchange وchange_rate."""
    return [
        (Q1, fmt_count(row["workers_q1"]), None),
        (Q2, fmt_count(row["workers_q2"]), None),
        (CHANGE, fmt_signed(row["change"]), direction_of(row["change"])),
        (RATE, fmt_percent(row["change_rate"], signed=True), direction_of(row["change_rate"])),
    ]


def group_title(title, subtitle=None):
    html = f'<p class="group-title">{title}</p>'
    if subtitle:
        html += f'<p class="group-sub">{subtitle}</p>'
    st.markdown(html, unsafe_allow_html=True)


def show_chart(make, *args, key):
    with st.container(border=True, key=f"card-chart-{key}"):
        try:
            # theme=None: يحترم قالب الرسم وألوانه كما صممتها charts بدل قالب Streamlit.
            st.plotly_chart(make(*args), key=key, theme=None)
        except (ValueError, TypeError) as exc:
            st.error(f"تعذر رسم هذا الرسم: {exc}")


def one_row(df, **match):
    mask = pd.Series(True, index=df.index)
    for column, value in match.items():
        mask &= df[column] == value
    return df[mask].iloc[0] if mask.sum() == 1 else None


# --- الأقسام -----------------------------------------------------------------

def render_header(year, missing_count):
    st.title(TITLE)
    st.markdown(
        f'<div class="hero" dir="rtl"><p class="hero-sub">{SUBTITLE}</p>'
        f'<span class="period-chip">الربع الأول والثاني {year}</span></div>',
        unsafe_allow_html=True,
    )
    with st.container(border=True, key="card-notice"):
        st.markdown(
            "**حدود البيانات:** أعداد عاملين فقط؛ لا تقيس الشواغر أو الرواتب. "
            f"مقارنة بين ربعين وليست اتجاهًا. {missing_count} قيم فارغة تظهر «غير متاح» ولا تعني صفرًا. "
            "التفاصيل في «المصادر والمنهجية» أسفل الصفحة."
        )


def render_overview(tables, year):
    national = tables["national"].iloc[0]
    st.subheader(f"إجمالي المملكة — الربع الأول والثاني {year}")
    st.caption("مؤشرات المملكة كلها، ولا تتغير باختيار المنطقة. تشمل «تحت المعالجة».")
    kpi_row("national", change_cards(national))

    st.subheader("المناطق والأنشطة في رسوم")
    counts_tab, changes_tab, activities_tab = st.tabs(["أعداد المناطق", "تغير المناطق", "أكبر الأنشطة"])
    with counts_tab:
        show_chart(charts.make_region_counts, tables["regions"], key="chart_region_counts")
    with changes_tab:
        show_chart(charts.make_region_changes, tables["regions"], key="chart_region_changes")
    with activities_tab:
        show_chart(charts.make_activity_counts, tables["activities"], key="chart_activity_counts")


def _region_options(tables):
    return sorted(tables["regions"]["region"].tolist())


def _activity_options(tables):
    activities = tables["activities"]
    named = activities[~activities["is_pending"]]
    ordered = named.sort_values(["workers_q2", "economic_activity"], ascending=[False, True], na_position="last")
    return ordered["economic_activity"].tolist()


def _default_index(options, preferred, fallback=0):
    return options.index(preferred) if preferred in options else min(fallback, len(options) - 1)


def render_region_activity(tables, year):
    regions, region_activities = tables["regions"], tables["region_activities"]
    region_options = _region_options(tables)

    with st.container(border=True, key="card-select"):
        group_title("اختيار المناطق")
        left, right = st.columns(2)
        region = left.selectbox("المنطقة", region_options, key="region",
                                index=_default_index(region_options, DEFAULT_REGION))
        compare = right.selectbox("منطقة للمقارنة", region_options, key="compare_region",
                                  index=_default_index(region_options, DEFAULT_COMPARE_REGION, fallback=1))

    row = one_row(regions, region=region)
    st.subheader(f"إجمالي {region} — الربع الأول والثاني {year}")
    st.caption(
        f"حصتها من إجمالي المملكة: {Q1} {ltr(fmt_percent(row['share_q1']))}، "
        f"{Q2} {ltr(fmt_percent(row['share_q2']))}."
    )
    kpi_row("region", change_cards(row))

    with st.container(border=True, key="card-activity"):
        activity = st.selectbox("النشاط الاقتصادي", _activity_options(tables), key="activity")
        cell = one_row(region_activities, region=region, economic_activity=activity)
        group_title(f"{activity} في {region}")
        kpi_row("activity", change_cards(cell))
        group_title(f"حصة النشاط من إجمالي {region}", "المقام إجمالي المنطقة في الربع نفسه، ويشمل «تحت المعالجة».")
        kpi_row("activity-share", [(Q1, fmt_percent(cell["share_q1"]), None),
                                   (Q2, fmt_percent(cell["share_q2"]), None)])
        if pd.isna(cell["workers_q1"]) or pd.isna(cell["workers_q2"]):
            st.info("قيمة فارغة في المصدر لهذا النشاط والمنطقة؛ الفراغ لا يعني صفرًا، ولا تُحسب نسبة التغير أو الحصة دونه.")

    pending = one_row(region_activities[region_activities["is_pending"]], region=region)
    with st.container(border=True, key="card-pending"):
        group_title(f"«{PENDING_NAME}» في {region}",
                    "تصنيف غير مفسر وتعريفه غير محسوم؛ مشمول في إجمالي المنطقة ومقام الحصص.")
        kpi_row("pending", [
            (f"عدد {Q1}", fmt_count(pending["workers_q1"]), None),
            (f"عدد {Q2}", fmt_count(pending["workers_q2"]), None),
            (f"حصة {Q1}", fmt_percent(pending["share_q1"]), None),
            (f"حصة {Q2}", fmt_percent(pending["share_q2"]), None),
        ])

    st.subheader(f"حصص الأنشطة: {region} و{compare}")
    if region == compare:
        st.warning("اخترت المنطقة نفسها للمقارنة. اختر منطقة مختلفة في «منطقة للمقارنة» لعرض الرسم.")
    else:
        show_chart(charts.make_region_activity_comparison, region_activities, region, compare,
                   key="chart_region_comparison")


def missing_values(tables):
    """مواقع القيم الفارغة كما وردت في الجداول (عرض فقط)."""
    found = []
    for name, label_columns in (("regions", ["region"]), ("activities", ["economic_activity"]),
                                ("region_activities", ["region", "economic_activity"])):
        df = tables[name]
        for column, period in (("workers_q1", Q1), ("workers_q2", Q2)):
            for _, row in df[df[column].isna()].iterrows():
                found.append(f"{period}: " + " — ".join(str(row[c]) for c in label_columns))
    return found


def render_sources(tables, year, missing):
    with st.expander(f"المصادر والمنهجية — القيم الفارغة: {len(missing)}"):
        st.markdown(
            "**المصدر:** وزارة الموارد البشرية والتنمية الاجتماعية، بيانات مفتوحة. "
            f"**الفترة:** الربع الأول والثاني {year}. "
            "**المضمون:** أعداد العاملين في القطاع الخاص حسب النشاط الاقتصادي والمنطقة الإدارية."
        )
        st.markdown("\n".join(f"- [{label}]({url})" for label, url in SOURCE_LINKS))
        st.markdown(
            "**المنهجية والحدود**\n"
            "- البيانات أعداد عاملين فقط؛ لا تقيس الشواغر أو الرواتب أو فرص قبول الخريجين، ولا تفسر أسباب التغير.\n"
            "- مقارنة بين ربعين؛ لا تُجمع أعداد الربعين ولا تمثل اتجاهًا طويل المدى.\n"
            "- نسبة التغير مقامها الربع الأول. حصة المنطقة مقامها إجمالي المملكة، وحصة النشاط مقامها إجمالي المنطقة.\n"
            "- «تحت المعالجة» تصنيف غير مفسر وتعريفه غير محسوم، ومشمول في الإجماليات والمقامات."
        )
        if missing:
            st.markdown(
                "**القيم الفارغة** — تظهر «غير متاح»؛ لم تُعامل كأصفار، ومعناها غير محسوم. "
                "تطابق الإجماليات مع وجودها لا يعني اكتمال البيانات.\n"
                + "\n".join(f"- {item}" for item in missing)
            )
        else:
            st.markdown("لا توجد قيم فارغة في الجداول المعروضة.")


def main():
    st.set_page_config(page_title=TITLE, page_icon="📊", layout="wide")
    st.markdown(RTL_CSS, unsafe_allow_html=True)
    tables, error = load_tables()
    if error:
        st.title(TITLE)
        st.error(error)
        st.stop()
    year = int(tables["national"]["year"].iloc[0])
    missing = missing_values(tables)
    render_header(year, len(missing))
    overview_tab, region_tab = st.tabs(["نظرة عامة", "المناطق والأنشطة"])
    with overview_tab:
        render_overview(tables, year)
    with region_tab:
        render_region_activity(tables, year)
    render_sources(tables, year, missing)


if __name__ == "__main__":
    main()
