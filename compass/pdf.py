"""قراءة PDF مصغّرة بمكتبة Python القياسية، وفهرس صفحات «قاموس المهارات للقطاع الرقمي».

ما تحقق منه Claude في نسخة 2025-02 من القاموس (195 صفحة، مصدَّر من PowerPoint):
- لكل مهارة ذات أولوية صفحة «وثيقة المهارة الفنية» فيها أوصاف المستويات الخمسة.
- النص العربي مرسوم بترتيب بصري، وكثير من الحروف المشكَّلة بلا ربط Unicode، فلا يُستخرج
  وصف المستويات آليًا بموثوقية. لذلك لا نستخرج الأوصاف؛ نحدد رقم صفحة كل مهارة فقط.
طريقة الفهرسة: يُقرأ عنوان أعلى كل صفحة بالحروف المربوطة فقط، ويُطابَق نمطًا مع أسماء المهارات.
الصفحات المطابقة «مراسٍ»؛ إن اتفقت كلها على إزاحة واحدة مع ترتيب ورقة الأولوية في قاعدة البيانات
وبلغ عددها الحد الأدنى، تُحسب صفحات بقية المهارات بالإزاحة نفسها. أي تعارض يلغي الفهرس.
"""

from __future__ import annotations

import re
import zlib

_STREAM = re.compile(rb"stream\r?\n")
_WS = b"\x00\t\n\x0c\r "
# رموز PDF خارج النصوص الحرفية: مسافات، تعليق، << و>>، نص ست عشري، أقواس المصفوفات، بداية نص حرفي،
# اسم، رمز عادي (عدد أو كلمة). أي بايت لا يبدأ رمزًا من هذه خطأ بنيوي.
_TOKEN = re.compile(rb"[\x00\t\n\x0c\r ]+|%[^\r\n]*|<<|>>|<[0-9A-Fa-f\x00\t\n\x0c\r ]*>|[\[\]{}]|\("
                    rb"|/[^\x00\t\n\x0c\r ()<>\[\]{}/%]*|[^\x00\t\n\x0c\r ()<>\[\]{}/%]+")
_STRING_SPECIAL = re.compile(rb"[\\()]")
_INT = re.compile(rb"\d+")
# بعد بيانات التيار بالطول المعلن: نهاية سطر اختيارية ثم endstream ثم endobj، ولا شيء آخر.
_STREAM_TAIL = re.compile(rb"(?:\r\n|\r|\n)?endstream[\x00\t\n\x0c\r ]*endobj")
_KEYWORDS = (b"obj", b"endobj", b"stream", b"endstream", b"xref", b"trailer", b"startxref")


class PdfError(ValueError):
    """ليس PDF صالحًا للقراءة بهذا القارئ."""


class _Body(bytes):
    """جسم كائن على المستوى الأعلى كما حدده التحليل الموضعي.
    gen جيله؛ entries مفاتيح قاموسه الأعلى وقيمها رموزًا ({اسم: (رمز،) أو (رقم، جيل، R)}) أو None إن لم
    يكن قاموسًا؛ plain رموز الجسم خارج أي قاموس أو مصفوفة؛ raw بيانات تياره الخام بالطول المتحقق."""
    gen = None
    entries = None
    plain = ()
    raw = None


def _string_end(data: bytes, pos: int) -> int:
    """نهاية النص الحرفي الذي يبدأ «(» عند pos: الأقواس متوازنة، و«\\» تهرّب البايت التالي."""
    depth, i = 0, pos
    while True:
        m = _STRING_SPECIAL.search(data, i)
        if not m:
            raise PdfError(f"نص حرفي بلا نهاية عند الموضع {pos}")
        if m.group(0) == b"\\":
            i = m.end() + 1
            continue
        depth += 1 if m.group(0) == b"(" else -1
        i = m.end()
        if depth == 0:
            return i


def _token(data: bytes, pos: int):
    """(الرمز، بدايته، نهايته) لأول رمز من pos بعد المسافات والتعليقات، و(None، …) عند نهاية الملف.
    النص الحرفي رمز واحد «(» ينتهي بقوسه المقابل، فلا يُقرأ ما بداخله كلمات."""
    n = len(data)
    while pos < n:
        m = _TOKEN.match(data, pos)
        if not m:
            raise PdfError(f"بايت غير متوقع في بنية PDF عند الموضع {pos}")
        tok = m.group(0)
        if tok[0] in _WS or tok[0] == 0x25:  # مسافة أو تعليق %
            pos = m.end()
            continue
        if tok == b"(":
            return tok, pos, _string_end(data, pos)
        return tok, pos, m.end()
    return None, n, n


