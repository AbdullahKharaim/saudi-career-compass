// واجهة مستكشف بوصلة (نموذج أولي معزول). الرحلة: اكتشف اهتماماتك ← جرّب مجالًا ← اختر خطوتك الأولى.
// التقييم المفصّل اختياري بعد اختيار المجال، وغرضه تحديد احتياجات التعلّم، لا تأكيد الاهتمام.
// ثلاثة أشياء منفصلة دائمًا: الاهتمام (الأسئلة)، والتقييم الذاتي (التقييم المفصّل)، وسلوك التجربة ورأيك فيها.
import { QUESTIONS, FIELDS, DEMOS, SKILL_EXAMPLES, PRACTICE, GENERIC_PRACTICE, LEVELS, MIN_ANSWERED, BEGINNER_NOTES } from "./content.js";
import { STORAGE_KEY, emptyState, loadState, exploreResult, groupOf, fieldList, fieldKey, assessmentSections,
         assessmentResult, levelLabel, firstStepOptions, beginnerSkills, optionsOf, searchFields } from "./model.js";
import { compassMarkup, mountCompass, progressCompass } from "./compass.js";
import { DEMO_MOUNT } from "./demos.js";
import { icon } from "./icons.js";
import { exportRelease, parseRelease, restoreRelease, readLegacy, storageArchive, download } from "./journey.js";

const app = document.getElementById("app");
const h = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (n) => `<bdi class="num">${n}</bdi>`;
// العدد مع المعدود: 1 واحد، 2 مثنى، 3–10 جمع، 11+ مفرد منصوب.
const countOf = (n, [one, two, few, many]) => n === 1 ? one : n === 2 ? two : `${num(n)} ${n <= 10 ? few : many}`;
const QWORDS = ["سؤال واحد", "سؤالين", "أسئلة", "سؤالًا"];
const FWORDS = ["مجال واحد", "مجالان", "مجالات", "مجالًا"];
const SKILLS_ACC = ["مهارة واحدة", "مهارتين", "مهارات", "مهارة"];   // مفعول به: «قيّمت مهارتين»
const SKILLS_NOM = ["مهارة واحدة", "مهارتان", "مهارات", "مهارة"];   // مبتدأ/فاعل: «بقيت مهارتان»

// التقدم: يُرسم بالقيمة السابقة ثم يتحرك إلى الجديدة (الانتقال في CSS، ويُلغى عند تقليل الحركة).
let lastProgress = 0;
function progressBar(fraction) {
  const from = lastProgress; lastProgress = fraction;
  return `<div class="bar-track" aria-hidden="true"><span style="--p:${from * 100}%" data-to="${fraction * 100}%"></span></div>`;
}
function settleProgress() {
  const bar = app.querySelector(".bar-track span[data-to]");
  const needle = app.querySelector(".mini-needle[data-to]");
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (bar) bar.style.setProperty("--p", bar.dataset.to);
    if (needle) needle.style.transform = `rotate(${needle.dataset.to}deg)`;
  }));
}

const S = { data: null, L: null, state: emptyState(), storageOk: true, recovered: false, cleanup: null, notice: null, loadedVersion: null, status: null,
            query: new URLSearchParams() };

// ---------------------------------------------------------------------------
// التخزين: مفتاح النموذج وحده، في أصل منفصل عن الإنتاج.

function save() {
  if (S.blockSave) return; // لا تكتب فوق الأصل إن تعذر حفظ نسخة استرجاع.
  S.state.updated = new Date().toISOString();
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(S.state)); S.storageOk = true; } catch { S.storageOk = false; }
}
function load() {
  let raw = null;
  try { raw = localStorage.getItem(STORAGE_KEY); } catch { S.storageOk = false; }
  const r = loadState(raw, S.data);
  S.state = r.state; S.recovered = r.recovered;
  if (r.recovered && raw !== null) {
    // لا تضيع النسخة الأصلية حين تكون بياناتها غير متوافقة أو تالفة.
    try {
      const key = `compassExplorer.recovery.${Date.now()}`;
      localStorage.setItem(key, raw);
      if (localStorage.getItem(key) !== raw) throw new Error("backup");
    } catch { S.storageOk = false; S.blockSave = true; }
  }
}

