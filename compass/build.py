"""بناء بيانات الواجهة (web/data/compass.json) وبيان الحالة (web/data/manifest.json).

يُبنى دائمًا من آخر نسخة سليمة لكل مصدر (current.json)، لا من آخر محاولة جلب.
إن لم توجد نسخة سليمة من قاعدة المهارات لا يُكتب compass.json جديد، ويبقى السابق إن وُجد،
ويكتب البيان حالة «تعذر» لتعرضها الواجهة.
"""

from __future__ import annotations

import json
from pathlib import Path

from labor_market import analyze

from . import pdf
from .config import (CURATED_FILE, FEATURED_PATHS, GROUPS_PATHS, HRSD_OPEN_DATA_POLICY, HRSD_SOURCES,
                     MARKET_ACTIVITY, ODP_DATASET_PAGE, ODP_LICENSE, ODP_LICENSE_CHECKED, SKILLS_DB,
                     SKILLS_DICTIONARY, SOBOL_PAGE, SOURCES_DIR, TERMS_CHECKED_ON, WEB_DATA_DIR,
                     WORKERS_DATASETS, odp_terms)
from .fetch import SourceStore, _write_atomic, sha256, utcnow
from .skills import GENERAL, TECHNICAL, group_id, parse_skills_workbook, skill_id, summarize

OK_STATUSES = {"updated", "revised", "unchanged", "not_modified", "repaired"}
QUARTER_NAMES = {1: "الأول", 2: "الثاني", 3: "الثالث", 4: "الرابع"}


def source_card(store: SourceStore, **info) -> dict:
    current, last = store.current(), store.last_attempt()
    if current is None:
        status = "failed" if last else "missing"
    elif last and last.get("status") not in OK_STATUSES:
        status = "stale"
    else:
        status = "ok"
    card = {"id": store.id, "status": status, **info}
    if current:
        card |= {"sha256": current["sha256"], "size": current["size"], "fetched_at": current["fetched_at"],
                 "verified_at": current["verified_at"], "summary": current.get("summary", {}),
                 "last_modified": (current.get("http") or {}).get("last_modified")}
    if last:
        card["last_attempt"] = {k: last.get(k) for k in ("at", "status", "error") if last.get(k) is not None}
    return card


