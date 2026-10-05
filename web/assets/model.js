// منطق مستكشف بوصلة النقي (دون واجهة)، لتسهل مراجعته واختباره.
import { ANSWERS, CHOICE_NONE, CHOICE_UNSURE, QUESTIONS, FIELDS, BEGINNER, ALIASES, MIN_ANSWERED, SHOW, MAX_WITH_TIES, LEVELS, NEED_BELOW } from "./content.js";

export const STORAGE_KEY = "compassExplorer.v1"; // مساحة تخزين النموذج وحده؛ لا يُقرأ مفتاح الإنتاج compass.profile
export const STATE_VERSION = 1;

const QUESTION = Object.fromEntries(QUESTIONS.map((q) => [q.id, q]));
const FIELD_BY_ID = Object.fromEntries(Object.entries(FIELDS).map(([key, f]) => [f.id, key]));

export function fieldKey(groupId) { return FIELD_BY_ID[groupId] || null; }

// خيارات كل سؤال بالشكل نفسه: {key, label, value, links}. سؤال النشاط يوزّع روابطه على الخيارات الإيجابية.
export function optionsOf(q) {
  if (q.type === "choice") return [...q.options.map((o) => ({ ...o, value: 2 })), CHOICE_NONE, CHOICE_UNSURE];
  return ANSWERS.map((a) => ({ ...a, links: a.value ? q.links : [] }));
}
export function answerOf(q, key) { return optionsOf(q).find((o) => o.key === key) || null; }

// ---------------------------------------------------------------------------
// الحالة المحفوظة

export function emptyState() {
  return { v: STATE_VERSION, answers: {}, field: null, tried: {}, step: null, assess: {}, updated: null };
}

const isObj = (x) => !!x && typeof x === "object" && !Array.isArray(x);
const isGroup = (data, id) => typeof id === "string" && data.subsectors.some((s) => s.groups.some((g) => g.id === id));

// يتحقق من الحالة المخزنة؛ أي خلل يعيد حالة فارغة مع recovered = true (النموذج لا يرمّم جزئيًا).
export function loadState(raw, data) {
  if (raw == null) return { state: emptyState(), recovered: false };
  let s;
  try { s = typeof raw === "string" ? JSON.parse(raw) : raw; } catch { return { state: emptyState(), recovered: true }; }
  const ok = isObj(s) && s.v === STATE_VERSION && isObj(s.answers) && isObj(s.tried) && isObj(s.assess)
    && Object.entries(s.answers).every(([q, a]) => QUESTION[q] && answerOf(QUESTION[q], a))
    && (s.field === null || isGroup(data, s.field))
    && Object.entries(s.tried).every(([g, t]) => isGroup(data, g) && isObj(t) && (t.reflection === null || ["more", "maybe", "less"].includes(t.reflection)))
    && (s.step === null || (isObj(s.step) && isGroup(data, s.step.field) && typeof s.step.skill === "string" && data.skills[s.step.skill]))
    && Object.entries(s.assess).every(([g, a]) => isGroup(data, g) && isObj(a) && isObj(a.levels) && Array.isArray(a.unknown)
      && Number.isInteger(a.cursor) && a.cursor >= 0
      && Object.entries(a.levels).every(([id, v]) => data.skills[id] && LEVELS.some((l) => l.value === v))
      && a.unknown.every((id) => data.skills[id] && !(id in a.levels)));
  return ok ? { state: s, recovered: false } : { state: emptyState(), recovered: true };
}

// ---------------------------------------------------------------------------
// استكشاف الاهتمامات

