// واجهة «بوصلة»: توجيه بالـhash، وحالة محلية، وعرض الصفحات. المنطق في logic.js.
//
// الرحلة: اختر مجالك ← جلسة بداية من نحو 10 مهارات (مهارة في كل شاشة) ← نتيجة أولية وخطوة قادمة،
// ثم مواصلة التقييم والمقارنة والحفظ لمن أراد. كل شاشة تجيب: ماذا أفعل الآن؟ لماذا؟ ماذا بعد؟
import * as L from "./logic.js";
import { restoreRelease } from "../journey.js";

const h = L.escapeHtml;
const STORE_KEY = "compass.profile";
const OLD_STORE_KEY = "compass.profile.v1";   // قبل الإصدار 2؛ يُرحَّل مرة واحدة
const OLD_SCOPE_KEY = "compass.scope";
const BACKUP_KEY = "compass.profile.backup";  // نسخة من بيانات تعذر قراءتها، كي لا تضيع
const CURSOR_KEY = "compass.cursor";          // موضع التوقف في التقييم: {list, id}
const PLAN_VISIBLE = 3;
const app = document.getElementById("app");
const banner = document.getElementById("status-banner");

const state = {
  data: null, manifest: null, manifestError: null, profile: null,
  storageOk: true, storageNotice: null,
  ui: { pathError: false, compareTab: "shared", showAllPlan: false, planNotice: null, unsure: {},
        importPreview: null, importErrors: null, importDone: null, clearConfirm: false, cleared: false },
};

// ---------------------------------------------------------------- التخزين المحلي
function readStorage(key) {
  try { return window.localStorage.getItem(key); } catch { state.storageOk = false; return null; }
}
function writeStorage(key, value) {
  try { window.localStorage.setItem(key, value); return true; } catch { state.storageOk = false; return false; }
}
function removeStorage(key) {
  try { window.localStorage.removeItem(key); } catch { state.storageOk = false; }
}
function saveProfile() {
  if (state.blockSave) return;
  state.profile.updated = new Date().toISOString();
  writeStorage(STORE_KEY, JSON.stringify(state.profile));
}
function backupProfile() {
  const before = Object.fromEntries([STORE_KEY, OLD_STORE_KEY, OLD_SCOPE_KEY, CURSOR_KEY].map((k) => [k, readStorage(k)]));
  const key = `compass.restore.backup.${Date.now()}`, text = JSON.stringify(before);
  return writeStorage(key, text) && readStorage(key) === text;
}
function loadProfile(data) {
  const fresh = L.emptyProfile(null);
  let key = STORE_KEY, raw = readStorage(STORE_KEY);
  if (raw === null) { key = OLD_STORE_KEY; raw = readStorage(OLD_STORE_KEY); }
  if (raw === null) return fresh;
  const oldScope = readStorage(OLD_SCOPE_KEY);
  let profile = null;
  try { profile = L.loadStoredProfile(JSON.parse(raw), data, L.SCOPES.includes(oldScope) ? oldScope : "priority"); } catch { profile = null; }
  if (profile) {
    // الترحيل إلى الإصدار الحالي يحفظ القيم نفسها؛ يُكتب مرة واحدة ويُحذف المفتاح القديم.
    const serialized = JSON.stringify(profile);
    if (raw !== serialized && !backupProfile()) { state.blockSave = true; return profile; }
    if (!writeStorage(STORE_KEY, serialized) || readStorage(STORE_KEY) !== serialized) { state.blockSave = true; return profile; }
    if (key === OLD_STORE_KEY) { removeStorage(OLD_STORE_KEY); removeStorage(OLD_SCOPE_KEY); }
    return profile;
  }
  if (writeStorage(BACKUP_KEY, raw) && readStorage(BACKUP_KEY) === raw) removeStorage(key);
  else state.blockSave = true;
  state.storageNotice = "تعذر قراءة إجاباتك المحفوظة في هذا المتصفح، فبدأنا من جديد. احتفظنا بنسخة منها دون حذف. إن كانت لديك نسخة تقدم محفوظة في ملف، استعدها من صفحة «حفظ ونقل».";
  return fresh;
}
function readCursor() {
  try { const c = JSON.parse(readStorage(CURSOR_KEY) || "null"); return c && typeof c.id === "string" ? c : null; } catch { return null; }
}

// ---------------------------------------------------------------- مساعدات العرض
const num = (n) => `<span class="num">${h(L.formatNumber(n))}</span>`;
const count = (n) => h(L.countSkills(n));
const groups = () => L.indexGroups(state.data);
const paths = () => state.profile.paths || [];
const pathGroups = () => paths().map((id) => groups().get(id));
const label = (g) => `«${h(g.name)}» <span class="sector">(${h(g.subsector)})</span>`;
const plainLabel = (g) => `${g.name} (${g.subsector})`;
const starter = () => L.starterItems(state.data, state.profile.paths);
const fullList = () => L.assessmentItems(state.data, state.profile.paths, state.profile.scope);
const listFor = (name) => (name === "start" ? starter() : fullList());