// البدء من جديد بتأكيد صريح، في الرئيسية وصفحة «عن النموذج». لا يُمسح شيء قبل «نعم».
function bindReset() {
  const open = app.querySelector("[data-reset]"), box = app.querySelector(".reset-confirm");
  if (!open || !box) return;
  open.addEventListener("click", () => { box.hidden = false; open.setAttribute("aria-expanded", "true"); box.querySelector("[data-reset-no]").focus(); });
  box.querySelector("[data-reset-no]").addEventListener("click", () => { box.hidden = true; open.setAttribute("aria-expanded", "false"); open.focus(); });
  box.querySelector("[data-reset-yes]").addEventListener("click", () => {
    try { localStorage.removeItem(STORAGE_KEY); } catch { /* التخزين غير متاح */ }
    S.state = emptyState(); S.recovered = false; S.notice = "مُسح تقدمك في بوصلة، ويمكنك البدء من جديد.";
    S.blockSave = false;
    if (/^#?\/?$/.test(location.hash)) route(); else location.hash = "#/";
  });
}
const resetControls = (label) => `<button type="button" class="btn btn-quiet" data-reset aria-expanded="false" aria-controls="reset-confirm">${label}</button>
  <p class="reset-confirm" id="reset-confirm" hidden>سيُمسح تقدمك في هذا الإصدار: إجاباتك وتجاربك وخطوتك الأولى. <button type="button" class="btn btn-danger" data-reset-yes>نعم، امسح وابدأ من جديد</button> <button type="button" class="btn btn-quiet" data-reset-no>تراجع</button></p>`;

// سياق الدخول إلى صفحة المجال (من النتيجة أو من قائمة المجالات) يُحمل في الرابط، فيبقى بعد إعادة التحميل.
const fromParam = () => (["results", "fields"].includes(S.query.get("from")) ? S.query.get("from") : null);
const withFrom = (href, from) => (from ? `${href}?from=${from}` : href);
const returnContext = () => (fromParam() === "fields" ? "fields"
  : exploreResult(S.state.answers, S.data).status === "ok" ? "results" : "fields");

// ---------------------------------------------------------------------------
// أدوات العرض

const field = (gid) => groupOf(S.data, gid);
const skill = (id) => S.data.skills[id];
const starter = (gid) => S.L.starterItems(S.data, [gid]);
const sections = (gid) => assessmentSections(S.data, gid, starter(gid));
const order = (gid) => sections(gid).flatMap((s) => s.ids);
const demoOf = (gid) => { const k = fieldKey(gid); return k && DEMOS[k] ? { key: k, ...DEMOS[k] } : null; };
const fieldIcon = (gid, size = 24) => icon(FIELDS[fieldKey(gid)]?.icon || "compass", size);
const tag = (kind) => ({
  compass: `<span class="tag tag-compass">من بوصلة</span>`,
  source: `<span class="tag tag-source">من المصدر الرسمي</span>`,
  fiction: `<span class="tag tag-fiction">بيانات خيالية</span>`,
  curated: `<span class="tag tag-compass">اختيار بوصلة للمبتدئ</span>`,
}[kind]);
const REFLECTION = { more: "أعجبني، أريد المزيد", maybe: "ربما", less: "ليس كثيرًا" };

function back(href, label = "رجوع") {
  return `<a class="back" href="${href}"><span aria-hidden="true">→</span> ${h(label)}</a>`;
}
function page(title, body, { wide = false, cls = "" } = {}) {
  document.title = `${title} — بوصلة`;
  const banners = [
    !S.storageOk ? `<div class="banner warn" role="status">لا يمكن حفظ تقدمك في هذا المتصفح؛ ستعمل الصفحة، لكن قد تضيع إجاباتك عند إغلاقها.</div>` : "",
    S.recovered ? `<div class="banner warn" role="status">تعذر قراءة تقدم المستكشف. احتفظنا بالأصل للاسترجاع إن كان التخزين متاحًا؛ يمكنك تنزيل نسخة التخزين من «حفظ ونقل». لم يتغير التقييم الموسع.</div>` : "",
    S.notice ? `<div class="banner ok" role="status">${S.notice}</div>` : "",
  ].join("");
  S.notice = null;
  app.innerHTML = `<div class="wrap ${wide ? "wide" : ""} ${cls}">${banners}${body}</div>`;
}

function skillExample(id) {
  return SKILL_EXAMPLES[id]
    ? `<p class="example"><span class="ex-label">مثال:</span> ${h(SKILL_EXAMPLES[id])} ${tag("compass")}</p>`
    : `<p class="example muted">لا يوجد مثال مبسّط لهذه المهارة في بوصلة بعد. اقرأ الوصف الرسمي أدناه.</p>`;
}
function officialDescription(id, open = false) {
  const s = skill(id);
  return `<details class="more"${open ? " open" : ""}><summary>الوصف الرسمي للمهارة</summary>
    <p>${h(s.description || "لا يوجد وصف في المصدر.")}</p>
    <p class="small muted">${tag("source")} قاعدة بيانات المهارات للقطاع الرقمي (${h(S.data.framework.issuer)}، ${num(h(S.data.framework.year))}).</p></details>`;
}

// ---------------------------------------------------------------------------
// الصفحة الرئيسية

// إجراء رئيسي واحد بحسب المرحلة المحفوظة، مع سطر يصف أين توقفت.
function resumeTarget() {
  const st = S.state;
  if (st.step) return { href: "#/plan", label: "اعرض خطوتك الأولى",
    status: `اخترت خطوتك الأولى: «${h(skill(st.step.skill).name)}» في ${h(field(st.step.field).name)}.` };
  if (st.field) return { href: `#/field/${st.field}`, label: `تابع: ${field(st.field).name}`,
    status: `آخر مجال فتحته: ${h(field(st.field).name)}.` };
  const answered = Object.keys(st.answers).length;
  if (answered) {
    const next = QUESTIONS.findIndex((q) => !st.answers[q.id]);
    return next < 0
      ? { href: "#/results", label: "اعرض نتيجتي", status: "أجبت عن الأسئلة كلها." }
      : { href: `#/q/${next + 1}`, label: "تابع الأسئلة", status: `أجبت عن ${num(answered)} من ${countOf(QUESTIONS.length, QWORDS)}، والتالي السؤال ${num(next + 1)}.` };
  }
  return null;
}

const TOPO = `<svg class="topo" viewBox="0 0 600 400" aria-hidden="true" focusable="false" preserveAspectRatio="xMidYMid slice">
  <g fill="none" stroke="currentColor" stroke-width="1.2">
    <path d="M-20 300 C 80 250, 160 330, 260 290 S 440 220, 620 270"/><path d="M-20 330 C 90 285, 170 360, 270 322 S 450 255, 620 300"/>
    <path d="M-20 360 C 100 320, 180 390, 280 355 S 460 290, 620 332"/><path d="M-20 120 C 70 80, 150 150, 240 110 S 420 40, 620 90"/>
    <path d="M-20 150 C 80 112, 160 180, 250 142 S 430 75, 620 122"/><path d="M380 30 C 430 60, 500 40, 560 70 S 620 130, 600 160"/>
  </g></svg>`;

function viewHome() {
  const resume = resumeTarget();
  page("الرئيسية", `
    <section class="hero">
      ${TOPO}
      <div class="hero-text">
        <p class="eyebrow">${icon("compass", 18)} مستكشف المجالات الرقمية</p>
        <h1 tabindex="-1">اكتشف مجالًا رقميًا قد يناسبك، وجرّبه، وابدأ أول خطوة تعلّم</h1>
        <p class="lead">${countOf(QUESTIONS.length, QWORDS)} عن أنشطة يومية، ثم نشاط قصير من المجال، ثم خطوة تعلّم واحدة تبدأ بها.</p>
        ${resume ? `<p class="resume-status">${icon("clock", 18)} <span><strong>تقدمك محفوظ.</strong> ${resume.status}</span></p>` : ""}
        <div class="cta">
          <a class="btn btn-primary btn-lg" id="start" href="${resume ? resume.href : "#/q/1"}">${h(resume ? resume.label : "اكتشف اهتماماتي")}</a>
          <a class="btn btn-quiet" href="#/fields">${resume ? "تصفّح المجالات" : "أعرف مجالي"}</a>
        </div>
        ${resume ? `<div class="restart">${resetControls("ابدأ من جديد")}</div>`
          : `<p class="who">لا تعرف من أين تبدأ، أو تخرّجت وتستكشف، أو تفكّر في تغيير مسارك؟ ابدأ بالأسئلة.
          وإن كنت تعرف المجال الذي تريده، فـ«أعرف مجالي» يأخذك إليه مباشرة.</p>`}
      </div>
      <div class="hero-art">${compassMarkup(280)}</div>
    </section>
    <ol class="journey" aria-label="مراحل الرحلة">
      <li><span class="j-ico">${icon("search", 22)}</span><span><strong>اكتشف</strong><span>ما يشدّك من أنشطة</span></span></li>
      <li><span class="j-ico">${icon("flask", 22)}</span><span><strong>جرّب</strong><span>نشاطًا صغيرًا من المجال</span></span></li>
      <li><span class="j-ico">${icon("flag", 22)}</span><span><strong>ابدأ</strong><span>بخطوة تعلّم واحدة</span></span></li>
    </ol>
    <p class="small muted scope">يشمل ${num(17)} مجالًا رقميًا من إطار المهارات للقطاع الرقمي فقط، وليس كل المهن. إجاباتك تبقى في هذا المتصفح.</p>`, { cls: "home" });
  bindReset();
  S.cleanup = mountCompass(app.querySelector(".hero-art"));
}

// ---------------------------------------------------------------------------
// الأسئلة

function viewQuestion(n) {
  const q = QUESTIONS[n - 1];
  if (!q) return viewNotFound();
  const cur = S.state.answers[q.id];
  const answered = QUESTIONS.filter((x) => S.state.answers[x.id] && S.state.answers[x.id] !== "unsure").length;
  const opts = optionsOf(q);
  page(`السؤال ${n} من ${QUESTIONS.length}`, `
    <div class="topbar">${back(n > 1 ? `#/q/${n - 1}` : "#/", n > 1 ? "السؤال السابق" : "الرئيسية")}
      <div class="progress"><span>السؤال ${num(n)} من ${num(QUESTIONS.length)}</span>${progressCompass((n - 1) / QUESTIONS.length)}</div></div>
    ${progressBar((n - 1) / QUESTIONS.length)}
    <section class="question card" data-screen="q${n}">
      <div class="q-head"><span class="q-ico">${icon(q.icon, 30)}</span><p class="eyebrow">${h(q.short)}</p></div>
      <h1 tabindex="-1">${h(q.text)}</h1>
      <p class="hint">${q.type === "choice" ? "اختر الأقرب إليك. لا يهم إن لم تجرّبه بعد." : "هل يشدّك هذا النشاط؟ لا يهم إن كنت تجيده الآن."}</p>
      <div class="answers" role="group" aria-label="إجابتك">
        ${opts.map((a) => `<button type="button" class="answer${a.value === null ? " answer-unsure" : ""}${a.key === "none" ? " answer-none" : ""}" data-answer="${a.key}" aria-pressed="${cur === a.key}">${h(a.label)}</button>`).join("")}
      </div>
      <div class="q-foot">
        <a href="${n < QUESTIONS.length ? `#/q/${n + 1}` : "#/results"}" data-skip>${cur ? (n < QUESTIONS.length ? "التالي" : "اعرض النتيجة") : "تخطَّ هذا السؤال"}</a>
        ${answered >= MIN_ANSWERED && n < QUESTIONS.length ? `<a href="#/results">اعرض نتيجتي الآن</a>` : ""}
      </div>
    </section>`);
  settleProgress();
  app.querySelector(".answers").addEventListener("click", (e) => {
    const b = e.target.closest("[data-answer]");
    if (!b) return;
    S.state.answers[q.id] = b.dataset.answer;
    save();
    app.querySelectorAll("[data-answer]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    b.classList.add("chosen");
    location.hash = n < QUESTIONS.length ? `#/q/${n + 1}` : "#/results";
  });
}

// ---------------------------------------------------------------------------
// نتيجة الاستكشاف

function reasonLine(r) {
  return `<li><span class="r-q">${h(r.short)}</span>: ${r.choice ? "اخترت" : "أجبت"} «${h(r.answerLabel)}» <span class="r-s ${r.strength}">${r.strength === "direct" ? "صلة مباشرة" : "صلة أضعف"}</span></li>`;
}