def _dictionary_index(dict_store, skills_sha, parsed):
    """فهرس الصفحات مخزن مؤقتًا ببصمتي القاموس وقاعدة البيانات (يستغرق ثواني)."""
    current = dict_store.current()
    if not current:
        return {"pages": {}, "reason": "لا توجد نسخة سليمة من القاموس"}
    cache = dict_store.dir / "index_cache.json"
    keyed = {"dictionary_sha256": current["sha256"], "skills_sha256": skills_sha, "index_version": 2}
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if {k: cached.get(k) for k in keyed} == keyed:
            return cached["index"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    try:
        index = pdf.dictionary_index(dict_store.current_bytes(), parsed["priority_order"],
                                     list(parsed["technical"]) + list(parsed["general"]))
    except pdf.PdfError as exc:
        index = {"pages": {}, "reason": f"تعذر قراءة القاموس: {exc}"}
    _write_atomic(cache, json.dumps(keyed | {"index": index}, ensure_ascii=False).encode("utf-8"))
    return index


def _market(processed_dir=None):
    """سياق السوق من حسابات labor_market على البيانات المعتمدة في data/raw (لا من النسخ المجلوبة)."""
    workers, totals = analyze.read_processed(Path(processed_dir or analyze.PROCESSED_DIR))
    tables = analyze.build_analysis(workers, totals)
    national = tables["national"].iloc[0]
    act = tables["activities"]
    row = act[act["economic_activity"] == MARKET_ACTIVITY].iloc[0]
    reg = tables["region_activities"]
    reg = reg[reg["economic_activity"] == MARKET_ACTIVITY].sort_values("workers_q2", ascending=False)

    def num(v):
        return None if v is None or v != v else (int(v) if float(v).is_integer() else float(v))

    year = int(national["year"])
    return {
        "activity": MARKET_ACTIVITY, "year": year,
        "periods": [f"الربع {QUARTER_NAMES[1]} {year}", f"الربع {QUARTER_NAMES[2]} {year}"],
        "national": {k: num(row[k]) for k in ("workers_q1", "workers_q2", "change", "change_rate", "share_q1", "share_q2")},
        "all_private_sector": {k: num(national[k]) for k in ("workers_q1", "workers_q2")},
        "regions": [{"region": r["region"], **{k: num(r[k]) for k in ("workers_q1", "workers_q2", "change", "change_rate",
                                                                      "share_q2")}} for _, r in reg.iterrows()],
        "notes": [
            "النشاط الاقتصادي يصنّف المنشأة لا الوظيفة: يشمل غير التقنيين في منشآت المعلومات والاتصالات، ولا يشمل المبرمجين في البنوك مثلًا.",
            "أعداد عاملين على رأس العمل في القطاع الخاص، وليست شواغر ولا فرص توظيف.",
            "لا توجد بيانات منشورة تربط المجموعات الوظيفية الرقمية بالمناطق؛ جداول المهن حسب المنطقة متاحة على مستوى الأبواب الكبرى فقط.",
            "مقارنة بين ربعين، وليست اتجاهًا.",
        ],
        "datasets": [{"period": f"الربع {QUARTER_NAMES[d.quarter]} {d.year}", "url": ODP_DATASET_PAGE + d.dataset_id}
                     for d in WORKERS_DATASETS],
    }


def _curated(parsed, groups_store, group_ids):
    try:
        data = json.loads(Path(CURATED_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    current = groups_store.current()
    status = "missing_source" if not current else (
        "verified" if current["sha256"] == data.get("transcribed_from_sha256") else "needs_recheck")
    out = {}
    for g in data.get("groups", []):
        gid = group_ids.get((g["subsector"], g["group"]))
        if gid:
            out[gid] = {k: g[k] for k in ("overview", "tasks", "roles", "roles_count_in_source", "top_role",
                                          "occupation_units", "page")} | {
                "status": status, "transcribed_on": data.get("transcribed_on"),
                "source_url": GROUPS_PATHS.url + f"#page={g['page']}"}
    return out


def _discovery_summary(d: dict) -> dict:
    """حالة آخر محاولة اكتشاف، والمرشحون من آخر فحص ناجح فقط مع تاريخه (لا تُعرض نتيجة قديمة كفحص حديث)."""
    ok = d.get("status") == "ok"
    success = d if ok else (d.get("last_success") or {})
    return {"at": d.get("at"), "status": d.get("status"), "error": d.get("error"),
            "links_found": success.get("links_found"), "candidates": success.get("candidates") or [],
            "last_success_at": success.get("at")}


def build(sources_root=SOURCES_DIR, out_dir=WEB_DATA_DIR, processed_dir=None, now=None) -> dict:
    at = now or utcnow()
    out_dir = Path(out_dir)
    stores = {src.id: SourceStore(sources_root, src.id) for src in HRSD_SOURCES}
    cards = [source_card(stores[src.id], title=src.title, publisher=src.publisher, url=src.url, page_url=src.page_url,
                         edition=src.edition, terms=src.terms, terms_url=src.terms_url, kind=src.kind,
                         terms_status=src.terms_status, terms_checked=TERMS_CHECKED_ON)
             for src in HRSD_SOURCES]
    for ds in WORKERS_DATASETS:
        store = SourceStore(sources_root, ds.source_id)
        card = source_card(store, title=f"العاملون في القطاع الخاص حسب النشاط الاقتصادي والمنطقة الإدارية — الربع {QUARTER_NAMES[ds.quarter]} {ds.year}",
                           publisher="وزارة الموارد البشرية والتنمية الاجتماعية — منصة البيانات المفتوحة",
                           url=ODP_DATASET_PAGE + ds.dataset_id, page_url=ODP_DATASET_PAGE + ds.dataset_id,
                           edition=f"الربع {QUARTER_NAMES[ds.quarter]} {ds.year}", terms=odp_terms(ds.dataset_id),
                           terms_url=ODP_LICENSE, kind="csv", terms_checked=TERMS_CHECKED_ON,
                           terms_status="proven" if ds.dataset_id in ODP_LICENSE_CHECKED else "unresolved")
        if card.get("summary", {}).get("matches_pinned_raw") is False:
            card["note"] = "نُشرت نسخة تختلف عن النسخة المعتمدة في التحليل؛ لم تُعتمد بعد."
        cards.append(card)
    try:
        discovery = json.loads((Path(sources_root) / "discovery.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        discovery = {"status": "missing", "candidates": []}

    manifest = {"schema": 1, "generated_at": at, "sources": cards,
                "discovery": _discovery_summary(discovery)}
    skills_bytes = stores[SKILLS_DB.id].current_bytes()
    if skills_bytes is None:
        manifest["status"] = "failed"
        manifest["message"] = "لا توجد نسخة سليمة من قاعدة بيانات المهارات؛ تعذر بناء بيانات المسارات."
        _write_atomic(out_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"))
        return manifest
    manifest["status"] = "ok" if all(c["status"] == "ok" for c in cards) else "degraded"

    parsed = parse_skills_workbook(skills_bytes)
    index = _dictionary_index(stores[SKILLS_DICTIONARY.id], sha256(skills_bytes), parsed)
    pages = index.get("pages", {})
    verified = set(index.get("verified_pages") or [])
    skills = {}
    for name, info in parsed["technical"].items():
        skills[skill_id(TECHNICAL, name)] = {"name": name, "type": "technical", "description": info["description"],
                                             "priority": info["priority"], "page": pages.get(name),
                                             "page_verified": pages.get(name) in verified}
    for name, info in parsed["general"].items():
        skills[skill_id(GENERAL, name)] = {"name": name, "type": "general", "description": info["description"],
                                           "category": info["category"]}
    subsectors, group_ids = [], {}
    for i, s in enumerate(parsed["subsectors"]):
        groups = []
        for gname, lists in s["groups"].items():
            gid = group_id(i, gname)
            group_ids[(s["name"], gname)] = gid
            tech = [skill_id(TECHNICAL, n) for n in lists["technical"]]
            groups.append({"id": gid, "name": gname, "subsector": s["name"], "technical": tech,
                           "general": [skill_id(GENERAL, n) for n in lists["general"]],
                           "priority": sum(1 for t in tech if skills[t]["priority"])})
        subsectors.append({"name": s["name"], "groups": groups})

    data = {
        "schema": 1, "generated_at": at,
        "framework": {"title": parsed["title"], "issuer": parsed["issuer"], "year": parsed["year"],
                      "sector": "القطاع الرقمي", "scale": parsed["scale"], "declared": parsed["declared"],
                      "counts": summarize(parsed), "warnings": parsed["warnings"],
                      "dictionary_index": {k: index.get(k) for k in ("offset", "anchors", "priority_anchors", "conflicts", "reason")}
                      | {"linked": len(pages), "priority": len(parsed["priority_order"]), "verified": len(verified & set(pages.values()))},
                      "skills_sha256": sha256(skills_bytes)},
        "subsectors": subsectors,
        "skills": skills,
        "featured": [group_ids[p] for p in FEATURED_PATHS if p in group_ids],
        "curated": _curated(parsed, stores[GROUPS_PATHS.id], group_ids),
        "market": _market(processed_dir),
        "links": {"skills_page": SKILLS_DB.page_url, "skills_db": SKILLS_DB.url, "dictionary": SKILLS_DICTIONARY.url,
                  "groups_paths": GROUPS_PATHS.url, "sobol": SOBOL_PAGE, "hrsd_terms": SKILLS_DB.terms_url,
                  "odp_license": ODP_LICENSE, "hrsd_open_data_policy": HRSD_OPEN_DATA_POLICY},
    }
    _write_atomic(out_dir / "compass.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    _write_atomic(out_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"))
    return manifest
