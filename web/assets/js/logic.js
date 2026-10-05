// منطق «بوصلة» دون واجهة: المجال والمقارنة، والتقييم الذاتي، والفجوات، والخطة، والتقرير، وملف الرحلة.
// كل الدوال نقية (لا DOM ولا تخزين) لتُختبر مباشرة.
//
// مبادئ مقصودة:
// - الفجوة = هدف يختاره المستخدم − مستواه الذاتي. المصدر لا يحدد مستوى مطلوبًا لكل مجموعة وظيفية.
// - لا نسبة «جاهزية» ولا احتمال توظيف؛ نعرض أعدادًا من مدخلات المستخدم فقط.
// - المهارة التي لم تُقيَّم ليست صفرًا: لا تدخل الفجوات ولا الخطة، وتُعد «لم تقيّمها».
//   «لا أعرف هذه المهارة» و«لست متأكدًا» تبقيانها غير مقيّمة؛ «لم أبدأ تعلّمها» تقييم صريح (0).
// - «خطتي» ما اختاره المستخدم فقط؛ «اقتراحات بوصلة» منفصلة ولا تدخل اختياره إلا بفعل صريح.
// - حالة الخطة تُشتق في مكان واحد (planState) وتستخدمها صفحة النتيجة والتقرير والملف.
// - اتفاق ملف الرحلة وترحيله موثق في docs/JOURNEY-FILE.md ومطبَّق في parseJourney.

export const PROFILE_VERSION = 3;
export const FILE_FORMAT = "bawsala-journey";
export const FILE_VERSION = 3;
export const DEFAULT_TARGETS = Object.freeze({ technical: 3, general: 2 }); // افتراضي قابل للتعديل، ليس من المصدر
export const SCOPES = Object.freeze(["priority", "all"]);
export const PLAN_SIZE = 5;
export const STARTER_SIZE = 10;

// شرح تقريبي مبسّط من بوصلة لمساعدة المستخدم على الاختيار؛ ليس نص المصدر ولا وصفًا خاصًا بمهارة.
// المصدر يحدد السلّم (1–5 للفنية و1–3 للعامة) ويصف كل مستوى لكل مهارة ذات أولوية في القاموس.
export const LEVEL_GUIDE = Object.freeze({
  technical: [
    ["لم أبدأ تعلّمها", "لم أمارسها بعد."],
    ["مبتدئ", "أعرف الأساسيات، وأحتاج توجيهًا عند التطبيق."],
    ["أساسي", "أنفّذ مهامًا بسيطة بمساعدة."],
    ["متمكّن", "أنفّذ المهام المعتادة وحدي."],
    ["متقدّم", "أتعامل مع المهام المعقّدة وأساعد غيري."],
    ["خبير", "أقود العمل فيها وأطوّر طرقها."],
  ],
  general: [
    ["لم أبدأ تعلّمها", "لم أمارسها بعد."],
    ["أساسي", "أطبّقها في المواقف البسيطة."],
    ["متمكّن", "أطبّقها وحدي في أغلب المواقف."],
    ["متقدّم", "أطبّقها في المواقف الصعبة وأوجّه غيري."],
  ],
});

const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch]);
}

export function safeUrl(url) {
  try {
    const u = new URL(String(url));
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : null;
  } catch {
    return null;
  }
}

export function formatNumber(n) {
  return n == null || Number.isNaN(n) ? "غير متاح" : new Intl.NumberFormat("en-US").format(n);
}

export function formatSigned(n) {
  if (n == null || Number.isNaN(n)) return "غير متاح";
  return n === 0 ? "0" : (n > 0 ? "+" : "−") + new Intl.NumberFormat("en-US").format(Math.abs(n));
}

export function formatPercent(fraction, { signed = false, digits = 1 } = {}) {
  if (fraction == null || Number.isNaN(fraction)) return "غير متاح";
  const text = (Math.abs(fraction) * 100).toFixed(digits) + "%";
  if (!signed || fraction === 0) return (fraction < 0 ? "−" : "") + text;
  return (fraction > 0 ? "+" : "−") + text;
}

export function formatDate(iso, withTime = true) {
  if (!iso) return "غير متاح";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "غير متاح";
  return new Intl.DateTimeFormat("ar-SA-u-nu-latn-ca-gregory", {
    dateStyle: "long", ...(withTime ? { timeStyle: "short" } : {}), timeZone: "Asia/Riyadh",
  }).format(d);
}

export function ageDays(iso, now = new Date()) {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return null;
  return Math.max(0, Math.floor((now - d) / 86400000));
}

// عدد المهارات بصيغة عربية صحيحة: مهارة واحدة، مهارتان، 3 مهارات، 11 مهارة. الأرقام لاتينية كبقية الواجهة.
export function countSkills(n) {
  if (n === 0) return "لا مهارات";
  if (n === 1) return "مهارة واحدة";
  if (n === 2) return "مهارتان";
  const mod = n % 100;
  return `${new Intl.NumberFormat("en-US").format(n)} ${mod >= 3 && mod <= 10 ? "مهارات" : "مهارة"}`;
}

// ---------------------------------------------------------------------------
// البيانات

export function indexGroups(data) {
  const map = new Map();
  for (const sub of data.subsectors || []) for (const g of sub.groups) map.set(g.id, g);
  return map;
}

// اسم المجموعة مع قطاعها الفرعي: الاسم وحده يتكرر بين القطاعين (مثل «البرمجيات»).
export function groupLabel(group) {
  return group ? `${group.name} — ${group.subsector}` : "";
}

// المجالات التي يتكرر اسمها في قطاع آخر: {id: قطاع المجال الآخر}.
export function namesakes(data) {
  const byName = new Map();
  for (const g of indexGroups(data).values()) byName.set(g.name, [...(byName.get(g.name) || []), g]);
  const out = {};
  for (const list of byName.values()) if (list.length > 1) for (const g of list) out[g.id] = list.filter((x) => x !== g).map((x) => x.subsector);
  return out;
}

