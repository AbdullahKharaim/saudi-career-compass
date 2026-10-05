"""رسوم العرض فقط؛ القيم والتغيرات والحصص تأتي من جداول التحليل.

كل دالة تستقبل جدول سنة واحدة، وتعيد Figure دون كتابة ملفات أو تعديل الجدول.
الترتيب تنازلي حسب Q2، عدا رسم التغير المرتب تصاعديًا حسب change.
"""

from html import escape
from math import ceil, floor, log10
from numbers import Integral
import re
from textwrap import wrap

import pandas as pd
import plotly.graph_objects as go

__all__ = [
    "make_region_counts", "make_region_changes", "make_activity_counts",
    "make_region_activity_comparison",
]

_BASE = ["year", "workers_q1", "workers_q2", "change", "change_rate"]
_SHARES = ["share_q1", "share_q2"]
_Q1 = "الربع الأول"
_Q2 = "الربع الثاني"
_BLUE = "#64748B"
_ORANGE = "#0F766E"
_GREEN = "#0F766E"
_RED = "#B45353"
_GRAY = "#64748B"
_TEXT = "#12263A"
_EXCLUSION = "تصنيف تحت المعالجة مستبعد من العرض\nمعنى هذا التصنيف غير محسوم"
_REGION_DENOMINATOR = (
    "مقام الحصص هو إجمالي مصدر كل منطقة\nويشمل تصنيف تحت المعالجة"
)
_NATIONAL_DENOMINATOR = (
    "مقام الحصة هو إجمالي مصدر المملكة\nويشمل تصنيف تحت المعالجة"
)
# عزل الاتجاه: SVG الرسم LTR، فالسطر العربي يُعزل RTL والقيمة داخله LTR.
_LRI, _RLI, _PDI = "⁦", "⁧", "⁩"
_ARABIC = re.compile("[؀-ۿ]")
_NUMBER = re.compile(r"[+−-]?\d[\d,.]*%?")


def _table(frame, columns, keys):
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("المدخل يجب أن يكون pandas DataFrame")
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError("أعمدة مطلوبة غير موجودة: " + ", ".join(missing))
    if frame.empty:
        raise ValueError("الجدول فارغ؛ لا توجد سنة أو سجلات للعرض")
    if frame["year"].isna().any() or frame["year"].nunique() != 1:
        raise ValueError("الرسم يتطلب سنة واحدة غير مفقودة")
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError("مفاتيح العرض مفقودة أو مكررة")
    if "is_pending" in columns:
        if frame["is_pending"].isna().any() or not pd.api.types.is_bool_dtype(frame["is_pending"]):
            raise ValueError("is_pending يجب أن يحتوي قيمًا منطقية غير مفقودة")
    return frame.copy(), str(frame["year"].iloc[0])


def _wrap(text, width=32):
    return "<br>".join(escape(part) for part in wrap(
        str(text), width=width, break_long_words=False, break_on_hyphens=False,
    ))


def _rtl_wrap(text, width=42):
    # عزل كل سطر عربي يحافظ على الترقيم عند التفاف SVG دون قلب الرسم.
    return "<br>".join(
        "\u2067" + escape(part) + "\u2069"
        for line in str(text).splitlines()
        for part in wrap(line, width=width, break_long_words=False, break_on_hyphens=False)
    )


def _iso(text):
    """\u064a\u0639\u0632\u0644 \u0642\u064a\u0645\u0629 \u0645\u0639\u0631\u0648\u0636\u0629: \u0627\u0644\u0631\u0642\u0645 \u0645\u0639 \u0625\u0634\u0627\u0631\u062a\u0647 \u0648% \u0645\u0642\u0637\u0639 LTR \u0648\u0627\u062d\u062f\u060c \u0648\u0627\u0644\u0646\u0635 \u0627\u0644\u0639\u0631\u0628\u064a (\u00ab\u063a\u064a\u0631 \u0645\u062a\u0627\u062d\u00bb) RTL."""
    text = str(text)
    if _ARABIC.search(text):
        return _RLI + _NUMBER.sub(lambda m: _LRI + m.group() + _PDI, text) + _PDI
    return _LRI + text + _PDI