def _entries(tokens: list) -> dict:
    """{مفتاح: قيمة} من رموز القاموس الأعلى. القيمة المركبة (قاموس أو مصفوفة) تُمثَّل بأول رمز لها."""
    out, i = {}, 0
    while i < len(tokens):
        key = tokens[i]
        if not key.startswith(b"/") or i + 1 >= len(tokens):
            raise PdfError("قاموس غير صالح البنية: مفتاح ليس اسمًا أو بلا قيمة")
        if tokens[i + 3:i + 4] == [b"R"] and _INT.fullmatch(tokens[i + 1]) and _INT.fullmatch(tokens[i + 2]):
            value, i = tuple(tokens[i + 1:i + 4]), i + 4
        else:
            value, i = (tokens[i + 1],), i + 2
        if key in out:
            raise PdfError(f"مفتاح مكرر في قاموس: {key.decode('latin-1')}")
        out[key] = value
    return out


def _read_body(data: bytes, pos: int, trailer: bool = False):
    """يقرأ رموز جسم كائن من pos (بعد «obj») حتى «endobj» أو «stream» خارج أي قاموس أو مصفوفة، أو
    (مع trailer) قاموسًا واحدًا. يعيد (الكلمة، بدايتها، نهايتها، entries، plain)."""
    depth = arrays = 0
    top, plain = [], []
    while True:
        tok, s, e = _token(data, pos)
        if tok is None:
            raise PdfError("كائن بلا نهاية endobj")
        pos = e
        if depth == 0 and arrays == 0 and tok in (b"endobj", b"stream") and not trailer:
            entries = _entries(top) if plain == [b"<<"] else None
            return tok, s, e, entries, plain
        if tok in _KEYWORDS:
            raise PdfError(f"الكلمة {tok.decode()} في غير موضعها عند الموضع {s}")
        if depth == 1 and arrays == 0 and tok != b">>":
            top.append(tok)
        if depth == 0 and arrays == 0:
            plain.append(tok)
        if tok == b"<<":
            depth += 1
        elif tok == b">>":
            depth -= 1
            if depth < 0:
                raise PdfError(f"«>>» بلا «<<» عند الموضع {s}")
            if trailer and depth == 0 and arrays == 0:
                return tok, s, e, _entries(top), plain
        elif tok == b"[":
            arrays += 1
        elif tok == b"]":
            arrays -= 1
            if arrays < 0:
                raise PdfError(f"«]» بلا «[» عند الموضع {s}")


def _fits(data: bytes, start: int, length: int) -> bool:
    return start + length <= len(data) and _STREAM_TAIL.match(data, start + length) is not None


def _stream_length(data: bytes, num: int, entries: dict, start: int, candidates: dict, pending: list) -> int:
    """طول تيار الكائن num بعد التحقق من حدوده. الطول غير المباشر يُفترض من أنماط «n g obj <عدد> endobj»
    في الملف (افتراض فقط، قد يقع داخل تيار أو نص)، ويُشترط أن يطابق حدود التيار قيمةٌ واحدة؛ ثم يُسجَّل
    في pending ليؤكَّد بعد التحليل الكامل بكائن حقيقي على المستوى الأعلى."""
    value = entries.get(b"/Length")
    if value is None:
        raise PdfError(f"طول تيار الكائن {num} لا يطابق حدوده: بلا /Length")
    if len(value) == 1 and _INT.fullmatch(value[0]):
        length = int(value[0])
        if not _fits(data, start, length):
            raise PdfError(f"طول تيار الكائن {num} لا يطابق حدوده: /Length {length} لا ينتهي عند endstream "
                           f"(البيانات الفعلية بعد بدايته {len(data) - start} بايت حتى نهاية الملف)")
        return length
    if len(value) == 3:
        key = (int(value[0]), int(value[1]))
        if key not in candidates:
            pattern = rb"(?<![0-9])%d[\x00\t\n\x0c\r ]+%d[\x00\t\n\x0c\r ]+obj[\x00\t\n\x0c\r ]*(\d+)[\x00\t\n\x0c\r ]*endobj" % key
            candidates[key] = {int(m.group(1)) for m in re.finditer(pattern, data)}
        fitting = {n for n in candidates[key] if _fits(data, start, n)}
        if len(fitting) != 1:
            raise PdfError(f"طول تيار الكائن {num} لا يطابق حدوده: /Length {key[0]} {key[1]} R "
                           + ("لا يُحل إلى عدد ينتهي عنده التيار" if not fitting else "يحتمل أكثر من طول"))
        length = fitting.pop()
        pending.append((num, key[0], key[1], length))
        return length
    raise PdfError(f"طول تيار الكائن {num} ليس عددًا ولا مرجعًا")