// مسار أساسي، واختياريًا مسار للمقارنة مختلف عنه. null إن لم يكن صالحًا.
export function validPaths(data, paths) {
  if (!Array.isArray(paths) || paths.length < 1 || paths.length > 2) return null;
  const groups = indexGroups(data);
  if (!paths.every((id) => typeof id === "string" && groups.has(id))) return null;
  if (paths.length === 2 && paths[0] === paths[1]) return null;
  return [...paths];
}

export function defaultPaths(data) {
  return validPaths(data, data.featured) || null;
}

const inScope = (data, scope) => (id) => scope === "all" || !!data.skills[id]?.priority;
const byName = (data) => (x, y) => data.skills[x].name.localeCompare(data.skills[y].name, "ar");

// في كم مجالًا (من مداخل الإطار) تظهر كل مهارة فنية.
export function skillSpread(data) {
  const spread = {};
  for (const g of indexGroups(data).values()) for (const id of new Set(g.technical)) spread[id] = (spread[id] || 0) + 1;
  return spread;
}

// مقارنة المهارات الفنية بين مسارين. scope: "priority" (ذات أولوية في القطاع) أو "all".
export function comparePaths(data, aId, bId, scope = "priority") {
  const groups = indexGroups(data);
  const A = groups.get(aId), B = groups.get(bId);
  if (!A || !B) throw new Error("مسار غير معروف");
  const keep = inScope(data, scope);
  const a = new Set(A.technical.filter(keep)), b = new Set(B.technical.filter(keep));
  const shared = [...a].filter((id) => b.has(id)).sort(byName(data));
  const onlyA = [...a].filter((id) => !b.has(id)).sort(byName(data));
  const onlyB = [...b].filter((id) => !a.has(id)).sort(byName(data));
  return {
    scope, a: A, b: B, shared, onlyA, onlyB,
    counts: {
      aTechnical: A.technical.length, bTechnical: B.technical.length,
      aScoped: a.size, bScoped: b.size, shared: shared.length, onlyA: onlyA.length, onlyB: onlyB.length,
      generalShared: A.general.filter((id) => B.general.includes(id)).length,
    },
  };
}

// كل المهارات التي يمكن تقييمها: الفنية ضمن النطاق (المشتركة أولًا عند المقارنة)، ثم العامة.
// where: "both" مشتركة بين المسارين، "a" خاصة بالأساسي، "b" خاصة بمسار المقارنة.
export function assessmentItems(data, paths, scope = "priority") {
  const valid = validPaths(data, paths);
  if (!valid) return [];
  const groups = indexGroups(data);
  const tag = (ids, where) => ids.map((id) => ({ id, where }));
  if (valid.length === 1) {
    const A = groups.get(valid[0]);
    return [...tag(A.technical.filter(inScope(data, scope)).sort(byName(data)), "a"), ...tag(A.general, "a")];
  }
  const cmp = comparePaths(data, valid[0], valid[1], scope);
  const general = [...new Set([...cmp.a.general, ...cmp.b.general])].map((id) => ({
    id, where: cmp.a.general.includes(id) && cmp.b.general.includes(id) ? "both" : cmp.a.general.includes(id) ? "a" : "b",
  }));
  return [...tag(cmp.shared, "both"), ...tag(cmp.onlyA, "a"), ...tag(cmp.onlyB, "b"), ...general];
}

// جلسة البداية: حتى 10 مهارات فنية ذات أولوية من المجال الأساسي، لتصل إلى نتيجة أولية بسرعة.
// القاعدة (اجتهاد تعليمي من بوصلة، لا ترتيب رسمي ولا عينة تمثل المجال):
//   نصفها الأكثر انتشارًا في مجالات الإطار (تفيدك حتى لو غيّرت مجالك)، ثم نصفها الأكثر تمييزًا
//   للمجال (الأقل ظهورًا في غيره). التعادل بالاسم. المجال الذي فيه أقل من 10 يُعرض كله.
export function starterItems(data, paths) {
  const valid = validPaths(data, paths);
  if (!valid) return [];
  const A = indexGroups(data).get(valid[0]);
  const spread = skillSpread(data);
  const pool = [...new Set(A.technical.filter((id) => data.skills[id]?.priority))];
  const half = Math.ceil(Math.min(STARTER_SIZE, pool.length) / 2);
  const common = [...pool].sort((x, y) => (spread[y] - spread[x]) || byName(data)(x, y)).slice(0, half);
  const distinct = pool.filter((id) => !common.includes(id)).sort((x, y) => (spread[x] - spread[y]) || byName(data)(x, y))
    .slice(0, Math.min(STARTER_SIZE, pool.length) - common.length);
  const where = (id) => (valid[1] && indexGroups(data).get(valid[1]).technical.includes(id) ? "both" : "a");
  return [...common.map((id) => ({ id, where: where(id), why: "common" })),
          ...distinct.map((id) => ({ id, where: where(id), why: "distinct" }))];
}

// أمثلة من المهارات المميزة لمجال (لمساعدة الاختيار؛ مشتقة من الإطار، لا وصف رسمي للمجال).
export function fieldExamples(data, groupId, k = 3) {
  const g = indexGroups(data).get(groupId);
  if (!g) return [];
  const spread = skillSpread(data);
  return [...new Set(g.technical.filter((id) => data.skills[id]?.priority))]
    .sort((x, y) => (spread[x] - spread[y]) || byName(data)(x, y)).slice(0, k).map((id) => data.skills[id].name);
}

export function scaleFor(data, skillId) {
  const type = data.skills[skillId]?.type === "general" ? "general" : "technical";
  const s = data.framework?.scale?.[type] || (type === "general" ? { min: 1, max: 3 } : { min: 1, max: 5 });
  return { type, min: s.min, max: s.max };
}

export function levelGuide(data, skillId) {
  return LEVEL_GUIDE[scaleFor(data, skillId).type];
}

// ---------------------------------------------------------------------------
// الملف الشخصي وملف الرحلة (الاتفاق في docs/JOURNEY-FILE.md)

export function emptyProfile(paths = null, scope = "priority") {
  return { v: PROFILE_VERSION, paths, scope, targets: { ...DEFAULT_TARGETS }, levels: {}, plan: [], unmapped: [], updated: null };
}

export function hasAnswers(profile) {
  return !!profile && (Object.keys(profile.levels).length > 0 || profile.plan.length > 0 || profile.unmapped.length > 0);
}