def _hover(*lines):
    """\u0623\u0633\u0637\u0631 \u0627\u0644\u062a\u062d\u0648\u064a\u0645\u061b \u0643\u0644 \u0633\u0637\u0631 \u064a\u064f\u0631\u0633\u0645 \u0645\u0646\u0641\u0635\u0644\u064b\u0627 \u0641\u064a\u064f\u0639\u0632\u0644 \u0648\u062d\u062f\u0647\u060c \u0648\u0627\u0644\u0642\u064a\u0645 \u062f\u0627\u062e\u0644\u0647 \u0645\u0639\u0632\u0648\u0644\u0629 \u0628\u0640_iso."""
    return "<br>".join(_RLI + line + _PDI for line in lines) + "<extra></extra>"


def _hover_name(name, width=30):
    """\u0627\u0633\u0645 \u0637\u0648\u064a\u0644 \u0644\u0644\u062a\u062d\u0648\u064a\u0645 \u0639\u0644\u0649 \u0623\u0633\u0637\u0631\u061b \u0627\u0644\u0639\u0632\u0644 \u064a\u064f\u063a\u0644\u0642 \u0648\u064a\u064f\u0641\u062a\u062d \u0639\u0646\u062f \u0643\u0644 \u0633\u0637\u0631."""
    return (_PDI + "<br>" + _RLI).join(escape(part) for part in wrap(
        str(name), width=width, break_long_words=False, break_on_hyphens=False,
    ))


def _values(series):
    return [None if pd.isna(v) else (v.item() if hasattr(v, "item") else v) for v in series]


def _count(value):
    return "غير متاح" if pd.isna(value) else f"{value:,.0f}"


def _percent(value):
    if pd.isna(value):
        return "غير متاح"
    if value == 0 or abs(value) >= .001:
        return f"{value:.1%}"
    if abs(value) >= .0001:
        return f"{value:.2%}"
    text = f"{value:.4%}"
    if text in ("0.0000%", "-0.0000%"):
        return "أقل من 0.0001%" if value > 0 else "أكبر من −0.0001%"
    return text


def _signed_count(value):
    if pd.isna(value):
        return "غير متاح"
    return "0" if value == 0 else ("+" if value > 0 else "−") + f"{abs(value):,.0f}"


def _signed_percent(value):
    if pd.isna(value) or value == 0:
        return _percent(value)
    text = _percent(abs(value))
    if not text[0].isdigit():  # «أقل من 0.0001%» لا تُلصق به إشارة
        return text + (" (زيادة)" if value > 0 else " (انخفاض)")
    return ("+" if value > 0 else "−") + text


def _missing_note(names, values, period):
    absent = [str(name) for name, value in zip(names, values) if pd.isna(value)]
    return f"غير متاح في {period}\n" + "\n".join(absent) if absent else None


def _number_axis(values, signed=False):
    """وحدات تدريج العرض فقط؛ لا يغيّر قيم السلاسل."""
    available = [value for value in values if value is not None]
    largest = max((abs(value) for value in available), default=0)
    scale, unit = (1_000_000, "مليون عامل") if largest >= 1_000_000 else (
        (1_000, "ألف عامل") if largest >= 10_000 else (1, "عامل")
    )
    # تدريج قليل وواضح للمساحات الضيقة، بدلاً من أعداد طويلة على المحور.
    rough = max(largest / 4, 1)
    base = 10 ** floor(log10(rough))
    step = next(factor * base for factor in (1, 2, 5, 10) if factor * base >= rough)
    low = min(available + [0]) if signed else 0
    high = max(available + [0])
    ticks = [i * step for i in range(floor(low / step), ceil(high / step) + 1)]
    if len(ticks) < 2:
        ticks = [0, step]
    texts = []
    for tick in ticks:
        value = tick / scale
        prefix = "−" if value < 0 else ("+" if signed and value > 0 else "")
        texts.append(prefix + f"{abs(value):,.2f}".rstrip("0").rstrip(".") if scale != 1
                     else prefix + f"{abs(value):,.0f}")
    return dict(tickmode="array", tickvals=ticks, ticktext=texts), unit


