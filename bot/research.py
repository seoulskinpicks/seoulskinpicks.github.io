"""Monthly Gemini research: drafts new library topics into content/drafts/.

Two ways, so they can be compared (Claude's monthly run fact-checks both and scores them):
  free   : GEMINI_API_KEY (free tier). The bot collects the evidence itself: Olive Young Global
           bestseller names (what shoppers abroad buy), Wikipedia summaries and PubMed paper titles.
           Gemini may only use that evidence, and every source URL must come from it.
  search : GEMINI_SEARCH_API_KEY (a key from a billing-enabled project; Google Search grounding is
           not on the free tier). Gemini searches the web itself; sources come from its search results.

Every draft goes through the same automatic checks as the hand-researched library (length, claim-safe
wording, no Korean text, 2+ sources, ingredient really appears in Olive Young bestseller names).
Drafts are only ADDED to content/ automatically when [research] auto_add = "fallback" and the library
hasn't had a non-Gemini update for fallback_after_days (e.g. the Claude subscription ended), or "always".
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import date as Date
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

from . import editorial as ed
from .ai import GEMINI_URL, AITemporary, AIUnavailable, _gemini_models, _post
from .util import add_summary, clean_space, log, scrub, set_output, warn

UA = "SeoulSkinPicksBot/1.0 (monthly ingredient research; github.com/seoulskinpicks)"
WIKI = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_SUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

SCHEMA_NOTE = """Each ingredient is one JSON object with exactly these keys (English only, strict length limits in characters):
name (<=16, display name), full_name (<=42 or ""), nickname (<=26 or ""), heat ("korea" | "global" | "both"),
heat_note (<=50, a fact from the evidence explaining the heat), hot_since (year, integer), hook (<=54, cover headline,
curious, no hype), what_it_is (<=190, 1-2 plain sentences), origin (<=60), benefits (exactly 3, each <=62),
best_for (2-3, each <=30), when (<=16, e.g. "AM & PM", "Every wash", "2x a week"), how_to_use (exactly 3 steps, each <=68),
pairs_with (2-3 ingredient names, each <=20), avoid_with (0-2, only if well established), good_to_know (2-3 cautions or
facts, each <=88), myth (<=78), fact (<=108), keywords (lowercase words that appear in PRODUCT NAMES containing it),
hashtags (2-4), sources (2-4 URLs)."""
RULES = """Rules: cosmetic-claim-safe wording only ("helps", "supports", "known for", "may"); never "cures", "treats",
"heals", "clinically proven", "regrows", "removes wrinkles", "miracle". Be honest when evidence is thin (say so in
good_to_know or fact). Never invent studies, numbers, awards, rankings or products. Reply with JSON only."""


# ---------------------------------------------------------------------------
# Gemini calls
# ---------------------------------------------------------------------------
def _call(key: str, cfg, body: dict, http, sleep=time.sleep, tries: int = 2) -> dict:
    """generateContent on the first Flash model that answers. Returns the raw response JSON."""
    last = ""
    for attempt in range(tries):
        for model in _gemini_models(cfg):
            try:
                return _post(http, GEMINI_URL.format(model=model), {"x-goog-api-key": key, "content-type": "application/json"},
                             body, 120, (key,))
            except AIUnavailable as exc:
                last = f"{model}: {exc}"
                continue
            except AITemporary as exc:
                last = f"{model}: {exc}"
                continue
        if attempt + 1 < tries:
            sleep(60)
    raise RuntimeError(last or "Gemini 응답 없음")


def _text(data: dict) -> str:
    cands = data.get("candidates") or []
    parts = (cands[0].get("content", {}).get("parts") if cands else None) or []
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _json(text: str):
    text = text.strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("JSON 없음")
    s = min(starts)
    e = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[s:e + 1])


def _ask_json(key: str, cfg, prompt: str, http, sleep) -> object:
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3, "maxOutputTokens": 16384}}
    return _json(_text(_call(key, cfg, body, http, sleep)))


# ---------------------------------------------------------------------------
# free mode: evidence the bot collects itself
# ---------------------------------------------------------------------------
def _wiki(title: str, http) -> dict | None:
    try:
        r = http.get(WIKI.format(quote(title.replace(" ", "_"))), headers={"User-Agent": UA}, timeout=20)
        if r.status_code != 200:
            return None
        d = r.json()
        if d.get("type") == "disambiguation" or not d.get("extract"):
            return None
        return {"url": (d.get("content_urls") or {}).get("desktop", {}).get("page") or f"https://en.wikipedia.org/wiki/{quote(title)}",
                "text": d["extract"][:1200]}
    except Exception:
        return None


def _pubmed(query: str, http, n: int = 3) -> list[dict]:
    try:
        r = http.get(PUBMED_SEARCH, params={"db": "pubmed", "term": query, "retmax": n, "sort": "relevance", "retmode": "json"},
                     headers={"User-Agent": UA}, timeout=20)
        ids = r.json().get("esearchresult", {}).get("idlist", [])[:n]
        if not ids:
            return []
        s = http.get(PUBMED_SUMMARY, params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
                     headers={"User-Agent": UA}, timeout=20).json().get("result", {})
        return [{"url": f"https://pubmed.ncbi.nlm.nih.gov/{i}/", "text": f"{s.get(i, {}).get('title', '')} ({s.get(i, {}).get('pubdate', '')[:4]})"}
                for i in ids if s.get(i, {}).get("title")]
    except Exception:
        return []


def _catalog_lines(catalog: list[dict], lists: set[str], limit: int = 250) -> str:
    rows = [c for c in catalog if c.get("list") in lists]
    rows.sort(key=lambda c: -(c.get("review_count") or 0))
    return "\n".join(f"- {c['brand']} | {c['product']} | {c.get('review_count') or 0} reviews" for c in rows[:limit])


def research_free(cfg, lib: ed.Library, catalog: list[dict], http, sleep, n_skin: int, n_hair: int) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    if not catalog:
        return [], ["올리브영 베스트셀러 목록(data/oy_catalog.json)이 없어서 무료 조사를 건너뜀"]
    have = sorted({e["name"] for e in lib.skin + lib.hair})
    prompt = (
        "You help a K-beauty Instagram account find NEW ingredient topics.\n"
        "Below are current Olive Young Global bestseller product names (bought by K-beauty fans abroad).\n"
        f"Pick up to {n_skin} skincare ingredients from the SKIN list and up to {n_hair} hair/scalp ingredients from the HAIR list "
        "that appear by name in several product names and are NOT already covered.\n"
        f"Already covered (skip these and their synonyms): {', '.join(have)}\n"
        'Reply JSON: {"skin": [{"name": "...", "wiki_title": "exact English Wikipedia article title", '
        '"pubmed_query": "short PubMed query about its use on skin or hair", "keywords": ["words as they appear in product names"]}], "hair": [...]}\n\n'
        f"SKIN list:\n{_catalog_lines(catalog, ed.SKIN_LISTS)}\n\nHAIR list:\n{_catalog_lines(catalog, ed.HAIR_LISTS, 120)}"
    )
    picks = _ask_json(cfg.gemini_key, cfg, prompt, http, sleep)
    out: list[dict] = []
    for area in ("skin", "hair"):
        for cand in (picks.get(area) or [])[: (n_skin if area == "skin" else n_hair)]:
            name = clean_space(str(cand.get("name", "")))
            if not name:
                continue
            probe = {"area": area, "keywords": [k.lower() for k in cand.get("keywords", []) if k]}
            matches = ed.match_catalog(probe, catalog, limit=6, min_rating=0, min_reviews=0)
            if not matches:
                notes.append(f"{name}: 베스트셀러 제품명에서 확인 안 돼서 제외")
                continue
            wiki = _wiki(cand.get("wiki_title") or name, http)
            papers = _pubmed(cand.get("pubmed_query") or f"{name} skin", http)
            evidence = [{"url": m["url"], "text": f"Olive Young Global bestseller: {m['brand']} {m['product']} ({m.get('review_count') or 0} reviews)"} for m in matches[:4]]
            if wiki:
                evidence.append(wiki)
            evidence += papers
            if not wiki and not papers:
                notes.append(f"{name}: 위키백과·PubMed 자료가 없어 제외")
                continue
            prompt = (
                f"Write ONE Ingredient 101 entry about '{name}' for {area} care, using ONLY the evidence below. "
                "If the evidence does not support a statement, leave it out. heat must be \"global\" (these are bestsellers "
                "with shoppers abroad) unless the evidence says it is hot in Korea. sources must be URLs copied from the evidence.\n"
                f"{SCHEMA_NOTE}\n{RULES}\n\nEVIDENCE:\n" + "\n".join(f"[{x['url']}] {x['text']}" for x in evidence)
            )
            try:
                e = _ask_json(cfg.gemini_key, cfg, prompt, http, sleep)
            except Exception as exc:
                notes.append(f"{name}: 초안 실패 ({str(exc)[:80]})")
                continue
            if isinstance(e, list):
                e = e[0] if e else {}
            allowed = {x["url"] for x in evidence}
            e["sources"] = [s for s in e.get("sources", []) if s in allowed][:4]
            e["examples"] = [{"brand": m["brand"], "product": m["product"]} for m in matches[:3]]
            e["keywords"] = probe["keywords"]
            out.append(_normalize(e, area, "gemini-free"))
            sleep(2)
    return out, notes


# ---------------------------------------------------------------------------
# search mode: Gemini + Google Search grounding
# ---------------------------------------------------------------------------
def _resolve(uri: str, http) -> str:
    try:
        r = http.head(uri, allow_redirects=True, timeout=15, headers={"User-Agent": UA})
        url = getattr(r, "url", "") or uri
    except Exception:
        return ""
    host = urlparse(url).netloc
    return "" if (not host or "vertexaisearch" in host or "google." in host) else url


def research_search(cfg, key: str, lib: ed.Library, http, sleep, n_skin: int, n_hair: int, today: Date) -> tuple[list[dict], list[dict], list[str]]:
    have = sorted({e["name"] for e in lib.skin + lib.hair})
    prompt = (
        f"Today is {today.isoformat()}. Use Google Search to research what is trending in K-beauty RIGHT NOW, separately in "
        "Korea (Olive Young / Hwahae rankings and awards, Korean beauty press) and abroad (US/UK/EU beauty media, Amazon, TikTok).\n"
        f"Then write {n_skin} NEW skincare ingredient entries (about half heat \"korea\", half \"global\") and {n_hair} NEW "
        f"hair/scalp ingredient entries, not already covered: {', '.join(have)}.\n"
        "Also write ONE comparison entry with keys: id (\"ingredients-YYYY-MM\"), year, topic (<=18), title (<=34), subtitle (<=60), "
        "korea (exactly 5 {name<=20, why<=58}), global (exactly 5), both (names on both lists), next (1-3 {name, why}), basis (<=90).\n"
        f"{SCHEMA_NOTE}\nInstead of sources, give source_sites: the 2-4 website domains (like \"allure.com\") of the search "
        "results you used for that entry. Also add examples: 2-3 real products whose name contains the ingredient "
        "[{\"brand\": \"...\", \"product\": \"...\"}].\n"
        f"{RULES}\nReply JSON: {{\"skin\": [...], \"hair\": [...], \"versus\": {{...}}}}"
    )
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 16384}}
    data = _call(key, cfg, body, http, sleep)
    meta = ((data.get("candidates") or [{}])[0]).get("groundingMetadata") or {}
    chunks = [c.get("web", {}) for c in meta.get("groundingChunks", []) if c.get("web")]
    urls = []
    for c in chunks[:40]:
        u = _resolve(c.get("uri", ""), http)
        if u and u not in urls:
            urls.append(u)
    notes = [f"검색어 {len(meta.get('webSearchQueries', []))}개, 확인된 출처 {len(urls)}개"]
    if not urls:
        notes.append("검색 출처를 하나도 확인하지 못함 (검색이 실제로 안 됐을 수 있어요)")
    res = _json(_text(data))

    def attach(e: dict) -> dict:
        sites = [s.lower().removeprefix("www.") for s in e.pop("source_sites", []) or []]
        e["sources"] = [u for u in urls if any(urlparse(u).netloc.lower().removeprefix("www.").endswith(s) for s in sites)][:4]
        return e

    ings = [_normalize(attach(e), "skin", "gemini-search") for e in (res.get("skin") or [])[:n_skin]]
    ings += [_normalize(attach(e), "hair", "gemini-search") for e in (res.get("hair") or [])[:n_hair]]
    versus = []
    if isinstance(res.get("versus"), dict) and res["versus"]:
        v = attach(dict(res["versus"]))
        v.setdefault("id", f"ingredients-{today:%Y-%m}")
        v.setdefault("year", today.year)
        v.setdefault("title", "Hot in Seoul vs. hot abroad")
        v["both"] = [b for b in v.get("both", []) if b]
        versus.append(v)
    return ings, versus, notes


# ---------------------------------------------------------------------------
def _normalize(e: dict, area: str, by: str) -> dict:
    out = {k: e.get(k) for k in ed.ING_KEYS if k in e}
    out["area"] = area
    out["name"] = clean_space(str(out.get("name", "")))
    out["id"] = ed.slug(e.get("id") or out["name"])
    for k in ("full_name", "nickname", "heat_note", "myth", "fact", "hook", "what_it_is", "origin", "when"):
        out[k] = clean_space(str(out.get(k) or ""))
    for k in ("benefits", "best_for", "how_to_use", "pairs_with", "avoid_with", "good_to_know", "keywords", "hashtags", "sources"):
        out[k] = [clean_space(str(x)) for x in (out.get(k) or []) if str(x).strip()]
    out["keywords"] = [k.lower() for k in out["keywords"]]
    out["hashtags"] = [h if h.startswith("#") else "#" + h.replace(" ", "") for h in out["hashtags"]][:4]
    out["examples"] = [{"brand": clean_space(x.get("brand", "")), "product": clean_space(x.get("product", ""))}
                       for x in (e.get("examples") or []) if isinstance(x, dict) and x.get("brand") and x.get("product")][:4]
    try:
        out["hot_since"] = int(out.get("hot_since") or Date.today().year)
    except (TypeError, ValueError):
        out["hot_since"] = Date.today().year
    out["_by"] = by
    return out


def _fetch_catalog(cfg, today: Date, session, sleep) -> list[dict]:
    """No saved bestseller list yet: fetch it now (same rules as the weekly job: robots.txt first)."""
    from .sources import oliveyoung as oy
    try:
        if not oy.robots_allows_display(session):
            return []
        lists = cfg.raw.get("discover", {}).get("catalog_lists", ["Skincare", "Suncare", "Face Masks", "Hair"])
        items = oy.fetch_bestsellers(lists, int(cfg.raw.get("discover", {}).get("catalog_top_n", 100)), session=session, sleep=sleep)
        if items:
            ed.save_catalog(cfg, items, today.isoformat())
        return ed.load_catalog(cfg)
    except Exception as exc:
        warn(f"올리브영 베스트셀러를 가져오지 못했어요: {exc}")
        return []


def last_human_update(root: Path) -> Date | None:
    """Date of the last content/ change that wasn't made by the Gemini job (i.e. Claude or you)."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--invert-grep", "--grep=Gemini", "--",
                              "content/skin.toml", "content/hair.toml", "content/trends.toml"],
                             cwd=root, capture_output=True, text=True, timeout=30).stdout.strip()
        return Date.fromisoformat(out) if out else None
    except Exception:
        return None