const isObject = (x) => !!x && typeof x === "object" && !Array.isArray(x);
const isSha = (x) => typeof x === "string" && /^[0-9A-Fa-f]{64}$/.test(x);
const sameSha = (a, b) => !!a && !!b && a.toUpperCase() === b.toUpperCase();
const isId = (x) => typeof x === "string" && x.length > 0 && x.length <= 200;

const PROFILE_KEYS = {
  1: ["v", "paths", "targets", "levels", "plan", "updated"],
  2: ["v", "paths", "scope", "targets", "levels", "plan", "unmapped", "updated"],
  3: ["v", "paths", "scope", "targets", "levels", "plan", "unmapped", "updated"],
};
const REQUIRED_KEYS = { 1: ["paths", "targets", "levels", "plan"], 2: ["paths", "scope", "targets", "levels", "plan"], 3: ["paths", "scope", "targets", "levels", "plan", "unmapped"] };
const FIELD_NAMES = { paths: "المجال", scope: "نطاق المهارات", targets: "الأهداف", levels: "التقييمات", plan: "الخطة", unmapped: "الإجابات غير المطابقة", v: "رقم الإصدار", updated: "تاريخ الحفظ" };

// خطأ تحقق: نص للمستخدم بالعربية، وتفصيل تقني منفصل للتشخيص.
const fail = (text, detail) => ({ text, detail });

function checkLevels(levels, data, where, errors) {
  // يعيد [المعروفة، غير المعروفة] بعد التحقق من كل قيمة؛ أي قيمة غير صالحة خطأ يرفض الملف.
  const known = {}, unknown = {};
  if (!isObject(levels)) { errors.push(fail(`${where} ليست بالشكل المتوقع.`, `${where}: not an object`)); return [known, unknown]; }
  for (const [id, level] of Object.entries(levels)) {
    const skill = data.skills[id];
    const max = skill ? scaleFor(data, id).max : 5;
    if (!isId(id) || !Number.isInteger(level) || level < 0 || level > max) {
      errors.push(fail(`في ${where} تقييم خارج السلّم${skill ? ` لمهارة «${skill.name}»` : ""}.`, `${where}[${id}] = ${JSON.stringify(level)} (allowed 0..${max})`));
    } else if (skill) known[id] = level;
    else unknown[id] = level;
  }
  return [known, unknown];
}

function checkPlan(plan, where, errors) {
  if (!Array.isArray(plan) || !plan.every(isId)) {
    errors.push(fail(`${where} ليست قائمة مهارات صالحة.`, `${where}: expected array of non-empty strings, got ${JSON.stringify(plan)?.slice(0, 80)}`));
    return [];
  }
  if (new Set(plan).size !== plan.length) errors.push(fail(`${where} فيها مهارة مكررة.`, `${where}: duplicate ids`));
  return plan;
}

function checkUnmappedGroups(raw, version, fileSha, currentSha, errors) {
  // v2: {levels: {}, plan: []} بلا مصدر؛ v3: [{framework_sha256, levels, plan}]. لا تحويل صامت لنوع خاطئ.
  if (version === 2) {
    if (raw === undefined) return [];
    if (!isObject(raw) || Object.keys(raw).some((k) => !["levels", "plan"].includes(k)) || !("levels" in raw) || !("plan" in raw)) {
      errors.push(fail("قسم الإجابات غير المطابقة في الملف تالف.", `unmapped (v2): expected {levels: object, plan: array}, got ${JSON.stringify(raw)?.slice(0, 80)}`));
      return [];
    }
    return [{ framework_sha256: null, levels: raw.levels, plan: raw.plan }];
  }
  if (!Array.isArray(raw)) {
    errors.push(fail("قسم الإجابات غير المطابقة في الملف تالف.", `unmapped (v3): expected array, got ${JSON.stringify(raw)?.slice(0, 80)}`));
    return [];
  }
  const out = [], seen = new Map();
  raw.forEach((g, i) => {
    const keys = isObject(g) ? Object.keys(g).sort().join(",") : "";
    if (keys !== "framework_sha256,levels,plan") {
      errors.push(fail("قسم الإجابات غير المطابقة في الملف تالف.", `unmapped[${i}]: expected keys framework_sha256, levels, plan`));
      return;
    }
    if (g.framework_sha256 !== null && !isSha(g.framework_sha256)) {
      errors.push(fail("مصدر بعض الإجابات غير المطابقة غير صالح.", `unmapped[${i}].framework_sha256 invalid`));
      return;
    }
    if (sameSha(g.framework_sha256, fileSha) || sameSha(g.framework_sha256, currentSha)) {
      errors.push(fail("الملف يصف إجابات بأنها من إصدار آخر وهي من الإصدار نفسه؛ قد يكون عُدّل يدويًا.", `unmapped[${i}].framework_sha256 equals file or current framework`));
      return;
    }
    // مجموعة واحدة لكل مصدر (البصمة دون اعتبار حالة الأحرف، والمجهول null مصدر واحد)؛ هكذا يصدّر التطبيق دائمًا.
    const key = sourceKey(g.framework_sha256);
    if (seen.has(key)) {
      const j = seen.get(key);
      const clash = isObject(g.levels) && isObject(raw[j].levels) ? levelConflict(raw[j].levels, g.levels) : null;
      errors.push(clash
        ? fail(CONFLICT_TEXT, `unmapped[${j}] and unmapped[${i}] share framework_sha256 ${key} and disagree on ${clash.id}: ${clash.a} vs ${clash.b}`)
        : fail("الملف يكرر مجموعة الإجابات غير المطابقة للمصدر نفسه؛ قد يكون عُدّل يدويًا.", `unmapped[${j}] and unmapped[${i}] share framework_sha256 ${key}`));
      return;
    }
    seen.set(key, i);
    out.push(g);
  });
  return out;
}

const sourceKey = (sha) => (sha ? sha.toUpperCase() : null);
const CONFLICT_TEXT = "الملف يعطي المهارة نفسها تقييمين مختلفين من المصدر نفسه، ولا يمكن معرفة أيهما الصحيح؛ قد يكون عُدّل يدويًا.";

