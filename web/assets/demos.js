// تجارب «جرّب المجال»: أنشطة قصيرة من بوصلة ببيانات خيالية. ليست اختبارًا، وإكمالها لا يثبت كفاءة ولا ملاءمة،
// والخطأ فيها لا يعني شيئًا عن صاحبه: التلميح يساعد على المحاولة من جديد، دون عدّاد ولا عقوبة.
// كل تجربة أربع مراحل: الموقف، ثم جرّب (فعل ونتيجة فورية)، ثم «هذا في العمل الحقيقي»، ثم تمرين صغير يكمل التجربة.
// mount(root, {done, extra}): done() عند إكمال النشاط الأساسي، وextra() عند إكمال التمرين الإضافي (اختياري).

const h = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (n) => `<bdi class="num">${n}</bdi>`;
const ltr = (s) => `<bdi dir="ltr" class="ltr">${h(s)}</bdi>`;

function stages(situation, tryHtml, explain, extraTitle, extraHtml) {
  return `<ol class="demo-steps">
    <li class="stage"><h3 class="stage-title"><span class="stage-n">${num(1)}</span>الموقف</h3><p>${situation}</p></li>
    <li class="stage"><h3 class="stage-title"><span class="stage-n">${num(2)}</span>جرّب</h3>${tryHtml}</li>
    <li class="stage stage-explain" hidden><h3 class="stage-title"><span class="stage-n">${num(3)}</span>هذا في العمل الحقيقي</h3>
      <p>${explain}</p><p class="small muted">شرح مبسّط من بوصلة، وليس وصفًا رسميًا للمهنة.</p></li>
    <li class="stage stage-extra" hidden><h3 class="stage-title"><span class="stage-n">${num(4)}</span>تمرين صغير يكمل التجربة <span class="optional">اختياري</span></h3>
      <p class="small muted">${h(extraTitle)}</p>${extraHtml}</li>
  </ol>`;
}
function reveal(root) {
  for (const el of root.querySelectorAll(".stage-explain, .stage-extra")) if (el.hidden) { el.hidden = false; el.classList.add("appear"); }
}
function feedback(el, kind, html) {
  el.classList.remove("good", "hint");   // تبقى الأصناف الأساسية (main-fb/extra-fb) ليُعثر على العنصر لاحقًا
  el.classList.add(kind);
  el.innerHTML = html;
}

// ---------------------------------------------------------------------------
// البيانات: مبيعات مقهى خيالي في أسبوع واحد

const CAFE = [
  { day: "السبت", temp: 31, cold: 42, hot: 30 },
  { day: "الأحد", temp: 33, cold: 48, hot: 28 },
  { day: "الاثنين", temp: 38, cold: 71, hot: 22 },
  { day: "الثلاثاء", temp: 36, cold: 63, hot: 25 },
  { day: "الأربعاء", temp: 29, cold: 35, hot: 34 },
  { day: "الخميس", temp: 41, cold: 84, hot: 20 },
  { day: "الجمعة", temp: 34, cold: 55, hot: 41 },
];
// سجل الأسبوع التالي: صف مكرر (الثلاثاء أُدخل مرتين)، وصف ينقصه قياس الحرارة لكن مبيعاته صحيحة.
const LOG = [
  { k: "sat", day: "السبت", temp: "32", cold: 46 },
  { k: "sun", day: "الأحد", temp: "35", cold: 58 },
  { k: "tue", day: "الثلاثاء", temp: "37", cold: 66 },
  { k: "tue2", day: "الثلاثاء", temp: "37", cold: 66, dup: true },
  { k: "wed", day: "الأربعاء", temp: null, cold: 40 },
];

const countRows = (n) => n === 1 ? "صف واحد" : n === 2 ? "صفين" : `${n} صفوف`;

