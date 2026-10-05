"""قراءة «قاعدة بيانات المهارات للقطاع الرقمي» (وزارة الموارد البشرية، المجلس القطاعي للمهارات، 2025).

ما يدعمه الملف فعلًا (تحقق Claude من نسخة 2025-02):
- المجموعات الوظيفية في القطاعين الفرعيين، ولكل مجموعة قائمة مهاراتها الفنية والعامة.
- وصف موجز لكل مهارة، وعلامة «مهارة ذات أولوية» على مستوى القطاع.
- سلّم الإتقان نصًّا: الفنية 1–5 والعامة 1–3.
ما لا يدعمه: معرّفات رسمية للمهارات، والمستوى المطلوب لكل مجموعة، والمهن (رموز التصنيف) لكل مهارة.
المعرّفات هنا مشتقة من الاسم (بصمة ثابتة)، وليست معرّفات المصدر.
"""

from __future__ import annotations

import hashlib
import re

from .xlsx import read_workbook

PRIORITY_SHEET = "المهارات ذات الأولوية"
UNIQUE_SHEET = "المهارات الفنية الفريدة"
TECH_DESC_SHEET = "وصف المهارات الفنية"
GENERAL_DESC_SHEET = "وصف المهارات العامة"
INTRO_SHEET = "المقدمة"
COVER_SHEET = "الغلاف"
SUBSECTOR_SHEETS = ("تقنية المعلومات", "الاتصالات")
TECHNICAL, GENERAL = "المهارات الفنية", "المهارات العامة"
YES = "نعم"