function external(url, text) {
  const safe = L.safeUrl(url);
  return safe ? `<a href="${h(safe)}" target="_blank" rel="noopener">${text}<span class="sr-only"> (يفتح في نافذة جديدة)</span> ↗</a>` : text;
}
function whereText(where) {
  const [A, B] = pathGroups();
  if (!B) return "";
  if (where === "both") return `<span class="chip chip-both"><span class="dot dot-both" aria-hidden="true"></span>مشتركة بين المجالين</span>`;
  const g = where === "a" ? A : B;
  return `<span class="chip chip-${where}"><span class="dot dot-${where}" aria-hidden="true"></span>من «${h(g.name)}» فقط</span>`;
}
function emptyState(icon, title, text, action = "") {
  return `<div class="card empty"><div class="icon" aria-hidden="true">${icon}</div><h1 tabindex="-1">${title}</h1><p>${text}</p>${action}</div>`;
}
function stepHead(n, title, lead) {
  const names = ["اختر مجالك", "حدّد مستواك", "نتيجتك وخطوتك القادمة"];
  const steps = names.map((t, i) => `<li class="${i + 1 === n ? "current" : i + 1 < n ? "done" : ""}"${i + 1 === n ? ' aria-current="step"' : ""}><span class="n" aria-hidden="true">${i + 1}</span>${t}</li>`).join("");
  return `<ol class="stepline" aria-label="خطوات بوصلة">${steps}</ol>
    <div class="page-head"><span class="eyebrow">الخطوة ${n} من 3</span><h1 tabindex="-1">${title}</h1>${lead ? `<p class="lead">${lead}</p>` : ""}</div>`;
}
function pageHead(eyebrow, title, lead) {
  return `<div class="page-head"><span class="eyebrow">${eyebrow}</span><h1 tabindex="-1">${title}</h1>${lead ? `<p class="lead">${lead}</p>` : ""}</div>`;
}
function setNav(route) {
  document.querySelectorAll("[data-nav]").forEach((a) => {
    if (a.dataset.nav === route) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
}
// موضع الاستئناف: آخر مهارة فُتحت، وإلا أول مهارة لم تُقيَّم في جلسة البداية ثم في الكل.
function resumeHref() {
  const c = readCursor();
  if (c && (c.list === "start" || c.list === "all")) {
    const i = listFor(c.list).findIndex((x) => x.id === c.id);
    if (i >= 0) return `#/assess/${c.list}/${i + 1}`;
  }
  const s = starter();
  const i = s.findIndex(({ id }) => state.profile.levels[id] === undefined);
  if (i >= 0) return `#/assess/start/${i + 1}`;
  const all = fullList();
  const j = all.findIndex(({ id }) => state.profile.levels[id] === undefined);
  return `#/assess/all/${j >= 0 ? j + 1 : 1}`;
}

// ---------------------------------------------------------------- لافتة حالة المصادر
function renderBanner() {
  const m = state.manifest;
  const items = [];
  if (state.manifestError) {
    items.push(["warn", `تعذر قراءة حالة المصادر (${h(state.manifestError)}). البيانات المعروضة من آخر بناء محلي، وتاريخ التحقق غير معروف.`]);
  } else if (m?.status === "failed") {
    items.push(["error", `تعذر بناء بيانات جديدة: ${h(m.message || "")} تُعرض آخر بيانات سليمة بُنيت في ${h(L.formatDate(state.data.generated_at))}. <a href="#/about">التفاصيل</a>`]);
  } else if (m?.status === "degraded") {
    const bad = m.sources.filter((s) => s.status !== "ok");
    const list = bad.map((s) => `${h(s.title)}${s.verified_at ? ` (آخر نسخة سليمة: ${h(L.formatDate(s.verified_at, false))})` : ""}`).join("، ");
    items.push(["warn", `تعذر تحديث بعض المصادر في آخر محاولة: ${list}. تُعرض آخر نسخة سليمة لكل مصدر. <a href="#/about">التفاصيل</a>`]);
  }
  if (state.storageNotice) items.push(["warn", h(state.storageNotice)]);
  if (!state.storageOk) items.push(["warn", "التخزين المحلي غير متاح في هذا المتصفح؛ لن تُحفظ إجاباتك بعد إغلاق الصفحة. نزّل نسخة من تقدمك من صفحة «حفظ ونقل» قبل المغادرة."]);
  banner.innerHTML = items.map(([kind, text]) =>
    `<div class="banner banner-${kind}" role="${kind === "error" ? "alert" : "status"}"><span class="icon" aria-hidden="true">${kind === "error" ? "⛔" : "⚠️"}</span><p>${text}</p></div>`).join("");
}

// ---------------------------------------------------------------- الصفحة الرئيسية
function compassArt() {
  const ticks = Array.from({ length: 48 }, (_, i) => {
    const a = (i * 7.5) * Math.PI / 180, r1 = i % 6 === 0 ? 88 : 92, r2 = 97;
    return `<line x1="${(110 + r1 * Math.sin(a)).toFixed(1)}" y1="${(110 - r1 * Math.cos(a)).toFixed(1)}" x2="${(110 + r2 * Math.sin(a)).toFixed(1)}" y2="${(110 - r2 * Math.cos(a)).toFixed(1)}" stroke="#F6F3EC" stroke-opacity="${i % 6 === 0 ? .9 : .45}" stroke-width="${i % 6 === 0 ? 2 : 1}"/>`;
  }).join("");
  return `<svg viewBox="0 0 220 220" aria-hidden="true" focusable="false">
    <circle cx="110" cy="110" r="106" fill="#0E5E63"/><circle cx="110" cy="110" r="78" fill="#0A474B"/>${ticks}
    <path d="M110 110 L160 52" stroke="#1F5FA8" stroke-width="6" stroke-linecap="round" opacity=".95"/>
    <path d="M110 110 L52 64" stroke="#B4541D" stroke-width="6" stroke-linecap="round" opacity=".95"/>
    <circle cx="160" cy="52" r="10" fill="#E4EDF8" stroke="#1F5FA8" stroke-width="3"/><text x="160" y="57" text-anchor="middle" font-size="13" font-weight="700" fill="#1F5FA8">1</text>
    <circle cx="52" cy="64" r="10" fill="#F8E8DD" stroke="#B4541D" stroke-width="3"/><text x="52" y="69" text-anchor="middle" font-size="13" font-weight="700" fill="#B4541D">2</text>
    <path d="M110 34 L121 110 L110 104 L99 110 Z" fill="#C8902E"/><path d="M110 186 L99 110 L110 116 L121 110 Z" fill="#F6F3EC"/>
    <circle cx="110" cy="110" r="7" fill="#102A3A" stroke="#F6F3EC" stroke-width="2.5"/></svg>`;
}

function viewHome() {
  const d = state.data, c = d.framework.counts;
  const p = state.profile;
  let action = `<div class="actions"><a class="btn btn-primary btn-lg" href="#/path">ابدأ: اختر مجالك</a></div>
    <p class="small muted">تختار مجالًا، ثم تحدد مستواك في نحو 10 مهارات منه، مهارة في كل شاشة، فترى نتيجة أولية وخطوة قادمة. يمكنك التوقف والعودة متى شئت.</p>`;
  if (p.paths && L.hasAnswers(p)) {
    const prog = L.progress(d, p);
    const [A, B] = pathGroups();
    action = `<div class="card resume" role="region" aria-labelledby="resume-h">
      <h2 id="resume-h">مرحبًا بعودتك</h2>
      <p>مجالك: ${label(A)}${B ? `، وتقارنه بـ${label(B)}` : ""}. قيّمت ${num(prog.rated)} من ${num(prog.total)} مهارة في نطاقك.</p>
      <div class="actions"><a class="btn btn-primary btn-lg" href="#/result">اعرض نتيجتي وخطوتي القادمة</a><a class="btn btn-ghost" href="${resumeHref()}">تابع التقييم من حيث توقفت</a></div>
      <p class="small muted" style="margin:.6rem 0 0">إجاباتك محفوظة في هذا المتصفح فقط. لتغيير المجال: <a href="#/path">اختر مجالًا آخر</a> (تبقى تقييماتك).</p></div>`;
  }
  return `
  <section class="hero">
    <div>
      <span class="eyebrow">بوصلة · القطاع الرقمي في السعودية</span>
      <h1 tabindex="-1">اعرف ما تحتاج تطويره في مجالك المهني</h1>
      <p class="lead">اختر مجالًا مهنيًا، وحدّد مستواك في مهاراته، ثم اعرف ما تحتاج تطويره وخطوتك القادمة. المهارات من إطار المهارات الرسمي للقطاع الرقمي.</p>
      <p class="note small">تغطي بوصلة حاليًا مجالات <strong>القطاع الرقمي فقط</strong>: ${num(c.group_entries)} مجالًا في تقنية المعلومات والاتصالات.</p>
      ${action}
    </div>
    <div class="hero-art">${compassArt()}</div>
  </section>
  <section class="section" aria-labelledby="how-h">
    <h2 id="how-h">كيف تعمل؟</h2>
    <ol class="steps">
      <li class="step"><h3>اختر مجالك</h3><p>مثل «البرمجيات». ابحث بالاسم، وترى أمثلة على مهارات كل مجال.</p></li>
      <li class="step"><h3>حدّد مستواك</h3><p>نحو 10 مهارات للبداية، مهارة في كل شاشة. «لا أعرف» تتركها دون تقييم.</p></li>
      <li class="step"><h3>نتيجتك وخطوتك القادمة</h3><p>ما تحتاج تطويره أولًا، ولماذا، وخطوة عملية صغيرة.</p></li>
    </ol>
  </section>
  <section class="section grid grid-2">
    <div class="card"><h2>خصوصيتك</h2><p>إجاباتك تبقى في هذا المتصفح فقط، ولا تُرسل إلى أي جهة. يمكنك تنزيل نسخة منها أو مسحها في أي وقت من صفحة <a href="#/save">حفظ ونقل</a>.</p></div>
    <div class="card"><h2>ما لا تقوله بوصلة</h2>
      <ul class="checklist">
        <li class="n">ليست اختبارًا معتمدًا: النتيجة من تقييمك الذاتي.</li>
        <li class="n">لا تعرض وظائف شاغرة ولا تقدّر فرص توظيفك.</li>
        <li class="n">المصدر لا يحدد «المستوى المطلوب» لكل مجال؛ الهدف تختاره أنت.</li>
      </ul>
      <p class="small" style="margin:.7rem 0 0">للإرشاد المهني الشخصي: ${external(d.links.sobol, "برنامج «سبل» للتوجيه والإرشاد المهني")}. ولمصادر البيانات: <a href="#/about">عن البيانات</a>.</p></div>
  </section>`;
}

// ---------------------------------------------------------------- الخطوة 1: المجال
function fieldOption(g, selectedId, twins) {
  const examples = L.fieldExamples(state.data, g.id);
  const prio = g.technical.filter((id) => state.data.skills[id].priority).length;
  const twin = twins[g.id] ? `<span class="field-twin">يوجد مجال بالاسم نفسه في قطاع ${h(twins[g.id].join("، "))}، بمهارات مختلفة.</span>` : "";
  return `<label class="field-option" data-name="${h(g.name)}"><input type="radio" name="field" value="${h(g.id)}" data-field${g.id === selectedId ? " checked" : ""}>
    <span class="field-body"><strong>${h(g.name)}</strong> <span class="sector">(${h(g.subsector)})</span>
    <span class="field-examples">من مهاراته المميزة: ${examples.map(h).join("، ")}${prio > examples.length ? "…" : ""}</span>${twin}</span></label>`;
}

function fieldList(selectedId) {
  const twins = L.namesakes(state.data);
  return `<div class="field-search"><label class="field-label" for="field-search">ابحث باسم المجال</label>
      <input id="field-search" class="search" type="search" autocomplete="off" placeholder="مثال: البرمجيات" data-action="field-search"></div>
    <p id="field-none" class="muted" hidden>لا يوجد مجال بهذا الاسم. جرّب كلمة أقصر.</p>
    ${state.data.subsectors.map((sub) => `<fieldset class="field-group"><legend>${h(sub.name)} <span class="muted small">(${num(sub.groups.length)} مجالًا)</span></legend>
      ${sub.groups.map((g) => fieldOption(g, selectedId, twins)).join("")}</fieldset>`).join("")}
    <p class="small muted">الأمثلة مشتقة من الإطار الرسمي: مهارات معلَّمة «ذات أولوية» في المجال وتظهر في مجالات قليلة غيره. ليست وصفًا رسميًا للمجال.</p>`;
}

function nameList(ids, limit = 8) {
  const names = ids.map((id) => state.data.skills[id].name);
  if (!names.length) return `<p class="muted">لا مهارات في هذا القسم.</p>`;
  const shown = names.slice(0, limit).map((n) => `<li>${h(n)}</li>`).join("");
  const rest = names.slice(limit).map((n) => `<li>${h(n)}</li>`).join("");
  return `<ul class="name-list">${shown}</ul>${rest ? `<details class="more"><summary>اعرض البقية (${num(names.length - limit)})</summary><ul class="name-list">${rest}</ul></details>` : ""}`;
}

function fieldSummary(g) {
  const d = state.data;
  const c = d.curated?.[g.id];
  const s = starter();
  const all = fullList();
  return `<section class="card path-card path-a" aria-labelledby="chosen-h">
    <span class="eyebrow">مجالك</span>
    <h2 id="chosen-h" tabindex="-1"><span class="dot dot-a" aria-hidden="true"></span> ${h(g.name)} <span class="sector">— ${h(g.subsector)}</span></h2>
    ${c ? `<p>${h(c.overview)} <span class="small muted">(${external(c.source_url, `ملف المجموعات والمسارات الرسمي، صفحة ${c.page}`)})</span></p>` : ""}
    <p><strong>ماذا بعد؟</strong> تحدد مستواك في ${count(s.length)} للبداية، مهارة في كل شاشة، ثم ترى نتيجة أولية. يمكنك بعدها مواصلة تقييم بقية مهارات المجال (${count(all.length)} في نطاقك).</p>
    <div class="actions"><a class="btn btn-primary btn-lg" href="#/assess/start/1">ابدأ بـ${count(s.length)}</a>
      <a class="btn btn-ghost" href="#/assess/all/1">قيّم كل مهارات المجال</a></div>
    <details class="more" id="starter-rule"><summary>كيف اخترنا مهارات البداية؟</summary>
      <p class="small">من المهارات المعلَّمة «ذات أولوية» في مجالك، اخترنا نصفها الأكثر انتشارًا في مجالات الإطار (تفيدك حتى لو غيّرت مجالك)، ونصفها الأكثر تمييزًا لمجالك (الأقل ظهورًا في غيره). هذا اجتهاد تعليمي من بوصلة لبداية سريعة، ليس ترتيبًا رسميًا ولا عينة تمثل المجال، ولا يعني أنها متطلبات وظيفة. بقية مهارات المجال متاحة للتقييم في أي وقت.</p>
      ${nameList(s.map((x) => x.id), 10)}</details>
    ${c ? `<details class="more"><summary>أمثلة على أدواره الوظيفية (من المصدر)</summary><ul class="roles">${c.roles.map((r) => `<li>${h(r)}</li>`).join("")}</ul>
      <h3 class="h4">رموز التصنيف السعودي الموحد للمهن ذات الصلة</h3>
      <table class="codes">${c.occupation_units.map((u) => `<tr><td class="num">${h(u.code)}</td><td>${h(u.title)}</td></tr>`).join("")}</table></details>` : ""}
  </section>`;
}

function compareBlock(aId, bId) {
  const cmp = L.comparePaths(state.data, aId, bId, state.profile.scope);
  const total = cmp.counts.onlyA + cmp.counts.shared + cmp.counts.onlyB || 1;
  const w = (n) => (100 * n / total).toFixed(2);
  const lists = { shared: cmp.shared, a: cmp.onlyA, b: cmp.onlyB };
  const tabs = [["shared", `المشتركة (${cmp.counts.shared})`], ["a", `في «${cmp.a.name}» فقط (${cmp.counts.onlyA})`], ["b", `في «${cmp.b.name}» فقط (${cmp.counts.onlyB})`]];
  return `<div class="compare-result">
    <p>يشترك ${label(cmp.a)} و${label(cmp.b)} في ${num(cmp.counts.shared)} مهارة فنية${state.profile.scope === "all" ? "" : " ذات أولوية"}. في الأول وحده ${num(cmp.counts.onlyA)}، وفي الثاني وحده ${num(cmp.counts.onlyB)}.</p>
    <div class="overlap" aria-hidden="true"><span class="seg-a" style="width:${w(cmp.counts.onlyA)}%"></span><span class="seg-both" style="width:${w(cmp.counts.shared)}%"></span><span class="seg-b" style="width:${w(cmp.counts.onlyB)}%"></span></div>
    <div class="compare-stats">
      <div class="stat"><span class="value num">${cmp.counts.shared}</span><span class="label">مشتركة</span></div>
      <div class="stat"><span class="value num">${cmp.counts.onlyA}</span><span class="label">في «${h(cmp.a.name)}» فقط</span></div>
      <div class="stat"><span class="value num">${cmp.counts.onlyB}</span><span class="label">في «${h(cmp.b.name)}» فقط</span></div>
    </div>
    <p class="small muted" style="margin-top:.7rem">المهارات المشتركة تظهر أولًا في التقييم الكامل والخطة لأنها تخدم المجالين معًا. جلسة البداية تبقى من مجالك الأساسي.</p>
    <details class="more" id="cmp-names"><summary>اعرض أسماء المهارات</summary>
      <div class="tabs" role="group" aria-label="قوائم المهارات">${tabs.map(([k, l]) =>
        `<button class="tab" type="button" data-ctab="${k}" aria-pressed="${state.ui.compareTab === k}">${h(l)}</button>`).join("")}</div>
      ${nameList(lists[state.ui.compareTab], 12)}
    </details></div>`;
}

function pathOptions(selected, exclude) {
  return `<option value="">— اختر مجالًا للمقارنة —</option>` + state.data.subsectors.map((sub) => `<optgroup label="${h(sub.name)}">${sub.groups.filter((g) => g.id !== exclude).map((g) =>
    `<option value="${h(g.id)}"${g.id === selected ? " selected" : ""}>${h(g.name)} — ${h(sub.name)}</option>`).join("")}</optgroup>`).join("");
}

function marketDetails() {
  const m = state.data.market;
  if (!m) return "";
  const max = Math.max(...m.regions.map((r) => r.workers_q2 || 0));
  return `<details class="card more-card" id="market"><summary><strong>سياق عام: كم يعمل في نشاط «${h(m.activity)}»؟</strong> <span class="small muted">(اختياري)</span></summary>
    <p class="small">هذه أعداد منشآت النشاط كله في القطاع الخاص، وليست أعداد مجالك ولا وظائف شاغرة.</p>
    <div class="grid grid-3">
      <div class="stat"><span class="value num">${h(L.formatNumber(m.national.workers_q2))}</span><span class="label">عاملون على رأس العمل، ${h(m.periods[1])}</span></div>
      <div class="stat"><span class="value num">${h(L.formatSigned(m.national.change))}</span><span class="label">التغير عن ${h(m.periods[0])} (<span class="num">${h(L.formatPercent(m.national.change_rate, { signed: true }))}</span>)</span></div>
      <div class="stat"><span class="value num">${h(L.formatPercent(m.national.share_q2))}</span><span class="label">من كل العاملين في القطاع الخاص</span></div>
    </div>
    <h3 class="h4" style="margin-top:14px">حسب المنطقة الإدارية — ${h(m.periods[1])}</h3>
    <ul class="bars">${m.regions.slice(0, 13).map((r) => `<li><span>${h(r.region)}</span><span class="bar" aria-hidden="true"><span style="width:${max ? (100 * (r.workers_q2 || 0) / max).toFixed(1) : 0}%"></span></span><span class="val num">${h(L.formatNumber(r.workers_q2))}</span></li>`).join("")}</ul>
    <ul class="checklist small" style="margin-top:14px">${m.notes.map((n) => `<li class="n">${h(n)}</li>`).join("")}</ul>
    <p class="small muted" style="margin:10px 0 0">المصدر: ${m.datasets.map((ds) => external(ds.url, h(ds.period))).join(" · ")} — منصة البيانات المفتوحة.</p>
  </details>`;
}

function viewPath() {
  const [aId, bId] = paths();
  const head = stepHead(1, "اختر مجالك المهني",
    "المجال المهني (يسميه الإطار الرسمي «مجموعة وظيفية») عائلة من الوظائف المتقاربة في مهاراتها، مثل «البرمجيات». اختر المجال الأقرب لما تريد العمل فيه؛ يمكنك تغييره لاحقًا دون فقد تقييماتك.");
  const err = state.ui.pathError && !aId ? `<p id="field-err" class="field-error" role="alert">اختر مجالًا من القائمة أولًا.</p>` : "";
  if (!aId) {
    return `${head}<section class="card" aria-labelledby="pick-h"><h2 id="pick-h" class="h3">ما المجال الذي يهمك؟</h2>${err}${fieldList(null)}</section>
      <nav class="step-nav" aria-label="التنقل بين الخطوات"><a class="btn btn-ghost" href="#/">رجوع</a>
        <div class="step-nav-main"><p class="small muted">اختر مجالًا لتنتقل إلى الخطوة التالية.</p>
        <button class="btn btn-primary btn-lg" type="button" data-action="path-next">التالي: حدّد مستواك</button></div></nav>`;
  }
  return `${head}
  ${fieldSummary(groups().get(aId))}
  <details class="card more-card section" id="change-field"><summary><strong>غيّر المجال</strong> <span class="small muted">(تبقى تقييماتك محفوظة)</span></summary>${fieldList(aId)}</details>
  <details class="card more-card section" id="compare-box"${bId ? " open" : ""}><summary><strong>قارن مجالك بمجال آخر</strong> <span class="small muted">(اختياري)</span></summary>
    <p class="small">مفيد إن كنت مترددًا بين مجالين: ترى ما يشتركان فيه، فتبدأ بما يخدمهما معًا.</p>
    <label class="field-label" for="compare">مجال المقارنة</label>
    <select id="compare" class="select select-b" data-path="compare">${pathOptions(bId, aId)}</select>
    ${bId ? `${compareBlock(aId, bId)}<button class="link-btn" type="button" data-action="compare-off">ألغِ المقارنة</button>` : ""}
  </details>
  <div class="section">${marketDetails()}</div>
  <nav class="step-nav" aria-label="التنقل بين الخطوات"><a class="btn btn-ghost" href="#/">رجوع</a></nav>`;
}

// ---------------------------------------------------------------- الخطوة 2: مهارة في كل شاشة
function levelOptions(id) {
  const guide = L.levelGuide(state.data, id);
  const current = state.profile.levels[id];
  return `<div class="level-options">${guide.map(([name, meaning], lvl) =>
    `<label class="level-option"><input type="radio" name="level" value="${lvl}" data-skill="${h(id)}"${current === lvl ? " checked" : ""}>
      <span class="lv-num" aria-hidden="true">${lvl === 0 ? "—" : lvl}</span>
      <span class="lv-text"><strong>${lvl === 0 ? h(name) : `${lvl}. ${h(name)}`}</strong><span>${h(meaning)}</span></span></label>`).join("")}</div>`;
}

function statusLine(id) {
  const level = state.profile.levels[id];
  if (level === undefined) {
    const why = state.ui.unsure[id];
    return why ? `<span class="status-unrated">تركتها دون تقييم (${why === "dontknow" ? "لا تعرف هذه المهارة" : "لست متأكدًا من مستواك"}).</span> لا تُحسب صفرًا ولا تدخل النتيجة.`
      : `<span class="status-unrated">لم تقيّمها بعد.</span> اختر مستوى، أو انتقل إلى التالية إن أردت تخطيها.`;
  }
  const [name] = L.levelGuide(state.data, id)[level];
  return `<span class="status-rated">✓ اخترت: ${level === 0 ? h(name) : `${level}. ${h(name)}`}</span>`;
}

function shortDescription(id) {
  const s = state.data.skills[id];
  if (!s.description) return `<p class="skill-desc muted">لا يوجد وصف لهذه الصيغة من اسم المهارة في قاعدة البيانات.</p>`;
  if (s.description.length <= 170) return `<p class="skill-desc">${h(s.description)}</p>`;
  const cut = s.description.slice(0, 160).replace(/\s+\S*$/, "");
  return `<p class="skill-desc">${h(cut)}… </p><details class="more small" id="desc-more"><summary>اقرأ الوصف كاملًا</summary><p class="skill-desc">${h(s.description)}</p></details>`;
}

function skillJump(list, listName, n) {
  return `<details class="more" id="skill-jump"><summary>انتقل إلى مهارة بعينها</summary>
    <ol class="jump-list">${list.map(({ id }, i) => {
      const rated = state.profile.levels[id] !== undefined;
      return `<li><a href="#/assess/${listName}/${i + 1}"${i + 1 === n ? ' aria-current="true"' : ""}>${h(state.data.skills[id].name)}</a> <span class="small ${rated ? "status-rated" : "muted"}">${rated ? "✓ مقيّمة" : "غير مقيّمة"}</span></li>`;
    }).join("")}</ol></details>`;
}

function viewAssess(listArg, nArg) {
  if (!state.profile.paths) {
    return emptyState("🧭", "اختر مجالك أولًا", "نحتاج أن نعرف مجالك لنعرض مهاراته.", `<a class="btn btn-primary btn-lg" href="#/path">اختر مجالك</a>`);
  }
  const listName = listArg === "all" ? "all" : "start";
  const list = listFor(listName);
  if (!list.length) return emptyState("🧭", "لا مهارات في هذا النطاق", "غيّر النطاق أو المجال.", `<a class="btn btn-primary" href="#/path">المجال</a>`);
  const n = Math.min(Math.max(1, Number(nArg) || 1), list.length);
  const { id, where } = list[n - 1];
  writeStorage(CURSOR_KEY, JSON.stringify({ list: listName, id }));
  const s = state.data.skills[id];
  const prog = L.progress(state.data, state.profile, list);
  const { max, type } = L.scaleFor(state.data, id);
  const t = L.targetFor(state.data, state.profile, id);
  const isDefault = state.profile.targets[type] === L.DEFAULT_TARGETS[type];
  const last = n === list.length;
  return `${stepHead(2, listName === "start" ? "حدّد مستواك: جلسة البداية" : "حدّد مستواك: كل المهارات")}
  <div class="progress-box" id="progress-box">
    <p class="progress-text"><strong>المهارة ${num(n)} من ${num(list.length)}</strong> · <span id="progress-text">قيّمت ${num(prog.rated)} من ${num(list.length)}</span></p>
    <div class="progress" aria-hidden="true"><span id="progress-bar" style="width:${(100 * prog.rated / list.length).toFixed(1)}%"></span></div>
  </div>
  <article class="card skill-screen" aria-labelledby="skill-title">
    <div class="skill-tags">${whereText(where)}${s.type === "general" ? `<span class="chip">مهارة عامة</span>` : ""}</div>
    <h2 id="skill-title" class="skill-title" tabindex="-1">${h(s.name)}</h2>
    ${shortDescription(id)}
    <fieldset class="level-set"><legend>ما مستواك في هذه المهارة؟</legend>
      <p class="small muted scale-hint">الشرح بجانب كل خيار مبسّط من بوصلة وعام لكل المهارات، وليس الوصف الرسمي لهذه المهارة.</p>
      ${levelOptions(id)}</fieldset>
    <div class="unsure-row"><span class="small muted">أو اتركها دون تقييم:</span>
      <button class="btn btn-ghost btn-sm" type="button" data-unknown="dontknow">لا أعرف هذه المهارة</button>
      <button class="btn btn-ghost btn-sm" type="button" data-unknown="unsure">لست متأكدًا من مستواي</button></div>
    <p class="skill-status" id="skill-status" aria-live="polite">${statusLine(id)}</p>
    <p class="small muted target-line">الهدف المستخدم في الحساب: المستوى ${num(t)} من ${num(max)}${isDefault ? " — قيمة مقترحة من بوصلة، ليست متطلبًا رسميًا" : " — اخترته أنت"}. يمكنك تغييره في <a href="#/result#targets">صفحة النتيجة</a>.</p>
    ${s.page ? `<details class="more small" id="official-levels"><summary>الوصف الرسمي لمستويات هذه المهارة</summary>
      <p>${external(`${L.safeUrl(state.data.links.dictionary)}#page=${s.page}`, `افتح قاموس المهارات الرسمي — ملف PDF خارجي، صفحة ${s.page}`)}</p>
      ${s.page_verified ? "" : `<p class="muted">حُدّدت الصفحة بترتيب المهارات في القاموس، وقد يختلف عنوانها قليلًا عن الاسم هنا.</p>`}</details>` : ""}
  </article>
  <nav class="step-nav" aria-label="التنقل بين المهارات">
    ${n > 1 ? `<a class="btn btn-ghost" href="#/assess/${listName}/${n - 1}">السابق</a>` : `<a class="btn btn-ghost" href="#/path">رجوع: المجال</a>`}
    <div class="step-nav-main">
      <p class="small muted">${last ? (listName === "start" ? "هذه آخر مهارة في جلسة البداية. بعدها ترى نتيجتك الأولية." : "هذه آخر مهارة في القائمة.") : "اختر مستوى ثم اضغط «التالي»، أو اضغط «التالي» لتخطيها."}</p>
      ${last ? `<a class="btn btn-primary btn-lg" href="#/result">${listName === "start" ? "اعرض نتيجتي الأولية" : "اعرض نتيجتي"}</a>` : `<a class="btn btn-primary btn-lg" href="#/assess/${listName}/${n + 1}">التالي</a>`}
    </div>
  </nav>
  <div class="assess-extra">${last ? "" : `<p class="small"><a href="#/result">أنهيت الآن؟ اعرض نتيجتي (تشمل ما قيّمته فقط)</a></p>`}${skillJump(list, listName, n)}</div>`;
}

// ---------------------------------------------------------------- الخطوة 3: النتيجة والخطة
function stepItems(steps) {
  return steps.map((s) => `<li>${s.url ? external(s.url, h(s.text)) : h(s.text)}<span class="src">${h(s.source)}</span></li>`).join("");
}

function targetsBlock() {
  const sc = state.data.framework.scale;
  const t = state.profile.targets;
  const isDefault = t.technical === L.DEFAULT_TARGETS.technical && t.general === L.DEFAULT_TARGETS.general;
  const stepper = (type, text, max) => `<div><div class="field-label" id="tl-${type}">${text}</div><div class="stepper" role="group" aria-labelledby="tl-${type}">
    <button type="button" data-target="${type}" data-delta="-1" aria-label="خفض هدف ${text}"${t[type] <= 1 ? " disabled" : ""}>−</button><output class="num" aria-live="polite">${t[type]}</output>
    <button type="button" data-target="${type}" data-delta="1" aria-label="رفع هدف ${text}"${t[type] >= max ? " disabled" : ""}>+</button><span class="small muted">من <span class="num">${max}</span></span></div></div>`;
  return `<section class="card" id="targets" aria-labelledby="targets-h"><h2 id="targets-h" class="h3" tabindex="-1">هدفك</h2>
    <p class="small">المستخدم في الحساب الآن: المستوى ${num(t.technical)} للمهارات الفنية و${num(t.general)} للعامة${isDefault ? " — قيمة مقترحة من بوصلة للبداية، ليست متطلبًا رسميًا" : " — اخترته أنت"}. الفجوة = هدفك ناقص مستواك. المصدر لا يحدد مستوى مطلوبًا لكل مجال.</p>
    <div class="targets">${stepper("technical", "المهارات الفنية", sc.technical.max)}${stepper("general", "المهارات العامة", sc.general.max)}</div>
    ${isDefault ? "" : `<button class="link-btn" type="button" data-action="reset-targets">ارجع إلى القيمة المقترحة (3 و2)</button>`}
    <p class="small muted" style="margin:.4rem 0 0">تغيير الهدف يعيد حساب الفجوات، ولا يحذف اختياراتك في الخطة.</p></section>`;
}

function scopeChoice() {
  const count2 = (scope) => L.assessmentItems(state.data, state.profile.paths, scope).length;
  return `<fieldset class="radio-row"><legend class="h4">أي المهارات تدخل الحساب؟</legend>
      <label class="check"><input type="radio" name="scope" value="priority" data-scope-choice${state.profile.scope === "priority" ? " checked" : ""}> ذات الأولوية في القطاع والعامة (${num(count2("priority"))}) — <span class="muted">مقترح</span></label>
      <label class="check"><input type="radio" name="scope" value="all" data-scope-choice${state.profile.scope === "all" ? " checked" : ""}> كل المهارات الفنية والعامة (${num(count2("all"))})</label>
    </fieldset><p class="small muted">تقييماتك لا تُحذف عند تغيير النطاق.</p>`;
}

function viewResult() {
  if (!state.profile.paths) {
    return emptyState("🧭", "لا نتيجة بعد", "اختر مجالك أولًا، ثم حدّد مستواك في مهاراته.", `<a class="btn btn-primary btn-lg" href="#/path">اختر مجالك</a>`);
  }
  const d = state.data;
  const s = L.planState(d, state.profile);
  const pg = pathGroups();
  if (s.mode === "unrated") {
    return stepHead(3, "نتيجتك وخطوتك القادمة") + emptyState("📝", "لم تقيّم أي مهارة بعد", "ابدأ بجلسة البداية القصيرة؛ تكفي بضع مهارات لترى نتيجة أولية.", `<a class="btn btn-primary btn-lg" href="#/assess/start/1">ابدأ جلسة البداية</a>`);
  }
  const name = (id) => h(d.skills[id].name);
  const st = starter();
  const startRated = st.filter(({ id }) => state.profile.levels[id] !== undefined).length;
  const sums = pg.map((g) => L.pathSummary(d, state.profile, g.id));
  const met = s.progress.rated - s.gaps.length;
  const next = L.nextStep(s);
  const summaryCards = pg.map((g, i) => `<div class="summary-card ${i ? "b" : "a"}"><h3><span class="dot dot-${i ? "b" : "a"}" aria-hidden="true"></span> ${h(g.name)} <span class="sector">— ${h(g.subsector)}</span></h3>
    ${i ? `<p class="small muted" style="margin:0">مجال المقارنة</p>` : ""}
    <div class="counts"><div><strong class="num">${sums[i].below}</strong><span>دون هدفك</span></div><div><strong class="num">${sums[i].met}</strong><span>بلغت هدفك</span></div><div><strong class="num">${sums[i].unrated}</strong><span>لم تقيّمها</span></div></div></div>`).join("");
  const planItem = ({ gap, steps, why }, i, chosen) => `<li class="plan-item">
      <div class="plan-head"><h3><span class="num">${i + 1}</span>. ${name(gap.id)}</h3>
        ${chosen ? `<button class="btn btn-ghost btn-sm" type="button" data-plan-remove="${h(gap.id)}">أزل من خطتي</button>`
          : `<button class="btn btn-ghost btn-sm" type="button" data-plan-add="${h(gap.id)}">أضف إلى خطتي</button>`}</div>
      <p class="small"><strong>لماذا:</strong> ${h(why)}</p>
      <details class="more"><summary>خطوات عملية</summary><ol class="steps-list">${stepItems(steps)}</ol></details></li>`;
  const visible = state.ui.showAllPlan ? s.active : s.active.slice(0, PLAN_VISIBLE);
  const excluded = s.excluded.length ? `<div class="note" role="note"><h3 class="h4">مهارات اخترتها ولم تعد في الخطة (${num(s.excluded.length)})</h3>
      <p class="small">لم نحذفها من اختيارك؛ تعود تلقائيًا إن صارت فجوة من جديد.</p>
      <ul class="small">${s.excluded.map((x) => `<li><strong>${name(x.id)}</strong>: ${h(x.reason.text)} <button class="link-btn" type="button" data-plan-remove="${h(x.id)}">أزلها من اختياري</button></li>`).join("")}</ul></div>` : "";
  const gapRow = (g) => {
    const inPlan = s.chosen.includes(g.id);
    return `<li class="gap-row"><div><strong>${name(g.id)}</strong><span class="small muted"> — مستواك ${g.level === 0 ? "«لم أبدأ»" : g.level} وهدفك ${g.target}</span><div class="small">${h(L.whyGap(d, state.profile, g))}</div></div>
      ${inPlan ? `<button class="btn btn-ghost btn-sm" type="button" data-plan-remove="${h(g.id)}">في خطتي — أزل</button>` : `<button class="btn btn-ghost btn-sm" type="button" data-plan-add="${h(g.id)}">أضف إلى خطتي</button>`}</li>`;
  };
  const unratedNote = s.progress.unrated
    ? `<div class="banner banner-info" role="note"><span class="icon" aria-hidden="true">ℹ️</span><p><strong>نتيجة ${startRated && s.progress.rated <= st.length ? "أولية" : "جزئية"}:</strong> مبنية على ما قيّمته فقط. المهارات المقيّمة: ${num(s.progress.rated)}، وغير المقيّمة في نطاقك: ${num(s.progress.unrated)} (لا نعرف مستواك فيها، ولا تُحسب صفرًا).${st.length && startRated < st.length ? ` من جلسة البداية: ${num(startRated)} من ${num(st.length)} مقيّمة.` : ""}</p></div>` : "";

  return `${stepHead(3, "نتيجتك وخطوتك القادمة", "مبنية على تقييمك الذاتي مقابل هدف تختاره أنت.")}
  ${unratedNote}
  <section aria-labelledby="sum-h"><h2 id="sum-h" class="sr-only">ملخص</h2>
    <p class="result-line">من المهارات التي قيّمتها (${num(s.progress.rated)}): ${num(s.gaps.length)} دون هدفك، و${num(met)} بلغت هدفك.</p>
    <div class="summary-cards${pg.length === 1 ? " single" : ""}">${summaryCards}</div></section>
  ${s.mode === "no-gaps" ? `<div class="card empty-inline"><h2>لا فجوات فيما قيّمته</h2>
      <p>كل ما قيّمته بلغ الهدف الذي اخترته${s.progress.unrated ? `. وفي نطاقك مهارات لم تقيّمها بعد (${num(s.progress.unrated)})، فلا نعرف عنها شيئًا` : ""}. يمكنك مواصلة التقييم أو رفع هدفك (أدناه).</p></div>` : ""}
  ${next ? `<section class="card next-step section" aria-labelledby="next-h">
      <span class="eyebrow">خطوتك القادمة${next.suggested ? ` <span class="chip chip-gold">اقتراح بوصلة</span>` : ""}</span>
      <h2 id="next-h">${name(next.gap.id)}</h2>
      <p class="why"><strong>لماذا هذه؟</strong> ${next.suggested ? "أول فجوة بترتيب بوصلة (لم تخترها بعد). " : "أول مهارة في خطتك. "}${h(next.why)}</p>
      <ol class="steps-list">${stepItems(next.steps)}</ol>
      ${next.suggested ? `<button class="btn btn-ghost btn-sm" type="button" data-plan-add="${h(next.gap.id)}">أضف إلى خطتي</button>` : ""}
    </section>` : ""}
  ${s.mode !== "no-gaps" ? `<section class="card section" aria-labelledby="plan-h">
    <h2 id="plan-h" tabindex="-1">خطتي${s.active.length ? ` (${num(s.active.length)})` : ""}</h2>
    <p class="small">${s.mode === "custom" ? "المهارات التي اخترتها بنفسك." : s.mode === "custom-empty" ? `<strong>${h(L.modeText("custom-empty"))}</strong>` : "خطتك فارغة: لم تختر مهارات بعد. أضف من اقتراحات بوصلة أدناه أو من كل الفجوات."}</p>
    ${state.ui.planNotice ? `<p class="small status-ok" role="status">${h(state.ui.planNotice)}</p>` : ""}
    ${s.active.length ? `<ol class="plan-list">${visible.map((x, i) => planItem(x, i, true)).join("")}</ol>
      ${s.active.length > PLAN_VISIBLE ? `<button class="btn btn-ghost" type="button" data-action="toggle-plan-all" aria-expanded="${state.ui.showAllPlan}">${state.ui.showAllPlan ? "اعرض أول ثلاث فقط" : `اعرض بقية خطتي (${s.active.length - PLAN_VISIBLE})`}</button>` : ""}` : ""}
    ${excluded}
  </section>` : ""}
  ${s.suggestions.length ? `<section class="card section suggestions" aria-labelledby="sugg-h">
    <h2 id="sugg-h" class="h3">اقتراحات بوصلة <span class="small muted">(لم تخترها)</span></h2>
    <p class="small">أول الفجوات بالترتيب: المشتركة بين المجالين أولًا، ثم ذات الأولوية، ثم الأكبر فجوة. اقتراح من بوصلة لا متطلب رسمي، ولا يدخل خطتك إلا إذا أضفته.</p>
    ${next?.suggested ? `<p class="small muted">أولها «${name(next.gap.id)}» معروض أعلاه بوصفه خطوتك القادمة.</p>` : ""}
    <ol class="plan-list" start="${next?.suggested ? 2 : 1}">${s.suggestions.slice(next?.suggested ? 1 : 0, PLAN_VISIBLE + (next?.suggested ? 1 : 0)).map((x, i) => planItem(x, i + (next?.suggested ? 1 : 0), false)).join("")}</ol>
    <button class="btn btn-ghost" type="button" data-action="adopt-suggestions">أضف الاقتراحات كلها إلى خطتي (${num(s.suggestions.length)})</button>
  </section>` : ""}
  ${s.gaps.length ? `<details class="card more-card section" id="all-gaps"><summary><strong>كل الفجوات (${num(s.gaps.length)})</strong> — اختر بنفسك ما يدخل خطتك</summary>
    <ul class="gap-list">${s.gaps.map(gapRow).join("")}</ul></details>` : ""}
  <section class="card section" aria-labelledby="then-h"><h2 id="then-h" class="h3">ماذا بعد؟</h2>
    <div class="actions">
      ${s.progress.unrated ? `<a class="btn btn-primary" href="${resumeHref()}">واصل التقييم (غير المقيّمة: ${num(s.progress.unrated)})</a>` : ""}
      <a class="btn btn-ghost" href="#/save">احفظ نتيجتك أو انقلها</a>
      <a class="btn btn-ghost" href="#/path">قارن بمجال آخر</a></div></section>
  <div class="section grid grid-2">
    ${targetsBlock()}
    <div class="card"><h2 class="h3">حدود هذه النتيجة</h2><ul class="checklist small">
      <li class="n">تقييم ذاتي لم يتحقق منه أحد؛ ليس اختبارًا معتمدًا ولا شهادة.</li>
      <li class="n">ليس حكمًا على جاهزيتك ولا تقديرًا لفرص توظيفك.</li>
      <li class="n">الخطوات العملية اقتراحات عامة من بوصلة؛ المصدر لا يربط المهارات ببرامج تدريب.</li>
      <li class="y">لقياس مهاراتك وإرشادك مع مختصين: ${external(d.links.sobol, "خدمات «سبل»")}.</li></ul>
      <details class="more" id="scope-box"><summary>نطاق المهارات</summary>${scopeChoice()}</details></div>
  </div>
  <nav class="step-nav" aria-label="التنقل بين الخطوات"><a class="btn btn-ghost" href="${resumeHref()}">رجوع: التقييم</a></nav>`;
}

// ---------------------------------------------------------------- حفظ ونقل
function download(name, text, type, noteId) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  const note = document.getElementById(noteId);
  if (note) note.textContent = `بدأ طلب تنزيل «${name}». إذا لم يظهر الملف، راجع قائمة تنزيلات المتصفح.`;
}
const today = () => new Date().toISOString().slice(0, 10);

function profileFacts(p) {
  const g = groups();
  const [a, b] = p.paths || [];
  const prog = p.paths ? L.progress(state.data, p) : { rated: 0, total: 0 };
  const unmapped = p.unmapped.reduce((n, x) => n + Object.keys(x.levels).length + x.plan.length, 0);
  return `<dl class="kv">
    <dt>المجال الأساسي</dt><dd>${a ? h(plainLabel(g.get(a))) : "—"}</dd>
    <dt>مجال المقارنة</dt><dd>${b ? h(plainLabel(g.get(b))) : "لا يوجد"}</dd>
    <dt>التقييمات</dt><dd>${count(Object.keys(p.levels).length)} (${num(prog.rated)} منها في النطاق الحالي من ${num(prog.total)})</dd>
    ${unmapped ? `<dt>إجابات غير مطابقة</dt><dd>${count(unmapped)} من إصدار آخر للإطار، محفوظة دون عرض</dd>` : ""}
    <dt>خطتي</dt><dd>${p.plan.length ? count(p.plan.length) : "فارغة (لم تُختر مهارات)"}</dd>
    <dt>نطاق المهارات</dt><dd>${p.scope === "all" ? "كل المهارات الفنية" : "ذات الأولوية"}</dd>
    <dt>الهدف</dt><dd>فنية ${num(p.targets.technical)}، عامة ${num(p.targets.general)}</dd>
    <dt>آخر حفظ</dt><dd>${h(L.formatDate(p.updated))}</dd></dl>`;
}

function importPanel() {
  const ui = state.ui;
  if (ui.importErrors) {
    return `<div class="panel panel-error" id="import-panel" tabindex="-1" role="alert"><h3>لم نستعد الملف، ولم يتغير شيء في بياناتك</h3>
      <ul>${[...new Set(ui.importErrors.map((e) => e.text))].map((t) => `<li>${h(t)}</li>`).join("")}</ul>
      <p class="small"><strong>ماذا تفعل؟</strong> اختر نسخة تقدم نزّلتها من صفحة «حفظ ونقل» في بوصلة دون تعديلها. إن لم تكن لديك نسخة سليمة، تابع ببياناتك الحالية.</p>
      ${ui.importErrors.some((e) => e.detail) ? `<details class="more small"><summary>تفاصيل تقنية للمساعدة</summary><ul class="tech">${ui.importErrors.filter((e) => e.detail).map((e) => `<li><code>${h(e.detail)}</code></li>`).join("")}</ul></details>` : ""}
      <button class="btn btn-ghost" type="button" data-action="import-cancel">حسنًا</button></div>`;
  }
  if (ui.importPreview) {
    const { result, fileName } = ui.importPreview;
    const hasCurrent = L.hasAnswers(state.profile);
    return `<div class="panel" id="import-panel" tabindex="-1" role="region" aria-labelledby="imp-h"><h3 id="imp-h">راجع الملف قبل الاستعادة</h3>
      <p class="small">الملف: <span class="num">${h(fileName)}</span></p>
      ${profileFacts(result.profile)}
      ${result.info.notes.length ? `<ul class="small notes">${result.info.notes.map((n) => `<li>${h(n)}</li>`).join("")}</ul>` : ""}
      <p><strong>${hasCurrent ? "سيحل الملف محل بياناتك الحالية في هذا المتصفح" : "لا توجد بيانات حالية؛ سيُحفظ الملف في هذا المتصفح"}.</strong>${hasCurrent ? " إن أردت الاحتفاظ بالحالية فنزّل نسخة منها أولًا." : ""}</p>
      <div class="actions"><button class="btn btn-primary" type="button" data-action="import-confirm">استعد بيانات الملف</button>
        <button class="btn btn-ghost" type="button" data-action="import-cancel">إلغاء — أبقِ بياناتي كما هي</button></div></div>`;
  }
  if (ui.importDone) {
    return `<div class="panel panel-ok" id="import-panel" tabindex="-1" role="status"><h3>${h(ui.importDone.title)}</h3><p>${h(ui.importDone.text)}</p>
      ${ui.importDone.result ? `<div class="actions"><a class="btn btn-primary" href="#/result">اعرض نتيجتي</a></div>` : ""}</div>`;
  }
  return "";
}

function viewSave() {
  const p = state.profile;
  const has = L.hasAnswers(p) && p.paths;
  return `${pageHead("حفظ ونقل", "حفظ بياناتك ونقلها", "إجاباتك تُحفظ تلقائيًا في هذا المتصفح. هنا تنزّل تقريرًا للقراءة، أو نسخة من تقدمك تستعيدها لاحقًا، أو تمسح بياناتك.")}
  <p class="small muted">آخر حفظ تلقائي: ${has ? h(L.formatDate(p.updated)) : "لا توجد إجابات محفوظة بعد."}</p>
  <div class="grid grid-2">
    <section class="card" aria-labelledby="rep-h"><h2 id="rep-h" class="h3">1. تقرير نتيجتك للقراءة</h2>
      <p class="small">صفحة HTML تفتحها في أي متصفح أو تطبعها: ملخصك وخطتك والاقتراحات ومصادرها. لا تُستعاد منها الرحلة.</p>
      <div class="actions"><button class="btn btn-primary" type="button" data-action="download-html"${has ? "" : " disabled"}>نزّل التقرير</button>
        <button class="btn btn-ghost" type="button" data-action="print"${has ? "" : " disabled"}>اطبع</button></div>
      <p class="small dl-note" id="dl-note-html" role="status" aria-live="polite"></p>
      ${has ? "" : `<p class="small muted">قيّم مهارة واحدة على الأقل أولًا.</p>`}</section>
    <section class="card" aria-labelledby="json-h"><h2 id="json-h" class="h3">2. نسخة من تقدمك (لاستعادته لاحقًا)</h2>
      <p class="small">ملف يحفظ مجالك ومجال المقارنة وأهدافك وتقييماتك وخطتك ونطاق المهارات، مع بصمة إصدار قاعدة المهارات. استعده هنا لاحقًا أو على جهاز آخر لتعود الرحلة نفسها.</p>
      <div class="actions"><button class="btn btn-primary" type="button" data-action="download-json"${p.paths ? "" : " disabled"}>نزّل نسخة قابلة للاستعادة</button></div>
      <p class="small dl-note" id="dl-note-json" role="status" aria-live="polite"></p></section>
    <section class="card" aria-labelledby="imp-label"><h2 id="imp-label" class="h3">3. استعادة تقدمك من نسخة محفوظة</h2>
      <p class="small">اختر ملف نسخة نزّلته من بوصلة. سنعرض محتواه أولًا، ولن يتغير شيء قبل موافقتك.</p>
      <label class="btn btn-ghost file-btn" for="import-file">اختر ملف النسخة…</label>
      <input id="import-file" type="file" accept="application/json,.json" class="sr-only file-input" data-action="import">
      ${importPanel()}</section>
    <section class="card" aria-labelledby="clr-h"><h2 id="clr-h" class="h3" tabindex="-1">4. مسح بياناتك من هذا المتصفح</h2>
      <p class="small">يحذف مجالك وتقييماتك وأهدافك وخطتك من هذا المتصفح. لا يمكن التراجع، فنزّل نسخة من تقدمك أولًا إن أردت الاحتفاظ بها.</p>
      ${state.ui.clearConfirm ? `<div class="panel panel-error" id="clear-panel" tabindex="-1" role="alertdialog" aria-labelledby="clr-q"><p id="clr-q"><strong>متأكد؟ ستُحذف إجاباتك من هذا المتصفح.</strong></p>
        <div class="actions"><button class="btn btn-danger" type="button" data-action="clear-confirm">نعم، امسح</button><button class="btn btn-ghost" type="button" data-action="clear-cancel">إلغاء</button></div></div>`
        : `<button class="btn btn-danger" type="button" data-action="clear"${has || p.paths ? "" : " disabled"}>امسح بياناتي…</button>`}
      ${state.ui.cleared ? `<p class="small status-ok" role="status">مُسحت بياناتك من هذا المتصفح.</p>` : ""}</section>
  </div>`;
}

// ---------------------------------------------------------------- عن البيانات
const STATUS = {
  ok: ["chip-ok", "سليم"], stale: ["chip-gap", "تعذر التحديث — تُعرض آخر نسخة سليمة"],
  failed: ["chip-danger", "غير متاح — فشلت كل المحاولات"], missing: ["chip-danger", "لم يُجلب بعد"],
};
const ATTEMPT = { updated: "جُلب نسخة جديدة", revised: "نُشرت نسخة معدلة وقُبلت", unchanged: "لم يتغير", not_modified: "لم يتغير (304)",
  repaired: "أُصلحت نسخة الأرشيف التالفة من تنزيل سليم", failed_download: "تعذر التنزيل", failed_validation: "فشل التحقق ورُفض الملف",
  failed_storage: "تعذر الحفظ؛ بقيت النسخة السابقة", failed_unexpected: "خطأ غير متوقع؛ بقيت النسخة السابقة" };
const TERMS_STATUS = { proven: ["chip-ok", "رخصة بيانات مفتوحة معروضة لهذه المجموعة"], unresolved: ["chip-gap", "إذن إعادة الاستخدام العام غير محسوم"] };

function sourceCard(s) {
  const [cls, text] = STATUS[s.status] || ["chip", s.status];
  const [tcls, ttext] = TERMS_STATUS[s.terms_status] || ["chip", "لم يُسجَّل"];
  const la = s.last_attempt || {};
  return `<article class="card source-card"><header><div><h3 style="margin:0">${h(s.title)}</h3><p class="small muted" style="margin:0">${h(s.publisher)}</p></div><span class="chip ${cls}">${h(text)}</span></header>
    <dl class="kv"><dt>الإصدار أو الفترة</dt><dd>${h(s.edition || "—")}</dd>
    <dt>آخر تحقق ناجح</dt><dd>${h(L.formatDate(s.verified_at))}</dd>
    <dt>آخر محاولة</dt><dd>${h(L.formatDate(la.at))} — ${h(ATTEMPT[la.status] || la.status || "—")}${la.error ? `<br><span class="status-bad small">${h(la.error)}</span>` : ""}</dd>
    <dt>آخر تعديل لدى المصدر</dt><dd>${h(s.last_modified ? L.formatDate(s.last_modified) : "—")}</dd>
    <dt>بصمة SHA-256</dt><dd><span class="hash">${h((s.sha256 || "—").slice(0, 16))}${s.sha256 ? "…" : ""}</span> · <span class="num">${h(L.formatNumber(s.size))}</span> بايت</dd>
    <dt>الرابط</dt><dd>${external(s.page_url || s.url, "صفحة المصدر")}</dd></dl>
    <div class="terms"><p class="small" style="margin:0 0 .3rem"><strong>شروط الاستخدام</strong> <span class="chip ${tcls}">${h(ttext)}</span></p>
      <p class="small" style="margin:0">${h(s.terms)} ${external(s.terms_url, "النص")}</p>
      ${s.terms_checked ? `<p class="small muted" style="margin:.3rem 0 0">فُحص الدليل في ${h(L.formatDate(s.terms_checked, false))}. ليس رأيًا قانونيًا.</p>` : ""}</div>
    ${s.note ? `<p class="note small" style="margin:0">${h(s.note)}</p>` : ""}</article>`;
}

function viewAbout() {
  const m = state.manifest;
  const d = state.data;
  const c = d.framework.counts, dec = d.framework.declared || {};
  const di = d.framework.dictionary_index || {};
  const disc = m?.discovery || {};
  const cand = disc.candidates || [];
  const candText = { new_period: "فترة جديدة مرشحة — تحتاج مراجعة قبل اعتمادها", known_period_other_id: "فترة معروفة بمعرّف آخر", period_conflict: "تعارض في أدلة الفترة", title_mismatch: "عنوان الرابط لا يطابق عنوان المجموعة في المنصة", metadata_failed: "تعذر قراءة البيانات الوصفية" };
  const age = L.ageDays(disc.last_success_at);
  const discLine = disc.status === "ok"
    ? `آخر فحص: ${h(L.formatDate(disc.at))} — نجح.`
    : disc.status === "failed"
      ? `<span class="status-bad">آخر محاولة فحص (${h(L.formatDate(disc.at))}) فشلت: ${h(disc.error || "")}</span>. ${disc.last_success_at ? `النتائج أدناه من آخر فحص ناجح في ${h(L.formatDate(disc.last_success_at))} (قبل ${num(age)} يوم)، وليست فحصًا حديثًا.` : "لا يوجد فحص ناجح سابق."}`
      : "لم يُشغَّل فحص الاكتشاف بعد.";
  const sc = d.framework.scale;
  return `${pageHead("الشفافية", "عن البيانات ومصادرها", "من أين تأتي المهارات والأرقام، وكيف نتحقق منها، وما حدودها.")}
  <section class="card" aria-labelledby="nums-h"><h2 id="nums-h">ماذا تعني الأرقام؟</h2>
    <ul class="small">
      <li><strong>${num(c.group_entries)} مجالًا</strong> في القائمة: ${num(dec.groups ?? c.groups)} مجموعة وظيفية معلنة، بعضها بالاسم نفسه في قطاعي تقنية المعلومات والاتصالات ولكلٍّ مهاراته.</li>
      <li><strong>${num(c.technical_skills)} مدخل مهارة فنية في بوصلة</strong>: يشمل صيغ أسماء احتفظنا بها كما وردت في قوائم المجموعات حين لم تطابق جدول المهارات الفريدة حرفيًا. ليس العدد الرسمي للمهارات الفريدة: جدول المصدر فيه ${num(921)} مهارة، والرقم المعلن ${num(dec.unique_technical ?? 922)}.</li>
      <li><strong>${num(c.priority_skills)} مهارة ذات أولوية</strong> على مستوى القطاع الرقمي، و<strong>${num(c.general_skills)} مهارة عامة</strong> مشتركة بين كل المجالات.</li>
      <li>روابط صفحات القاموس: ${num(di.linked ?? 0)} من ${num(di.priority ?? 0)} مهارة ذات أولوية؛ منها ${num(di.verified ?? 0)} قُرئ عنوان صفحتها وطابق الاسم، والبقية حُددت بترتيب المهارات في القاموس فقد يختلف عنوانها قليلًا (مثل «لغات البرمجة» وعنوانها في القاموس «البرمجة»).</li>
    </ul></section>
  <section class="card section" aria-labelledby="scale-h"><h2 id="scale-h">سلّم الإتقان وجلسة البداية</h2>
    <p class="small"><strong>نص المصدر:</strong> ${h(sc.technical.text)}</p><p class="small">${h(sc.general.text)}</p>
    <p class="small"><strong>شرحنا المبسّط (ليس من المصدر، وعام لكل المهارات):</strong> ${L.LEVEL_GUIDE.technical.slice(1).map(([n, t], i) => `${i + 1}. ${h(n)}: ${h(t)}`).join(" ")}</p>
    <p class="small"><strong>جلسة البداية:</strong> من المهارات ذات الأولوية في مجالك، نصفها الأكثر انتشارًا في مجالات الإطار ونصفها الأكثر تمييزًا لمجالك. اجتهاد تعليمي من بوصلة، لا ترتيب رسمي ولا عينة تمثل المجال.</p></section>
  ${m ? `<p class="small muted section">آخر بناء لبيانات الواجهة: ${h(L.formatDate(m.generated_at))} · الحالة العامة: <strong class="${m.status === "ok" ? "status-ok" : m.status === "degraded" ? "status-warn" : "status-bad"}">${m.status === "ok" ? "كل المصادر سليمة" : m.status === "degraded" ? "بعض المصادر تعذر تحديثها" : "تعذر البناء"}</strong></p>` : `<div class="banner banner-warn section"><span class="icon" aria-hidden="true">⚠️</span><p>بيان الحالة غير متاح.</p></div>`}
  <h2 class="section">المصادر الخمسة</h2>
  <p class="small">شروط كل مصدر مسجلة على حدة: ما ثبت، وما بقي غير محسوم. إتاحة الملف للتنزيل لا تعني إذنًا بإعادة نشره. بوصلة نموذج محلي للاستخدام الشخصي، والنشر العام خارج نطاقها. سياسة الوزارة للبيانات المفتوحة: ${external(d.links.hrsd_open_data_policy, "النص")}.</p>
  <section class="grid grid-2">${(m?.sources || []).map(sourceCard).join("")}</section>
  <section class="grid grid-2 section">
    <div class="card"><h2 class="h3">ما تدعمه البيانات</h2><ul class="checklist small">
      <li class="y">مهارات كل مجال (فنية وعامة) ووصف كل مهارة، من قاعدة البيانات.</li>
      <li class="y">سلّم الإتقان وأوصاف المستويات للمهارات ذات الأولوية في القاموس.</li>
      <li class="y">أدوار مجالين ورموز مهنهما (منقولة يدويًا بصفحاتها).</li>
      <li class="y">أعداد العاملين في القطاع الخاص حسب النشاط الاقتصادي والمنطقة، لربعين.</li></ul></div>
    <div class="card"><h2 class="h3">ما لا تدعمه</h2><ul class="checklist small">
      <li class="n">المستوى المطلوب من كل مهارة لكل مجال (غير منشور).</li>
      <li class="n">الشواغر أو الرواتب أو احتمال التوظيف، أو برامج تدريب مرتبطة بالمهارات.</li>
      <li class="n">توزيع المجالات الرقمية على المناطق.</li>
      <li class="n">معرّفات رسمية للمهارات؛ المعرّفات هنا مشتقة من الاسم.</li></ul></div>
  </section>
  <details class="card more-card section"><summary><strong>ملاحظات جودة وُجدت أثناء التحقق</strong></summary><ul class="small">
    ${(d.framework.warnings || []).map((w) => `<li>${h(w)}</li>`).join("")}
    ${(di.conflicts || []).map((x) => `<li>القاموس صفحة <span class="num">${x.page}</span> بعنوان «${h(x.in_dictionary)}» بينما ترتيب قاعدة البيانات يضع «${h(x.in_database)}»؛ استُبعد رابط هذه المهارة.</li>`).join("")}
    ${di.reason ? `<li>فهرس صفحات القاموس غير متاح: ${h(di.reason)}</li>` : ""}
    <li>المهارات ذات الأولوية لكل مجموعة في القاموس أضيق من ربط قاعدة البيانات، وبعض الأسماء مصاغة بصيغ مختلفة بين الملفين؛ نعتمد قاعدة البيانات لأنها القابلة للقراءة الآلية.</li></ul></details>
  <details class="card more-card section" id="discovery"${disc.status === "failed" ? " open" : ""}><summary><strong>اكتشاف الفترات الجديدة لبيانات العاملين</strong></summary>
    <p class="small">يُفحص فهرس البيانات المفتوحة في موقع الوزارة بحثًا عن فترات جديدة. المرشح لا يدخل التحليل إلا بعد مراجعة بشرية.</p>
    <p class="small">${discLine}</p>
    ${cand.length ? `<ul class="small">${cand.map((x) => `<li><span class="hash">${h(x.dataset_id.slice(0, 8))}</span> — ${h(candText[x.status] || x.status)}: ${h(x.title_ar || x.title || "")}</li>`).join("")}</ul>` : `<p class="small">لا مرشحين جدد${disc.status === "failed" && !disc.last_success_at ? " معروفين" : ""}.</p>`}</details>`;
}

function viewNotFound() {
  return emptyState("🧭", "الصفحة غير موجودة", "ربما تغير الرابط.", `<a class="btn btn-primary" href="#/">الرئيسية</a>`);
}

// ---------------------------------------------------------------- التوجيه والأحداث
const ALIASES = { compare: "path", skills: "assess", plan: "result", sources: "about" };
const VIEWS = { "": viewHome, path: viewPath, assess: viewAssess, result: viewResult, save: viewSave, about: viewAbout };

function parseRoute() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [pathPart, anchor] = raw.split("#");
  const parts = pathPart.split(/[?/]/);
  return { key: ALIASES[parts[0]] ?? parts[0], args: parts.slice(1), anchor };
}