// يحكم على مجموعة البيانات الناتجة، لا على رقم صف بعينه: الصحيح أن تبقى نسخة واحدة من الثلاثاء المكرر،
// وأن تبقى الصفوف السليمة كلها، ومنها الأربعاء الناقص قياس حرارته. مصدّرة للاختبار.
export function judgeLog(excluded) {
  const kept = LOG.filter((r) => !excluded.has(r.k));
  if (!kept.length) return { ok: false, hint: "استبعدت كل الصفوف، فلا يبقى ما نحسب منه المتوسط. أعد الصفوف السليمة، واستبعد المكرر وحده." };
  const tuesdays = kept.filter((r) => r.day === "الثلاثاء").length;
  const validOut = LOG.filter((r) => excluded.has(r.k) && r.day !== "الثلاثاء");
  if (tuesdays === 0) return { ok: false, hint: "استبعدت صفّي الثلاثاء كليهما. أحدهما مكرر، لكن الآخر بيانات صحيحة يجب أن تبقى." };
  if (validOut.some((r) => r.k === "wed")) return { ok: false, hint: "صف الأربعاء ينقصه قياس الحرارة، لكن مبيعاته صحيحة. استبعاده يُضيع معلومة مفيدة." };
  if (validOut.length) return { ok: false, hint: `صف ${validOut[0].day} سليم ولا يتكرر. هل يوجد يوم أُدخل مرتين؟` };
  if (tuesdays === 2) return { ok: false, hint: "انظر إلى الأيام: هل يوجد يوم أُدخل مرتين بالقيم نفسها؟" };
  return { ok: true };
}