def _layout(fig, title, period, names, axis_title, notes, *, activity=False, percent=False, row_labels=None,
            tick_labels=None):
    labels = tick_labels if tick_labels is not None else [_wrap(name, 26 if activity else 20) for name in names]
    notes = [note for note in notes if note]
    note_lines = sum(_rtl_wrap(note).count("<br>") + 1 for note in notes)
    max_lines = max((label.count("<br>") + 1 for label in labels), default=1)
    row_height = max(30 if activity else 26, max_lines * 13 + 10)
    bottom = 65 + 15 * note_lines
    right = min(172, max(105, max((len(line) for name in names for line in wrap(str(name), width=26)), default=0) * 6)) if activity else 108
    if row_labels is not None:
        labels = [_rtl_wrap(name, 42) for name in names]
        max_lines = max((label.count("<br>") + 1 for label in labels), default=1)
        row_height = max(48, max_lines * 15 + 32)
        right = 18
    top = 142 if len(fig.data) > 1 else 102
    fig.update_layout(
        template="plotly_white", paper_bgcolor="white", plot_bgcolor="white",
        title=dict(text=f"{title}<br><sup>{period}</sup>", x=.99, xanchor="right",
                   y=1, yref="container", yanchor="top", pad=dict(t=48),
                   font=dict(size=17, color=_TEXT)),
        autosize=True, barmode="group", bargap=.3, bargroupgap=.08,
        height=max(300, top + bottom + max(1, len(names)) * row_height),
        margin=dict(l=20, r=right, t=top, b=bottom, pad=3, autoexpand=False),
        font=dict(family="Segoe UI, Tahoma, Arial, sans-serif", size=12, color=_TEXT),
        hoverlabel=dict(bgcolor="white", bordercolor="#CBD5E1", font=dict(color=_TEXT, size=12), align="right"),
        hovermode="closest", hoverdistance=30,
        legend=dict(title_text="", orientation="h", y=1, yanchor="bottom", x=1, xanchor="right", xref="container",
                    entrywidth=.5, entrywidthmode="fraction",
                    font=dict(size=11, color=_TEXT), bgcolor="white", traceorder="normal"),
        showlegend=len(fig.data) > 1,
        xaxis=dict(title=dict(text=axis_title, font=dict(color=_GRAY, size=12), standoff=10),
                   tickformat=".0%" if percent else ",.0f", automargin=True,
                   tickfont=dict(color=_GRAY, size=11), nticks=4, gridcolor="#E2E8F0",
                   showline=True, linecolor="#CBD5E1", zeroline=True, zerolinecolor="#94A3B8"),
        yaxis=dict(
            title=None, side="right", tickfont=dict(size=11, color=_TEXT),
            type="category", tickmode="array", tickvals=list(names), ticktext=labels,
            categoryorder="array", categoryarray=list(names), autorange="reversed", automargin=True,
            showgrid=False, showline=False, ticks="", fixedrange=True,
            showticklabels=row_labels is None,
        ),
    )
    if row_labels is not None:
        for name, label, shares in zip(names, labels, row_labels):
            fig.add_annotation(
                x=1, xref="paper", y=name, yref="y", yshift=6,
                xanchor="right", yanchor="bottom", text=label + "<br>" + shares,
                showarrow=False, align="right", font=dict(size=11, color=_TEXT),
            )
    if notes:
        fig.add_annotation(
            x=1, y=0, xref="paper", yref="paper", xanchor="right", yanchor="top",
            xshift=right - 6, yshift=-58, text="<br>".join(_rtl_wrap(note) for note in notes),
            showarrow=False, align="right", font=dict(size=11, color=_GRAY),
        )
    return fig


def make_region_counts(regions):
    """أعداد المصدر لكل منطقة في الربعين؛ الترتيب تنازلي حسب Q2."""
    frame, year = _table(regions, _BASE + ["region"] + _SHARES, ["region"])
    frame = frame.sort_values(["workers_q2", "region"], ascending=[False, True], na_position="last")
    names = frame["region"].tolist()
    fig, notes = go.Figure(), []
    for column, period, color in [("workers_q1", _Q1, _BLUE), ("workers_q2", _Q2, _ORANGE)]:
        fig.add_bar(
            x=_values(frame[column]), y=names, orientation="h", name=period,
            marker_color=color,
            customdata=[[escape(str(n)), _iso(_count(v))] for n, v in zip(names, frame[column])],
            hovertemplate=_hover("المنطقة: %{customdata[0]}", f"{period} — {year}", "عدد العاملين: %{customdata[1]}"),
        )
        notes.append(_missing_note(names, frame[column], period))
    ticks, unit = _number_axis(_values(frame["workers_q1"]) + _values(frame["workers_q2"]))
    fig = _layout(fig, "العاملون حسب المنطقة", f"الربعان الأول والثاني · {year}", names, unit, notes)
    fig.update_xaxes(**ticks)
    return fig