function route({ keepScroll = false, focus = true } = {}) {
  const { key, args, anchor } = parseRoute();
  // «#/assess» دون موضع: يستأنف من حيث توقف المستخدم، لا من البداية.
  if (key === "assess" && !args[0] && state.profile.paths) { location.replace(resumeHref()); return; }
  const view = VIEWS[key] || viewNotFound;
  setNav(key);
  app.innerHTML = view(...args);
  renderBanner();
  if (!keepScroll) {
    const target = anchor && document.getElementById(anchor);
    if (target) { target.scrollIntoView(); target.querySelector("h2")?.focus({ preventScroll: true }); return; }
    window.scrollTo(0, 0);
    if (focus) (app.querySelector("#skill-title") || app.querySelector("h1"))?.focus({ preventScroll: true });
  }
}

// إعادة رسم الصفحة نفسها مع إبقاء موضع التمرير والتركيز والتفاصيل المفتوحة.
function rerender(focusSelector = null) {
  const y = window.scrollY;
  const active = document.activeElement;
  const id = active?.dataset?.planAdd || active?.dataset?.planRemove;
  const key = focusSelector || (active?.id ? `#${CSS.escape(active.id)}`
    : id ? `[data-plan-add="${CSS.escape(id)}"], [data-plan-remove="${CSS.escape(id)}"]`
    : active?.dataset?.action ? `[data-action="${CSS.escape(active.dataset.action)}"]`
    : active?.dataset?.target ? `[data-target="${active.dataset.target}"][data-delta="${active.dataset.delta}"]` : null);
  const open = [...app.querySelectorAll("details[open][id]")].map((d) => d.id);
  route({ keepScroll: true });
  open.forEach((x) => { const d = document.getElementById(x); if (d) d.open = true; });
  window.scrollTo(0, y);
  const el = key && app.querySelector(key);
  if (el) el.focus({ preventScroll: !focusSelector });
  else if (id) app.querySelector("#plan-h")?.focus({ preventScroll: true });
}