function fieldCard(f, rank) {
  const demo = demoOf(f.id);
  const g = field(f.id);
  const tried = S.state.tried[f.id];
  return `<article class="card field-card${rank === 0 ? " is-first" : ""}">
    <div class="fc-head"><span class="f-ico">${fieldIcon(f.id, 26)}</span><div><h2>${h(f.name)}</h2><span class="sector">${h(g.subsector)}</span></div></div>
    ${f.tiedWith ? `<p class="tie">متساوٍ في قوة الصلة مع ${countOf(f.tiedWith, ["مجال آخر", "مجالين آخرين", "مجالات أخرى", "مجالًا آخر"])}، فرُتّبت المتساوية أبجديًا.</p>` : ""}
    <p>${h(FIELDS[f.key].plain)} ${tag("compass")}</p>
    ${tried?.done ? `<p class="tried">${icon("flask", 16)} جرّبته${tried.reflection ? `، وقلت: «${REFLECTION[tried.reflection]}»` : ""}. <span class="muted">رأيك لا يغيّر الترتيب.</span></p>` : ""}
    <details class="more"${rank === 0 ? " open" : ""}><summary>لماذا يظهر هذا المجال؟</summary><ul class="reasons">${f.reasons.map(reasonLine).join("")}</ul></details>
    <a class="btn ${rank === 0 ? "btn-primary" : "btn-secondary"}" href="#/field/${f.id}?from=results">${demo ? "جرّب المجال" : "استكشف المجال"}</a>
  </article>`;
}

function answersEditor() {
  return `<details class="more edit"><summary>راجع إجاباتك وغيّرها (تتحدث النتيجة فورًا)</summary>
    <ul class="edit-list">${QUESTIONS.map((q) => `<li><p>${h(q.short)}</p><div class="seg" role="group" aria-label="${h(q.short)}">
      ${optionsOf(q).map((a) => `<button type="button" class="chip" data-q="${q.id}" data-a="${a.key}" aria-pressed="${S.state.answers[q.id] === a.key}">${h(a.label)}</button>`).join("")}
      </div></li>`).join("")}</ul></details>`;
}

function viewResults() {
  const r = exploreResult(S.state.answers, S.data);
  const editorOpen = app.querySelector("details.edit")?.open;
  let body;
  if (r.status === "insufficient") {
    const next = QUESTIONS.findIndex((q) => !S.state.answers[q.id]);
    body = `<section class="card empty"><h1 tabindex="-1">نحتاج إجابات أكثر</h1>
      <p>${r.answered ? `أجبت عن ${countOf(r.answered, QWORDS)} بإجابة واضحة` : "لم تجب بعد عن أي سؤال بإجابة واضحة"}${r.unsure ? `، وقلت «لا أعرف» في ${countOf(r.unsure, QWORDS)}` : ""}. نحتاج ${num(MIN_ANSWERED)} على الأقل لنقترح مجالات بأمانة. «لا أعرف» لا تُحسب ضدك.</p>
      <div class="cta">${next >= 0 ? `<a class="btn btn-primary" href="#/q/${next + 1}">أكمل الأسئلة</a>` : ""}<a class="btn btn-quiet" href="#/fields">تصفّح المجالات بنفسك</a></div></section>`;
  } else if (r.status === "inconclusive") {
    body = `<section class="card empty"><h1 tabindex="-1">لم تظهر مجالات واضحة من إجاباتك</h1>
      <p>لم يشدّك أي من هذه الأنشطة. هذا لا يعني أن المجالات الرقمية لا تناسبك: الأسئلة قليلة، وتغطي جزءًا من الأنشطة فقط.</p>
      <div class="cta"><a class="btn btn-primary" href="#/fields">تصفّح المجالات بنفسك</a></div></section>`;
  } else {
    const last = r.shown[r.shown.length - 1];
    const hiddenTied = r.hidden.filter((f) => f.score === last.score && f.directScore === last.directScore);
    body = `<header class="page-head"><p class="eyebrow">${icon("search", 18)} نتيجة الاستكشاف</p><h1 tabindex="-1">مجالات تستحق أن تستكشفها</h1>
      <p class="lead">من إجاباتك عن ${countOf(r.answered, QWORDS)}${r.skipped ? `، وتخطيت ${countOf(r.skipped, QWORDS)}` : ""}. هذه اقتراحات للاستكشاف، لا حكم على ما يناسبك.</p>
      <p class="order-note small">${icon("compass", 16)} <span><strong>كيف رتّبناها؟</strong> أولًا المجالات المرتبطة مباشرة بنشاط قلت إنه يشدّك، ثم مجموع الصلات كلها. لذلك قد يتقدم مجال بصلة مباشرة واحدة على مجال تجمّعت له صلات أضعف. <a href="#/about">التفاصيل</a></span></p>
      ${r.onlyMaybe ? `<p class="note">كل إجاباتك الإيجابية كانت «ربما»، فهذه الاقتراحات أضعف دلالة. جرّب المجال قبل أن تقرر.</p>` : ""}</header>
      <div class="field-grid">${r.shown.map(fieldCard).join("")}</div>
      ${r.tieAtCut ? `<p class="note">ويتساوى معها في قوة الصلة: ${hiddenTied.map((f) => `<a href="#/field/${f.id}?from=results">${h(f.name)}</a>`).join("، ")}.</p>` : ""}
      ${r.hidden.length ? `<details class="more"><summary>مجالات أخرى ظهرت في إجاباتك: ${countOf(r.hidden.length, FWORDS)}</summary>
        <p class="small muted">تأتي بعد المعروضة في الترتيب نفسه، وكلها تستحق النظر إن شدّك اسمها.</p><ul class="plain-list">
        ${r.hidden.map((f) => `<li><a href="#/field/${f.id}?from=results">${h(f.name)}</a> <span class="r-s ${f.direct ? "direct" : "related"}">${f.direct ? "صلة مباشرة" : "صلات أضعف فقط"}</span> — ${[...new Set(f.reasons.map((x) => x.short))].map(h).join("، ")}</li>`).join("")}</ul></details>` : ""}`;
  }
  page("نتيجة الاستكشاف", `${back("#/q/" + QUESTIONS.length, "الأسئلة")}${body}
    ${answersEditor()}
    <p class="small muted scope">الأسئلة من إعداد بوصلة لتشجيع الاستكشاف، وليست اختبارًا نفسيًا معتمدًا، ولا تقيس قدرتك. تغطي المجالات الرقمية في إطار المهارات للقطاع الرقمي فقط، وبعض المجالات لا تظهر إلا نادرًا؛ <a href="#/fields">تصفّح المجالات كلها</a> أو <a href="#/about">اعرف كيف نقترح</a>.</p>`, { wide: true });
  if (editorOpen) app.querySelector("details.edit").open = true;
  app.querySelector(".edit-list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-q]");
    if (!b) return;
    S.state.answers[b.dataset.q] = b.dataset.a;
    save();
    const focusKey = `[data-q="${b.dataset.q}"][data-a="${b.dataset.a}"]`;
    viewResults();
    app.querySelector(focusKey)?.focus();
  });
}

// ---------------------------------------------------------------------------
// اختيار المجال مباشرة

const SUGGEST = ["بيانات", "برمجة", "تصميم", "أمن", "شبكات"];

function viewFields() {
  const list = fieldList(S.data);
  page("اختر مجالك", `${back("#/", "الرئيسية")}
    <header class="page-head"><h1 tabindex="-1">اختر المجال الذي تعرفه</h1>
      <p class="lead">${num(list.length)} مجالًا رقميًا. ما عليه علامة «تجربة قصيرة» يمكنك تجربته فورًا، ولكل مجال خطوة أولى مقترحة.</p></header>
    <div class="search"><label for="q">ابحث باسم المجال أو بكلمة مثل: برمجة، شبكات، تصميم</label><input type="search" id="q" autocomplete="off" aria-describedby="search-count"></div>
    <p class="search-count small muted" id="search-count" role="status" aria-live="polite"></p>
    <ul class="field-list">${list.map((f) => `<li data-id="${f.id}"><a href="#/field/${f.id}?from=fields">
      <span class="f-ico">${icon(f.icon, 22)}</span><span class="fl-text"><strong>${h(f.name)}</strong>${DEMOS[f.key] ? ` <span class="tag tag-demo">تجربة قصيرة</span>` : ""}<span>${h(f.plain)}</span><span class="via small" hidden></span></span></a></li>`).join("")}</ul>
    <div class="empty-search card" hidden><p><strong>لم نجد مجالًا بهذه الكلمة.</strong> جرّب كلمة أعم:</p>
      <div class="seg">${SUGGEST.map((s) => `<button type="button" class="chip" data-suggest="${s}">${s}</button>`).join("")}</div>
      <p>أو <a href="#/q/1">اكتشف اهتماماتك بالأسئلة</a> إن لم تكن متأكدًا من اسم المجال.</p></div>
    <p class="small muted">الأوصاف مبسّطة من بوصلة. لبعض المجالات مدخل بالاسم نفسه في قطاع الاتصالات، ويعرض التطبيق مدخلًا واحدًا لكل اسم.</p>`);
  const input = app.querySelector("#q"), count = app.querySelector("#search-count");
  const run = () => {
    const v = input.value.trim();
    const hits = new Map(searchFields(list, v).map((x) => [x.id, x.via]));
    app.querySelectorAll(".field-list li").forEach((li) => {
      li.hidden = !hits.has(li.dataset.id);
      const via = li.querySelector(".via"), alias = hits.get(li.dataset.id);
      via.hidden = !alias;
      via.textContent = alias ? `يطابق كلمة «${alias}»` : "";
    });
    app.querySelector(".empty-search").hidden = hits.size > 0;
    count.innerHTML = !v ? "" : hits.size ? `يظهر ${countOf(hits.size, FWORDS)}` : "لا توجد نتائج";
  };
  input.addEventListener("input", run);
  app.querySelector(".empty-search").addEventListener("click", (e) => {
    const b = e.target.closest("[data-suggest]");
    if (!b) return;
    input.value = b.dataset.suggest; run(); input.focus();
  });
}

