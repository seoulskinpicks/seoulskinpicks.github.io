"""Topic-based schedule + the newer information series.

Schedule (config.toml [series])
  Every series has a monthly target (per_month), a minimum gap in days between two posts of
  that series (gap) and optionally a fixed weekday (day = "thu"). Each day the bot posts the
  series that is furthest behind its target for this point in the month; fixed-day series go
  first on their day. If a series has nothing to post, the next one in line is tried.

Series added here
  routine  : routine builder by concern (content/routines.toml)
  myth     : myth vs. fact, 4 per post, taken from the ingredient library (myth / fact fields)
  combo    : mix & match cheat sheet, 4 ingredients per post (pairs_with / avoid_with fields)
  season   : Seoul seasons guide (content/seasons.toml), once per season
  words    : Speak K-beauty, Korean beauty words (content/words.toml)
  recap    : last month's Olive Young Global bestsellers, from the weekly snapshots (data/oy_history/)
  industry : what makers and expos are pushing (content/industry.toml, written by the monthly research)
"""
from __future__ import annotations

import calendar
import html
import json
import math
from collections import Counter
from datetime import date as Date
from datetime import timedelta
from pathlib import Path

from .util import warn

SERIES_NAMES = ("skin", "product", "weekly", "hair", "routine", "myth", "combo", "industry", "recap", "history",
                "versus", "season", "words")
NEW_KINDS = ("routine", "myth", "combo", "season", "words", "recap", "industry")
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
GROUP = 4  # myths / combos per post
HISTORY_DIR = "oy_history"


# ---------------------------------------------------------------------------
# schedule
# ---------------------------------------------------------------------------
def series_cfg(cfg) -> dict[str, dict] | None:
    raw = cfg.raw.get("series")
    if not raw:
        return None
    out = {}
    for name, c in raw.items():
        name = str(name).strip().lower()
        if name not in SERIES_NAMES:
            warn(f"config.toml [series] 의 '{name}' 은 모르는 종류예요 (건너뜀)")
            continue
        c = c if isinstance(c, dict) else {"per_month": c}
        day = str(c.get("day", "")).strip().lower()[:3]
        out[name] = {"per_month": float(c.get("per_month", 0) or 0), "gap": int(c.get("gap", 0) or 0),
                     "day": DAYS.get(day)}
    return out


def series_of(post: dict) -> str:
    src = post.get("source", "")
    return "product" if src in ("kbeauty", "tools") else src


def posts_per_day(cfg) -> int:
    try:
        return max(1, int(cfg.raw.get("schedule", {}).get("posts_per_day", 1)))
    except (TypeError, ValueError):
        return 1


def plan_order(cfg, state, today: Date) -> tuple[str, list[str]] | None:
    """(this slot's series, the steps to try in order), or None when [series] isn't set (weekday plan).

    With [schedule] posts_per_day = 2 the monthly targets double (fixed-day series like the Thursday
    top 10 stay once a week) and the minimum gaps halve, so the mix stays the same, just faster."""
    sc = series_cfg(cfg)
    if not sc:
        return None
    ppd = posts_per_day(cfg)
    iso = today.isoformat()
    pubs = [p for p in state.published if p.get("date", "") <= iso]
    today_posts = [series_of(p) for p in pubs if p.get("date") == iso]
    month = today.strftime("%Y-%m")
    count = Counter(series_of(p) for p in pubs if p.get("date", "").startswith(month))
    last: dict[str, Date] = {}
    for p in pubs:
        try:
            d = Date.fromisoformat(p["date"])
        except (KeyError, ValueError):
            continue
        s_ = series_of(p)
        if s_ not in last or d > last[s_]:
            last[s_] = d
    slot = min(len(today_posts), ppd - 1)
    frac = (today.day - 1 + (slot + 1) / ppd) / calendar.monthrange(today.year, today.month)[1]
    fixed, ready, waiting = [], [], []
    for i, (name, c) in enumerate(sc.items()):
        if c["per_month"] <= 0:
            continue
        if c["day"] is not None:
            if today.weekday() == c["day"] and name not in today_posts:
                fixed.append(name)
            continue
        target = c["per_month"] * ppd
        gap = math.ceil(c["gap"] / ppd)
        deficit = target * frac - count[name]
        gap_ok = name not in today_posts and (name not in last or (today - last[name]).days >= gap)
        room = count[name] < math.ceil(target)
        (ready if gap_ok and room else waiting).append((-deficit, i, name))
    order = fixed + [n for *_, n in sorted(ready)] + [n for *_, n in sorted(waiting)]
    if "product" not in order:
        order.append("product")
    skin_total = sum(1 for p in pubs if p.get("source") == "skin")
    steps: list[str] = []
    for name in order:
        if name == "skin":
            pair = ["skin_korea", "skin_global"] if skin_total % 2 == 0 else ["skin_global", "skin_korea"]
            steps += pair + ["skin"]
        else:
            steps.append(name)
    return order[0], list(dict.fromkeys(steps))