def run_research(cfg, today: Date, session=None, sleep=time.sleep, last_update: Date | None | str = "git") -> dict:
    r = cfg.raw.get("research", {})
    http = session or requests
    lib = ed.load_library(cfg)
    catalog = ed.load_catalog(cfg) or _fetch_catalog(cfg, today, session, sleep)
    n_skin, n_hair = int(r.get("max_skin", 6)), int(r.get("max_hair", 3))
    results = {"free": {"entries": [], "versus": [], "notes": []}, "search": {"entries": [], "versus": [], "notes": []}}
    if r.get("free_mode", True) and cfg.gemini_key:
        try:
            ents, notes = research_free(cfg, lib, catalog, http, sleep, n_skin, n_hair)
            results["free"].update(entries=ents, notes=notes)
        except Exception as exc:
            results["free"]["notes"].append(f"실패: {scrub(str(exc), cfg.gemini_key)[:160]}")
    elif r.get("free_mode", True):
        results["free"]["notes"].append("GEMINI_API_KEY 없음")
    search_key = cfg.gemini_search_key
    if r.get("search_mode", True) and search_key:
        try:
            ents, vs, notes = research_search(cfg, search_key, lib, http, sleep, n_skin, n_hair, today)
            results["search"].update(entries=ents, versus=vs, notes=notes)
        except Exception as exc:
            msg = scrub(str(exc), search_key)[:200]
            hint = " (구글 검색은 결제가 켜진 프로젝트의 키가 필요해요)" if any(x in msg for x in ("400", "403", "429", "billing", "not available")) else ""
            results["search"]["notes"].append(f"실패: {msg}{hint}")
    elif r.get("search_mode", True):
        results["search"]["notes"].append("GEMINI_SEARCH_API_KEY 없음 → 구글 검색 조사는 건너뜀")

    # automatic checks
    for mode in results.values():
        for e in mode["entries"]:
            e["_problems"] = ed.check_ingredient({k: v for k, v in e.items() if not k.startswith("_")}, lib, catalog or None)
        for v in mode["versus"]:
            v["_problems"] = ed.check_versus(v, lib)

    stamp = today.strftime("%Y-%m")
    drafts = ed.content_dir(cfg) / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    for name, mode in results.items():
        if not (mode["entries"] or mode["versus"]):
            continue
        blocks = [f"# Gemini ({name}) research drafts, {today.isoformat()}. NOT posted unless merged into content/.\n"]
        for e in mode["entries"]:
            status = "PASS" if not e["_problems"] else "FAIL: " + "; ".join(e["_problems"])
            blocks.append(f"# {status}\n" + ed.toml_block("ingredient", e, ed.ING_KEYS))
        for v in mode["versus"]:
            status = "PASS" if not v["_problems"] else "FAIL: " + "; ".join(v["_problems"])
            blocks.append(f"# {status}\n" + ed.toml_block("versus", v, ed.VS_KEYS))
        (drafts / f"gemini-{name}-{stamp}.toml").write_text("\n".join(blocks), encoding="utf-8")

    # fallback: add passing drafts when nobody else has updated the library for a while
    mode_setting = str(r.get("auto_add", "fallback")).lower()
    last = last_human_update(cfg.root) if last_update == "git" else last_update
    days = (today - last).days if last else None
    wait = int(r.get("fallback_after_days", 40))
    do_add = mode_setting == "always" or (mode_setting == "fallback" and days is not None and days >= wait)
    added = []
    if do_add:
        added = _merge(cfg, lib, results)
    report = _report(results, today, mode_setting, days, wait, added)
    (drafts / f"report-{stamp}.md").write_text(report, encoding="utf-8")
    add_summary(report)
    log(report)
    set_output("commit_message", f"Gemini content auto-add {stamp}" if added else f"Gemini research drafts {stamp}")
    return {"results": results, "added": added, "days_since_update": days}


