// البوصلة في الصفحة الرئيسية: حركة ذاتية هادئة، ولا تتبع المؤشر أبدًا (تصحيح صريح من المستخدم).
// - الهدوء: الإبرة «تبحث» ببطء حول الشمال (موجتان جيبيتان، ±13° تقريبًا، دورة 5–11 ثوانٍ).
// - التفعيل (نقر أو لمس أو Enter أو Space): دورة كاملة واحدة تنتهي عند اتجاه رئيسي، مع موجة خفيفة حول القرص،
//   ثم ثبات قصير وعودة إلى الهدوء. التكرار يغيّر الاتجاه دون دورة إضافية: لا تراكم ولا تسارع.
// - التفعيل لا ينقل الصفحة ولا يغيّر الإجابات أو الاقتراحات: زخرفة تفاعلية فقط.
// - الكفاءة: الحلقة تتوقف حين تُخفى الصفحة أو تخرج البوصلة من الشاشة أو تهدأ وهي متوقفة.
// - تقليل الحركة، أو إيقاف المستخدم للحركة: لا حركة ذاتية، والتفعيل يغيّر الاتجاه فورًا مع وميض لوني دون حركة، ثم يعود.
// - زر هادئ لإيقاف الحركة الزخرفية، ويُحفظ الاختيار في المتصفح.
import { icon } from "./icons.js";

const MOTION_KEY = "compassExplorer.motion";
const REST = 0;
const HEADINGS = [0, 90, 180, 270];
const K = 2.5e-5, C = 0.0055, VMAX = 1.2;        // نابض بقليل من التجاوز: دورة كاملة في نحو ثانية
const HOLD_MS = 900, DEBOUNCE_MS = 220, REDUCED_SHOW_MS = 1500;

const norm = (a) => ((a % 360) + 540) % 360 - 180;

export function compassMarkup(size = 280) {
  const ticks = Array.from({ length: 72 }, (_, i) => {
    const a = (i * 5 * Math.PI) / 180, major = i % 18 === 0, mid = i % 6 === 0;
    const r1 = major ? 76 : mid ? 82 : 86, r2 = 90;
    return `<line x1="${(100 + r1 * Math.sin(a)).toFixed(2)}" y1="${(100 - r1 * Math.cos(a)).toFixed(2)}" x2="${(100 + r2 * Math.sin(a)).toFixed(2)}" y2="${(100 - r2 * Math.cos(a)).toFixed(2)}"
      stroke="#F4E7CC" stroke-opacity="${major ? 0.95 : mid ? 0.6 : 0.28}" stroke-width="${major ? 2.4 : mid ? 1.5 : 1}" stroke-linecap="round"/>`;
  }).join("");
  const letters = [["ش", 100, 58], ["ق", 143, 104], ["ج", 100, 149], ["غ", 57, 104]]
    .map(([t, x, y]) => `<text x="${x}" y="${y}" class="cardinal" text-anchor="middle">${t}</text>`).join("");
  return `<div class="compass-stage">
    <button type="button" class="compass-btn" aria-label="حرّك البوصلة (زخرفة، لا تغيّر شيئًا في إجاباتك)">
      <svg class="compass-art" viewBox="0 0 200 200" width="${size}" height="${size}" aria-hidden="true" focusable="false">
        <defs>
          <radialGradient id="dial" cx="50%" cy="42%" r="62%"><stop offset="0" stop-color="#147078"/><stop offset="1" stop-color="#0A474B"/></radialGradient>
          <linearGradient id="gold" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#E2B04F"/><stop offset="1" stop-color="#B57D1F"/></linearGradient>
        </defs>
        <circle cx="100" cy="100" r="99" fill="#08393C"/>
        <circle cx="100" cy="100" r="95" fill="url(#dial)"/>
        <circle class="ripple" cx="100" cy="100" r="70" fill="none" stroke="#E2B04F" stroke-width="2"/>
        ${ticks}
        <circle cx="100" cy="100" r="64" fill="none" stroke="#F4E7CC" stroke-opacity=".18" stroke-dasharray="1.5 5"/>
        ${letters}
        <g class="needle">
          <path d="M100 30 L111 100 L100 93 L89 100 Z" fill="url(#gold)"/>
          <path d="M100 30 L100 93 L89 100 Z" fill="#000" opacity=".12"/>
          <path d="M100 170 L89 100 L100 107 L111 100 Z" fill="#F6F3EC"/>
        </g>
        <circle cx="100" cy="100" r="8" fill="#102A3A" stroke="#F6F3EC" stroke-width="2.5"/>
        <circle cx="100" cy="100" r="2.4" fill="#E2B04F"/>
      </svg>
    </button>
    <button type="button" class="motion-toggle" aria-pressed="false">${icon("pause", 16)}<span>أوقف حركة البوصلة</span></button>
  </div>`;
}