function updateAssessStatus(id) {
  const st = document.getElementById("skill-status");
  if (st) st.innerHTML = statusLine(id);
  const { args } = parseRoute();
  const list = listFor(args[0] === "all" ? "all" : "start");
  const prog = L.progress(state.data, state.profile, list);
  const t = document.getElementById("progress-text");
  if (t) t.innerHTML = `قيّمت ${num(prog.rated)} من ${num(list.length)}`;
  const bar = document.getElementById("progress-bar");
  if (bar) bar.style.width = `${(100 * prog.rated / list.length).toFixed(1)}%`;
}

// الخطة: الإضافة والإزالة على اختيار المستخدم الصريح فقط؛ الاقتراحات لا تدخل إلا بإضافة.
function addToPlan(ids) {
  const plan = [...state.profile.plan];
  for (const id of ids) if (!plan.includes(id)) plan.push(id);
  state.profile.plan = plan;
  state.ui.planNotice = ids.length > 1 ? `أُضيفت ${L.countSkills(ids.length)} إلى خطتك.` : "أُضيفت إلى خطتك.";
  saveProfile();
}
function removeFromPlan(id) {
  state.profile.plan = state.profile.plan.filter((x) => x !== id);
  state.ui.planNotice = state.profile.plan.length ? "أُزيلت من خطتك." : "أُزيلت. خطتك فارغة الآن؛ الاقتراحات معروضة منفصلة ولا تُضاف إلا إذا اخترتها.";
  saveProfile();
}