def _parse(data: bytes) -> dict:
    """تحليل موضعي صارم: الملف يُقرأ رمزًا رمزًا من بدايته، والكائن يبدأ حيث انتهى ما قبله فقط.

    بين الكائنات لا يُقبل إلا المسافات والتعليقات وجداول xref مع trailer وstartxref؛ وأي بايتات أخرى خطأ.
    بيانات التيار تُتجاوز بطولها المتحقق دون قراءتها رموزًا، والنصوص الحرفية والتعليقات رموز كاملة. لذلك
    لا يصير نص يشبه «12 0 obj … endobj» داخل تيار أو نص أو تعليق كائنًا، ولا يُستخدم لحل طول.
    """
    objs, pending, candidates, pos = {}, [], {}, 0
    while True:
        tok, s, e = _token(data, pos)
        if tok is None:
            break
        if tok == b"startxref":
            tok, s, e = _token(data, e)
            if tok is None or not _INT.fullmatch(tok):
                raise PdfError("startxref بلا موضع")
            pos = e
            continue
        if tok == b"xref":
            while True:
                tok, s, e = _token(data, e)
                if tok is None:
                    raise PdfError("جدول xref بلا trailer")
                if tok == b"trailer":
                    break
                if not (_INT.fullmatch(tok) or tok in (b"f", b"n")):
                    raise PdfError(f"مدخل غير صالح في جدول xref عند الموضع {s}")
        if tok == b"trailer":
            _, _, pos, entries, _ = _read_body(data, e, trailer=True)
            if b"/Encrypt" in entries:
                raise PdfError("الملف مشفّر (/Encrypt)، وهذا القارئ لا يدعم PDF المشفّر")
            continue
        gen_tok, _, e2 = _token(data, e) if _INT.fullmatch(tok) else (None, 0, 0)
        kw, _, e3 = _token(data, e2) if gen_tok is not None and _INT.fullmatch(gen_tok) else (None, 0, 0)
        if kw != b"obj":
            raise PdfError(f"بايتات غير متوقعة بين الكائنات عند الموضع {s}: {tok[:24]!r}")
        num, gen = int(tok), int(gen_tok)
        word, ws, we, entries, plain = _read_body(data, e3)
        if word == b"endobj":
            body, pos = _Body(data[e3:ws]), we
        else:
            eol = 2 if data[we:we + 2] == b"\r\n" else 1 if data[we:we + 1] == b"\n" else 0
            if not eol:
                raise PdfError(f"كلمة stream في الكائن {num} لا تتبعها نهاية سطر صحيحة")
            if entries is None:
                raise PdfError(f"تيار الكائن {num} بلا قاموس")
            start = we + eol
            length = _stream_length(data, num, entries, start, candidates, pending)
            tail = _STREAM_TAIL.match(data, start + length)
            body = _Body(data[e3:tail.end() - len(b"endobj")])
            body.raw = data[start:start + length]
            pos = tail.end()
        body.gen, body.entries, body.plain = gen, entries, tuple(plain)
        objs[num] = body
    for owner, ref, ref_gen, length in pending:
        target = objs.get(ref)
        if (target is None or target.gen != ref_gen or len(target.plain) != 1
                or not _INT.fullmatch(target.plain[0]) or int(target.plain[0]) != length):
            raise PdfError(f"طول تيار الكائن {owner} يشير إلى {ref} {ref_gen} R، ولا يوجد كائن مستقل حقيقي بهذا الرقم "
                           f"والجيل قيمته {length}؛ نص يشبه كائنًا داخل تيار أو نص أو تعليق لا يُعد كائنًا")
    for body in objs.values():
        if body.entries and body.entries.get(b"/Type") == (b"/XRef",) and b"/Encrypt" in body.entries:
            raise PdfError("الملف مشفّر (/Encrypt)، وهذا القارئ لا يدعم PDF المشفّر")
    return objs