function levelConflict(a, b) {
  // أول مهارة لها تقييمان مختلفان في المجموعتين، أو null.
  for (const [id, level] of Object.entries(b)) {
    if (Object.hasOwn(a, id) && a[id] !== level) return { id, a: a[id], b: level };
  }
  return null;
}

function mergeGroups(groups) {
  // يدمج المجموعات ذات المصدر نفسه، ويحذف الفارغة. لا يختار بين تقييمين مختلفين: parseJourney يرفض
  // التعارض قبل الوصول إلى هنا، فوصوله خطأ برمجي لا يُسكت.
  const map = new Map();
  for (const g of groups) {
    const key = sourceKey(g.framework_sha256);
    const cur = map.get(key) || { framework_sha256: g.framework_sha256, levels: {}, plan: [] };
    const clash = levelConflict(cur.levels, g.levels);
    if (clash) throw new Error(`mergeGroups: conflicting levels for ${clash.id} from source ${key}`);
    Object.assign(cur.levels, g.levels);
    for (const id of g.plan) if (!cur.plan.includes(id)) cur.plan.push(id);
    map.set(key, cur);
  }
  return [...map.values()].filter((g) => Object.keys(g.levels).length || g.plan.length);
}

// يتحقق من ملف رحلة (مستورد أو مخزن) كاملًا قبل أي استبدال. أي خلل بنيوي أو نوع خاطئ أو قيمة
// خارج السلّم يرفض الملف كله. الإجابات لمهارات غير موجودة في الإطار الحالي لا تُحذف: تُحفظ في
// unmapped مع بصمة الإطار الذي جاءت منه، وتُعاد إلى التقييمات إن عادت مهاراتها موجودة.
// يعيد {ok: false, errors: [{text, detail}]} أو {ok: true, profile, info}.
export function parseJourney(raw, data, { fallbackScope = "priority", allowEmptyPaths = false } = {}) {
  const errors = [];
  const reject = (text, detail) => ({ ok: false, errors: [fail(text, detail)] });
  if (!isObject(raw)) return reject("الملف ليس ملف تقدم من بوصلة.", `top level: ${Array.isArray(raw) ? "array" : typeof raw}`);
  let wrapper = null, p = raw;
  if ("format" in raw || "app" in raw || "profile" in raw) {
    wrapper = raw;
    if (raw.format === FILE_FORMAT) {
      if (raw.version !== 2 && raw.version !== 3) return reject("هذا الملف من إصدار أحدث أو غير معروف من بوصلة.", `version: ${JSON.stringify(raw.version)}`);
    } else if (raw.app !== "bawsala") {
      return reject("الملف ليس ملف تقدم من بوصلة.", "missing format/app marker");
    }
    p = raw.profile;
    if (!isObject(p)) return reject("الملف لا يحوي بيانات تقدمك.", "profile: missing or not an object");
    if (raw.framework !== undefined && (!isObject(raw.framework) || (raw.framework.skills_sha256 != null && !isSha(raw.framework.skills_sha256)))) {
      errors.push(fail("معلومات إصدار قاعدة المهارات في الملف تالفة.", "framework.skills_sha256 invalid"));
    }
    if (raw.framework_sha256 !== undefined && raw.framework_sha256 !== null && !isSha(raw.framework_sha256)) {
      errors.push(fail("معلومات إصدار قاعدة المهارات في الملف تالفة.", "framework_sha256 invalid"));
    }
    if (raw.result !== undefined && !validSnapshot(raw.result)) errors.push(fail("ملخص النتيجة المحفوظ في الملف تالف.", "result: invalid snapshot"));
  }
  const version = p.v;
  if (![1, 2, 3].includes(version)) {
    return reject(version === undefined ? "الملف لا يحدد إصدار بياناته؛ قد يكون ناقصًا." : "إصدار بيانات الملف غير مدعوم.", `profile.v: ${JSON.stringify(version)}`);
  }
  if (wrapper?.format === FILE_FORMAT && wrapper.version !== version) {
    errors.push(fail("أجزاء الملف من إصدارين مختلفين.", `file version ${wrapper.version} vs profile.v ${version}`));
  }
  const missing = REQUIRED_KEYS[version].filter((k) => !(k in p));
  if (missing.length) {
    return { ok: false, errors: [fail(`الملف ناقص: لا يحوي ${missing.map((k) => FIELD_NAMES[k]).join("، ")}.`, `missing keys: ${missing.join(", ")}`)] };
  }
  const extra = Object.keys(p).filter((k) => !PROFILE_KEYS[version].includes(k));
  if (extra.length) errors.push(fail("الملف يحوي بيانات غير متوقعة؛ قد يكون عُدّل يدويًا.", `unexpected keys: ${extra.join(", ")}`));

  const fileSha = wrapper?.framework?.skills_sha256 ?? wrapper?.framework_sha256 ?? null;
  const currentSha = data.framework?.skills_sha256 ?? null;
  const sameFramework = fileSha ? sameSha(fileSha, currentSha) : null;
  const groups = indexGroups(data);

  // المجال
  let paths = null;
  if (p.paths === null) {
    if (!allowEmptyPaths) errors.push(fail("الملف لا يحدد مجالًا مهنيًا.", "paths: null"));
  } else if (!Array.isArray(p.paths) || p.paths.length < (version === 1 ? 2 : 1) || p.paths.length > 2 || !p.paths.every(isId)) {
    errors.push(fail("المجال المحفوظ في الملف ليس بالشكل المتوقع.", `paths: ${JSON.stringify(p.paths)?.slice(0, 80)}`));
  } else if (p.paths.some((x) => !groups.has(x))) {
    errors.push(fail("المجال المحفوظ في الملف غير موجود في الإطار الحالي، فلا يمكن استرجاع الرحلة.", `unknown paths: ${p.paths.filter((x) => !groups.has(x)).join(", ")}`));
  } else if (p.paths.length === 2 && p.paths[0] === p.paths[1]) {
    errors.push(fail("الملف يحوي المجال نفسه مرتين.", "paths: duplicate"));
  } else paths = [...p.paths];

  // النطاق
  let scope = fallbackScope;
  if (version >= 2) {
    if (!SCOPES.includes(p.scope)) errors.push(fail("نطاق المهارات المحفوظ في الملف غير معروف.", `scope: ${JSON.stringify(p.scope)}`));
    else scope = p.scope;
  }

  // الأهداف
  const targets = {};
  if (!isObject(p.targets) || Object.keys(p.targets).sort().join(",") !== "general,technical") {
    errors.push(fail("الأهداف المحفوظة في الملف ليست بالشكل المتوقع.", `targets: ${JSON.stringify(p.targets)?.slice(0, 80)}`));
  } else {
    for (const t of ["technical", "general"]) {
      const max = data.framework?.scale?.[t]?.max ?? (t === "general" ? 3 : 5);
      const v = p.targets[t];
      if (!Number.isInteger(v) || v < 1 || v > max) errors.push(fail(`هدف ${t === "technical" ? "المهارات الفنية" : "المهارات العامة"} في الملف خارج المسموح (من 1 إلى ${max}).`, `targets.${t}: ${JSON.stringify(v)}`));
      else targets[t] = v;
    }
  }

  // التقييمات والخطة (المطابقة للإطار الحالي)
  const [levels, unknownLevels] = checkLevels(p.levels, data, "التقييمات", errors);
  const planRaw = checkPlan(p.plan, "الخطة", errors);
  const plan = planRaw.filter((id) => data.skills[id]);
  const unknownPlan = planRaw.filter((id) => !data.skills[id]);
  if ((Object.keys(unknownLevels).length || unknownPlan.length) && sameFramework === true) {
    errors.push(fail("الملف من إصدار قاعدة المهارات نفسه لكنه يحوي مهارات غير معروفة؛ قد يكون عُدّل يدويًا.", `unknown ids with same framework: ${[...Object.keys(unknownLevels), ...unknownPlan].slice(0, 5).join(", ")}`));
  }

  // الإجابات غير المطابقة المحفوظة سابقًا: أنواعها وعناصرها كلها تُتحقق
  const priorGroups = (version === 1 ? [] : checkUnmappedGroups(p.unmapped, version, fileSha, currentSha, errors)).map((g, i) => {
    const [known, unknown] = checkLevels(g.levels, data, `الإجابات غير المطابقة (${i + 1})`, errors);
    return { framework_sha256: g.framework_sha256, levels: { ...unknown, ...known }, plan: checkPlan(g.plan, `خطة الإجابات غير المطابقة (${i + 1})`, errors) };
  });
  if (p.updated !== undefined && p.updated !== null && typeof p.updated !== "string") errors.push(fail("تاريخ الحفظ في الملف تالف.", "updated: not a string"));
  if (paths === null && p.paths === null && (Object.keys(p.levels || {}).length || (Array.isArray(p.plan) && p.plan.length))) {
    errors.push(fail("الملف يحوي تقييمات دون مجال مهني.", "levels without paths"));
  }
  // الإجابات غير المعروفة في levels تُنسب إلى مصدر إطار الملف (أو المجهول null)، وقد تقع في مصدر مجموعة
  // سابقة (المجهول فقط عمليًا). تقييمان مختلفان للمهارة نفسها من المصدر نفسه تناقض: يُرفض الملف.
  const fresh = { framework_sha256: sameFramework === false ? fileSha : null, levels: unknownLevels, plan: unknownPlan };
  priorGroups.forEach((g, i) => {
    const clash = sourceKey(g.framework_sha256) === sourceKey(fresh.framework_sha256) ? levelConflict(g.levels, fresh.levels) : null;
    if (clash) errors.push(fail(CONFLICT_TEXT, `levels and unmapped[${i}] share source ${sourceKey(fresh.framework_sha256)} and disagree on ${clash.id}: ${clash.b} vs ${clash.a}`));
  });
  if (errors.length) return { ok: false, errors };

  // إعادة ربط ما صار معروفًا من الإجابات غير المطابقة السابقة. القاعدة (docs/JOURNEY-FILE.md):
  // - للمهارة تقييم حالي في الملف: يبقى، والإجابة السابقة محفوظة بمصدرها دون الكتابة فوقه.
  // - مصادر سابقة تختلف في تقييمها: لا يُختار أحدها؛ تبقى كلها محفوظة والمهارة غير مقيّمة.
  // - غير ذلك: تُعاد القيمة (أول مصدر يعيدها، والمتفق معها من مصادر أخرى يبقى محفوظًا بمصدره).
  const offered = new Map();
  for (const g of priorGroups) {
    for (const [id, level] of Object.entries(g.levels)) if (data.skills[id]) offered.set(id, (offered.get(id) || new Set()).add(level));
  }
  let remapped = 0, heldCurrent = 0;
  const disputed = new Set();
  const kept = priorGroups.map((g) => {
    const rest = { framework_sha256: g.framework_sha256, levels: {}, plan: [] };
    for (const [id, level] of Object.entries(g.levels)) {
      if (!data.skills[id]) rest.levels[id] = level;
      else if (levels[id] !== undefined) { rest.levels[id] = level; heldCurrent += 1; }
      else if (offered.get(id).size > 1) { rest.levels[id] = level; disputed.add(id); }
      else { levels[id] = level; remapped += 1; }
    }
    for (const id of g.plan) {
      if (data.skills[id]) { if (!plan.includes(id)) { plan.push(id); remapped += 1; } } else rest.plan.push(id);
    }
    return rest;
  });
  const unmapped = mergeGroups([...kept, fresh]);
  const unmappedCount = unmapped.reduce((n, g) => n + Object.keys(g.levels).filter((id) => !data.skills[id]).length + g.plan.length, 0);

  const profile = { v: PROFILE_VERSION, paths, scope, targets, levels, plan, unmapped, updated: p.updated ?? null };
  const notes = [];
  if (version === 1) {
    notes.push("ملف من إصدار سابق من بوصلة؛ رُحّل: المسار الأول صار مجالك الأساسي والثاني مجال المقارنة.");
    notes.push(`لم يكن الملف يحفظ نطاق المهارات؛ استُخدم النطاق الحالي (${scope === "all" ? "كل المهارات الفنية" : "ذات الأولوية"}).`);
  }
  if (!fileSha && wrapper) notes.push("الملف لا يحفظ بصمة قاعدة المهارات، فلا يمكن تأكيد أنه من الإصدار نفسه.");
  if (sameFramework === false) notes.push("الملف حُفظ مع إصدار آخر من قاعدة المهارات؛ قد تختلف النتيجة لأن قوائم المهارات قد تغيّرت.");
  if (remapped) notes.push(`إجابات سابقة غير مطابقة صارت مهاراتها موجودة في الإطار الحالي، فأُعيدت إلى تقييماتك (العدد: ${remapped}).`);
  if (heldCurrent) notes.push(`إجابات سابقة لمهارات لها تقييم حالي في الملف (العدد: ${heldCurrent}): بقي التقييم الحالي، وحُفظت السابقة بمصدرها دون أن تُكتب فوقه.`);
  if (disputed.size) notes.push(`في الملف أكثر من تقييم مختلف من إصدارات سابقة لمهارات موجودة الآن (العدد: ${disputed.size})، فلم نختر أحدها: بقيت كلها محفوظة بمصادرها، وتبقى هذه المهارات غير مقيّمة حتى تقيّمها.`);
  if (unmappedCount) notes.push(`في الملف إجابات لمهارات غير موجودة في الإطار الحالي (العدد: ${unmappedCount}). حُفظت كما هي ولم تُحذف، وتبقى في أي نسخة تنزّلها لاحقًا.`);
  return { ok: true, profile, info: { version, sameFramework, frameworkSha: fileSha, notes, snapshot: sameFramework ? wrapper?.result ?? null : null } };
}