async function handleImport(file) {
  state.ui.importPreview = null; state.ui.importErrors = null; state.ui.importDone = null; state.ui.cleared = false;
  let raw;
  try { raw = JSON.parse(await file.text()); } catch {
    state.ui.importErrors = [{ text: "هذا الملف ليس نسخة تقدم من بوصلة، أو أنه تالف.", detail: "JSON.parse failed" }];
    return rerender("#import-panel");
  }
  const result = L.parseJourney(raw, state.data, { fallbackScope: state.profile.scope });
  if (!result.ok) state.ui.importErrors = result.errors;
  else state.ui.importPreview = { result, fileName: file.name };
  return rerender("#import-panel");
}

function confirmImport() {
  const { result } = state.ui.importPreview;
  try { restoreRelease({ legacy: result.profile }, window.localStorage); }
  catch {
    state.ui.importErrors = [{ text: "تعذر حفظ نسخة استرجاع؛ لم نستبدل تقدمك.", detail: "backup storage failed" }];
    state.ui.importPreview = null; return rerender("#import-panel");
  }
  state.profile = result.profile;
  state.blockSave = false;
  const snap = result.info.snapshot;
  let text = "تقييماتك وخطتك وأهدافك ونطاقك صارت كما في الملف.";
  if (snap) {
    text += L.sameSnapshot(snap, L.resultSnapshot(state.data, state.profile))
      ? " النتيجة المحسوبة الآن مطابقة للنتيجة المحفوظة في الملف."
      : " النتيجة المحسوبة الآن تختلف عن المحفوظة في الملف.";
  } else if (result.info.sameFramework === false) {
    text += " الملف من إصدار آخر لقاعدة المهارات، فقد تختلف النتيجة عما كانت عليه عند الحفظ.";
  }
  state.ui.importPreview = null;
  state.ui.importDone = { title: "استُعيد تقدمك", text, result: true };
  rerender("#import-panel");
}