export function mountCompass(root) {
  const btn = root.querySelector(".compass-btn");
  const svg = btn?.querySelector(".compass-art");
  const needle = svg?.querySelector(".needle");
  const toggle = root.querySelector(".motion-toggle");
  if (!needle) return () => {};
  const media = matchMedia("(prefers-reduced-motion: reduce)");
  let paused = false;
  try { paused = localStorage.getItem(MOTION_KEY) === "paused"; } catch { /* التخزين غير متاح */ }

  let angle = REST, vel = 0, target = REST, mode = "idle", raf = 0, last = 0, holdUntil = 0, lastActivate = 0;
  let visible = !document.hidden, onScreen = true, reducedTimer = 0;

  const draw = () => {
    needle.setAttribute("transform", `rotate(${angle.toFixed(2)} 100 100)`);
    btn.dataset.angle = angle.toFixed(1);
  };
  const motionOn = () => !media.matches && !paused;
  const idleTarget = (t) => motionOn() ? REST + 9 * Math.sin((2 * Math.PI * t) / 11000) + 4 * Math.sin((2 * Math.PI * t) / 4700 + 1.3) : REST;
  // الحالة المعلنة (للاختبار والتشخيص): لا حلقة تعمل = متوقفة، أيًّا كانت المرحلة التي أوقفت فيها.
  const status = () => { btn.dataset.motion = media.matches ? "reduced" : !raf ? (paused && mode === "idle" ? "paused" : "stopped") : mode !== "idle" ? mode : "idle"; };

  const frame = (now) => {
    const dt = Math.min(32, last ? now - last : 16);
    last = now;
    if (mode === "active" && Math.abs(norm(target - angle)) < 0.6 && Math.abs(vel) < 0.02) {
      if (!holdUntil) holdUntil = now + HOLD_MS;
      else if (now >= holdUntil) { mode = "return"; holdUntil = 0; }
    }
    if (mode !== "active") target = angle + norm(idleTarget(now) - angle);
    if (mode === "return" && Math.abs(norm(target - angle)) < 1.5) mode = "idle";
    const acc = K * (target - angle) - C * vel;
    vel = Math.max(-VMAX, Math.min(VMAX, vel + acc * dt));
    angle += vel * dt;
    draw();
    const resting = mode === "idle" && !motionOn() && Math.abs(norm(REST - angle)) < 0.2 && Math.abs(vel) < 0.005;
    if (resting) { angle = REST; vel = 0; draw(); raf = 0; last = 0; status(); return; }
    raf = requestAnimationFrame(frame);
    status();
  };
  const run = () => { if (!raf && visible && onScreen && !media.matches) { last = 0; raf = requestAnimationFrame(frame); } status(); };
  const stop = () => { cancelAnimationFrame(raf); raf = 0; last = 0; status(); };

  const activate = () => {
    const now = performance.now();
    if (now - lastActivate < DEBOUNCE_MS) return;
    lastActivate = now;
    const current = ((Math.round(target) % 360) + 360) % 360;
    const choices = HEADINGS.filter((hd) => Math.abs(norm(hd - current)) > 10);
    const heading = choices[Math.floor(Math.random() * choices.length)];
    svg.classList.remove("pulse", "flash");
    void svg.getBoundingClientRect();                 // إعادة تشغيل الموجة دون تراكم
    if (media.matches || paused) {      // اختيار المستخدم «أوقف الحركة» يُحترم في التفعيل أيضًا
      stop(); clearTimeout(reducedTimer);
      mode = "idle"; angle = target = heading; vel = 0; draw();
      svg.classList.add("flash");
      reducedTimer = setTimeout(() => { angle = target = REST; draw(); svg.classList.remove("flash"); }, REDUCED_SHOW_MS);
      btn.dataset.activations = String(Number(btn.dataset.activations || 0) + 1);
      btn.dataset.motion = media.matches ? "reduced" : "paused";
      return;
    }
    svg.classList.add("pulse");
    // أثناء تفعيل سابق: اتجاه جديد فقط، دون دورة إضافية. وإلا: دورة كاملة واحدة ثم الاتجاه.
    target = mode === "active" ? angle + norm(heading - angle) : angle + 360 + (((heading - angle) % 360) + 360) % 360;
    mode = "active"; holdUntil = 0;
    btn.dataset.activations = String(Number(btn.dataset.activations || 0) + 1);
    if (!raf && visible) { last = 0; raf = requestAnimationFrame(frame); }
    status();
  };

  const setPaused = (p, remember = true) => {
    paused = p;
    if (p) { stop(); mode = "idle"; holdUntil = 0; angle = target = REST; vel = 0; draw(); }
    if (remember) try { localStorage.setItem(MOTION_KEY, p ? "paused" : "on"); } catch { /* التخزين غير متاح */ }
    toggle.setAttribute("aria-pressed", String(p));
    toggle.innerHTML = p ? `${icon("play", 16)}<span>شغّل حركة البوصلة</span>` : `${icon("pause", 16)}<span>أوقف حركة البوصلة</span>`;
    run();
  };
  const onVisibility = () => { visible = !document.hidden; visible ? run() : stop(); };
  const onMotionPref = () => { stop(); angle = target = REST; vel = 0; mode = "idle"; draw(); toggle.hidden = media.matches; run(); };
  const io = "IntersectionObserver" in window ? new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; onScreen ? run() : stop(); }) : null;

  btn.addEventListener("click", activate);
  toggle.addEventListener("click", () => setPaused(!paused));
  document.addEventListener("visibilitychange", onVisibility);
  media.addEventListener("change", onMotionPref);
  io?.observe(svg);
  toggle.hidden = media.matches;
  setPaused(paused, false);   // لا يُحفظ شيء ما لم يختر المستخدم
  draw();

  return () => {
    stop(); clearTimeout(reducedTimer); io?.disconnect();
    document.removeEventListener("visibilitychange", onVisibility);
    media.removeEventListener("change", onMotionPref);
  };
}

// إبرة التقدم في رأس الأسئلة: تشير إلى نسبة الإنجاز (انتقال CSS يُلغى عند تقليل الحركة).
let lastDeg = 0;
export function progressCompass(fraction) {
  const deg = Math.round(fraction * 360), from = lastDeg;
  lastDeg = deg;
  return `<span class="mini-compass" aria-hidden="true"><svg viewBox="0 0 40 40" width="40" height="40" focusable="false">
    <circle cx="20" cy="20" r="19" fill="#0E5E63"/>
    <circle cx="20" cy="20" r="15" fill="none" stroke="#F4E7CC" stroke-opacity=".5" stroke-width="1.5"
      stroke-dasharray="${(94.25 * fraction).toFixed(2)} 94.25" transform="rotate(-90 20 20)"/>
    <g class="mini-needle" style="transform: rotate(${from}deg)" data-to="${deg}"><path d="M20 7 L23 20 L20 18.5 L17 20 Z" fill="#C8902E"/><path d="M20 33 L17 20 L20 21.5 L23 20 Z" fill="#F6F3EC"/></g>
    <circle cx="20" cy="20" r="2.4" fill="#102A3A"/></svg></span>`;
}