function dataDemo(root, { done, extra }) {
  let sort = "day", answered = false, cleaned = false;
  const excluded = new Set();
  const max = Math.max(...CAFE.map((r) => r.cold));
  root.innerHTML = stages(
    "تدير مقهى صغيرًا مع صديقك. يسألك: «متى نجهّز مشروبات باردة أكثر؟» لديكما جدول مبيعات أسبوع واحد.",
    `<div class="seg" role="group" aria-label="ترتيب الجدول">
      <span class="seg-label">رتّب حسب:</span>
      <button type="button" class="chip" data-sort="day">الأيام</button>
      <button type="button" class="chip" data-sort="cold">المشروبات الباردة</button>
      <button type="button" class="chip" data-sort="temp">الحرارة</button>
    </div>
    <div class="table-wrap"><table class="cafe">
      <caption class="sr-only">مبيعات مقهى خيالي خلال أسبوع</caption>
      <thead><tr><th scope="col">اليوم</th><th scope="col">الحرارة</th><th scope="col">مشروبات باردة</th><th scope="col">مشروبات حارة</th></tr></thead>
      <tbody class="cafe-rows"></tbody></table></div>
    <fieldset class="q"><legend>ما الذي يرافق ارتفاع المشروبات الباردة في هذا الجدول؟</legend>
      <div class="opts">
        <button type="button" class="opt" data-a="temp">ارتفاع الحرارة</button>
        <button type="button" class="opt" data-a="friday">يوم الجمعة</button>
        <button type="button" class="opt" data-a="hot">زيادة المشروبات الحارة</button>
      </div></fieldset>
    <div class="feedback main-fb" role="status" aria-live="polite"></div>`,
    "من يحلّل البيانات يرتّبها ويقارن أعمدتها ليجد نمطًا يساعد على قرار، مثل كمية التجهيز، ثم يختبر القرار ببيانات أكثر قبل تعميمه. وقبل التحليل كله: يتأكد أن البيانات نظيفة.",
    "صديقك أرسل سجل الأسبوع التالي، وفيه أخطاء إدخال. استبعد ما يجب استبعاده، وراقب المتوسط.",
    `<div class="table-wrap"><table class="cafe log">
      <caption class="sr-only">سجل الأسبوع التالي</caption>
      <thead><tr><th scope="col">استبعد</th><th scope="col">اليوم</th><th scope="col">الحرارة</th><th scope="col">مشروبات باردة</th></tr></thead>
      <tbody>${LOG.map((r) => `<tr data-row="${r.k}"><td><label class="check"><input type="checkbox" data-ex="${r.k}"><span class="sr-only">استبعد صف ${h(r.day)}${r.dup ? " (الثاني)" : ""}</span></label></td>
        <th scope="row">${h(r.day)}</th><td>${r.temp ? num(r.temp + "°") : '<span class="missing">غير مسجّلة</span>'}</td><td>${num(r.cold)}</td></tr>`).join("")}</tbody></table></div>
    <p class="metric">متوسط المشروبات الباردة يوميًا: <strong class="avg"></strong> <span class="avg-basis small muted"></span></p>
    <div class="feedback extra-fb" role="status" aria-live="polite"></div>`);

  const renderTable = () => {
    const rows = [...CAFE].sort((a, b) => sort === "cold" ? b.cold - a.cold : sort === "temp" ? b.temp - a.temp : CAFE.indexOf(a) - CAFE.indexOf(b));
    root.querySelector(".cafe-rows").innerHTML = rows.map((r) => `<tr>
        <th scope="row">${h(r.day)}</th><td>${num(r.temp + "°")}</td>
        <td><span class="bar" style="--w:${Math.round((r.cold / max) * 100)}" aria-hidden="true"></span>${num(r.cold)}</td><td>${num(r.hot)}</td></tr>`).join("");
    root.querySelectorAll("[data-sort]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sort === sort)));
  };
  const renderLog = () => {
    const kept = LOG.filter((r) => !excluded.has(r.k));
    // المتوسط بلا صفوف غير معرَّف، فلا يُعرض صفرًا: الصفر قيمة حقيقية ممكنة، وغياب الملاحظات شيء آخر.
    root.querySelector(".avg").innerHTML = kept.length ? num((kept.reduce((s, r) => s + r.cold, 0) / kept.length).toFixed(1)) : "غير متاح";
    root.querySelector(".avg-basis").textContent = kept.length ? `من ${countRows(kept.length)}` : "لا توجد صفوف لحسابه";
    root.querySelectorAll("[data-row]").forEach((tr) => tr.classList.toggle("is-excluded", excluded.has(tr.dataset.row)));
    const fb = root.querySelector(".extra-fb");
    const v = judgeLog(excluded);
    if (v.ok) {
      feedback(fb, "good", `<strong>نظيف الآن.</strong> الثلاثاء أُدخل مرتين بالقيم نفسها، فاستبعاد أي نسخة منه يكفي. التكرار كان يرفع المتوسط إلى ${num("55.2")} بدل ${num("52.5")}. وأبقيت الأربعاء لأن مبيعاته صحيحة، والناقص قياس الحرارة فقط. هذا هو «تنظيف البيانات».`);
      if (!cleaned) { cleaned = true; extra?.(); }
    } else {
      feedback(fb, "hint", v.hint);
    }
  };

  root.addEventListener("click", (e) => {
    const s = e.target.closest("[data-sort]");
    if (s) { sort = s.dataset.sort; renderTable(); return; }
    const a = e.target.closest("[data-a]");
    if (!a) return;
    root.querySelectorAll("[data-a]").forEach((b) => b.setAttribute("aria-pressed", String(b === a)));
    const fb = root.querySelector(".main-fb");
    if (a.dataset.a === "temp") {
      feedback(fb, "good", `<strong>هذا ما تقوله البيانات.</strong> أحرّ يومين، الخميس (${num("41°")}) والاثنين (${num("38°")})، هما الأعلى في المشروبات الباردة.<br><span class="caveat">انتبه: هذا ارتباط في أسبوع خيالي واحد، ولا يثبت وحده أن الحرارة هي السبب. يكفي لتجربة تجهيز كمية أكبر في الأيام الحارة، ثم مراقبة النتيجة.</span>`);
      if (!answered) { answered = true; reveal(root); done(); }
    } else {
      feedback(fb, "hint", a.dataset.a === "friday"
        ? "الجمعة فيه أعلى مبيعات حارة، لكنه ليس الأعلى في الباردة. رتّب الجدول حسب <strong>المشروبات الباردة</strong>، وانظر إلى عمود الحرارة."
        : "المشروبات الحارة تنخفض حين ترتفع الباردة تقريبًا. جرّب الترتيب حسب <strong>الحرارة</strong>.");
    }
  });
  root.addEventListener("change", (e) => {
    const c = e.target.closest("[data-ex]");
    if (!c) return;
    c.checked ? excluded.add(c.dataset.ex) : excluded.delete(c.dataset.ex);
    renderLog();
  });
  renderTable();
  root.querySelector(".avg").innerHTML = num((LOG.reduce((s, r) => s + r.cold, 0) / LOG.length).toFixed(1));
  root.querySelector(".avg-basis").textContent = `من ${countRows(LOG.length)}`;
}

// ---------------------------------------------------------------------------
// البرمجيات: قاعدة توصيل مجاني واختبارها، ثم شرط إضافي

const ORDERS = [40, 99, 100, 150, 250];
const OPS = { gt: { label: "أكبر من", f: (a, b) => a > b }, gte: { label: "أكبر من أو يساوي", f: (a, b) => a >= b }, lt: { label: "أقل من", f: (a, b) => a < b } };
const MEMBER_ORDERS = [{ x: 60, m: true }, { x: 120, m: false }, { x: 40, m: false }, { x: 100, m: true }];

// سياسة الأرقام في هذه التجربة: الحد بالريال عدد صحيح من 0 إلى 500، دون كسور. تُقبل الأرقام العربية المشرقية
// والفارسية وتُحوَّل إلى القيمة نفسها. الفارغ والكسر وما خرج عن المدى: أخطاء تُشرح، ولا تُجرَّب القاعدة بها.
const LIMIT_MIN = 0, LIMIT_MAX = 500;
export function parseLimit(text) {
  const t = String(text ?? "").trim()
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
    .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06F0))
    .replace(/[٫,]/g, ".").replace(/^−/, "-");
  if (!t) return { error: "اكتب مبلغًا بالريال، مثل 100." };
  if (!/^-?\d+(\.\d+)?$/.test(t)) return { error: "اكتب أرقامًا فقط، مثل 100." };
  // افحص النص قبل التحويل: Number قد يقرّب كسرًا طويلًا إلى عدد صحيح.
  if (/[1-9]/.test(t.split(".")[1] || "")) return { error: "المبلغ هنا بالريال دون كسور. اكتب عددًا صحيحًا، مثل 100." };
  const v = Number(t);
  if (v < LIMIT_MIN || v > LIMIT_MAX) return { error: `اكتب مبلغًا من ${LIMIT_MIN} إلى ${LIMIT_MAX} ريال.` };
  return { value: v };
}

