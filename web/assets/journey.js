// غلاف الإصدار المحلي: المستكشف مستقل عن ملف التقييم الموسع، ولا تحويل بين السُّلّمين.
import * as L from "./js/logic.js";
import { loadState, STORAGE_KEY } from "./model.js";

const obj = (x) => x && typeof x === "object" && !Array.isArray(x);
const keys = (x, names) => obj(x) && Object.keys(x).length === names.length && names.every((k) => k in x);
const date = (x) => x === null || (typeof x === "string" && Number.isFinite(Date.parse(x)));
const fail = (text) => ({ ok: false, errors: [{ text, detail: "release journey validation" }] });
const jsonClone = (x) => JSON.parse(JSON.stringify(x));
export const MOTION_KEY = "compassExplorer.motion";

export function validExplorer(s, data) {
  if (!keys(s, ["v", "answers", "field", "tried", "step", "assess", "updated"]) || !date(s.updated)
      || loadState(s, data).recovered) return false;
  const group = (id) => data.subsectors.flatMap((x) => x.groups).find((x) => x.id === id);
  return Object.entries(s.tried).every(([, t]) => keys(t, ["done", "reflection"]) && typeof t.done === "boolean")
    && (s.step === null || (keys(s.step, ["field", "skill", "from"])
      && ["demo", "choice", "assessment"].includes(s.step.from)
      && [...group(s.step.field).technical, ...group(s.step.field).general].includes(s.step.skill)))
    && Object.entries(s.assess).every(([id, a]) => keys(a, ["levels", "unknown", "cursor"])
      && new Set(a.unknown).size === a.unknown.length
      && [...Object.keys(a.levels), ...a.unknown].every((skill) => [...group(id).technical, ...group(id).general].includes(skill)));
}

// قراءة فقط: لا ترحيل تلقائي ولا دمج أو إزالة للمفاتيح السابقة.
export function readLegacy(storage, data) {
  const raw = storage.getItem("compass.profile") ?? storage.getItem("compass.profile.v1");
  if (raw === null) return { raw: null, profile: null };
  try {
    const profile = L.loadStoredProfile(JSON.parse(raw), data, storage.getItem("compass.scope") || "priority");
    return { raw, profile, invalid: !profile };
  } catch { return { raw, profile: null, invalid: true }; }
}

export function exportRelease(state, data, manifest, storage, now = new Date().toISOString()) {
  if (!validExplorer(state, data)) throw new Error("التقدم الحالي غير صالح للحفظ؛ لم نغيّر الأصل.");
  const legacy = readLegacy(storage, data);
  if (legacy.invalid) throw new Error("التقييم القديم غير صالح. نزّل نسخة التخزين الأصلية للاسترجاع قبل إصلاحه؛ لم نحذفه.");
  return { format: "bawsala-journey", version: 4, exported_at: now,
    framework_sha256: data.framework.skills_sha256, explorer: jsonClone(state),
    legacy: legacy.profile ? L.exportJourney(data, manifest, legacy.profile, now) : null,
    motion: storage.getItem(MOTION_KEY) === "paused" ? "paused" : "on" };
}

export function parseRelease(raw, data) {
  if (raw?.format !== "bawsala-journey" || raw.version !== 4) {
    const legacy = L.parseJourney(raw, data);
    return legacy.ok ? { ok: true, explorer: null, legacy: legacy.profile, motion: null,
      notes: ["ملف تقييم موسع قديم: يستبدل التقييم الموسع فقط، ولا يغيّر اهتماماتك أو تجاربك أو خطوتك الأولى.", ...legacy.info.notes] } : legacy;
  }
  if (!keys(raw, ["format", "version", "exported_at", "framework_sha256", "explorer", "legacy", "motion"])
      || !date(raw.exported_at) || raw.exported_at === null || !["on", "paused"].includes(raw.motion))
    return fail("الملف ناقص أو يحوي بيانات غير متوقعة. اختر نسخة أصلية محفوظة من بوصلة.");
  if (raw.framework_sha256 !== data.framework.skills_sha256)
    return fail("إطار المهارات في الملف مختلف. احتفظ بالملف الأصلي؛ لا نستبدل تقدم المستكشف قبل التحقق من توافقه.");
  if (!validExplorer(raw.explorer, data)) return fail("تقدم المستكشف في الملف غير صالح؛ لم نغيّر بياناتك. اختر نسخة سليمة.");
  const legacy = raw.legacy === null ? null : L.parseJourney(raw.legacy, data, { allowEmptyPaths: true });
  if (legacy && !legacy.ok) return legacy;
  return { ok: true, explorer: jsonClone(raw.explorer), legacy: legacy?.profile || null, motion: raw.motion,
    notes: ["يستبدل تقدم المستكشف وتفضيل الحركة.", legacy ? "يستبدل التقييم الموسع أيضًا دون دمجه مع المستكشف." : "لا يحتوي تقييمًا موسعًا؛ يترك تقييمك الموسع الحالي كما هو.", ...(legacy?.info.notes || [])] };
}

// نسخة كاملة قبل الكتابة، ثم تحقق قراءة؛ أي فشل يعيد القيم السابقة.
export function restoreRelease(result, storage) {
  const changes = [];
  if (result.explorer) changes.push([STORAGE_KEY, JSON.stringify(result.explorer)]);
  if (result.legacy) changes.push(["compass.profile", JSON.stringify(result.legacy)], ["compass.cursor", null]);
  if (result.motion) changes.push([MOTION_KEY, result.motion]);
  const before = Object.fromEntries(changes.map(([k]) => [k, storage.getItem(k)]));
  const backup = `compass.restore.backup.${Date.now()}`;
  storage.setItem(backup, JSON.stringify(before));
  if (storage.getItem(backup) !== JSON.stringify(before)) throw new Error("تعذر حفظ نسخة استرجاع؛ لم نستبدل تقدمك.");
  try {
    for (const [k, v] of changes) {
      if (v === null) storage.removeItem(k); else storage.setItem(k, v);
      if (storage.getItem(k) !== v) throw new Error("تعذر التحقق من الحفظ");
    }
  } catch (e) {
    for (const [k, v] of Object.entries(before)) { if (v === null) storage.removeItem(k); else storage.setItem(k, v); }
    throw e;
  }
  return backup;
}

export function storageArchive(storage) {
  const out = {};
  for (let i = 0; i < storage.length; i++) {
    const k = storage.key(i);
    if (k.startsWith("compass")) out[k] = storage.getItem(k);
  }
  return out;
}

export function download(name, text, type = "application/json") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