function validSnapshot(r) {
  return isObject(r) && typeof r.mode === "string" && Number.isInteger(r.rated) && Number.isInteger(r.total)
    && Array.isArray(r.gaps) && r.gaps.every((g) => Array.isArray(g) && g.length === 3 && isId(g[0]) && Number.isInteger(g[1]) && Number.isInteger(g[2]))
    && Array.isArray(r.plan) && r.plan.every(isId);
}

// تحميل الملف المخزن في المتصفح: التحقق نفسه، مع قبول ملف لم يُختر فيه مجال بعد.
export function loadStoredProfile(raw, data, fallbackScope) {
  const r = parseJourney(raw, data, { fallbackScope, allowEmptyPaths: true });
  return r.ok ? r.profile : null;
}

// ---------------------------------------------------------------------------
// الفجوات والخطة

export function targetFor(data, profile, skillId) {
  const { type, max } = scaleFor(data, skillId);
  return Math.min(profile.targets[type] ?? DEFAULT_TARGETS[type], max);
}

export function pathSummary(data, profile, groupId, scope = profile.scope || "priority") {
  const g = indexGroups(data).get(groupId);
  const ids = [...g.technical.filter(inScope(data, scope)), ...g.general];
  let rated = 0, below = 0, met = 0;
  for (const id of ids) {
    const level = profile.levels[id];
    if (level === undefined) continue;
    rated += 1;
    if (level < targetFor(data, profile, id)) below += 1; else met += 1;
  }
  return { total: ids.length, rated, unrated: ids.length - rated, below, met };
}