// يحسب المجالات التي تستحق الاستكشاف من الإجابات الفعلية فقط.
// الدرجة = مجموع (قيمة الإجابة × قوة الصلة) لكل سؤال مرتبط بالمجال. «لا أعرف» وغير المجاب: لا أثر.
// الترتيب بقوة الدليل: أولًا درجة الصلات المباشرة، ثم الدرجة الكلية. فلا تتقدم صلات أضعف متراكمة على
// نشاط قلت إنه يشدّك مباشرة. رأي المستخدم بعد التجارب لا يدخل هنا أبدًا. لا نسب مئوية ولا ترتيب خفي:
// المتساوون في المعيارين يُعرضون معًا بترتيب الأسماء.
export function exploreResult(answers, data) {
  const chosen = QUESTIONS.map((q) => ({ q, a: answers[q.id] ? answerOf(q, answers[q.id]) : null })).filter((x) => x.a);
  const answered = chosen.filter((x) => x.a.value !== null);
  const positive = answered.filter((x) => x.a.value > 0);
  const unsure = chosen.filter((x) => x.a.value === null).length;
  const base = { answered: answered.length, positive: positive.length, unsure, total: QUESTIONS.length,
                 skipped: QUESTIONS.length - chosen.length };
  if (answered.length < MIN_ANSWERED) return { ...base, status: "insufficient", shown: [], hidden: [] };
  if (!positive.length) return { ...base, status: "inconclusive", shown: [], hidden: [] };

  const scores = {};
  for (const { q, a } of positive) {
    for (const [key, strength, why] of a.links) {
      const f = (scores[key] ||= { key, id: FIELDS[key].id, score: 0, directScore: 0, reasons: [] });
      f.score += a.value * strength;
      if (strength === 2) f.directScore += a.value * strength;
      f.reasons.push({ q: q.id, short: q.short, choice: q.type === "choice", answer: a.key, answerLabel: a.label,
                       strength: strength === 2 ? "direct" : "related", why });
    }
  }
  const ranked = Object.values(scores).map((f) => ({ ...f, name: groupName(data, f.id), direct: f.reasons.some((r) => r.strength === "direct") }))
    .sort((x, y) => cmp(y, x) || x.name.localeCompare(y.name, "ar"));
  for (const f of ranked) f.tiedWith = ranked.filter((g) => g !== f && cmp(g, f) === 0).length;

  const cutoff = ranked[Math.min(SHOW, ranked.length) - 1];
  let shown = ranked.filter((f) => cmp(f, cutoff) >= 0);
  if (shown.length > MAX_WITH_TIES) {
    const above = ranked.filter((f) => cmp(f, cutoff) > 0);
    shown = above.length ? above : ranked.filter((f) => cmp(f, ranked[0]) === 0); // القمة نفسها متعادلة: تُعرض كاملة
  }
  const hidden = ranked.filter((f) => !shown.includes(f));
  const onlyMaybe = positive.every((x) => x.a.key === "maybe");
  const tieAtCut = shown.length > 1 && hidden.some((f) => cmp(f, shown[shown.length - 1]) === 0);
  return { ...base, status: "ok", shown, hidden, onlyMaybe, tieAtCut };
}

// موازنة قوة الدليل: الصلات المباشرة أولًا، ثم الدرجة الكلية.
const cmp = (a, b) => (a.directScore - b.directScore) || (a.score - b.score);

export function groupName(data, id) {
  for (const s of data.subsectors) for (const g of s.groups) if (g.id === id) return g.name;
  return id;
}

export function groupOf(data, id) {
  for (const s of data.subsectors) for (const g of s.groups) if (g.id === id) return { ...g, subsector: s.name };
  return null;
}

// المجالات بالاسم (17 اسمًا لـ26 مدخلًا): المدخل المعتمد في النموذج، وأخوه في القطاع الآخر إن وُجد.
export function fieldList(data) {
  const byName = new Map();
  for (const s of data.subsectors) for (const g of s.groups) byName.set(g.name, [...(byName.get(g.name) || []), { id: g.id, subsector: s.name }]);
  return Object.entries(FIELDS).map(([key, f]) => {
    const g = groupOf(data, f.id);
    return { key, id: f.id, icon: f.icon, name: g.name, subsector: g.subsector, plain: f.plain,
             siblings: (byName.get(g.name) || []).filter((x) => x.id !== f.id) };
  }).sort((a, b) => a.name.localeCompare(b.name, "ar"));
}

// ---------------------------------------------------------------------------
// البحث عن مجال