_OBJ_START = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")
_DIRECT_LENGTH = re.compile(rb"/Length\s+(\d+)(?!\d)(?!\s+\d+\s+R)")


def _scan_loose(data: bytes) -> dict:
    """قراءة متسامحة للاستخراج فقط، حين يتعذر التحليل الموضعي: بحث نصي عن الكائنات، والتيار بطوله المباشر
    إن طابق حدوده وإلا بحدود endstream/endobj النصية. لا يستخدمها التحقق الصارم أبدًا."""
    objs, pos = {}, 0
    for m in _OBJ_START.finditer(data):
        if m.start() < pos:
            continue
        num, start = int(m.group(1)), m.end()
        end = data.find(b"endobj", start)
        if end < 0:
            break
        s = _STREAM.search(data, start, end)
        length = _DIRECT_LENGTH.search(data, start, s.start()) if s else None
        if length and _fits(data, s.end(), int(length.group(1))):
            tail = _STREAM_TAIL.match(data, s.end() + int(length.group(1)))
            body = _Body(data[start:tail.end() - len(b"endobj")])
            body.raw = data[s.end():s.end() + int(length.group(1))]
            objs[num], pos = body, tail.end()
        else:
            objs[num], pos = _Body(data[start:end]), end + len(b"endobj")
    return objs


def _objects(data: bytes, strict: bool = False) -> dict:
    """{رقم الكائن: جسمه} للكائنات على المستوى الأعلى.

    strict: التحليل الموضعي وحده (_parse)، وأي خلل بنيوي يرفض الملف، دون رجوع إلى قراءة متسامحة.
    دون strict (استخراج النص من ملف اجتاز التحقق): التحليل نفسه، ثم القراءة المتسامحة إن تعذر.
    """
    try:
        return _parse(data)
    except PdfError:
        if strict:
            raise
        return _scan_loose(data)


def _stream(body: bytes, strict: bool = False):
    """بيانات التيار بعد فك FlateDecode، أو None إن تعذر.

    strict: يشترط تيارًا حدوده متحققة بالتحليل الموضعي، ومرشحًا مدعومًا صراحة (لا مرشح، أو FlateDecode
    وحده دون DecodeParms)، واكتمال تيار zlib (وصول علامة نهايته) دون بيانات زائدة بعدها داخل الطول
    المعلن إلا نهاية سطر. دون ذلك قد يعيد decompressobj نصًا جزئيًا من تيار مقطوع دون استثناء.
    """
    m = _STREAM.search(body)
    if not m:
        return None
    raw = getattr(body, "raw", None)
    entries = getattr(body, "entries", None)
    if strict:
        if raw is None or entries is None or b"/DecodeParms" in entries or b"/DP" in entries:
            return None
        if entries.get(b"/Filter", (b"/FlateDecode",)) != (b"/FlateDecode",):
            return None  # مرشح آخر أو سلسلة مرشحات: غير مدعوم
        flate = b"/Filter" in entries
    else:
        if raw is None:
            raw = body[m.end():]
            raw = raw[:raw.rfind(b"endstream")].rstrip(b"\r\n")
        flate = b"/FlateDecode" in body[:m.start()]
    if flate:
        d = zlib.decompressobj()
        try:
            out = d.decompress(raw)
        except zlib.error:
            return None
        if strict and (not d.eof or d.unused_data.strip(b"\r\n")):
            return None  # تيار مقطوع (لم تصل نهاية zlib) أو بيانات غريبة بعد نهايته
        return out
    return raw