class SkillsFormatError(ValueError):
    """بنية الملف لا تطابق المتوقع؛ لا تُبنى بيانات منه."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("؛ ".join(self.errors))


_MARKS = re.compile("[ً-ْٰـ]")  # التشكيل والتطويل
_PUNCT = re.compile(r"[،,؛;:().\[\]\-–/]")  # فروق ترقيم بين الأوراق لا تغيّر المهارة


def norm(text) -> str:
    return " ".join(str(text).split())


def key(text) -> str:
    """مفتاح مطابقة بين الأوراق: دون تشكيل أو ترقيم أو فرق حالة لاتينية (العرض يبقى بالنص الأصلي).

    لا مطابقة تقريبية للصياغة: «تثبيت النُظم» و«تثبيت النظام» يبقيان مهارتين كما وردتا.
    """
    return norm(_PUNCT.sub(" ", _MARKS.sub("", str(text))).lower())


def split_list(text) -> list:
    return [norm(x) for x in re.split(r"[،,]", str(text)) if norm(x)]


def skill_id(kind: str, name: str) -> str:
    return ("t" if kind == TECHNICAL else "g") + hashlib.sha1(key(name).encode("utf-8")).hexdigest()[:8]


def group_id(subsector_index: int, name: str) -> str:
    return f"s{subsector_index + 1}-" + hashlib.sha1(key(name).encode("utf-8")).hexdigest()[:6]


def _sheet(sheets, name, errors):
    for key, cells in sheets.items():
        if norm(key) == name:
            return cells
    errors.append(f"ورقة مفقودة: {name}")
    return None


def _find(cells, text):
    return sorted((r, c) for (r, c), v in cells.items() if norm(v) == text)


def _declared(cells, prefix):
    for (r, c), v in sorted(cells.items()):
        if norm(v).startswith(prefix):
            value = norm(cells.get((r, c + 1), ""))
            return int(value) if value.isdigit() else None
    return None


def _table(cells, header):
    """صفوف الجدول تحت عنوان العمود الأول المحدد: [{عمود: نص}] حتى نهاية الورقة."""
    found = _find(cells, header)
    if not found:
        return None
    r0, c0 = found[0]
    rows = {}
    for (r, c), v in cells.items():
        if r > r0 and c >= c0:
            rows.setdefault(r, {})[c - c0] = norm(v)
    return [rows[r] for r in sorted(rows)]


def parse_skills_workbook(data: bytes) -> dict:
    """يعيد بنية المهارات بعد التحقق، أو يرفع SkillsFormatError. التحذيرات لا تمنع البناء."""
    sheets = read_workbook(data)
    errors, warnings = [], []
    prio_cells = _sheet(sheets, PRIORITY_SHEET, errors)
    unique_cells = _sheet(sheets, UNIQUE_SHEET, errors)
    tech_desc = _sheet(sheets, TECH_DESC_SHEET, errors)
    gen_desc = _sheet(sheets, GENERAL_DESC_SHEET, errors)
    intro = _sheet(sheets, INTRO_SHEET, errors)
    subsector_cells = [(name, _sheet(sheets, name, errors)) for name in SUBSECTOR_SHEETS]
    if errors:
        raise SkillsFormatError(errors)

    declared = {
        "groups": _declared(prio_cells, "عدد المجموعات الوظيفية"),
        "subsectors": _declared(prio_cells, "عدد القطاعات الفرعية"),
        "priority": _declared(prio_cells, "عدد المهارات الفنية ذات الأولوية"),
        "unique_technical": _declared(unique_cells, "عدد المهارات الفنية الفريدة"),
    }
    if None in declared.values():
        errors.append("تعذر قراءة الأعداد المعلنة في رأس ورقتي الأولوية والمهارات الفريدة")

    # سلّم الإتقان من نص المقدمة («من 1 إلى 5» و«من 1 إلى 3»).
    scale = {}
    for (r, c), v in sorted(intro.items()):
        m = re.search(r"من\s*(\d)\s*إلى\s*(\d)", v)
        if m and "الفنية" in v and "technical" not in scale:
            scale["technical"] = {"min": int(m.group(1)), "max": int(m.group(2)), "text": norm(v)}
        elif m and "العامة" in v and "general" not in scale:
            scale["general"] = {"min": int(m.group(1)), "max": int(m.group(2)), "text": norm(v)}
    if set(scale) != {"technical", "general"}:
        errors.append("لم يُعثر على سلّم الإتقان (الفنية والعامة) في ورقة المقدمة")

    # الأوصاف (المفتاح دون تشكيل؛ الاسم المعروض من ورقة الأوصاف)
    technical, general = {}, {}
    rows = _table(tech_desc, TECHNICAL)
    if rows is None:
        errors.append(f"عنوان «{TECHNICAL}» غير موجود في {TECH_DESC_SHEET}")
    else:
        for row in rows:
            name = row.get(0, "")
            if name:
                technical[key(name)] = {"name": name, "description": row.get(1, ""), "priority": False,
                                        "subsectors": [], "groups": []}
    rows = _table(gen_desc, GENERAL)
    if rows is None:
        errors.append(f"عنوان «{GENERAL}» غير موجود في {GENERAL_DESC_SHEET}")
    else:
        category = None
        for row in rows:
            name, description = row.get(0, ""), row.get(1, "")
            if name and not description:
                category = name  # صف فئة (مثل «المهارات الأساسية»)
            elif name:
                general[key(name)] = {"name": name, "description": description, "category": category}

    # المهارات الفريدة وعلامة الأولوية
    unique = {}
    for row in _table(unique_cells, "المهارات الفريدة") or []:
        if row.get(0):
            unique[key(row[0])] = {"name": row[0], "priority": row.get(1) == YES}
    priority_names = [r[0] for r in (_table(prio_cells, "المهارات الفريدة") or []) if r.get(0)]
    if not unique or not priority_names:
        errors.append("جدول المهارات الفريدة أو جدول المهارات ذات الأولوية فارغ")
    flagged = {k for k, u in unique.items() if u["priority"]}
    if {key(n) for n in priority_names} != flagged:
        errors.append(f"قائمة الأولوية ({len(priority_names)}) لا تطابق علامة «نعم» في المهارات الفريدة ({len(flagged)})")
    if declared["priority"] is not None and declared["priority"] != len(priority_names):
        errors.append(f"عدد المهارات ذات الأولوية {len(priority_names)} والمعلن {declared['priority']}")
    if declared["unique_technical"] is not None and declared["unique_technical"] != len(unique):
        warnings.append(f"المهارات الفنية الفريدة في الجدول {len(unique)} بينما الرقم المعلن {declared['unique_technical']}")

    # المجموعات حسب القطاع الفرعي (قوائم بمفاتيح المهارات)
    subsectors = []
    for index, (sheet_name, cells) in enumerate(subsector_cells):
        labels = {norm(cells.get((r, 2), "")) for r in (2, 3, 4)}
        if labels != {"القطاع الفرعي", "المجموعة الوظيفية", "المهارات"}:
            errors.append(f"{sheet_name}: صفوف العناوين (القطاع الفرعي/المجموعة الوظيفية/المهارات) غير متوقعة")
            continue
        groups = {}
        for col in sorted({c for (r, c) in cells if c >= 3 and r in (2, 3, 4)}):
            sub, grp, kind = (norm(cells.get((r, col), "")) for r in (2, 3, 4))
            if sub != sheet_name or not grp or kind not in (TECHNICAL, GENERAL):
                errors.append(f"{sheet_name}: العمود {col} بلا قطاع أو مجموعة أو نوع مهارة صالح")
                continue
            listed = [norm(v) for (r, c), v in sorted(cells.items()) if c == col and r >= 5 and norm(v)]
            entry = groups.setdefault(grp, {"technical": [], "general": []})
            entry["technical" if kind == TECHNICAL else "general"] = list(dict.fromkeys(listed))
        subsectors.append({"name": sheet_name, "groups": groups})
    distinct_groups = {g for s in subsectors for g in s["groups"]}
    if declared["groups"] is not None and len(distinct_groups) != declared["groups"]:
        errors.append(f"عدد المجموعات الوظيفية {len(distinct_groups)} والمعلن {declared['groups']}")
    if declared["subsectors"] is not None and len(subsectors) != declared["subsectors"]:
        errors.append(f"عدد القطاعات الفرعية {len(subsectors)} والمعلن {declared['subsectors']}")
    for s in subsectors:
        for g, lists in s["groups"].items():
            if not lists["technical"]:
                errors.append(f"{s['name']} › {g}: لا مهارات فنية")
    if errors:
        raise SkillsFormatError(errors)

    # ربط المهارات بالمجموعات والأولوية؛ القوائم تُحوَّل إلى الأسماء المعروضة الموحدة
    no_description, not_unique, unknown_general = set(), set(), set()
    for s in subsectors:
        for g, lists in s["groups"].items():
            canonical = []
            for name in lists["technical"]:
                k = key(name)
                info = technical.get(k)
                if info is None:
                    no_description.add(name)
                    shown = unique[k]["name"] if k in unique else name
                    info = technical[k] = {"name": shown, "description": "", "priority": False,
                                           "subsectors": [], "groups": []}
                if k not in unique:
                    not_unique.add(name)
                if s["name"] not in info["subsectors"]:
                    info["subsectors"].append(s["name"])
                if g not in info["groups"]:
                    info["groups"].append(g)
                canonical.append(info["name"])
            lists["technical"] = list(dict.fromkeys(canonical))
            shown_general = []
            for name in lists["general"]:
                info = general.get(key(name))
                if info is None:
                    unknown_general.add(name)
                    info = general[key(name)] = {"name": name, "description": "", "category": None}
                shown_general.append(info["name"])
            lists["general"] = list(dict.fromkeys(shown_general))
    for k, u in unique.items():
        if k in technical:
            technical[k]["priority"] = u["priority"]
    if no_description:
        warnings.append(f"{len(no_description)} مهارة فنية في قوائم المجموعات بلا وصف في ورقة الأوصاف")
    if not_unique:
        warnings.append(f"{len(not_unique)} مهارة فنية في قوائم المجموعات غير مدرجة في المهارات الفريدة")
    if unknown_general:
        warnings.append(f"مهارات عامة في قوائم المجموعات بلا وصف: {sorted(unknown_general)}")

    ids = {}
    for kind, table in ((TECHNICAL, technical), (GENERAL, general)):
        for k, info in table.items():
            sid = skill_id(kind, k)
            if sid in ids:
                raise SkillsFormatError([f"تصادم معرّف مشتق بين «{ids[sid]}» و«{info['name']}»"])
            ids[sid] = info["name"]
    technical = {info.pop("name"): info for info in technical.values()}
    general = {info.pop("name"): info for info in general.values()}
    shown_priority = {key(n): n for n in technical}
    priority_names = [shown_priority.get(key(n), n) for n in priority_names]

    cover = sheets.get(COVER_SHEET, {})
    cover_text = [norm(v) for _, v in sorted(cover.items())]
    return {
        "title": next((t for t in cover_text if t.startswith("قاعدة بيانات المهارات")), "قاعدة بيانات المهارات"),
        "issuer": next((t for t in cover_text if "المجلس القطاعي" in t), ""),
        "year": next((t for t in cover_text if re.fullmatch(r"20\d\d", t)), ""),
        "scale": scale,
        "declared": declared,
        "subsectors": [{"name": s["name"], "groups": s["groups"]} for s in subsectors],
        "technical": technical,
        "general": general,
        "priority_order": priority_names,
        "warnings": warnings,
    }


def summarize(parsed: dict) -> dict:
    """أعداد مختصرة لسجل الجلب والوثائق."""
    return {
        "subsectors": len(parsed["subsectors"]),
        "groups": len({g for s in parsed["subsectors"] for g in s["groups"]}),
        "group_entries": sum(len(s["groups"]) for s in parsed["subsectors"]),
        "technical_skills": len(parsed["technical"]),
        "priority_skills": sum(1 for v in parsed["technical"].values() if v["priority"]),
        "general_skills": len(parsed["general"]),
        "warnings": len(parsed["warnings"]),
    }