app.addEventListener("change", (ev) => {
  const t = ev.target;
  if (t.matches("input[data-field]")) {
    const [, b] = paths();
    state.profile.paths = b && b !== t.value ? [t.value, b] : [t.value];
    state.ui.pathError = false;
    saveProfile();
    route();                                       // ملخص المجال وزر البداية في الأعلى
    document.getElementById("chosen-h")?.focus();
    return undefined;
  }
  if (t.matches("select[data-path=compare]")) {
    state.profile.paths = t.value ? [paths()[0], t.value] : [paths()[0]];
    saveProfile();
    return rerender("#compare");
  }
  if (t.matches("[data-scope-choice]")) {
    state.profile.scope = t.value; saveProfile();
    return rerender(`input[name=scope][value=${t.value}]`);
  }
  if (t.matches("input[type=radio][data-skill]")) {
    const id = t.dataset.skill;
    state.profile.levels[id] = Number(t.value);
    delete state.ui.unsure[id];
    saveProfile();
    updateAssessStatus(id);
    return undefined;
  }
  if (t.matches("input[data-action=import]") && t.files?.[0]) {
    const file = t.files[0];
    t.value = "";
    handleImport(file);
  }
  return undefined;
});

app.addEventListener("input", (ev) => {
  if (!ev.target.matches("[data-action=field-search]")) return;
  const q = ev.target.value.trim();
  let shown = 0;
  app.querySelectorAll(".field-option").forEach((el) => {
    const hit = !q || el.dataset.name.includes(q);
    el.hidden = !hit; shown += hit ? 1 : 0;
  });
  app.querySelectorAll(".field-group").forEach((fs) => { fs.hidden = ![...fs.querySelectorAll(".field-option")].some((el) => !el.hidden); });
  document.getElementById("field-none").hidden = shown > 0;
});