def make_region_changes(regions):
    """عرض change وchange_rate كما وردا دون إعادة حسابهما."""
    frame, year = _table(regions, _BASE + ["region"] + _SHARES, ["region"])
    frame = frame.sort_values(["change", "region"], na_position="last")
    names, values = frame["region"].tolist(), _values(frame["change"])
    colors = [_GRAY if v is None or v == 0 else (_GREEN if v > 0 else _RED) for v in values]
    labels = ["غير متاح" if v is None else ("0" if v == 0 else f"{'↑ +' if v > 0 else '↓ −'}{abs(v):,.0f}") for v in values]
    labels = [f"{'↑ +' if v > 0 else '↓ −'}{abs(v) / 1_000:.1f} ألف" if v is not None and abs(v) >= 10_000 else label
              for v, label in zip(values, labels)]
    # التسمية تحت اسم المنطقة في عمود الأسماء لا على العمود: على عرض 390px عمود 18.6 ألف
    # أضيق من نصه، ولا يتسع النص خارجه قبل الأسماء؛ عمود الأسماء عرضه ثابت بأي شاشة.
    tick_labels = [f'{_wrap(name, 20)}<br><span style="color:{color}">{escape(label)}</span>'
                   for name, label, color in zip(names, labels, colors)]
    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h", name="التغير العددي", marker_color=colors,
        marker_pattern_shape=["/" if v is not None and v > 0 else ("\\" if v is not None and v < 0 else "") for v in values],
        customdata=[
            [escape(str(n)), _iso(_signed_count(v)), _iso(_signed_percent(rate)), _iso(_count(q1)), _iso(_count(q2))]
            for n, v, rate, q1, q2 in zip(names, frame["change"], frame["change_rate"], frame["workers_q1"], frame["workers_q2"])
        ],
        hovertemplate=_hover(
            "المنطقة: %{customdata[0]}", year, _Q1 + ": %{customdata[3]}", _Q2 + ": %{customdata[4]}",
            "التغير العددي: %{customdata[1]}", "نسبة التغير (مقامها الربع الأول): %{customdata[2]}",
        ),
    ))
    fig.add_vline(x=0, line_color=_TEXT, line_width=1.5)
    ticks, unit = _number_axis(values, signed=True)
    fig = _layout(
        fig, "التغير في عدد العاملين", f"من الربع الأول إلى الثاني · {year}",
        names, f"التغير · {unit}",
        ["↑ زيادة   ↓ انخفاض   0 دون تغير\nمقام نسبة التغير هو الربع الأول",
         _missing_note(names, frame["change"], "التغير")],
        tick_labels=tick_labels,
    )
    available = [v for v in values if v is not None]
    low, high = min(available + [0]), max(available + [0])
    # لا نصوص على الأعمدة، فالهامش يكفي لتدريج المحور فقط.
    padding = max((high - low) * .1, 1)
    fig.update_xaxes(**ticks, range=[low - padding, high + padding])
    return fig