def _merge(cfg, lib: ed.Library, results: dict) -> list[str]:
    from .state import State
    published = {p["key"] for p in State(cfg.state_file).published}
    seen = {e["name"].lower() for e in lib.skin + lib.hair}
    added = []
    for area, fname, prefix in (("skin", "skin.toml", "ing-"), ("hair", "hair.toml", "hair-")):
        blocks = []
        for mode in ("search", "free"):  # searched drafts first
            for e in results[mode]["entries"]:
                if e["area"] != area or e["_problems"] or e["name"].lower() in seen:
                    continue
                seen.add(e["name"].lower())
                clean = {k: v for k, v in e.items() if not k.startswith("_")}
                blocks.append(ed.toml_block("ingredient", clean, ed.ING_KEYS))
                added.append(f"{area}: {e['name']} ({mode})")
        if blocks:
            ids = {k[len(prefix):] for k in published if k.startswith(prefix)}
            ed.insert_blocks(ed.content_dir(cfg) / fname, "ingredient", blocks, ids)
    vs_blocks = []
    for v in results["search"]["versus"]:
        if not v["_problems"]:
            vs_blocks.append(ed.toml_block("versus", {k: x for k, x in v.items() if not k.startswith("_")}, ed.VS_KEYS))
            added.append(f"versus: {v['id']} (search)")
    if vs_blocks:
        ids = {k[3:] for k in published if k.startswith("vs-")}
        ed.insert_blocks(ed.content_dir(cfg) / "trends.toml", "versus", vs_blocks, ids)
    return added