function softwareDemo(root, { done, extra }) {
  let op = "gt", limit = 100, join = "and", finished = false, extraDone = false, invalid = null;
  const ruleOk = (x) => OPS[op].f(x, limit);
  root.innerHTML = stages(
    "متجر إلكتروني صغير طلب منك: «التوصيل مجاني للطلبات من 100 ريال فأكثر». كتب زميلك القاعدة، لكن فيها خطأ صغير.",
    `<div class="rule" role="group" aria-label="القاعدة">
      <span>إذا كان مبلغ الطلب</span>
      <label class="sr-only" for="rule-op">المقارنة</label>
      <select id="rule-op">${Object.entries(OPS).map(([k, o]) => `<option value="${k}">${o.label}</option>`).join("")}</select>
      <span class="stepper">
        <button type="button" class="chip" data-step="-10" aria-label="أنقص 10">−</button>
        <label class="sr-only" for="rule-limit">المبلغ بالريال، عدد صحيح من 0 إلى 500</label>
        <input id="rule-limit" lang="en" dir="ltr" type="text" inputmode="numeric" autocomplete="off" spellcheck="false" value="${limit}" aria-describedby="rule-error rule-now">
        <button type="button" class="chip" data-step="10" aria-label="زِد 10">+</button>
      </span>
      <span>ريال، فالتوصيل مجاني.</span>
    </div>
    <p class="field-error" id="rule-error" hidden></p>
    <p class="rule-now small" id="rule-now"></p>
    <ul class="tests" aria-label="الطلبات التجريبية"></ul>
    <div class="feedback main-fb" role="status" aria-live="polite"></div>`,
    "المبرمج يحوّل طلبًا مكتوبًا بلغة الناس إلى قاعدة دقيقة لا تحتمل التأويل، ثم يختبرها بحالات مختارة، خصوصًا «الحالات الحدّية» مثل 100 بالضبط، حيث تختبئ أكثر الأخطاء.",
    "طلب المتجر شرطًا جديدًا: «والتوصيل مجاني أيضًا لأعضاء النادي، مهما كان المبلغ». اختر الرابط الصحيح بين الشرطين.",
    `<div class="rule" role="group" aria-label="القاعدة الموسّعة">
      <span>إذا كان المبلغ ${OPS.gte.label} 100</span>
      <label class="sr-only" for="rule-join">الرابط بين الشرطين</label>
      <select id="rule-join"><option value="and">و</option><option value="or">أو</option></select>
      <span>كان العميل عضوًا في النادي، فالتوصيل مجاني.</span>
    </div>
    <ul class="tests member-tests" aria-label="طلبات الأعضاء التجريبية"></ul>
    <div class="feedback extra-fb" role="status" aria-live="polite"></div>`);
  const sel = root.querySelector("#rule-op"), input = root.querySelector("#rule-limit"), joinSel = root.querySelector("#rule-join");
  sel.value = op;
  const testRow = (ok, text) => `<li class="${ok ? "pass" : "fail"}"><span class="mark" aria-hidden="true">${ok ? "✓" : "✗"}</span><span>${text}${ok ? "" : " — لا يطابق المطلوب"}</span></li>`;
  const render = () => {
    const err = root.querySelector("#rule-error"), now = root.querySelector("#rule-now"), fb = root.querySelector(".main-fb");
    input.setAttribute("aria-invalid", String(!!invalid));
    err.hidden = !invalid;
    err.textContent = invalid || "";
    if (invalid) {   // لا تُجرَّب القاعدة بقيمة لم يكتبها المستخدم: تبقى غير مكتملة حتى يُصحَّح المبلغ
      now.textContent = "القاعدة غير مكتملة، فلم نجرّبها على الطلبات.";
      root.querySelector(".tests").innerHTML = "";
      feedback(fb, "hint", "صحّح المبلغ لنجرّب القاعدة على الطلبات.");
      return;
    }
    now.innerHTML = `القاعدة الآن: إذا كان مبلغ الطلب <strong>${OPS[op].label} ${num(limit)}</strong> ريال، فالتوصيل مجاني.`;
    const results = ORDERS.map((x) => ({ x, want: x >= 100, got: ruleOk(x) }));
    const passed = results.filter((r) => r.want === r.got).length;
    root.querySelector(".tests").innerHTML = results.map((r) => testRow(r.want === r.got,
      `طلب بـ${num(r.x)} ريال: المطلوب <strong>${r.want ? "مجاني" : "برسوم"}</strong>، والقاعدة تعطي <strong>${r.got ? "مجاني" : "برسوم"}</strong>`)).join("");
    if (passed === ORDERS.length) {
      feedback(fb, "good", "<strong>تعمل القاعدة في الطلبات الخمسة كلها.</strong> لاحظ أن طلب 100 بالضبط هو الذي كشف الخطأ.");
      if (!finished) { finished = true; reveal(root); done(); }
    } else {
      const failing = ORDERS.length - passed;
      feedback(fb, "hint", failing === 1
        ? "طلب واحد لا يطابق المطلوب، وهو المعلَّم بـ✗. ماذا تقول القاعدة عنه، وماذا يريد المتجر؟"
        : `${failing === 2 ? "طلبان لا يطابقان" : `${num(failing)} طلبات لا تطابق`} المطلوب، وهي المعلَّمة بـ✗. ماذا تقول القاعدة عنها، وماذا يريد المتجر؟`);
    }
  };
  const renderMember = () => {
    const free = (o) => join === "or" ? (o.x >= 100 || o.m) : (o.x >= 100 && o.m);
    const results = MEMBER_ORDERS.map((o) => ({ ...o, want: o.x >= 100 || o.m, got: free(o) }));
    root.querySelector(".member-tests").innerHTML = results.map((r) => testRow(r.want === r.got,
      `طلب بـ${num(r.x)} ريال من ${r.m ? "عضو" : "غير عضو"}: المطلوب <strong>${r.want ? "مجاني" : "برسوم"}</strong>، والقاعدة تعطي <strong>${r.got ? "مجاني" : "برسوم"}</strong>`)).join("");
    const fb = root.querySelector(".extra-fb");
    if (results.every((r) => r.want === r.got)) {
      feedback(fb, "good", "<strong>صحيح: «أو».</strong> يكفي أن يتحقق أحد الشرطين. «و» تشترط الاثنين معًا، فيدفع العضو صاحب الطلب الصغير. اختيار الرابط الصحيح بين الشروط من أكثر ما يمارسه المبرمج.");
      if (!extraDone) { extraDone = true; extra?.(); }
    } else {
      feedback(fb, "hint", "مع «و» يجب أن يتحقق الشرطان معًا. هل هذا ما طلبه المتجر لعضو طلبه 60 ريالًا؟");
    }
  };
  sel.addEventListener("change", () => { op = sel.value; render(); });
  joinSel.addEventListener("change", () => { join = joinSel.value; renderMember(); });
  // ما يكتبه المستخدم يبقى كما كتبه (لا تصحيح خفي أثناء الكتابة)، والقيمة الصالحة وحدها تُجرَّب.
  input.addEventListener("input", () => {
    const r = parseLimit(input.value);
    invalid = r.error || null;
    if (!invalid) limit = r.value;
    render();
  });
  root.addEventListener("click", (e) => {
    const b = e.target.closest("[data-step]");
    if (!b) return;
    limit = Math.max(LIMIT_MIN, Math.min(LIMIT_MAX, limit + Number(b.dataset.step)));   // من آخر قيمة صالحة
    invalid = null;
    input.value = String(limit); render();
  });
  render(); renderMember();
}