export function progress(data, profile, items = assessmentItems(data, profile.paths, profile.scope)) {
  const rated = items.filter(({ id }) => profile.levels[id] !== undefined).length;
  return { total: items.length, rated, unrated: items.length - rated };
}

// الفجوات: الفنية المشتركة أولًا (تخدم المسارين)، ثم الفنية الخاصة بكل مسار، ثم العامة.
// داخل كلٍّ: ذات الأولوية، ثم الأكبر فجوة، ثم الاسم. تُحسب على كل ما قيّمه المستخدم في نطاقه.
export function computeGaps(data, profile) {
  const items = assessmentItems(data, profile.paths, profile.scope);
  const gaps = [];
  for (const { id, where } of items) {
    const level = profile.levels[id];
    if (level === undefined) continue;
    const target = targetFor(data, profile, id);
    if (level < target) {
      const skill = data.skills[id];
      gaps.push({ id, where, level, target, gap: target - level, priority: !!skill.priority, type: skill.type });
    }
  }
  const tier = (g) => (g.type === "general" ? 2 : g.where === "both" ? 0 : 1);
  const rank = (g) => [tier(g), g.priority ? 0 : 1, -g.gap];
  gaps.sort((x, y) => {
    const a = rank(x), b = rank(y);
    for (let i = 0; i < a.length; i += 1) if (a[i] !== b[i]) return a[i] - b[i];
    return data.skills[x.id].name.localeCompare(data.skills[y.id].name, "ar");
  });
  return gaps;
}

export function suggestedPlan(gaps, size = PLAN_SIZE) {
  return gaps.slice(0, size).map((g) => g.id);
}

// لماذا تظهر هذه المهارة: من أي مسار، وهل هي ذات أولوية، والفارق.
export function whyGap(data, profile, gap) {
  const groups = indexGroups(data);
  const [aId, bId] = profile.paths || [];
  const parts = [];
  if (gap.type === "general") parts.push("مهارة عامة مطلوبة في كل المجالات الرقمية");
  else if (gap.where === "both" && bId) parts.push("مشتركة بين المجالين، فتطويرها يخدمهما معًا");
  else parts.push(`من مهارات «${groupLabel(groups.get(gap.where === "b" ? bId : aId))}»`);
  if (gap.priority) parts.push("معلَّمة «ذات أولوية» في القطاع الرقمي");
  parts.push(`مستواك ${gap.level === 0 ? "«لم أبدأ»" : gap.level} وهدفك ${gap.target}`);
  return parts.join("؛ ") + ".";
}