def _report(results: dict, today: Date, mode: str, days, wait: int, added: list[str]) -> str:
    lines = [f"### 제미나이 조사 {today.isoformat()}", ""]
    for name, label in (("free", "무료 (베스트셀러 + 위키백과 + PubMed)"), ("search", "구글 검색")):
        m = results[name]
        ok = sum(1 for e in m["entries"] if not e["_problems"]) + sum(1 for v in m["versus"] if not v["_problems"])
        total = len(m["entries"]) + len(m["versus"])
        lines.append(f"**{label}**: 초안 {total}개 중 자동 검사 통과 {ok}개")
        for e in m["entries"]:
            lines.append(f"- {'✅' if not e['_problems'] else '❌'} {e['area']} · {e['name']} · 출처 {len(e.get('sources', []))}개"
                         + ("" if not e["_problems"] else f" — {'; '.join(e['_problems'])}"))
        for v in m["versus"]:
            lines.append(f"- {'✅' if not v['_problems'] else '❌'} versus · {v.get('id')}" + ("" if not v["_problems"] else f" — {'; '.join(v['_problems'])}"))
        for n in m["notes"]:
            lines.append(f"- ℹ️ {n}")
        lines.append("")
    since = f"{days}일 전" if days is not None else "기록 없음"
    if added:
        lines.append(f"**자동 추가됨** (마지막 Claude/직접 업데이트 {since}, 기준 {wait}일): " + ", ".join(added))
    else:
        lines.append(f"자동 추가 안 함 (설정 {mode}, 마지막 Claude/직접 업데이트 {since}). 초안은 content/drafts/ 에 있고, "
                     "매달 1일 Claude가 사실 확인해서 비교해요.")
    return "\n".join(lines)