def month_summary(cfg, state, today: Date) -> str:
    sc = series_cfg(cfg) or {}
    month = today.strftime("%Y-%m")
    count = Counter(series_of(p) for p in state.published if p.get("date", "").startswith(month))
    ppd = posts_per_day(cfg)
    return " · ".join(f"{n} {count[n]}/{c['per_month'] * (1 if c['day'] is not None else ppd):g}"
                      for n, c in sc.items() if c["per_month"] > 0)


# ---------------------------------------------------------------------------
# topics for the new series
# ---------------------------------------------------------------------------
def _ingredients(lib) -> list[dict]:
    return list(lib.skin) + list(lib.hair)


def _group_used(prefix: str, used: dict) -> dict[str, Date]:
    """ingredient id -> last time it was in a myth / combo post."""
    out: dict[str, Date] = {}
    for key, d in used.items():
        if key.startswith(prefix):
            for ident in key[len(prefix):].split("+"):
                if ident not in out or d > out[ident]:
                    out[ident] = d
    return out


def _pick_group(pool: list[dict], prefix: str, used: dict, today: Date, days: int) -> tuple[list[dict], bool]:
    """Up to GROUP ingredients from one area that haven't been in this series yet
    (or, once all have, the ones featured longest ago)."""
    seen = _group_used(prefix, used)
    fresh = [e for e in pool if e["id"] not in seen]
    repeat = False
    if len(fresh) < 3:
        fresh = sorted((e for e in pool if e["id"] in seen and (today - seen[e["id"]]).days >= days),
                       key=lambda e: seen[e["id"]])
        repeat = True
    if not fresh:
        return [], False
    area = fresh[0].get("area", "skin")
    group = [e for e in fresh if e.get("area", "skin") == area][:GROUP]
    if len(group) < 3:
        group = fresh[:GROUP]
    return (group, repeat) if len(group) >= 3 else ([], False)


def season_for(lib, today: Date) -> tuple[dict, int, Date] | None:
    for s in lib.seasons:
        months = [int(m) for m in s.get("months", [])]
        if today.month in months:
            first = months[0]
            year = today.year - 1 if first > today.month else today.year
            return s, year, Date(year, first, 1)
    return None