def make_activity_counts(activities, top_n=10):
    """أكبر top_n أنشطة في Q2، باستبعاد is_pending دون تغيير الحصص."""
    if isinstance(top_n, bool) or not isinstance(top_n, Integral) or top_n < 1:
        raise ValueError("top_n يجب أن يكون عددًا صحيحًا موجبًا")
    frame, year = _table(activities, _BASE + ["economic_activity", "is_pending"] + _SHARES, ["economic_activity"])
    frame = frame.loc[~frame["is_pending"]].sort_values(
        ["workers_q2", "economic_activity"], ascending=[False, True], na_position="last",
    ).head(top_n)
    names = frame["economic_activity"].tolist()
    fig = go.Figure(go.Bar(
        x=_values(frame["workers_q2"]), y=names, orientation="h", name=_Q2, marker_color=_ORANGE,
        customdata=[[escape(str(n)), _iso(_count(v)), _iso(_percent(s)), _hover_name(n)]
                    for n, v, s in zip(names, frame["workers_q2"], frame["share_q2"])],
        hovertemplate=_hover(
            "النشاط: %{customdata[3]}", f"{_Q2} — {year}", "عدد العاملين: %{customdata[1]}",
            "الحصة من إجمالي مصدر المملكة: %{customdata[2]}", "(يشمل تحت المعالجة)",
        ),
    ))
    ticks, unit = _number_axis(_values(frame["workers_q2"]))
    fig = _layout(
        fig, "أكبر الأنشطة", f"{_Q2} · {year} · حتى {top_n} أنشطة", names, unit,
        [_EXCLUSION, _NATIONAL_DENOMINATOR,
         "لا توجد أنشطة متاحة للعرض بعد الاستبعاد." if frame.empty else None,
         _missing_note(names, frame["workers_q2"], _Q2)], activity=True,
    )
    fig.update_xaxes(**ticks)
    return fig


def make_region_activity_comparison(region_activities, region_a="نجران", region_b="الشرقية"):
    """حصص الأنشطة داخل منطقتين في Q2؛ المقامات تشمل التصنيف المستبعد."""
    frame, year = _table(
        region_activities, _BASE + ["region", "economic_activity", "is_pending"] + _SHARES,
        ["region", "economic_activity"],
    )
    if region_a == region_b:
        raise ValueError("اختر منطقتين مختلفتين")
    for region in (region_a, region_b):
        if region not in set(frame["region"]):
            raise ValueError(f"المنطقة المطلوبة غير موجودة: {region}")
    selected = frame.loc[frame["region"].isin([region_a, region_b]) & ~frame["is_pending"]]
    # أكبر حصة معطاة لكل نشاط تستخدم للفرز فقط، دون جمع أو إعادة تطبيع.
    order = selected.groupby("economic_activity", sort=False)["share_q2"].max().reset_index().sort_values(
        ["share_q2", "economic_activity"], ascending=[False, True], na_position="last",
    )
    names = order["economic_activity"].tolist()
    fig, notes = go.Figure(), [_EXCLUSION, _REGION_DENOMINATOR]
    if not names:
        notes.append("لا توجد أنشطة متاحة للعرض بعد الاستبعاد.")
    for region, color, symbol in [(region_a, _BLUE, "circle"), (region_b, _ORANGE, "diamond")]:
        rows = selected.loc[selected["region"] == region].set_index("economic_activity").reindex(names)
        fig.add_scatter(
            x=_values(rows["share_q2"]), y=names, mode="markers", name=region,
            marker=dict(color=color, symbol=symbol, size=11, line=dict(color="white", width=1)),
            customdata=[[escape(str(n)), _iso(_percent(s)), _iso(_count(v)), _hover_name(n)]
                        for n, s, v in zip(names, rows["share_q2"], rows["workers_q2"])],
            hovertemplate=_hover(
                "المنطقة: " + escape(str(region)), "النشاط: %{customdata[3]}", f"{_Q2} — {year}",
                "حصة النشاط: %{customdata[1]}", "عدد العاملين: %{customdata[2]}",
                "المقام: إجمالي مصدر المنطقة", "(يشمل تحت المعالجة)",
            ),
        )
        notes.append(_missing_note(names, rows["share_q2"], f"{_Q2} في {region}"))
    # قيم نصية من الحصص المعطاة لتظل الحصص الصغيرة والمفقودات مقروءة.
    # لا يتغير المقياس الخطي أو موضع أي نقطة أو مقام الحصص.
    shown = [selected.loc[selected["region"] == region].set_index("economic_activity").reindex(names)["share_q2"]
             for region in (region_a, region_b)]
    row_labels = [f"● {_iso(_percent(a))}   ◆ {_iso(_percent(b))}" for a, b in zip(*shown)]
    return _layout(
        fig, "حصص الأنشطة داخل المنطقتين", f"{_Q2} · {year}",
        names, "حصة النشاط من إجمالي المنطقة", notes, activity=True, percent=True, row_labels=row_labels,
    )