// ---------------------------------------------------------------------------
// جرّب المجال

function viewField(gid) {
  const g = field(gid), k = fieldKey(gid);
  if (!g || !k) return viewNotFound();
  if (S.state.field !== gid) { S.state.field = gid; save(); }
  const demo = demoOf(gid);
  const tried = S.state.tried[gid];
  // الرجوع إلى سياق الدخول الفعلي؛ وللروابط المباشرة دون سياق: النتيجة إن وُجدت، وإلا قائمة المجالات.
  const from = returnContext();
  const curated = S.data.curated?.[gid];
  const sib = fieldList(S.data).find((f) => f.id === gid)?.siblings || [];
  const stepHref = withFrom(`#/step/${gid}`, from);
  const firstSkills = beginnerSkills(S.data, gid);
  const listed = S.L.fieldExamples(S.data, gid, 3).filter((name) => !firstSkills.some((id) => skill(id).name === name));
  page(g.name, `${back(from === "results" ? "#/results" : "#/fields", from === "results" ? "نتيجة الاستكشاف" : "المجالات")}
    <header class="page-head field-head"><span class="f-ico big">${fieldIcon(gid, 34)}</span><div>
      <p class="eyebrow">${demo ? "جرّب المجال" : "استكشف المجال"} · ${h(g.subsector)}</p><h1 tabindex="-1">${h(g.name)}</h1>
      <p class="lead">${h(FIELDS[k].plain)} ${tag("compass")}</p></div></header>
    ${curated ? `<details class="more"><summary>وصف المجال في المصدر الرسمي</summary><p>${h(curated.overview)}</p>
      <p class="small muted">${tag("source")} <a href="${h(curated.source_url || `${S.data.links.groups_paths}#page=${curated.page}`)}" rel="noopener noreferrer" target="_blank">نظرة عامة على المجموعات الوظيفية للقطاع الرقمي، صفحة ${num(curated.page)}</a> <span class="muted">(ملف PDF خارجي)</span></p></details>` : ""}
    ${sib.length ? `<p class="small muted">يوجد مجال بالاسم نفسه في قطاع ${h(sib.map((s) => s.subsector).join("، "))} بمهارات مختلفة؛ يعرض التطبيق مدخل ${h(g.subsector)}.</p>` : ""}
    ${demo ? `<section class="card demo" aria-labelledby="demo-title">
        <div class="demo-head"><h2 id="demo-title">${h(demo.title)}</h2>${tag("fiction")}</div>
        <p class="small muted">نشاط قصير من بوصلة يشبه جزءًا من عمل هذا المجال. جرّب كما تشاء؛ لا عدّاد ولا درجات، والخطأ جزء من التجربة.</p>
        <div id="demo-root"></div></section>
      <section class="card reflect" id="reflect" ${tried?.done ? "" : "hidden"}>
        <h2>هل أعجبك هذا النوع من العمل؟</h2>
        <div class="seg" role="group" aria-label="رأيك في التجربة">
          ${Object.entries(REFLECTION).map(([v, l]) => `<button type="button" class="chip" data-reflect="${v}" aria-pressed="${tried?.reflection === v}">${l === REFLECTION.more ? "نعم، أريد أن أعرف أكثر" : l}</button>`).join("")}
        </div>
        <p class="small muted">رأيك لا يغيّر نتيجة الأسئلة ولا ترتيبها. يساعدك أنت على المقارنة، ويحدد فقط الإجراء التالي المقترح هنا. ونجاحك أو تعثرك في التجربة لا يُحفظ ولا يُستخدم.</p>
        <div class="next" aria-live="polite"></div>
      </section>`
    : `<section class="card"><h2>ابدأ من مهارة واحدة</h2>
        <p>لا توجد تجربة قصيرة لهذا المجال في بوصلة بعد، لكن يمكنك أن تبدأ بخطوة تعلّم صغيرة.</p>
        ${firstSkills.length ? `<p>مهارات بداية اخترناها لهذا المجال ${tag("curated")}</p><ul class="plain-list">${firstSkills.map((id) => `<li>${h(skill(id).name)}</li>`).join("")}</ul>` : ""}
        <div class="cta"><a class="btn btn-primary" href="${stepHref}">اختر خطوتك الأولى</a></div>
        ${listed.length ? `<details class="more"><summary>مهارات أخرى يذكرها المصدر لهذا المجال</summary>
          <p>${listed.map(h).join("، ")}.</p>
          <p class="small muted">${tag("source")} يذكرها الإطار ضمن مهارات المجال، وبعضها يتكرر في مجالات أخرى. ليست بالضرورة مناسبة للبداية، ولا تعرّف المجال وحدها.</p></details>` : ""}</section>`}`);
  if (!demo) return;
  const renderNext = () => {
    const ref = S.state.tried[gid]?.reflection;
    const other = exploreResult(S.state.answers, S.data).shown?.find((f) => f.id !== gid);
    const otherLink = (cls) => `<a class="btn ${cls}" href="#/field/${other.id}?from=results">${demoOf(other.id) ? "جرّب" : "استكشف"} «${h(other.name)}»</a>`;
    const primary = ref === "less" && other
      ? `${otherLink("btn-primary")}<a class="btn btn-quiet" href="${stepHref}">اختر خطوة أولى هنا رغم ذلك</a>`
      : `<a class="btn btn-primary" href="${stepHref}">اختر خطوتك الأولى في هذا المجال</a>${other ? otherLink("btn-quiet") : `<a class="btn btn-quiet" href="#/fields">مجال آخر</a>`}`;
    app.querySelector(".next").innerHTML = ref ? `<div class="cta">${primary}</div>` : "";
  };
  DEMO_MOUNT[demo.key](app.querySelector("#demo-root"), {
    done: () => {
      S.state.tried[gid] = { done: true, reflection: S.state.tried[gid]?.reflection ?? null };
      save();
      const box = app.querySelector("#reflect");
      if (box.hidden) { box.hidden = false; box.classList.add("appear"); }
    },
  });
  app.querySelector("#reflect").addEventListener("click", (e) => {
    const b = e.target.closest("[data-reflect]");
    if (!b) return;
    S.state.tried[gid] = { done: true, reflection: b.dataset.reflect };
    save();
    app.querySelectorAll("[data-reflect]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    renderNext();
  });
  renderNext();
}

// ---------------------------------------------------------------------------
// اختيار الخطوة الأولى

function viewStep(gid) {
  const g = field(gid), k = fieldKey(gid);
  if (!g || !k) return viewNotFound();
  const demo = demoOf(gid);
  const ids = firstStepOptions(S.data, gid, demo?.skill);
  const cur = S.state.step?.field === gid ? S.state.step.skill : null;
  const from = returnContext();
  page("اختر خطوتك الأولى", `${back(withFrom(`#/field/${gid}`, from), g.name)}
    <header class="page-head"><p class="eyebrow">${icon("flag", 18)} الخطوة الأولى</p><h1 tabindex="-1">اختر خطوتك الأولى في «${h(g.name)}»</h1>
      <p class="lead">مهارة واحدة تبدأ بها. الأولى هي ما نقترحه للبداية، ويمكنك تغييرها لاحقًا.</p></header>
    <div class="options" role="group" aria-label="مهارات للبداية">
      ${ids.map((id, i) => `<button type="button" class="option${i === 0 ? " is-suggested" : ""}" data-skill="${id}" aria-pressed="${cur === id}">
        <span class="opt-top"><strong>${h(skill(id).name)}</strong>${i === 0 ? `<span class="tag tag-compass">مقترحة للبداية</span>` : ""}${demo?.skill === id ? `<span class="tag tag-demo">مرتبطة بالتجربة</span>` : ""}</span>
        <span>${h(SKILL_EXAMPLES[id] ? "مثال: " + SKILL_EXAMPLES[id] : "")}</span></button>`).join("")}
    </div>
    <p class="small muted">${tag("curated")} أسماء المهارات رسمية، ويذكرها الإطار ضمن مهارات هذا المجال، وهي معلَّمة فيه بأنها ذات أولوية على مستوى القطاع الرقمي كله. أما اختيارها للبداية وترتيبها والأمثلة فاجتهاد من بوصلة، لا ترتيب رسمي.${BEGINNER_NOTES[k] ? ` ${h(BEGINNER_NOTES[k])}` : ""}</p>
    <p><a href="#/assess/${gid}">لست متأكدًا؟ قيّم مستواك في مهارات المجال أولًا (اختياري)</a></p>`);
  app.querySelector(".options").addEventListener("click", (e) => {
    const b = e.target.closest("[data-skill]");
    if (!b) return;
    S.state.step = { field: gid, skill: b.dataset.skill, from: demo?.skill === b.dataset.skill ? "demo" : "choice" };
    save();
    location.hash = withFrom("#/plan", from);
  });
}

function viewPlan() {
  const st = S.state.step;
  if (!st) {
    return page("خطوتك الأولى", `${back("#/", "الرئيسية")}<section class="card empty"><h1 tabindex="-1">لم تختر خطوة أولى بعد</h1>
      <p>ابدأ باكتشاف اهتماماتك، أو اختر مجالًا تعرفه.</p><div class="cta"><a class="btn btn-primary" href="#/q/1">اكتشف اهتماماتي</a><a class="btn btn-quiet" href="#/fields">أعرف مجالي</a></div></section>`);
  }
  const g = field(st.field), s = skill(st.skill);
  const why = { demo: "اخترتها بعد تجربة نشاط قريب منها.", choice: "اخترتها من مهارات البداية في المجال.", assessment: "ظهرت أول احتياج في تقييمك المفصّل." }[st.from] || "";
  const curated = beginnerSkills(S.data, st.field).includes(st.skill);
  const ref = s.page ? `قاموس المهارات للقطاع الرقمي، صفحة ${num(s.page)}${s.page_verified ? "" : " (محسوبة بترتيب القاموس، لم يُطابَق عنوانها)"}` : null;
  page("خطوتك الأولى", `${back(withFrom(`#/step/${st.field}`, returnContext()), "غيّر الخطوة")}
    <header class="page-head"><p class="eyebrow">${icon("flag", 18)} خطوتك الأولى · ${h(g.name)}</p><h1 tabindex="-1">تعرّف على «${h(s.name)}»</h1><p class="lead">${h(why)}</p></header>
    <section class="card step-card">
      <h2>ما هذه المهارة؟</h2>${skillExample(st.skill)}
      <h2>ماذا تفعل هذا الأسبوع؟</h2>
      <p class="practice">${h(PRACTICE[st.skill] || GENERIC_PRACTICE)}</p>
      <p class="small muted">${tag("compass")} تمرين أول للتعرّف على المهارة، لا يعني إتقانها ولا جاهزية مهنية. وليس برنامجًا تدريبيًا معتمدًا ولا متطلبًا رسميًا.${curated ? " والمهارة من «مهارات البداية» التي اخترناها لهذا المجال." : ""}</p>
      ${officialDescription(st.skill)}
      ${ref ? `<p class="small">المرجع الرسمي لمستويات المهارة: <a href="${h(S.data.links.dictionary)}#page=${s.page}" rel="noopener noreferrer" target="_blank">${ref}</a> <span class="muted">(ملف PDF خارجي)</span></p>` : ""}
    </section>
    <section class="after">
      <h2 class="h3">بعد ذلك، إن أردت</h2>
      <div class="cta"><a class="btn btn-secondary" href="#/assess/${st.field}">قيّم مستواك في مهارات المجال (اختياري)</a>
        <a class="btn btn-quiet" href="${exploreResult(S.state.answers, S.data).status === "ok" ? "#/results" : "#/fields"}">استكشف مجالًا آخر</a></div>
    </section>`);
}

// ---------------------------------------------------------------------------
// التقييم المفصّل (اختياري)

const rec = (gid) => (S.state.assess[gid] ||= { levels: {}, unknown: [], cursor: 0 });

function viewAssessIntro(gid) {
  const g = field(gid);
  if (!g || !fieldKey(gid)) return viewNotFound();
  const secs = sections(gid), total = order(gid).length, r = S.state.assess[gid];
  const res = assessmentResult(secs, r);
  const resumeAt = r ? Math.min(r.cursor + 1, total) : 1;
  page("تقييم مفصّل", `${back(S.state.step?.field === gid ? "#/plan" : `#/field/${gid}`, "رجوع")}
    <header class="page-head"><p class="eyebrow">اختياري · ${h(g.name)}</p><h1 tabindex="-1">قيّم مستواك في مهارات المجال</h1>
      <p class="lead">لتعرف ماذا تتعلّم أولًا. لا يؤكد هذا التقييم اهتمامك بالمجال ولا يقيس قدرتك؛ هو تقدير ذاتي.</p></header>
    <section class="card">
      <ul class="plain-list">${secs.map((s, i) => `<li><strong>القسم ${num(i + 1)}:</strong> ${h(s.title)}، وفيه ${countOf(s.ids.length, SKILLS_NOM)}</li>`).join("")}</ul>
      <p>مهارة في كل شاشة، بأربعة مستويات بسيطة. يمكنك أن تقول «لا أعرف ما هذه» أو تتخطى، فتبقى المهارة غير مقيّمة ولا تُحسب صفرًا. يمكنك التوقف في أي وقت؛ تقدمك محفوظ.</p>
      <p class="small muted">${tag("compass")} السلّم مبسّط في هذا الإصدار، من «لم أبدأ بعد» إلى «أطبّقها وحدي»، وليس مستويات الإطار الرسمية الخمسة. القسم الأول اختيار بوصلة للمبتدئ، والثاني مهارات يذكرها المصدر للمجال.</p>
      <div class="cta">${res.rated || r?.cursor ? `<a class="btn btn-primary" href="#/assess/${gid}/${resumeAt}">تابع من المهارة ${num(resumeAt)}</a><a class="btn btn-quiet" href="#/assess/${gid}/result">اعرض نتيجتي حتى الآن</a>`
        : `<a class="btn btn-primary" href="#/assess/${gid}/1">ابدأ التقييم</a>`}</div>
    </section>`);
}

function viewAssessSkill(gid, n) {
  const g = field(gid), secs = sections(gid), ids = order(gid);
  const id = ids[n - 1];
  if (!g || !id) return viewNotFound();
  const r = rec(gid);
  r.cursor = n - 1; save();
  let before = 0, sec = secs[0], idx = n;
  for (const s of secs) { if (n <= before + s.ids.length) { sec = s; idx = n - before; break; } before += s.ids.length; }
  const si = secs.indexOf(sec);
  const cur = r.levels[id], unknown = r.unknown.includes(id);
  const nextHref = n >= ids.length ? `#/assess/${gid}/result` : (idx === sec.ids.length ? `#/assess/${gid}/pause/${si + 1}` : `#/assess/${gid}/${n + 1}`);
  page(`تقييم: ${skill(id).name}`, `
    <div class="topbar">${back(n > 1 ? `#/assess/${gid}/${n - 1}` : `#/assess/${gid}`, n > 1 ? "المهارة السابقة" : "رجوع")}
      <div class="progress"><span>القسم ${num(si + 1)} من ${num(secs.length)} · المهارة ${num(idx)} من ${num(sec.ids.length)}</span>${progressCompass((n - 1) / ids.length)}</div></div>
    ${progressBar((n - 1) / ids.length)}
    <section class="question card" data-screen="a${n}">
      <p class="eyebrow">${h(sec.title)}</p>
      <h1 tabindex="-1">${h(skill(id).name)}</h1>
      ${skillExample(id)}
      ${officialDescription(id)}
      <h2 class="h3">أين أنت منها الآن؟</h2>
      <div class="answers" role="group" aria-label="مستواك">
        ${LEVELS.map((l) => `<button type="button" class="answer" data-level="${l.value}" aria-pressed="${cur === l.value}">${h(l.label)}</button>`).join("")}
        <button type="button" class="answer answer-unsure" data-level="unknown" aria-pressed="${unknown}">لا أعرف ما هذه المهارة</button>
      </div>
      <div class="q-foot"><a href="${nextHref}" data-skip>${cur !== undefined || unknown ? "التالي" : "تخطَّها الآن"}</a><a href="#/assess/${gid}/result">توقف واعرض نتيجتي</a></div>
    </section>`);
  settleProgress();
  app.querySelector(".answers").addEventListener("click", (e) => {
    const b = e.target.closest("[data-level]");
    if (!b) return;
    if (b.dataset.level === "unknown") { delete r.levels[id]; if (!r.unknown.includes(id)) r.unknown.push(id); }
    else { r.levels[id] = Number(b.dataset.level); r.unknown = r.unknown.filter((x) => x !== id); }
    r.cursor = Math.min(n, ids.length - 1);
    save();
    app.querySelectorAll("[data-level]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    b.classList.add("chosen");
    location.hash = nextHref;
  });
}

function viewAssessPause(gid, done) {
  const secs = sections(gid), next = secs[done];
  if (!next) return viewAssessResult(gid);
  const start = secs.slice(0, done).reduce((n, s) => n + s.ids.length, 0) + 1;
  page("أنهيت قسمًا", `<section class="card empty"><p class="eyebrow">${h(field(gid).name)}</p>
    <h1 tabindex="-1">أنهيت القسم ${num(done)}: ${h(secs[done - 1].title)}</h1>
    <p>بقي قسم واحد: ${h(next.title)}، وفيه ${countOf(next.ids.length, SKILLS_NOM)}. يمكنك أن ترى نتيجتك الآن، وتكمل لاحقًا من حيث توقفت.</p>
    <div class="cta"><a class="btn btn-primary" href="#/assess/${gid}/${start}">تابع القسم ${num(done + 1)}</a><a class="btn btn-quiet" href="#/assess/${gid}/result">اعرض نتيجتي الآن</a></div></section>`);
}

function viewAssessResult(gid) {
  const g = field(gid);
  if (!g || !fieldKey(gid)) return viewNotFound();
  const secs = sections(gid), r = S.state.assess[gid];
  const res = assessmentResult(secs, r);
  const total = order(gid).length;
  const resumeAt = Math.min((r?.cursor ?? 0) + 1, total);
  const row = (x) => `<li><strong>${h(skill(x.id).name)}</strong> — ${x.level === undefined ? (x.unknown ? "قلت «لا أعرف ما هذه»" : "لم تقيّمها") : `قيّمتها «${h(levelLabel(x.level))}»`}</li>`;
  let lead;
  if (!res.rated) {
    lead = `<section class="card empty"><h1 tabindex="-1">لم تقيّم أي مهارة بعد</h1>
      <p>المهارات التي تتخطاها أو تقول عنها «لا أعرف» تبقى غير مقيّمة، ولا نحسبها صفرًا، فلا نستنتج منها حاجة.</p>
      <div class="cta"><a class="btn btn-primary" href="#/assess/${gid}/${resumeAt}">قيّم المهارات</a></div></section>`;
  } else if (!res.first) {
    lead = `<section class="card empty"><h1 tabindex="-1">لم تظهر حاجة تعلّم فيما قيّمته</h1>
      <p>قيّمت ${countOf(res.rated, SKILLS_ACC)} من ${num(total)}، ${res.rated === 1 ? "وتقييمها" : "وكلها"} «أطبّقها بمساعدة» أو أعلى. ${res.unrated.length ? "قيّم الباقي لصورة أوضح، أو اختر" : "اختر"} خطوة أولى بنفسك.</p>
      <div class="cta">${res.unrated.length ? `<a class="btn btn-primary" href="#/assess/${gid}/${resumeAt}">تابع التقييم</a>` : ""}<a class="btn btn-quiet" href="#/step/${gid}">اختر خطوتك الأولى</a></div></section>`;
  } else {
    const f = res.first;
    lead = `<header class="page-head"><p class="eyebrow">نتيجة التقييم · ${h(g.name)}</p><h1 tabindex="-1">ابدأ بـ«${h(skill(f.id).name)}»</h1>
      <p class="lead">لأنك قيّمتها «${h(levelLabel(f.level))}»${f.section === "beginner" ? "، وهي من مهارات البداية التي اخترناها لهذا المجال" : "، وهي من المهارات التي يذكرها المصدر لهذا المجال"}.</p></header>
      <section class="card step-card">${skillExample(f.id)}
        <div class="cta"><button type="button" class="btn btn-primary" data-make-step="${f.id}">اجعلها خطوتي الأولى</button></div></section>`;
  }
  page("نتيجة التقييم", `${back(`#/assess/${gid}`, "التقييم")}${lead}
    ${res.rated ? `<p class="summary">قيّمت ${countOf(res.rated, SKILLS_ACC)} من ${num(total)}${res.zeros ? `، واخترت «لم أبدأ بعد» في ${res.zeros === 1 ? "واحدة منها" : `${num(res.zeros)} منها`}` : ""}.${res.unrated.length ? ` وبقيت ${countOf(res.unrated.length, SKILLS_NOM)} دون تقييم، ولا نحسبها صفرًا.` : ""}</p>` : ""}
    ${res.needs.length > 1 ? `<details class="more"><summary>احتياجات أخرى: ${num(res.needs.length - 1)}</summary><ul class="plain-list">${res.needs.slice(1).map(row).join("")}</ul></details>` : ""}
    ${res.met.length ? `<details class="more"><summary>مهارات تطبّقها بمساعدة أو وحدك: ${num(res.met.length)}</summary><ul class="plain-list">${res.met.map(row).join("")}</ul></details>` : ""}
    ${res.unrated.length && res.rated ? `<details class="more"><summary>لم تقيّمها بعد: ${num(res.unrated.length)}</summary><ul class="plain-list">${res.unrated.map(row).join("")}</ul>
      <a href="#/assess/${gid}/${resumeAt}">تابع التقييم</a></details>` : ""}
    <p class="small muted">${tag("compass")} قاعدة النموذج: «حاجة تعلّم» = مهارة قيّمتها دون «أطبّقها بمساعدة». الأولى هي الأدنى تقييمًا، ثم الأسبق في القائمة. هذا تقدير ذاتي، لا شهادة ولا اختبار.</p>`);
  app.querySelector("[data-make-step]")?.addEventListener("click", (e) => {
    S.state.step = { field: gid, skill: e.currentTarget.dataset.makeStep, from: "assessment" };
    save();
    location.hash = "#/plan";
  });
}

// ---------------------------------------------------------------------------
// عن النموذج

function viewAbout() {
  const fw = S.data.framework;
  page("عن بوصلة", `${back("#/", "الرئيسية")}
    <header class="page-head"><h1 tabindex="-1">عن بوصلة ومصادرها</h1></header>
    <section class="card prose">
      <h2>ما هذا؟</h2>
      <p>بوصلة تساعدك على استكشاف اهتماماتك وتجربة نشاط قصير واختيار أول خطوة تعلم. التقييم الموسع والرحلات السابقة متاحان اختياريًا من «حفظ ونقل»، دون دمجهما مع الاهتمامات.</p>
      <h2>من أين تأتي المعلومات؟</h2>
      <ul>
        <li>${tag("source")} أسماء المجالات والمهارات وأوصافها الرسمية من «${h(fw.title)}» (${h(fw.issuer)}، ${num(h(fw.year))}). <a href="${h(S.data.links.skills_page)}" rel="noopener noreferrer" target="_blank">صفحة المصدر</a>.</li>
        <li>${tag("compass")} الأسئلة، وربطها بالمجالات، والأوصاف المبسّطة، ومهارات البداية المختارة، والأمثلة، والتمارين، والتجارب: من إعداد بوصلة.</li>
        <li>${tag("fiction")} أرقام التجارب ورسائلها وأسماء الجهات فيها خيالية.</li>
      </ul>
      <h2>كيف نقترح المجالات؟</h2>
      <p>${countOf(QUESTIONS.length, QWORDS)}: تسعة عن أنشطة («يشدّني» أقوى من «ربما»، و«لا يشدّني» لا تضيف شيئًا)، واثنان تختار فيهما الدور الأقرب إليك. كل إجابة مرتبطة بمجال أو أكثر بصلة مباشرة أو أضعف، ومبرر الربط من مهارات يذكرها الإطار للمجال. «لا أعرف» والتخطي لا أثر لهما. نرتّب أولًا بالصلات المباشرة (نشاط قلت إنه يشدّك)، ثم بالمجموع، فلا تتقدم صلات أضعف متراكمة على دليل مباشر. نعرض حتى ${num(3)} مجالات، وأكثر قليلًا عند التعادل. رأيك بعد التجارب لا يدخل في الحساب. لا نسب مئوية ولا تصنيف للشخصية.</p>
      <h2>ما حدود هذا الإصدار؟</h2>
      <ul>
        <li>الأسئلة ليست اختبارًا نفسيًا معتمدًا، ولم تُجرَّب مع مستخدمين بعد.</li>
        <li>يشمل المجالات الرقمية في الإطار فقط، وليس كل المهن في السعودية، ولا يتنبأ بالتوظيف.</li>
        <li>التجارب القصيرة متاحة لأربعة مجالات فقط. ومهارات البداية اختيار تحريري.</li>
        <li>التقييم المفصّل يستخدم سلّمًا مبسّطًا وعددًا قليلًا من المهارات، والتقييم الموسع بسُلّم الإطار متاح اختياريًا من «حفظ ونقل».</li>
      </ul>
      <h2>تحديث البيانات</h2>
      <p>حين يعمل التطبيق من برنامج التشغيل على هذا الحاسوب، يراجع ملفات المصادر الرسمية مرة كل أسبوع تقريبًا، ما دام البرنامج والحاسوب يعملان. ولا يعرض أي نسخة جديدة إلا بعد فحصها بنجاح. هذه ليست بيانات لحظية. التفاصيل في سطر «إطار المهارات» أسفل الصفحة.</p>
      <h2>بياناتك</h2>
      <p>تُحفظ في هذا المتصفح فقط. بقي تقدم المستكشف السابق متوافقًا؛ والتقييم الموسع سجل مستقل. يمكنك تنزيل نسخة أو استعادتها من <a href="#/save">حفظ ونقل</a>.</p>
      ${resetControls("امسح تقدم المستكشف وابدأ من جديد")}
    </section>`);
  bindReset();
}

function viewNotFound() {
  page("غير موجودة", `<section class="card empty"><h1 tabindex="-1">هذه الصفحة غير موجودة</h1><div class="cta"><a class="btn btn-primary" href="#/">الرئيسية</a></div></section>`);
}

// حفظ ونقل: مدخل ثانوي، يفصل تقدم المستكشف عن التقييم الموسع ولا يدمج الإجابات.
function viewSave() {
  page("حفظ ونقل", `${back("#/", "الرئيسية")}
    <header class="page-head"><h1 tabindex="-1">حفظ ونقل تقدمك</h1><p class="lead">تقدمك محفوظ في هذا المتصفح. نزّل نسخة للاستعادة على الجهاز نفسه أو جهاز آخر.</p></header>
    <section class="card"><h2>نسخة قابلة للاستعادة</h2>
      <p>تحفظ الاهتمامات والتجارب والخطوة الأولى والتقييم المختصر وتفضيل الحركة. إن وُجد تقييم موسع، يُحفظ منفصلًا بسُلّمه وأهدافه.</p>
      <button class="btn btn-primary" type="button" id="export-release">نزّل نسخة تقدمي</button>
      <p id="save-note" role="status"></p>
      <h2>استعادة نسخة</h2><p>نتحقق من الملف كاملًا، ثم نعرض أثره قبل الاستبدال. لا دمج صامت، وتُحفظ نسخة محلية من القيم السابقة.</p>
      <label for="import-release">اختر ملف رحلة بوصلة</label><input id="import-release" type="file" accept=".json,application/json">
      <div id="import-preview" aria-live="polite"></div>
    </section>
    <details class="more"><summary>التقييم الموسع والنسخ السابقة</summary>
      <p>التقييم الموسع يستخدم سلّم الإطار الرسمي وأهدافك، بينما التقييم المختصر في المستكشف سلّم مبسط. لا نحول أحدهما إلى الآخر.</p>
      <p id="legacy-note"></p><a class="btn btn-secondary" href="assessment.html#/assess">افتح التقييم الموسع المحفوظ</a>
      <a class="btn btn-quiet" href="assessment.html#/save">تقرير التقييم الموسع وحفظه</a>
      <button type="button" class="btn btn-quiet" id="export-storage">نزّل نسخة التخزين الأصلية للمساعدة</button>
      <p class="small muted">نسخة التخزين للمساعدة والاسترجاع اليدوي، وليست ملف رحلة يقبله المستورد. احتفظ بها خاصة.</p>
      <p>إن كان تقدمك القديم على 8502، افتح ذلك العنوان في متصفحك وصدّر ملف الرحلة منه، ثم استورده هنا. تخزين المنافذ مستقل؛ لا نستطيع قراءة الأصل الآخر تلقائيًا.</p>
    </details>`);
  const note = app.querySelector("#save-note"), preview = app.querySelector("#import-preview");
  try {
    const old = readLegacy(localStorage, S.data);
    app.querySelector("#legacy-note").textContent = old.invalid ? "وجدنا سجلًا قديمًا غير صالح؛ لم نغيره. نزّل الأصل للمساعدة." : old.profile ? "يوجد تقييم موسع محفوظ؛ بقي منفصلًا دون تغيير." : "لا يوجد تقييم موسع في هذا الأصل. يمكنك بدء تقييم اختياري.";
  } catch { app.querySelector("#legacy-note").textContent = "التخزين غير متاح."; }
  app.querySelector("#export-release").onclick = () => {
    try {
      const file = exportRelease(S.state, S.data, S.status, localStorage);
      download(`bawsala-journey-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(file, null, 2));
      note.textContent = "طلبنا تنزيل نسخة تقدمك. تأكد من ظهور الملف في التنزيلات.";
    } catch (e) { note.textContent = e.message; }
  };
  app.querySelector("#export-storage").onclick = () => {
    try { download("bawsala-storage-recovery.json", JSON.stringify(storageArchive(localStorage), null, 2)); note.textContent = "طلبنا تنزيل نسخة التخزين الأصلية."; }
    catch { note.textContent = "تعذر قراءة التخزين."; }
  };
  app.querySelector("#import-release").onchange = async (e) => {
    preview.replaceChildren();
    const file = e.target.files[0]; if (!file) return;
    let result;
    try { result = parseRelease(JSON.parse(await file.text()), S.data); }
    catch { result = { ok: false, errors: [{ text: "الملف تالف أو ليس JSON. اختر النسخة الأصلية المحفوظة." }] }; }
    if (!result.ok) { preview.innerHTML = `<p role="alert">${result.errors.map((x) => h(x.text)).join(" ")}</p>`; return; }
    preview.innerHTML = `<h3>راجع الأثر قبل الاستعادة</h3><p>${h(file.name)}</p>
      <ul>${result.notes.map((n) => `<li>${h(n)}</li>`).join("")}</ul>
      ${result.explorer ? `<p>إجابات الاهتمامات: ${num(Object.keys(result.explorer.answers).length)}. الخطوة: ${h(result.explorer.step ? skill(result.explorer.step.skill).name : "لم تُختر")}.</p>` : ""}
      ${result.legacy ? `<p>تقييمات موسعة محفوظة: ${num(Object.keys(result.legacy.levels).length)}.</p>` : ""}
      <button type="button" class="btn btn-primary" id="restore-confirm">نعم، استبدل ما ذُكر بالملف</button>
      <button type="button" class="btn btn-quiet" id="restore-cancel">تراجع</button>`;
    preview.querySelector("#restore-cancel").onclick = () => { preview.textContent = "أُلغيت الاستعادة؛ لم يتغير شيء."; };
    preview.querySelector("#restore-confirm").onclick = () => {
      try {
        restoreRelease(result, localStorage);
        load(); S.blockSave = false;
        preview.textContent = "استُعيد التقدم بعد التحقق، وحُفظت نسخة من القيم السابقة في هذا المتصفح. يمكنك العودة للرئيسية والاستئناف.";
      } catch { preview.textContent = "تعذر حفظ الاستعادة؛ احتفظ بالملف. النسخة السابقة محفوظة للاسترجاع، ولم نعتمد حفظًا غير متحقق منه."; }
    };
  };
}