def next_topic(kind: str, lib, state, today: Date, cfg, used: dict):
    from .editorial import Topic
    days = int(cfg.raw.get("schedule", {}).get("repeat_after_days", 120)) if cfg is not None else 120
    if kind == "myth":
        pool = [e for e in _ingredients(lib) if e.get("myth") and e.get("fact")]
        group, repeat = _pick_group(pool, "my-", used, today, days)
        if not group:
            return None
        items = [{k: e.get(k) for k in ("id", "name", "area", "myth", "fact", "sources")} for e in group]
        return Topic("myth", "my-" + "+".join(e["id"] for e in group), {"items": items}, repeat=repeat)
    if kind == "combo":
        pool = [e for e in _ingredients(lib) if e.get("pairs_with")]
        pool.sort(key=lambda e: (e.get("area", "skin") != "skin", not e.get("avoid_with")))
        group, repeat = _pick_group(pool, "cb-", used, today, days)
        if not group:
            return None
        items = [{"id": e["id"], "name": e["name"], "area": e.get("area", "skin"), "pairs": e.get("pairs_with", [])[:3],
                  "benefit": (e.get("benefits") or [""])[0],
                  "avoid": e.get("avoid_with", [])[:2], "when": e.get("when", ""), "sources": e.get("sources", [])[:2]}
                 for e in group]
        return Topic("combo", "cb-" + "+".join(e["id"] for e in group), {"items": items}, repeat=repeat)
    if kind == "season":
        found = season_for(lib, today)
        if not found:
            return None
        s, year, start = found
        key = f"ss-{s['id']}-{year}"
        if key in used or (today - start).days > 60:
            return None
        return Topic("season", key, dict(s, year=year))
    if kind == "recap":
        data = recap_data(cfg, today)
        if not data or f"rc-{data['month']}" in used:
            return None
        return Topic("recap", f"rc-{data['month']}", data)
    if kind == "industry":
        issues = sorted((i for i in lib.industry if i.get("items")), key=lambda i: str(i.get("date", "")), reverse=True)
        if not issues:
            return None
        top = issues[0]
        try:
            age = (today - Date.fromisoformat(str(top["date"]))).days
        except (KeyError, ValueError):
            return None
        key = f"in-{top['id']}"
        if key in used or age > 45 or age < 0:
            return None
        return Topic("industry", key, top)
    return None


def find_topic(key: str, lib, post: dict | None = None):
    """Rebuild a topic from a state key (for the article pages)."""
    from .editorial import Topic
    if post and post.get("data") and key[:3] in ("my-", "cb-", "rc-"):
        kind = {"my-": "myth", "cb-": "combo", "rc-": "recap"}[key[:3]]
        return Topic(kind, key, post["data"])
    if key.startswith("rt-"):
        r = next((r for r in lib.routines if f"rt-{r['id']}" == key), None)
        return Topic("routine", key, r) if r else None
    if key.startswith("kw-"):
        w = next((w for w in lib.words if f"kw-{w['id']}" == key), None)
        return Topic("words", key, w) if w else None
    if key.startswith("ss-"):
        sid, _, year = key[3:].rpartition("-")
        s = next((s for s in lib.seasons if s["id"] == sid), None)
        return Topic("season", key, dict(s, year=int(year))) if s and year.isdigit() else None
    if key.startswith("in-"):
        i = next((i for i in lib.industry if f"in-{i['id']}" == key), None)
        return Topic("industry", key, i) if i else None
    return None


def title_of(topic) -> str:
    d = topic.data
    if topic.kind == "routine":
        return f"{d['title']}: {d['concern'].lower()}"
    if topic.kind == "myth":
        return "K-beauty myths vs. facts: " + ", ".join(i["name"] for i in d["items"])
    if topic.kind == "combo":
        return "Mix & match: " + ", ".join(i["name"] for i in d["items"])
    if topic.kind == "season":
        return d["title"]
    if topic.kind == "words":
        return f"Speak K-beauty: {d['title'].lower()}"
    if topic.kind == "recap":
        return f"{d['label']}'s K-beauty bestsellers"
    if topic.kind == "industry":
        return f"{d.get('title', 'Industry watch')} ({month_label(d)})"
    return topic.key


def month_label(d: dict) -> str:
    try:
        dt = Date.fromisoformat(str(d.get("date") or (d["id"] + "-01")))
        return f"{dt:%B %Y}"
    except (KeyError, ValueError):
        return str(d.get("id", ""))