def _objstm(body: bytes, strict: bool):
    """(N، First) إن كان الكائن تيار كائنات (أي منهما None إن غاب أو لم يكن عددًا)، وإلا None.
    التحقق الصارم يحدده من قاموسه المحلَّل (/Type /ObjStm)، لا من نص في أول الجسم."""
    entries = getattr(body, "entries", None)
    if entries is not None:
        if entries.get(b"/Type") != (b"/ObjStm",):
            return None
        return tuple(int(v[0]) if len(v) == 1 and _INT.fullmatch(v[0]) else None
                     for v in (entries.get(b"/N", ()), entries.get(b"/First", ())))
    if strict or b"/ObjStm" not in body[:400]:
        return None
    n, first = re.search(rb"/N\s+(\d+)", body), re.search(rb"/First\s+(\d+)", body)
    return (int(n.group(1)) if n else None, int(first.group(1)) if first else None)


def load(data: bytes, strict: bool = False) -> dict:
    """{رقم الكائن: جسمه} بما فيها الكائنات داخل تيارات الكائنات (ObjStm)."""
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
        raise PdfError("الملف لا يبدأ بترويسة PDF أو لا ينتهي بعلامة %%EOF")
    objs = _objects(data, strict)
    for body in list(objs.values()):
        info = _objstm(body, strict)
        if info is None:
            continue
        payload, (n, first) = _stream(body, strict), info
        try:
            if payload is None or n is None or first is None:
                raise ValueError("payload")
            head = payload[:first].split()
            pairs = [(int(head[i]), int(head[i + 1])) for i in range(0, 2 * n, 2)]
        except (ValueError, IndexError):
            if strict:  # تيار كائنات مقطوع أو تالف يعني كائنات ناقصة بصمت
                raise PdfError("تيار كائنات (ObjStm) غير قابل للقراءة كاملًا") from None
            continue
        for i, (num, off) in enumerate(pairs):
            end = pairs[i + 1][1] if i + 1 < n else len(payload) - first
            objs.setdefault(num, payload[first + off:first + end])
    if not objs:
        raise PdfError("لا كائنات PDF قابلة للقراءة")
    return objs


def _ref(body, key):
    m = re.search(re.escape(key) + rb"\s+(\d+)\s+0\s+R", body)
    return int(m.group(1)) if m else None