// خطوات عملية لفجوة واحدة (حتى ثلاث)، كل خطوة تذكر مصدرها. لا دورات ولا روابط ولا شهادات
// مخترعة: المصدر لا يربط المهارات ببرامج تدريب. الخطوة العملية اقتراح عام من بوصلة وموسومة بذلك.
export function stepsFor(data, gap) {
  const skill = data.skills[gap.id];
  const next = Math.min(gap.level + 1, gap.target);
  const steps = [];
  if (skill.description) {
    steps.push({ kind: "understand", text: `افهم المطلوب: «${skill.description}»`, source: "وصف المهارة من قاعدة بيانات المهارات" });
  }
  const dict = safeUrl(data.links?.dictionary);
  if (skill.page && dict) {
    steps.push({ kind: "read",
      text: `اقرأ وصف المستوى ${next} لهذه المهارة في قاموس المهارات الرسمي (ملف PDF خارجي، صفحة ${skill.page}${skill.page_verified ? "" : "، حُدّدت بترتيب المهارات وقد يختلف عنوانها قليلًا"}).`,
      url: `${dict}#page=${skill.page}`, source: "قاموس المهارات للقطاع الرقمي" });
  }
  steps.push({ kind: "practice",
    text: gap.level === 0
      ? `ابدأ بالتعرّف: اكتب بكلماتك تعريفًا قصيرًا لـ«${skill.name}» ومثالًا على استخدامها في العمل، من مصدر تعليمي تختاره بنفسك.`
      : `تمرين صغير: اختر جزءًا واحدًا من وصف المهارة ونفّذه في مثال تدريبي قصير، ثم دوّن ما أنجزته وقارنه بوصف المستوى ${next}.`,
    source: "اقتراح عام من بوصلة، ليس من المصدر ولا برنامجًا تدريبيًا معتمدًا" });
  return steps;
}

// سبب خروج مهارة مختارة من الخطة الفعلية.
function excludedReason(data, profile, id, itemIds) {
  const level = profile.levels[id];
  if (!itemIds.has(id)) {
    return !data.skills[id]?.priority && profile.scope === "priority"
      ? { code: "scope", text: "ليست ضمن النطاق الحالي «ذات الأولوية»؛ تعود إن اخترت «كل المهارات الفنية»." }
      : { code: "paths", text: "ليست من مهارات المجال أو المجالين المختارين حاليًا." };
  }
  if (level === undefined) return { code: "unrated", text: "ألغيت تقييمها، فلم تعد فجوة محسوبة." };
  return { code: "met", text: `بلغت هدفك فيها (مستواك ${level} والهدف ${targetFor(data, profile, id)}).` };
}

// المصدر الوحيد لحالة الخطة؛ تستخدمه صفحة النتيجة وتقرير HTML وملف الرحلة.
// «خطتي» = ما اختاره المستخدم صراحة فقط. «الاقتراحات» = أول فجوات غير مختارة، منفصلة.
// mode:
//  - "unrated": لم يقيّم أي مهارة بعد.
//  - "no-gaps": لا فجوات فيما قيّمه (قد تبقى مهارات لم يقيّمها).
//  - "empty": توجد فجوات ولم يختر شيئًا بعد (أو أزال كل ما اختاره) — الاقتراحات معروضة منفصلة.
//  - "custom": اختار مهارات وبعضها ما زال فجوة.
//  - "custom-empty": كل ما اختاره لم يعد فجوة، وتوجد فجوات أخرى. ليست «لا فجوات».
export function planState(data, profile) {
  const items = assessmentItems(data, profile.paths, profile.scope);
  const itemIds = new Set(items.map((i) => i.id));
  const gaps = computeGaps(data, profile);
  const byId = new Map(gaps.map((g) => [g.id, g]));
  const prog = progress(data, profile, items);
  const chosen = profile.plan.filter((id) => data.skills[id]);
  const activeIds = chosen.filter((id) => byId.has(id));
  let mode;
  if (!prog.rated) mode = "unrated";
  else if (!gaps.length) mode = "no-gaps";
  else if (!chosen.length) mode = "empty";
  else mode = activeIds.length ? "custom" : "custom-empty";
  const withSteps = (gap) => ({ gap, steps: stepsFor(data, gap), why: whyGap(data, profile, gap) });
  const excluded = chosen.filter((id) => !byId.has(id)).map((id) => ({ id, reason: excludedReason(data, profile, id, itemIds) }));
  const others = gaps.filter((g) => !activeIds.includes(g.id));
  return { mode, gaps, active: activeIds.map((id) => withSteps(byId.get(id))), excluded, others,
    suggestions: others.slice(0, PLAN_SIZE).map(withSteps), progress: prog, chosen };
}

// الخطوة القادمة: أول ما اختاره المستخدم، وإلا أول اقتراح (موسومًا اقتراحًا).
export function nextStep(state) {
  if (state.active.length) return { ...state.active[0], suggested: false };
  if (state.suggestions.length) return { ...state.suggestions[0], suggested: true };
  return null;
}

// ---------------------------------------------------------------------------
// ملف الرحلة (JSON) والتقرير (HTML)

export function resultSnapshot(data, profile) {
  const s = planState(data, profile);
  return { mode: s.mode, rated: s.progress.rated, total: s.progress.total,
    gaps: s.gaps.map((g) => [g.id, g.level, g.target]), plan: s.active.map((a) => a.gap.id) };
}

export function sameSnapshot(a, b) {
  return !!a && !!b && JSON.stringify([a.mode, a.rated, a.total, a.gaps, a.plan]) === JSON.stringify([b.mode, b.rated, b.total, b.gaps, b.plan]);
}

// الملف المصدَّر يُكتب بالاتفاق نفسه الذي يقبله parseJourney: الإجابات غير المطابقة تحمل بصمة
// إطارها الأصلي، فلا يتعارض وجودها مع بصمة الإطار الحالي في رأس الملف.
export function exportJourney(data, manifest, profile, now = new Date().toISOString()) {
  return {
    format: FILE_FORMAT, version: FILE_VERSION, exported_at: now,
    profile: { v: PROFILE_VERSION, paths: profile.paths, scope: profile.scope, targets: profile.targets, levels: profile.levels,
      plan: profile.plan, unmapped: profile.unmapped, updated: profile.updated },
    framework: { skills_sha256: data.framework?.skills_sha256 ?? null, title: data.framework?.title ?? null, year: data.framework?.year ?? null },
    sources: (manifest?.sources || []).filter((s) => s.sha256).map((s) => ({ id: s.id, sha256: s.sha256, verified_at: s.verified_at, edition: s.edition || null })),
    result: resultSnapshot(data, profile),
  };
}