// ---------------------------------------------------------------------------
// مؤشر حداثة البيانات (من /framework/status.json الذي يحسبه الخادم من حالة المشغّل والبيان المنشور)

const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  // التاريخ العربي يُترك في اتجاهه الطبيعي (يوم، شهر، سنة)؛ عزله يمينًا لليسار يقلب ترتيبه.
  return Number.isNaN(d.getTime()) ? "—" : `<span class="date">${d.toLocaleDateString("ar-SA-u-nu-latn-ca-gregory", { day: "numeric", month: "long", year: "numeric" })}</span>`;
};
const UPDATE_TEXT = {
  ok: ["ok", "آخر تحقق ناجح"],
  partial: ["warn", "بعض المصادر تعذر تحديثها"],
  failed: ["warn", "تعذر آخر تحديث"],
  running: ["run", "يجري التحقق الآن"],
  overdue: ["warn", "موعد التحقق فات"],
  inactive: ["idle", "التحديث التلقائي متوقف"],
};

// المصادر نوعان: إطار المهارات (أساس الرحلة كلها) وبيانات سوق العمل (يتحقق منها المشغّل، ولا تدخل في اقتراح المجالات).
// «النسخة» من الخادم بصيغة «الإصدار أو الفترة · ملف بتاريخ YYYY-MM-DD»، فتُفصل هنا دون تغيير الخادم.
const isFramework = (src) => src.id.startsWith("hrsd-");
function sourceParts(src) {
  const [period = "", file = ""] = String(src.version || "").split(" · ");
  return { period, fileDate: file.match(/\d{4}-\d{2}-\d{2}/)?.[0] || null };
}
function sourceItem(src, periodLabel) {
  const { period, fileDate } = sourceParts(src);
  return `<li><strong>${h(src.title)}</strong>
    <span>${periodLabel}: ${h(period.replace(/^إصدار\s*/, "") || "—")}</span><span>تاريخ الملف لدى المصدر: ${fmtDate(fileDate)}</span><span>آخر تحقق منه: ${fmtDate(src.verified_at)}</span>
    ${src.status !== "ok" ? `<span class="warn-text">${src.status === "stale" ? "تعذر آخر تحقق، فنعرض آخر نسخة سليمة" : "غير متاح"}</span>` : ""}</li>`;
}