# ---------------------------------------------------------------------------
# monthly bestseller recap (weekly snapshots of the Olive Young Global lists)
# ---------------------------------------------------------------------------
def history_dir(cfg) -> Path:
    return cfg.root / "data" / HISTORY_DIR


def save_snapshot(cfg, items: list[dict], today: str, top: int = 30, keep_days: int = 400) -> Path:
    keep = ("brand", "product", "prdt_no", "url", "list", "rank", "store_rating", "review_count")
    rows = [{k: it.get(k) for k in keep} for it in items if (it.get("rank") or 999) <= top]
    d = history_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{today}.json"
    path.write_text(json.dumps({"date": today, "items": rows}, ensure_ascii=False, indent=0), encoding="utf-8")
    cutoff = (Date.fromisoformat(today) - timedelta(days=keep_days)).isoformat()
    for old in d.glob("*.json"):
        if old.stem < cutoff:
            old.unlink()
    return path


def recap_data(cfg, today: Date, lst: str = "Skincare") -> dict | None:
    """Last month's recap, posted in the first 10 days of the month (needs ≥ 2 weekly snapshots)."""
    if cfg is None or today.day > 10:
        return None
    prev_end = today.replace(day=1) - timedelta(days=1)
    month = prev_end.strftime("%Y-%m")
    snaps = []
    for p in sorted(history_dir(cfg).glob(f"{month}-*.json")):
        try:
            snaps.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    if len(snaps) < 2:
        return None
    stats: dict[str, dict] = {}
    for s in snaps:
        for it in s.get("items", []):
            if it.get("list") != lst or not it.get("rank"):
                continue
            k = it.get("prdt_no") or f"{it['brand']}|{it['product']}"
            st = stats.setdefault(k, dict(it, ranks=[], top10=0))
            st.update({x: it.get(x) for x in ("store_rating", "review_count", "url")})
            st["ranks"].append((s["date"], it["rank"]))
            st["top10"] += it["rank"] <= 10
    if not stats:
        return None
    weeks = len(snaps)
    for st in stats.values():
        rs = [r for _, r in st["ranks"]]
        st["avg"] = sum(rs) / len(rs) + (weeks - len(rs)) * 10  # missing weeks count against it
        st["best"] = min(rs)
    top = sorted(stats.values(), key=lambda s: (-s["top10"], s["avg"]))[:5]
    first, last = snaps[0]["date"], snaps[-1]["date"]
    climbs = []
    for st in stats.values():
        r0 = next((r for d, r in st["ranks"] if d == first), None)
        r1 = next((r for d, r in st["ranks"] if d == last), None)
        if r1 and r1 <= 15:
            climbs.append(((r0 or 31) - r1, st, r0, r1))
    climbs.sort(key=lambda x: -x[0])
    climber = None
    if climbs and climbs[0][0] >= 3:
        _, st, r0, r1 = climbs[0]
        if st not in top[:3]:
            climber = {"brand": st["brand"], "product": st["product"], "url": st.get("url"), "prdt_no": st.get("prdt_no"),
                       "from": r0, "to": r1}
    slim = lambda s: {"brand": s["brand"], "product": s["product"], "url": s.get("url"), "prdt_no": s.get("prdt_no"),  # noqa: E731
                      "top10": s["top10"], "best": s["best"], "store_rating": s.get("store_rating"),
                      "review_count": s.get("review_count")}
    return {"month": month, "label": f"{prev_end:%B}", "year": prev_end.year, "weeks": weeks, "list": lst,
            "top": [slim(s) for s in top], "climber": climber}


