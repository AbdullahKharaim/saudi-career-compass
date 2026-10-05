"""قارئ xlsx مصغّر بمكتبة Python القياسية (zipfile + XML)، للقراءة فقط.

يكفي لقاعدة بيانات المهارات: أسماء الأوراق، والنصوص المشتركة، والقيم النصية والرقمية.
لا يقيّم الصيغ ولا يقرأ التنسيق؛ الخلايا الفارغة أو المسافات فقط لا تُعاد.
"""

from __future__ import annotations

import io
import re
import zipfile
import zlib
import xml.etree.ElementTree as ET

_M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_REF = re.compile(r"([A-Z]+)(\d+)")


class XlsxError(ValueError):
    """الملف ليس xlsx صالحًا أو تنقصه أجزاء أساسية."""


def _column(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _text(node):
    return "".join(t.text or "" for t in node.iter(f"{{{_M}}}t"))


def read_workbook(data: bytes) -> dict:
    """يعيد {اسم الورقة: {(الصف، العمود): نص}} بترقيم يبدأ من 1 كما في Excel."""
    try:
        return _read(data)
    except XlsxError:
        raise
    except (zipfile.BadZipFile, KeyError, ET.ParseError, zlib.error, EOFError, ValueError, IndexError) as exc:
        # أي جزء XML أو ضغط تالف داخل الحزمة يُرفع خطأ مصدر واضحًا لا استثناءً عامًا.
        raise XlsxError(f"ملف xlsx تالف أو غير مكتمل: {type(exc).__name__}: {exc}") from exc


def _read(data: bytes) -> dict:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise XlsxError(f"ليس ملف xlsx صالحًا: {exc}") from exc
    targets = {r.get("Id"): r.get("Target") for r in rels}
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        shared = [_text(si) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{{{_M}}}si")]
    sheets = {}
    for sheet in workbook.iter(f"{{{_M}}}sheet"):
        target = targets.get(sheet.get(f"{{{_R}}}id"), "")
        path = target.lstrip("/") if target.startswith("/xl/") else "xl/" + target
        try:
            root = ET.fromstring(z.read(path))
        except (KeyError, ET.ParseError) as exc:
            raise XlsxError(f"تعذر قراءة الورقة {sheet.get('name')!r}: {exc}") from exc
        cells = {}
        for c in root.iter(f"{{{_M}}}c"):
            m = _REF.fullmatch(c.get("r", ""))
            if not m:
                continue
            kind, v = c.get("t"), c.find(f"{{{_M}}}v")
            if kind == "s" and v is not None:
                value = shared[int(v.text)]
            elif kind == "inlineStr":
                node = c.find(f"{{{_M}}}is")
                value = _text(node) if node is not None else ""
            else:
                value = v.text if v is not None else ""
            if value is not None and value.strip():
                cells[(int(m.group(2)), _column(m.group(1)))] = value
        sheets[sheet.get("name")] = cells
    return sheets


def write_workbook(sheets: dict) -> bytes:
    """ينشئ xlsx بسيطًا بنصوص مضمّنة؛ للاختبارات فقط. sheets: {اسم: {(صف، عمود): نص}}."""
    def col(n):
        s = ""
        while n:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return s

    def esc(t):
        return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        names = list(sheets)
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{_M}" xmlns:r="{_R}"><sheets>' + "".join(
            f'<sheet name="{esc(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, 1)) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(
            f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml" Type="ws"/>' for i in range(1, len(names) + 1)) + "</Relationships>")
        for i, n in enumerate(names, 1):
            rows = {}
            for (r, c), v in sheets[n].items():
                rows.setdefault(r, []).append((c, v))
            xml = "".join(
                f'<row r="{r}">' + "".join(f'<c r="{col(c)}{r}" t="inlineStr"><is><t>{esc(str(v))}</t></is></c>' for c, v in sorted(cs)) + "</row>"
                for r, cs in sorted(rows.items()))
            z.writestr(f"xl/worksheets/sheet{i}.xml", f'<worksheet xmlns="{_M}"><sheetData>{xml}</sheetData></worksheet>')
    return buf.getvalue()