function renderFreshness(st) {
  const box = document.getElementById("freshness");
  if (!box || !st) return;
  const u = st.update || {};
  const [cls, label] = UPDATE_TEXT[u.state] || UPDATE_TEXT.inactive;
  const fw = (st.sources || []).filter(isFramework), market = (st.sources || []).filter((x) => !isFramework(x));
  const lastOk = fw.map((x) => x.verified_at).filter(Boolean).sort().pop();
  const every = u.interval_hours >= 24 ? Math.round(u.interval_hours / 24) : u.interval_hours;
  const detail = {
    ok: "راجعنا ملفات المصادر الرسمية ووجدناها سليمة. نجاح التحقق لا يعني أن المحتوى تغيّر أو صار أحدث.",
    partial: "تعذر التحقق من بعض المصادر في آخر محاولة، فنستخدم آخر نسخة سليمة من كل مصدر.",
    failed: `تعذرت آخر محاولة تحقق${u.last_attempt_at ? ` في ${fmtDate(u.last_attempt_at)}` : ""}، فنستخدم آخر نسخة سليمة.`,
    running: "نراجع ملفات المصادر الآن. تبقى النسخة الحالية معروضة حتى ينتهي الفحص بنجاح.",
    overdue: "حان موعد المراجعة ولم تتم بعد، لأنها تعمل فقط أثناء تشغيل برنامج بوصلة على هذا الحاسوب.",
    inactive: "برنامج التشغيل المحلي متوقف، فلا تُراجع المصادر تلقائيًا. المعروض آخر نسخة سليمة.",
  }[u.state] || "";
  const summary = u.state === "ok" ? `آخر تحقق ${fmtDate(lastOk)}` : label;
  box.innerHTML = `<details class="fresh"><summary><span class="dot ${cls}" aria-hidden="true"></span><span>إطار المهارات (أساس هذه الرحلة): إصدار ${num(h(S.data?.framework?.year || "—"))} · ${summary}</span></summary>
    <div class="fresh-body">
      <p>${detail}${u.next_due_at && u.state !== "running" ? ` المراجعة التالية: ${fmtDate(u.next_due_at)}، ثم كل ${num(every)} ${u.interval_hours >= 24 ? (every <= 10 ? "أيام" : "يومًا") : (every <= 10 ? "ساعات" : "ساعة")}.` : ""}</p>
      <h3 class="fresh-h">إطار المهارات: تقوم عليه الأسئلة والمجالات والمهارات</h3>
      <ul class="fresh-list">${fw.map((x) => sourceItem(x, "الإصدار")).join("")}</ul>
      ${market.length ? `<h3 class="fresh-h">بيانات سوق العمل: لا تُستخدم في اقتراح المجالات</h3>
      <p class="small muted">يتحقق منها البرنامج لأعمال أخرى في المشروع. لا تؤثر في ترتيب المجالات ولا في الخطوة الأولى.</p>
      <ul class="fresh-list">${market.map((x) => sourceItem(x, "الفترة")).join("")}</ul>` : ""}
      <details class="more tech"><summary>تفاصيل تقنية للمراجعين</summary>
        ${st.discovery?.needs_review ? `<p class="small">وجدنا في صفحة البيانات المفتوحة للوزارة ${num(st.discovery.needs_review)} ملفات لفترات أخرى لم نراجعها بعد، ولا تُضاف تلقائيًا.</p>` : ""}
        <p class="small">النسخة المعروضة: ${st.data?.origin === "published" ? "نُشرت بعد فحص وبناء ناجحين" : "آخر بناء محلي سليم قبل أول نشر مجدول"}، وبُنيت في ${fmtDate(st.data?.generated_at)}.</p>
      </details>
    </div></details>`;
  const newer = S.loadedVersion && st.data?.generated_at && st.data.generated_at !== S.loadedVersion;
  document.getElementById("newer").hidden = !newer;
}