# ---------------------------------------------------------------------------
# products for the new series
# ---------------------------------------------------------------------------
def products(topic, cfg, catalog: list[dict], lib=None) -> list[dict]:
    from .discover import _oy_link
    from .editorial import match_catalog
    d = topic.data

    def row(it):
        link = _oy_link(cfg, {"url": it["url"], "prdt_no": it.get("prdt_no", "")}) if it.get("url") else ""
        return {"brand": it["brand"], "name": it["product"], "links": {"oliveyoung": link} if link else {},
                "rating": it.get("store_rating"), "reviews": it.get("review_count"), "from": "catalog"}

    if topic.kind == "recap":
        out = [dict(row(it), top10=it.get("top10"), best=it.get("best")) for it in d.get("top", [])]
        if d.get("climber"):
            out.append(dict(row(d["climber"]), climber=True))
        return out
    if topic.kind not in ("routine", "season") or lib is None:
        return []
    ids = d.get("key", [])
    entries = [e for e in list(lib.skin) + list(lib.hair) if e["id"] in ids]
    entries.sort(key=lambda e: ids.index(e["id"]))
    out, seen = [], set()
    for e in entries:
        for it in match_catalog(e, catalog, limit=3):
            if (it["brand"], it["product"]) in seen:
                continue
            seen.add((it["brand"], it["product"]))
            out.append(dict(row(it), for_ingredient=e["name"]))
            break
    return out[:3]