// تطبيع عربي محدود للمطابقة فقط (لا يغيّر النص المعروض): التشكيل والتطويل، وصور الألف، والياء والألف المقصورة،
// والتاء المربوطة والهاء، والهمزة على الواو والياء، والأحرف اللاتينية الصغيرة، والمسافات.
export function normalizeAr(text) {
  return String(text ?? "").toLowerCase()
    .replace(/[\u064B-\u0652\u0670\u0640]/g, "")
    .replace(/[أإآٱ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه").replace(/ؤ/g, "و").replace(/ئ/g, "ي")
    .replace(/\s+/g, " ").trim();
}

// المجالات المطابقة: باسم المجال (جزء منه) أو بإحدى كلماته البحثية. يعيد {id, via} حيث via الكلمة المطابقة إن لم يكن الاسم.
export function searchFields(list, query) {
  const q = normalizeAr(query);
  if (!q) return list.map((f) => ({ id: f.id, via: null }));
  const out = [];
  for (const f of list) {
    if (normalizeAr(f.name).includes(q)) { out.push({ id: f.id, via: null }); continue; }
    const alias = (ALIASES[f.key] || []).find((a) => { const n = normalizeAr(a); return n.includes(q) || (n.length >= 3 && q.includes(n)); });
    if (alias) out.push({ id: f.id, via: alias });
  }
  return out;
}

// ---------------------------------------------------------------------------
// الخطوة الأولى والتقييم المفصّل

// مهارات البداية المختارة للمجال (اجتهاد بوصلة)، مع التحقق من أنها ذات أولوية في المجال نفسه.
export function beginnerSkills(data, groupId) {
  const key = fieldKey(groupId), g = groupOf(data, groupId);
  if (!key || !g) return [];
  return (BEGINNER[key] || []).filter((id) => g.technical.includes(id) && data.skills[id]?.priority);
}

// خيارات الخطوة الأولى: مهارة التجربة (إن وُجدت) ثم مهارات البداية المختارة، حتى ثلاث.
export function firstStepOptions(data, groupId, demoSkill) {
  return [...new Set([...(demoSkill ? [demoSkill] : []), ...beginnerSkills(data, groupId)])].slice(0, 3);
}

// قسمان: مهارات البداية المختارة أولًا، ثم مهارات أخرى يذكرها المصدر للمجال (من قاعدة جلسة البداية في الإنتاج،
// وهي تفضّل المهارات الأقل تكرارًا في المجالات الأخرى). لا تُستبعد مهارة رسمية، ولا يُدّعى أنها تعرّف المجال وحدها.
export function assessmentSections(data, groupId, starter) {
  const first = beginnerSkills(data, groupId);
  const more = starter.filter((x) => x.why === "distinct" && !first.includes(x.id)).map((x) => x.id).slice(0, 5);
  return [
    { key: "beginner", title: "مهارات بداية اخترناها لهذا المجال", ids: first },
    { key: "distinct", title: "مهارات أخرى يذكرها المصدر لهذا المجال", ids: more },
  ].filter((s) => s.ids.length);
}

// rec: {levels: {id: 0..3}, unknown: [id]}. المهارة غير المقيّمة لا تُحسب صفرًا أبدًا.
export function assessmentResult(sections, rec) {
  const order = sections.flatMap((s) => s.ids.map((id) => ({ id, section: s.key })));
  const levels = rec?.levels || {};
  const unknown = new Set(rec?.unknown || []);
  const rated = order.filter((x) => levels[x.id] !== undefined).map((x, i) => ({ ...x, level: levels[x.id], i }));
  const needs = rated.filter((x) => x.level < NEED_BELOW).sort((a, b) => (a.level - b.level) || (a.i - b.i));
  return {
    total: order.length,
    rated: rated.length,
    first: needs[0] || null,
    needs,
    met: rated.filter((x) => x.level >= NEED_BELOW),
    unrated: order.filter((x) => levels[x.id] === undefined).map((x) => ({ ...x, unknown: unknown.has(x.id) })),
    zeros: rated.filter((x) => x.level === 0).length,
  };
}

export function levelLabel(v) { return LEVELS.find((l) => l.value === v)?.label ?? "غير مقيّمة"; }