def _refs(body, key):
    m = re.search(re.escape(key) + rb"\s*\[(.*?)\]", body, re.S)
    if m:
        return [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", m.group(1))]
    r = _ref(body, key)
    return [r] if r else []


_PAGE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")
_PAGES = re.compile(rb"/Type\s*/Pages(?![a-zA-Z])")


def pages(objs: dict) -> list:
    """أرقام كائنات الصفحات بالترتيب. كل ورقة في الشجرة يجب أن تكون /Type /Page صراحة،
    وعدد الأوراق يجب أن يساوي /Count المعلن في جذر الشجرة؛ وإلا PdfError."""
    catalog = next((v for v in objs.values() if re.search(rb"/Type\s*/Catalog", v)), None)
    if catalog is None:
        raise PdfError("لا يوجد Catalog")
    root = _ref(catalog, b"/Pages")
    if root not in objs or not _PAGES.search(objs[root]):
        raise PdfError("جذر شجرة الصفحات ليس /Type /Pages")
    out, seen = [], set()

    def walk(num):
        if num in seen:
            raise PdfError(f"شجرة الصفحات فيها دورة عند الكائن {num}")
        if num not in objs:
            raise PdfError(f"شجرة الصفحات تشير إلى كائن غير موجود {num}")
        seen.add(num)
        body = objs[num]
        if _PAGES.search(body):
            for kid in _refs(body, b"/Kids"):
                walk(kid)
        elif _PAGE.search(body):
            out.append(num)
        else:
            raise PdfError(f"الكائن {num} في شجرة الصفحات ليس صفحة ولا عقدة صفحات")

    walk(root)
    if not out:
        raise PdfError("شجرة الصفحات فارغة")
    count = re.search(rb"/Count\s+(\d+)", objs[root])
    if not count or int(count.group(1)) != len(out):
        raise PdfError(f"عدد الصفحات المعلن {count.group(1).decode() if count else 'غائب'} لا يساوي الصفحات الموجودة {len(out)}")
    return out


def validate_structure(data: bytes) -> dict:
    """تحقق بنيوي من PDF: شجرة صفحات صالحة، ولكل صفحة MediaBox (مباشر أو موروث)، ومحتوى قابل
    للقراءة في كل صفحة لها /Contents، ونص مرسوم في صفحة واحدة على الأقل.

    كل تيار محتوى وتيار كائنات يجب أن يُفك كاملًا، لا نصًا جزئيًا من تيار مقطوع.
    حدوده: لا يرسم الصفحات ولا يفك الخطوط والصور ولا يتحقق من صحة النص؛ يثبت أن الملف PDF متماسك
    البنية بصفحات حقيقية ومحتوى كامل، لا أنه الوثيقة الرسمية الصحيحة. عدد الصفحات لا يُفرض رقمًا ثابتًا.
    """
    objs = load(data, strict=True)
    page_list = pages(objs)
    parents = {}
    for num, body in objs.items():
        if _PAGES.search(body):
            for kid in _refs(body, b"/Kids"):
                parents[kid] = num
    with_text = 0
    for num in page_list:
        node, box = num, False
        while node is not None and not box:
            box = b"/MediaBox" in objs.get(node, b"")
            node = parents.get(node)
        if not box:
            raise PdfError(f"الصفحة {num} بلا MediaBox")
        decoded = []
        for c in _refs(objs[num], b"/Contents"):
            stream = _stream(objs[c], strict=True) if c in objs else None
            if stream is None:
                raise PdfError(f"محتوى الصفحة {num} غير قابل للقراءة كاملًا (كائن {c}: مفقود أو مقطوع أو تالف أو بمرشح غير مدعوم)")
            decoded.append(stream)
        if any(re.search(rb"T[Jj]", s) for s in decoded):
            with_text += 1
    if not with_text:
        raise PdfError("لا توجد صفحة فيها نص مرسوم")
    return {"pages": len(page_list), "pages_with_text": with_text}


def _cmap(data: bytes) -> dict:
    m = {}
    for block in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
        for a, u in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            m[int(a, 16)] = bytes.fromhex(u.decode()).decode("utf-16-be", "replace")
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", data, re.S):
        for a, z, u in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            dst = bytes.fromhex(u.decode()).decode("utf-16-be", "replace")
            for i in range(int(a, 16), int(z, 16) + 1):
                m[i] = dst[:-1] + chr(ord(dst[-1]) + i - int(a, 16))
    return m


def _fonts(objs, page):
    body = objs[page]
    res = objs.get(_ref(body, b"/Resources"), body)
    fm = re.search(rb"/Font\s*(<<.*?>>|\d+\s+0\s+R)", res, re.S)
    if not fm:
        return {}
    fd = fm.group(1)
    if fd[:1].isdigit():
        fd = objs.get(int(fd.split()[0]), b"")
    out = {}
    for name, num in re.findall(rb"/([A-Za-z0-9_+.-]+)\s+(\d+)\s+0\s+R", fd):
        font = objs.get(int(num), b"")
        tu = _ref(font, b"/ToUnicode")
        data = _stream(objs[tu]) if tu in objs else None
        out[name.decode()] = (_cmap(data) if data else {}, b"/Type0" in font)
    return out


_TOKENS = re.compile(
    rb"<<[^>]*?/MCID\s+(\d+)[^>]*>>\s*BDC"                     # 1 بداية مقطع موسوم
    rb"|/([A-Za-z0-9_+.-]+)\s+([\d.]+)\s+Tf"                   # 2,3 الخط وحجمه
    rb"|\[(.*?)\]\s*TJ"                                         # 4 مصفوفة نص
    rb"|(<[0-9A-Fa-f]*>)\s*Tj"                                  # 5 نص ست عشري
    rb"|\bEMC\b"
    rb"|[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+([-\d.]+)\s+([-\d.]+)\s+Tm",  # 6,7 الموضع
    re.S)


def page_spans(objs, page) -> list:
    """[(حجم الخط، y، النص بترتيب الرسم)] لكل مقطع موسوم؛ الحروف غير المربوطة تظهر «?»."""
    fonts = _fonts(objs, page)
    data = b"\n".join(_stream(objs[c]) or b"" for c in _refs(objs[page], b"/Contents") if c in objs)
    spans, buf, font, size, y = [], [], None, 0.0, 0.0

    def decode(hexes):
        cmap, two = fonts.get(font, ({}, False))
        step = 4 if two else 2
        return "".join(cmap.get(int(h[i:i + step], 16), "?") for h in hexes for i in range(0, len(h), step))

    def flush():
        if buf:
            spans.append((size, y, "".join(buf)))
            buf.clear()

    for m in _TOKENS.finditer(data):
        if m.group(1) is not None or m.group(0) == b"EMC":
            flush()
        elif m.group(2):
            font, size = m.group(2).decode(), float(m.group(3))
        elif m.group(4) is not None:
            buf.append(decode([h.decode() for h in re.findall(rb"<([0-9A-Fa-f]+)>", m.group(4))]))
        elif m.group(5):
            buf.append(decode([m.group(5)[1:-1].decode()]))
        elif m.group(6):
            y = float(m.group(7))
    flush()
    return spans


def _title_pattern(visual: str):
    """نمط مطابقة من نص مرسوم بصريًا: يُعكس، و«?» تقبل أي حرف. None إن قلّت الحروف المعروفة."""
    logical = visual[::-1].strip()
    known = sum(1 for ch in logical if ch != "?")
    if len(logical) < 4 or known < len(logical) * 0.4:
        return None
    return re.compile("^" + "".join("." if ch == "?" else re.escape(ch) for ch in logical) + "$")


def dictionary_index(data: bytes, priority_order: list, all_names: list, *, min_anchors=20, max_conflicts=2,
                     title_min_y=740.0, title_min_size=15.0) -> dict:
    """فهرس صفحات المهارات ذات الأولوية في القاموس، أو {"pages": {}, "reason": ...} عند عدم الثقة."""
    objs = load(data)
    page_list = pages(objs)
    anchors = {}
    for number, page in enumerate(page_list, 1):
        found = set()
        for size, y, text in page_spans(objs, page):
            if y < title_min_y or size < title_min_size:
                continue
            pattern = _title_pattern(text)
            if pattern:
                found |= {n for n in all_names if pattern.match(n)}
        if len(found) == 1:
            anchors[number] = found.pop()
    position = {name: i for i, name in enumerate(priority_order)}
    offsets = {}
    for number, name in anchors.items():
        if name in position:
            offsets.setdefault(number - position[name], []).append(number)
    result = {"page_count": len(page_list), "anchors": len(anchors),
              "priority_anchors": sum(len(v) for v in offsets.values()), "offsets": {str(k): len(v) for k, v in offsets.items()}}
    if len(offsets) != 1:
        return result | {"pages": {}, "reason": f"المراسي لا تتفق على إزاحة واحدة: {result['offsets']}"}
    (offset, matched), = offsets.items()
    if len(matched) < min_anchors:
        return result | {"pages": {}, "reason": f"مراسٍ قليلة ({len(matched)} من حد أدنى {min_anchors})"}
    last = offset + len(priority_order) - 1
    if offset < 1 or last > len(page_list):
        return result | {"pages": {}, "reason": "الإزاحة تتجاوز صفحات الملف"}
    computed = {offset + i: name for i, name in enumerate(priority_order)}
    # مرساة تخالف الاسم المحسوب (وليست بدايته لعنوان ملتف) تعني اختلاف الاسم بين القاموس وقاعدة
    # البيانات في تلك الصفحة: تُستبعد الصفحة وحدها. أكثر من max_conflicts يلغي الفهرس كله.
    conflicts = {n: a for n, a in anchors.items() if n in computed and a != computed[n] and not computed[n].startswith(a)}
    result["conflicts"] = [{"page": n, "in_dictionary": a, "in_database": computed[n]} for n, a in sorted(conflicts.items())]
    if len(conflicts) > max_conflicts:
        return result | {"pages": {}, "reason": f"مراسٍ كثيرة تخالف الترتيب: {conflicts}"}
    # الصفحات التي قُرئ عنوانها فطابق الاسم (أو بدايته لعنوان ملتف)؛ البقية محسوبة بالترتيب فقط،
    # فلا يُوحى للمستخدم بتطابق حرفي بين العنوانين فيها.
    verified = sorted(n for n, a in anchors.items() if n in computed and n not in conflicts)
    return result | {"offset": offset, "reason": None, "verified_pages": verified,
                     "pages": {name: page for page, name in computed.items() if page not in conflicts}}


def page_count(data: bytes) -> int:
    return validate_structure(data)["pages"]