app.addEventListener("click", (ev) => {
  const t = ev.target.closest("button, [data-action]");
  if (!t || t.matches("input")) return undefined;
  if (t.dataset.ctab) { state.ui.compareTab = t.dataset.ctab; return rerender(); }
  if (t.dataset.unknown) {
    const id = app.querySelector("input[data-skill]")?.dataset.skill;
    if (!id) return undefined;
    delete state.profile.levels[id];
    state.ui.unsure[id] = t.dataset.unknown;
    saveProfile();
    app.querySelectorAll("input[data-skill]").forEach((r) => { r.checked = false; });
    updateAssessStatus(id);
    return undefined;
  }
  if (t.dataset.target) {
    const type = t.dataset.target, max = state.data.framework.scale[type].max;
    state.profile.targets[type] = Math.min(max, Math.max(1, state.profile.targets[type] + Number(t.dataset.delta)));
    saveProfile(); return rerender();
  }
  if (t.dataset.planAdd) { addToPlan([t.dataset.planAdd]); return rerender(); }
  if (t.dataset.planRemove) { removeFromPlan(t.dataset.planRemove); return rerender(); }
  switch (t.dataset.action) {
    case "path-next":
      state.ui.pathError = true; rerender("#field-search"); break;
    case "compare-off":
      state.profile.paths = [paths()[0]]; saveProfile(); rerender("#compare"); break;
    case "reset-targets":
      state.profile.targets = { ...L.DEFAULT_TARGETS }; saveProfile(); rerender("#targets-h"); break;
    case "adopt-suggestions":
      addToPlan(L.planState(state.data, state.profile).suggestions.map((x) => x.gap.id)); rerender("#plan-h"); break;
    case "toggle-plan-all": state.ui.showAllPlan = !state.ui.showAllPlan; rerender(); break;
    case "print": window.print(); break;
    case "download-html":
      download(`bawsala-report-${today()}.html`, L.reportHtml(state.data, state.manifest, state.profile), "text/html;charset=utf-8", "dl-note-html"); break;
    case "download-json":
      download(`bawsala-journey-${today()}.json`, JSON.stringify(L.exportJourney(state.data, state.manifest, state.profile), null, 1), "application/json", "dl-note-json"); break;
    case "import-confirm": confirmImport(); break;
    case "import-cancel":
      state.ui.importPreview = null; state.ui.importErrors = null;
      state.ui.importDone = { title: "أُلغيت الاستعادة", text: "لم يتغير شيء في بياناتك.", result: false };
      rerender("#import-panel"); break;
    case "clear": state.ui.clearConfirm = true; state.ui.cleared = false; rerender("#clear-panel"); break;
    case "clear-cancel": state.ui.clearConfirm = false; rerender("[data-action=clear]"); break;
    case "clear-confirm":
      if (!backupProfile()) { state.storageNotice = "تعذر حفظ نسخة استرجاع؛ لم نمسح التقدم."; rerender("#clear-panel"); break; }
      removeStorage(STORE_KEY); removeStorage(OLD_STORE_KEY); removeStorage(CURSOR_KEY);
      state.profile = L.emptyProfile(null);
      state.ui = { ...state.ui, clearConfirm: false, cleared: true, importDone: null, planNotice: null, unsure: {} };
      rerender("#clr-h"); break;
    default: break;
  }
  return undefined;
});