# ---------------------------------------------------------------------------
# captions
# ---------------------------------------------------------------------------
def copy_lines(topic, number: int, products_: list[dict], lib=None) -> tuple[str, list[str], list[str]]:
    """(hook, caption body lines, bullets for the link page)."""
    d = topic.data
    linked = any(p["links"] for p in products_)
    shop_title = f"🛍 Where to find them (links in bio → No.{number})" if linked else "🛍 Where you'll find them"
    if topic.kind == "routine":
        hook = d["hook"]
        names = key_names(d, lib)
        lines = [f"{hook} ✨", f"Routine builder · {d['concern']}", "", d["why"], "", "☀️ Morning"]
        lines += [f"{i}. {s}" for i, s in enumerate(d["am"], 1)]
        lines += ["", "🌙 Night"] + [f"{i}. {s}" for i, s in enumerate(d["pm"], 1)]
        if names:
            lines += ["", f"🧪 Key ingredients: {', '.join(names)}"]
        lines += ["", "💡 Tips"] + [f"• {t}" for t in d.get("tips", [])]
        if products_:
            lines += ["", shop_title] + [f"• {p['brand']} {p['name']}" + (f" ({p['for_ingredient']})" if p.get("for_ingredient") else "")
                                         for p in products_]
        lines += ["", "Save it, then tell me your concern for the next routine 👇"]
        bullets = [f"For: {d['concern']}"] + ([f"Key ingredients: {', '.join(names)}"] if names else []) + d.get("tips", [])[:1]
    elif topic.kind == "myth":
        items = d["items"]
        hook = f"{len(items)} K-beauty myths, fact-checked"
        lines = [f"{hook} 🔍", "Myth or fact? Swipe before you read the answers.", ""]
        for it in items:
            lines += [f"🧪 {it['name']}", f"❌ Myth: {it['myth']}", f"✅ Fact: {it['fact']}", ""]
        lines += ["Which one did you believe? Tell me below 👇"]
        bullets = [f"{it['name']}: {it['fact']}" for it in items[:3]]
    elif topic.kind == "combo":
        items = d["items"]
        hook = "Mix & match: what to layer, what to space out"
        lines = [f"{hook} 🧩", "A quick pairing cheat sheet from our Ingredient 101 notes.", ""]
        for it in items:
            lines.append(f"🧪 {it['name']} ({it['when']})" if it.get("when") else f"🧪 {it['name']}")
            lines.append(f"✅ Pairs well with: {', '.join(it['pairs'])}")
            if it.get("avoid"):
                lines.append(f"⏸ Space out from: {', '.join(it['avoid'])}")
            lines.append("")
        lines += ["New to an active? Add one product at a time and patch test first.",
                  "What combo do you want checked next? 👇"]
        bullets = [f"{it['name']} + {it['pairs'][0]}" for it in items[:3] if it.get("pairs")]
    elif topic.kind == "season":
        hook = d["hook"]
        names = key_names(d, lib)
        lines = [f"{d['title']}: {hook.lower()} 🌦", "", "🌡 What the season does"] + [f"• {w}" for w in d["weather"]]
        lines += ["", "🧴 Skin swaps"] + [f"• {s}" for s in d["skin"]]
        lines += ["", "💇‍♀️ Hair & scalp"] + [f"• {s}" for s in d["hair"]]
        if names:
            lines += ["", f"🧪 Ingredients to reach for: {', '.join(names)}"]
        if products_:
            lines += ["", shop_title] + [f"• {p['brand']} {p['name']}" for p in products_]
        lines += ["", "What's the weather doing to your skin right now? 👇"]
        bullets = d["skin"][:3]
    elif topic.kind == "words":
        ws = d["words"]
        hook = d["hook"]
        lines = [f"Speak K-beauty · {d['title']} 🇰🇷", hook, ""]
        for w in ws:
            lines += [f"{w['ko']} ({w['rom']}): {w['en']}", w["note"], ""]
        lines += ["Which word will you use first? 👇", "Save this for your next Olive Young trip."]
        bullets = [f"{w['ko']} ({w['rom']}): {w['en']}" for w in ws[:3]]
    elif topic.kind == "recap":
        hook = f"{d['label']}'s most-bought K-beauty, all month"
        lines = [f"{hook} 🏆", f"Olive Young Global {d['list'].lower()} bestsellers across {d['weeks']} weekly lists.", ""]
        top = [p for p in products_ if not p.get("climber")]
        lines += [f"{i}. {p['brand']} {p['name']} · top 10 for {p.get('top10', 0)} of {d['weeks']} weeks"
                  for i, p in enumerate(top, 1)]
        if d.get("climber"):
            c = d["climber"]
            frm = f"#{c['from']}" if c.get("from") else "outside the top 30"
            lines += ["", f"🚀 Biggest climber: {c['brand']} {c['product']} ({frm} → #{c['to']})"]
        if linked:
            lines += ["", f"🛍 Links in bio → No.{number}"]
        lines += ["", "Did any of these make it into your cart? 👇"]
        bullets = [f"{p['brand']} {p['name']}" for p in top[:3]]
    else:  # industry
        hook = d.get("hook") or "What K-beauty makers are betting on next"
        lines = [f"{hook} 🔭", f"Industry watch · {month_label(d)}",
                 "What manufacturers, beauty expos and trade press are pushing before it hits shelves.", ""]
        for it in d["items"]:
            lines += [f"🧪 {it['name']}", f"📍 {it['signal']}", it["why"], ""]
        lines += ["Early signals, not guarantees: some of these will stay in the lab.", "Which one would you try? 👇"]
        bullets = [f"{it['name']}: {it['signal']}" for it in d["items"][:3]]
    return hook, lines, bullets


def key_names(d: dict, lib) -> list[str]:
    if lib is None:
        return []
    by_id = {e["id"]: e["name"] for e in list(lib.skin) + list(lib.hair)}
    return [by_id[i] for i in d.get("key", []) if i in by_id]


def sources(topic, lib) -> list[str]:
    d = topic.data
    if topic.kind in ("myth", "combo"):
        return list(dict.fromkeys(s for it in d["items"] for s in (it.get("sources") or [])[:2]))[:8]
    if topic.kind in ("routine", "season") and lib is not None:
        ids = d.get("key", [])
        return list(dict.fromkeys(s for e in list(lib.skin) + list(lib.hair) if e["id"] in ids
                                  for s in e.get("sources", [])[:2]))[:8]
    return list(d.get("sources", []))