// ---------------------------------------------------------------------------
// التصميم: بطاقة دعوة واضحة، والوضوح محسوب بنسبة التباين في WCAG

const THEMES = {
  sand: { label: "كحلي على رملي", bg: "#F6EAD1", fg: "#102A3A", accent: "#0E5E63" },
  mist: { label: "رمادي على أبيض", bg: "#FFFFFF", fg: "#B5BCC2", accent: "#C9CED3" },
  gold: { label: "أبيض على ذهبي", bg: "#D9A441", fg: "#FFFFFF", accent: "#FFF6E3" },
  teal: { label: "كريمي على تركواز", bg: "#0E5E63", fg: "#F6F3EC", accent: "#F4E7CC" },
};
const SIZES = { s: { label: "صغير", px: 18 }, m: { label: "متوسط", px: 26 }, l: { label: "كبير", px: 34 } };
const BUTTONS = {
  teal: { label: "تركوازي", bg: "#0E5E63", fg: "#FFFFFF" },
  gold: { label: "ذهبي", bg: "#C8902E", fg: "#102A3A" },
  sand: { label: "رملي فاتح", bg: "#F4E7CC", fg: "#102A3A" },
  coral: { label: "مرجاني", bg: "#B4541D", fg: "#FFFFFF" },
};

function luminance(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
export function contrast(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

function designDemo(root, { done, extra }) {
  let theme = "mist", size = "s", align = "right", button = null, finished = false, extraDone = false;
  const group = (name, label, items, cur) => `<div class="seg" role="group" aria-label="${label}"><span class="seg-label">${label}:</span>
    ${Object.entries(items).map(([k, v]) => `<button type="button" class="chip" data-${name}="${k}" aria-pressed="${k === cur}">${v.label ?? v}</button>`).join("")}</div>`;
  root.innerHTML = stages(
    "جمعية طلابية تريد بطاقة دعوة إلى «يوم المهن الرقمية» تُنشر على الهواتف وتُعلّق في الممرات. المسودة الحالية باهتة.",
    `<div class="design-grid">
      <div class="controls"></div>
      <figure class="invite-wrap"><div class="invite"><p class="i-kicker">دعوة</p><p class="i-title">يوم المهن الرقمية</p>
        <p class="i-body">الخميس، الساعة ${num(5)} مساءً · قاعة المكتبة</p><span class="i-btn" hidden>سجّل حضورك</span></div>
        <figcaption class="small muted">معاينة مباشرة لبطاقة خيالية</figcaption></figure>
    </div>
    <ul class="goals" aria-label="هدفا المهمة"></ul>
    <div class="feedback main-fb" role="status" aria-live="polite"></div>`,
    "المصمم يوازن بين الجمال والوضوح. يستخدم قواعد قابلة للقياس، مثل نسبة التباين بين النص والخلفية، حتى يقرأ التصميم الجميع، ومنهم من ضعف بصره أو يقرأ في ضوء الشمس.",
    "أضف إلى البطاقة زر «سجّل حضورك». يجب أن يتميز الزر عن خلفية البطاقة، ويُقرأ نصه بوضوح.",
    `${group("button", "لون الزر", BUTTONS, null)}<ul class="goals button-goals" aria-label="هدفا الزر"></ul>
    <div class="feedback extra-fb" role="status" aria-live="polite"></div>`);

  const goalRow = (ok, text) => `<li class="${ok ? "pass" : "fail"}"><span class="mark" aria-hidden="true">${ok ? "✓" : "✗"}</span><span>${text}</span></li>`;
  const render = () => {
    const t = THEMES[theme], ratio = contrast(t.fg, t.bg);
    root.querySelector(".controls").innerHTML = group("theme", "الألوان", THEMES, theme) + group("size", "حجم العنوان", SIZES, size)
      + group("align", "المحاذاة", { right: "يمين", center: "وسط" }, align);
    const card = root.querySelector(".invite");
    Object.assign(card.style, { background: t.bg, color: t.fg, textAlign: align });
    card.querySelector(".i-kicker").style.color = t.accent;
    card.querySelector(".i-title").style.fontSize = `${SIZES[size].px}px`;
    const readable = ratio >= 4.5, hierarchy = size !== "s";
    root.querySelector(".goals").innerHTML =
      goalRow(readable, `النص سهل القراءة: نسبة التباين ${num(ratio.toFixed(1) + ":1")} ${readable ? "(تبلغ 4.5:1 أو أكثر)" : "(أقل من 4.5:1 الموصى بها للنص العادي)"}`)
      + goalRow(hierarchy, `العنوان أوضح من التفاصيل: ${hierarchy ? "حجمه أكبر بوضوح" : "حجمه قريب من حجم التفاصيل"}`);
    const fb = root.querySelector(".main-fb");
    if (readable && hierarchy) {
      feedback(fb, "good", "<strong>تحقق الهدفان.</strong> لاحظ كيف تغيّر الإحساس بالبطاقة حين صار العنوان أكبر والتباين أعلى.");
      if (!finished) { finished = true; reveal(root); done(); }
    } else {
      feedback(fb, "hint", "جرّب ألوانًا أخرى وحجمًا آخر، وراقب الهدفين. لا يوجد اختيار واحد صحيح.");
    }
    renderButton();
  };
  const renderButton = () => {
    const pill = root.querySelector(".i-btn"), t = THEMES[theme];
    if (!button) { pill.hidden = true; root.querySelector(".button-goals").innerHTML = ""; return; }
    const b = BUTTONS[button];
    Object.assign(pill.style, { background: b.bg, color: b.fg });
    pill.hidden = false;
    const edge = contrast(b.bg, t.bg), label = contrast(b.fg, b.bg);
    root.querySelector(".button-goals").innerHTML =
      goalRow(edge >= 3, `الزر يتميز عن خلفية البطاقة: ${num(edge.toFixed(1) + ":1")} ${edge >= 3 ? "(3:1 أو أكثر)" : "(أقل من 3:1)"}`)
      + goalRow(label >= 4.5, `نص الزر واضح: ${num(label.toFixed(1) + ":1")}`);
    const fb = root.querySelector(".extra-fb");
    if (edge >= 3 && label >= 4.5) {
      feedback(fb, "good", "<strong>زر واضح.</strong> العناصر التي يُضغط عليها تحتاج تباينًا مع ما حولها (3:1 على الأقل) لا مع نصها فقط.");
      if (!extraDone) { extraDone = true; extra?.(); }
    } else {
      feedback(fb, "hint", edge < 3 ? "الزر يذوب في خلفية البطاقة. جرّب لونًا أبعد عنها." : "نص الزر صعب القراءة على هذا اللون.");
    }
  };
  root.addEventListener("click", (e) => {
    const b = e.target.closest("[data-theme],[data-size],[data-align],[data-button]");
    if (!b) return;
    const key = Object.keys(b.dataset)[0];
    if (key === "button") {
      button = b.dataset.button;
      root.querySelectorAll("[data-button]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      renderButton();
      return;
    }
    if (key === "theme") theme = b.dataset.theme;
    if (key === "size") size = b.dataset.size;
    if (key === "align") align = b.dataset.align;
    render();
    root.querySelector(`[data-${key}="${b.dataset[key]}"]`)?.focus();
  });
  render();
}

// ---------------------------------------------------------------------------
// الأمن السيبراني: رسالة احتيال خيالية، ثم قراءة الروابط

const PARTS = [
  { k: "greet", text: "عميلنا العزيز،", sign: false, why: "تحية عامة. ليست علامة وحدها، لكن الجهات تخاطبك غالبًا باسمك." },
  { k: "claim", text: "تم إيقاف بطاقتك مؤقتًا.", sign: false, why: "ادعاء مقلق، لكنه وحده لا يكفي للحكم. ابحث عما يطلبه منك." },
  { k: "urgent", text: "حدّث بياناتك خلال ساعة واحدة وإلا أُغلق حسابك نهائيًا", sign: true, why: "استعجال وتهديد: يدفعانك للتصرف قبل أن تفكر." },
  { k: "link", text: "عبر الرابط: masrif-almithal.verify-login.example", sign: true, why: "الرابط ليس عنوان الجهة الرسمي، وفيه كلمات مثل verify-login لإيهامك." },
  { k: "otp", text: "ثم أرسل رمز التحقق الذي سيصلك.", sign: true, why: "لا تطلب أي جهة موثوقة رمز التحقق. من يملكه يستطيع الدخول باسمك." },
];
const LINKS = [
  { k: "official", url: "https://masrif-almithal.example/login", ok: true, why: "اسم النطاق ينتهي بـ masrif-almithal.example، وهو العنوان الرسمي، وما بعد «/» مجرد صفحة داخله." },
  { k: "sub", url: "https://masrif-almithal.example.verify-login.example", ok: false, why: "النطاق الحقيقي هنا verify-login.example؛ اسم المصرف في أوله مجرد تمويه. اقرأ النطاق من نهايته." },
  { k: "typo", url: "http://masrif-a1mithal.example/login", ok: false, why: "حرف l صار رقم 1، والرابط بلا https. التشابه البصري خدعة شائعة." },
];

function cyberDemo(root, { done, extra }) {
  const found = new Set();
  let finished = false, extraDone = false;
  const smsPart = (p) => p.k === "link"
    ? `<button type="button" class="sms-part" data-part="link" aria-pressed="false">عبر الرابط: ${ltr("masrif-almithal.verify-login.example")}</button>`
    : `<button type="button" class="sms-part" data-part="${p.k}" aria-pressed="false">${h(p.text)}</button>`;
  root.innerHTML = stages(
    `وصلت أمك رسالة من رقم غير محفوظ باسم «مصرف المثال» (جهة خيالية، عنوانها الرسمي ${ltr("masrif-almithal.example")}). طلبت رأيك قبل أن تفعل شيئًا.`,
    `<p>اضغط على كل جزء تراه مريبًا. فيها ${num(3)} علامات واضحة.</p>
    <div class="sms" role="group" aria-label="نص الرسالة">${PARTS.map(smsPart).join(" ")}</div>
    <p class="count" role="status" aria-live="polite"></p>
    <div class="why" aria-live="polite"></div>
    <fieldset class="q" hidden><legend>ماذا تنصح أمك أن تفعل؟</legend><div class="opts">
      <button type="button" class="opt" data-d="click">تضغط الرابط لتتأكد بنفسها</button>
      <button type="button" class="opt" data-d="official">تتواصل مع المصرف عبر رقمه أو تطبيقه الرسمي، وتبلغ عن الرسالة</button>
      <button type="button" class="opt" data-d="reply">ترسل الرمز لأن الرسالة تبدو رسمية</button></div></fieldset>
    <div class="feedback main-fb" role="status" aria-live="polite"></div>`,
    "فرق الأمن السيبراني تقيّم التهديدات: تتعرف على علامات الاحتيال، وتقدّر خطرها، وتنبّه الناس، وتتبع خطوات واضحة عند وقوع حادث. ما فعلته الآن نسخة صغيرة من «تقييم التهديد» و«الاستجابة له».",
    "صديقك يسأل: أي هذه الروابط هو موقع المصرف الحقيقي؟",
    `<div class="opts links">${LINKS.map((l) => `<button type="button" class="opt" data-link="${l.k}">${ltr(l.url)}</button>`).join("")}</div>
    <div class="feedback extra-fb" role="status" aria-live="polite"></div>`);
  const update = () => {
    root.querySelector(".count").innerHTML = `وجدت ${num(found.size)} من ${num(3)} علامات.`;
    if (found.size === 3) root.querySelector("fieldset.q").hidden = false;
  };
  root.addEventListener("click", (e) => {
    const part = e.target.closest("[data-part]");
    if (part) {
      const p = PARTS.find((x) => x.k === part.dataset.part);
      part.classList.add(p.sign ? "is-sign" : "is-plain");
      part.setAttribute("aria-pressed", "true");
      if (p.sign) found.add(p.k);
      root.querySelector(".why").innerHTML = `<p class="${p.sign ? "sign" : "plain"}"><strong>${p.sign ? "علامة احتيال:" : "ليست علامة وحدها:"}</strong> ${h(p.why)}</p>`;
      update();
      return;
    }
    const d = e.target.closest("[data-d]");
    if (d) {
      root.querySelectorAll("[data-d]").forEach((b) => b.setAttribute("aria-pressed", String(b === d)));
      const fb = root.querySelector(".main-fb");
      if (d.dataset.d === "official") {
        feedback(fb, "good", "<strong>نصيحة سليمة.</strong> التحقق عبر القناة الرسمية ثم الإبلاغ هو ما يحمي أمك ويحمي غيرها.");
        if (!finished) { finished = true; reveal(root); done(); }
      } else {
        feedback(fb, "hint", d.dataset.d === "click" ? "الضغط على الرابط قد يفتح صفحة مزيفة تسرق بياناتها. ما الطريقة الأسلم للتأكد؟" : "إرسال الرمز يعطي المحتال مفتاح حسابها. ما البديل الآمن؟");
      }
      return;
    }
    const l = e.target.closest("[data-link]");
    if (!l) return;
    root.querySelectorAll("[data-link]").forEach((b) => b.setAttribute("aria-pressed", String(b === l)));
    const link = LINKS.find((x) => x.k === l.dataset.link);
    feedback(root.querySelector(".extra-fb"), link.ok ? "good" : "hint", `${link.ok ? "<strong>هذا هو.</strong> " : "<strong>ليس هذا.</strong> "}${h(link.why)}`);
    if (link.ok && !extraDone) { extraDone = true; extra?.(); }
  });
  update();
}

export const DEMO_MOUNT = { data: dataDemo, software: softwareDemo, design: designDemo, cyber: cyberDemo };