window.addEventListener("hashchange", () => {
  state.ui.pathError = false; state.ui.planNotice = null; state.ui.showAllPlan = false;
  state.ui.importErrors = null; state.ui.importDone = null; state.ui.importPreview = null; state.ui.cleared = false; state.ui.clearConfirm = false;
  route();
});

// ---------------------------------------------------------------- الإقلاع
async function loadJson(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function fatal(title, detail) {
  const sources = state.manifest?.sources || [];
  const list = sources.length ? `<ul class="checklist small" style="text-align:right;max-width:640px;margin:16px auto 0">${sources.map((s) =>
    `<li class="${s.status === "ok" ? "y" : "n"}"><span>${h(s.title)} — ${h((STATUS[s.status] || ["", s.status])[1])}${s.last_attempt?.error ? `: <span class="status-bad">${h(s.last_attempt.error)}</span>` : ""}</span></li>`).join("")}</ul>` : "";
  app.innerHTML = emptyState("⛔", title, `${h(detail)}<br><span class="small muted">إن كنت تشغّل بوصلة محليًا: شغّل <code>python -m compass update</code> ثم أعد تحميل الصفحة.</span>${list}`,
    `<div class="actions" style="justify-content:center"><button class="btn btn-primary" type="button" onclick="location.reload()">إعادة المحاولة</button></div>`);
  setNav("");
}

function renderBannerOnly() {
  if (state.manifest?.status === "failed") {
    banner.innerHTML = `<div class="banner banner-error" role="alert"><span class="icon" aria-hidden="true">⛔</span><p>${h(state.manifest.message || "تعذر بناء البيانات.")}</p></div>`;
  }
}

async function boot() {
  try { state.manifest = await loadJson("data/manifest.json"); } catch (err) { state.manifestError = err.message; }
  try {
    state.data = await loadJson("data/compass.json");
    if (!state.data?.subsectors?.length || !state.data?.skills || !state.data?.framework?.scale) throw new Error("بنية البيانات غير مكتملة");
  } catch (err) {
    const why = state.manifest?.status === "failed" ? state.manifest.message : `تعذر تحميل بيانات المسارات (${err.message}).`;
    if (state.manifest) renderBannerOnly();
    return fatal("تعذر تحميل بيانات بوصلة", why);
  }
  state.profile = loadProfile(state.data);
  route({ focus: false });
  return undefined;
}

boot();