export function reportModel(data, manifest, profile) {
  const groups = indexGroups(data);
  const paths = (profile.paths || []).map((id) => groups.get(id));
  return {
    created: new Date().toISOString(),
    paths,
    summaries: paths.map((p) => pathSummary(data, profile, p.id)),
    targets: profile.targets, scope: profile.scope,
    state: planState(data, profile),
    sources: (manifest?.sources || []).filter((s) => s.status !== "missing"),
    framework: data.framework,
  };
}

const MODE_TEXT = {
  empty: "لم تختر مهارات لخطتك بعد. اقتراحات بوصلة معروضة منفصلة، ولا تدخل خطتك إلا إذا أضفتها.",
  custom: "المهارات التي اخترتها بنفسك.",
  "custom-empty": "كل المهارات التي اخترتها لم تعد فجوات. لديك فجوات أخرى لم تخترها.",
  "no-gaps": "لا فجوات فيما قيّمته مقابل أهدافك الحالية.",
  unrated: "لم تقيّم أي مهارة بعد.",
};
export function modeText(mode) { return MODE_TEXT[mode]; }

export function reportHtml(data, manifest, profile) {
  const m = reportModel(data, manifest, profile);
  const s = m.state;
  const e = escapeHtml;
  const name = (id) => e(data.skills[id]?.name);
  const label = (g) => `${e(g.name)} (${e(g.subsector)})`;
  const item = ({ gap, steps, why }, i) => `<li><h3>${i + 1}. ${name(gap.id)} <small>(المستوى ${gap.level} ← هدف ${gap.target})</small></h3><p><small>لماذا: ${e(why)}</small></p><ol>${
    steps.map((st) => `<li>${e(st.text)}${st.url ? ` — <a href="${e(st.url)}">${e(st.url)}</a>` : ""} <em>[${e(st.source)}]</em></li>`).join("")}</ol></li>`;
  const mine = s.active.length ? `<ol>${s.active.map(item).join("")}</ol>` : `<p>${e(modeText(s.mode))}</p>`;
  const excluded = s.excluded.length ? `<h3>مهارات اخترتها ولم تعد في الخطة</h3><ul>${s.excluded.map((x) => `<li>${name(x.id)}: ${e(x.reason.text)}</li>`).join("")}</ul>` : "";
  const sugg = s.suggestions.length ? `<h2>اقتراحات بوصلة (لم تخترها)</h2><p><small>أول الفجوات بالترتيب: المشتركة بين المجالين أولًا، ثم ذات الأولوية، ثم الأكبر فجوة. اقتراح من بوصلة، لا متطلب رسمي.</small></p><ol>${s.suggestions.map(item).join("")}</ol>` : "";
  const summaries = m.paths.map((p, i) => {
    const x = m.summaries[i];
    return `<li><strong>${label(p)}</strong>${i === 1 ? " — مجال المقارنة" : ""}: قيّمت ${x.rated} من ${x.total}، دون هدفك ${x.below}، بلغت هدفك ${x.met}، لم تقيّمها ${x.unrated} (لا نعرف مستواك فيها).</li>`;
  }).join("");
  const partial = s.progress.unrated > 0 && s.progress.rated > 0
    ? `<p class="note"><strong>نتيجة جزئية:</strong> المهارات المقيّمة: ${s.progress.rated} من ${s.progress.total}. المهارات التي لم تقيّمها لا تُحسب صفرًا ولا تدخل الخطة.</p>` : "";
  const sources = m.sources.map((x) => `<li>${e(x.title)} — ${e(x.publisher)}${x.edition ? ` (${e(x.edition)})` : ""}. آخر تحقق ناجح: ${e(formatDate(x.verified_at))}. البصمة SHA-256: <code>${e((x.sha256 || "").slice(0, 16))}…</code> <a href="${e(x.page_url || x.url)}">${e(x.page_url || x.url)}</a></li>`).join("");
  const pathsLine = m.paths.length === 2
    ? `مجالك الأساسي: <strong>${label(m.paths[0])}</strong>، ومجال المقارنة: <strong>${label(m.paths[1])}</strong>.`
    : `مجالك: <strong>${label(m.paths[0])}</strong>.`;
  return `<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>نتيجتي — بوصلة</title>
<style>body{font-family:"IBM Plex Sans Arabic","Segoe UI",Tahoma,sans-serif;color:#102A3A;background:#fff;max-width:820px;margin:2rem auto;padding:0 1rem;line-height:1.8;font-size:17px}h1{color:#0E5E63}h2{border-bottom:2px solid #C8902E;padding-bottom:.2rem}small,em{color:#56656E}code{direction:ltr;unicode-bidi:isolate}.note{background:#FBF9F4;border:1px solid #E7E1D4;border-radius:10px;padding:.8rem 1rem}a{color:#0E5E63;word-break:break-all}</style></head><body>
<h1>بوصلة — نتيجتك وخطة التطوير</h1>
<p>أُنشئت في ${e(formatDate(m.created))}. ${pathsLine}</p>
<p class="note">هذا تقييم ذاتي لم يتحقق منه أحد، وليس اختبارًا معتمدًا ولا حكمًا على جاهزيتك ولا تقديرًا لفرص التوظيف. الأهداف (فنية ${m.targets.technical} من 5، عامة ${m.targets.general} من 3) اخترتها أنت أو أبقيت قيمة بوصلة الافتراضية؛ المصدر لا يحدد المستوى المطلوب لكل مجموعة. نطاق المهارات الفنية: ${m.scope === "all" ? "كل المهارات الفنية" : "المهارات ذات الأولوية في القطاع الرقمي"}.</p>
${partial}
<h2>ملخص التقييم</h2><ul>${summaries}</ul>
<h2>خطتي (ما اخترته)</h2>${mine}${excluded}
${sugg}
<h2>المصادر</h2><ul>${sources}</ul>
<p class="note">${e(data.framework?.issuer || "")} — ${e(data.framework?.title || "")} (${e(data.framework?.year || "")}). المحتوى المهاري من ملفات منشورة في بوابة وزارة الموارد البشرية والتنمية الاجتماعية، ويُعرض في هذا التقرير الشخصي مع ذكر المصدر؛ راجع شروط كل مصدر قبل أي مشاركة علنية.</p>
</body></html>`;
}