# ---------------------------------------------------------------------------
# article pages (/p/NNN.html)
# ---------------------------------------------------------------------------
def article(topic, lib, products_html: str, not_advice: str) -> str:
    esc = html.escape
    d = topic.data
    ul = lambda items: "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>"  # noqa: E731
    ol = lambda items: "<ol>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ol>"  # noqa: E731
    out = []
    if topic.kind == "routine":
        out.append(f"<p class=\"lead\">{esc(d['why'])}</p>")
        out.append("<h2>Morning</h2>" + ol(d["am"]) + "<h2>Night</h2>" + ol(d["pm"]))
        names = key_names(d, lib)
        if names:
            out.append(f"<p><b>Key ingredients:</b> {esc(', '.join(names))}</p>")
        out.append("<h2>Tips</h2>" + ul(d.get("tips", [])))
    elif topic.kind == "myth":
        for it in d["items"]:
            out.append(f"<h2>{esc(it['name'])}</h2><p><b>Myth:</b> {esc(it['myth'])}<br><b>Fact:</b> {esc(it['fact'])}</p>")
    elif topic.kind == "combo":
        for it in d["items"]:
            out.append(f"<h2>{esc(it['name'])}</h2><p><b>Pairs well with:</b> {esc(', '.join(it['pairs']))}"
                       + (f"<br><b>Space out from:</b> {esc(', '.join(it['avoid']))}" if it.get("avoid") else "")
                       + (f"<br><b>When:</b> {esc(it['when'])}" if it.get("when") else "") + "</p>")
    elif topic.kind == "season":
        out.append("<h2>What the season does</h2>" + ul(d["weather"]))
        out.append("<h2>Skin swaps</h2>" + ul(d["skin"]) + "<h2>Hair &amp; scalp</h2>" + ul(d["hair"]))
    elif topic.kind == "words":
        for w in d["words"]:
            out.append(f"<h2>{esc(w['ko'])} <small>({esc(w['rom'])})</small></h2><p><b>{esc(w['en'])}</b>. {esc(w['note'])}</p>")
    elif topic.kind == "recap":
        out.append(f"<p class=\"lead\">Olive Young Global {esc(d['list'].lower())} bestsellers across "
                   f"{d['weeks']} weekly lists in {esc(d['label'])} {d['year']}.</p>")
        out.append("<ol>" + "".join(f"<li><b>{esc(p['brand'])}</b> {esc(p['product'])}: top 10 for {p['top10']} of "
                                    f"{d['weeks']} weeks (best #{p['best']})</li>" for p in d["top"]) + "</ol>")
        if d.get("climber"):
            c = d["climber"]
            out.append(f"<p><b>Biggest climber:</b> {esc(c['brand'])} {esc(c['product'])} "
                       f"({'#' + str(c['from']) if c.get('from') else 'outside the top 30'} → #{c['to']})</p>")
    elif topic.kind == "industry":
        out.append("<p class=\"lead\">What manufacturers, beauty expos and trade press are pushing before it hits shelves.</p>")
        for it in d["items"]:
            out.append(f"<h2>{esc(it['name'])}</h2><p><i>{esc(it['signal'])}</i><br>{esc(it['why'])}</p>")
        out.append("<p class=\"note\">Early signals, not guarantees.</p>")
    if topic.kind in ("routine", "myth", "combo", "season"):
        out.append(f"<p class=\"note\">{esc(not_advice)}</p>")
    if products_html:
        out.append(products_html)
    return "\n".join(out)


TAGS = {
    "routine": ["#skincareroutine", "#kbeautyroutine", "#koreanskincareroutine"],
    "myth": ["#skincaremyths", "#skincarefacts", "#skincarescience"],
    "combo": ["#skincarelayering", "#skincaretips", "#skincareingredients"],
    "season": ["#seasonalskincare", "#seoullife", "#skincaretips"],
    "words": ["#learnkorean", "#koreanwords", "#kbeautytips"],
    "recap": ["#kbeautybestsellers", "#oliveyoungglobal", "#kbeautyfavorites"],
    "industry": ["#kbeautytrends", "#beautyindustry", "#cosmeticsindustry"],
}