async function pollStatus() {
  try {
    const st = await (await fetch("/framework/status.json", { cache: "no-store" })).json();
    S.status = st;
    renderFreshness(st);
  } catch { /* الخادم لا يقدم الحالة: يبقى المؤشر مخفيًا */ }
}

// ---------------------------------------------------------------------------
// التوجيه

function route() {
  S.cleanup?.(); S.cleanup = null;
  const [path, query = ""] = location.hash.replace(/^#\/?/, "").split("?");
  S.query = new URLSearchParams(query);
  const parts = path.split("/").filter(Boolean);
  const [a, b, c, d] = parts;
  if (!a) viewHome();
  else if (a === "q") viewQuestion(Number(b));
  else if (a === "results") viewResults();
  else if (a === "fields") viewFields();
  else if (a === "field") viewField(b);
  else if (a === "step") viewStep(b);
  else if (a === "plan") viewPlan();
  else if (a === "assess" && !c) viewAssessIntro(b);
  else if (a === "assess" && c === "result") viewAssessResult(b);
  else if (a === "assess" && c === "pause") viewAssessPause(b, Number(d));
  else if (a === "assess") viewAssessSkill(b, Number(c));
  else if (a === "about") viewAbout();
  else if (a === "save") viewSave();
  else viewNotFound();
  const h1 = app.querySelector("h1");
  if (h1) { h1.setAttribute("tabindex", "-1"); h1.focus({ preventScroll: true }); }
  scrollTo(0, 0);
}

async function start() {
  try {
    const [data, L] = await Promise.all([fetch("/framework/compass.json", { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
                                         import("/framework/logic.js")]);
    S.data = data; S.L = L; S.loadedVersion = data.generated_at;
  } catch (err) {
    app.innerHTML = `<div class="wrap"><section class="card empty"><h1>تعذر تحميل بيانات الإطار</h1><p>شغّل التطبيق بالأمر python -m compass launch بعد بناء بيانات بوصلة.</p><p class="small muted">${h(err)}</p></section></div>`;
    return;
  }
  load();
  addEventListener("hashchange", route);
  // رابط التخطي ينقل التركيز إلى محتوى الشاشة الحالية دون تغيير المسار أو إضافة خطوة إلى السجل.
  document.querySelector(".skip")?.addEventListener("click", (e) => {
    e.preventDefault();
    const target = app.querySelector("h1") || app;
    target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: "start" });
  });
  document.getElementById("newer-reload")?.addEventListener("click", () => location.reload());
  route();
  pollStatus();
  setInterval(() => { if (!document.hidden) pollStatus(); }, 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) pollStatus(); });
}

start();
