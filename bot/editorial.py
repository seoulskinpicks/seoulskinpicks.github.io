"""Information posts: Ingredient 101 (skin / hair), Seoul vs. abroad, and K-beauty history.

The facts come from content/*.toml, which was researched and sourced by hand, so these
posts never depend on an AI making things up. Products for the "Where to find it" card are
matched from the Olive Young Global bestseller lists that the weekly job saves
(data/oy_catalog.json); if none match, the library's example products are shown without links.

Which kind goes out on which weekday is set in config.toml [schedule] weekly.
"""
from __future__ import annotations

import html
import json
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date as Date
from pathlib import Path

from .util import clean_space, log, warn

ROOT = Path(__file__).resolve().parent.parent

NEW_KINDS = ("routine", "myth", "combo", "season", "words", "recap", "industry", "spotlight")
INFO_KINDS = ("skin", "hair", "versus", "history", "weekly") + NEW_KINDS
PLAN_TOKENS = ("product", "skin", "skin_korea", "skin_global", "hair", "versus", "history", "weekly") + NEW_KINDS
DEFAULT_WEEKLY = ["skin_korea", "product", "hair", "weekly", "skin_global", "history", "product"]
FALLBACK = {
    "product": ["product", "skin", "hair", "history", "versus"],
    "skin": ["skin", "hair", "history", "versus", "product"],
    "skin_korea": ["skin_korea", "skin", "hair", "history", "versus", "product"],
    "skin_global": ["skin_global", "skin", "hair", "history", "versus", "product"],
    "hair": ["hair", "skin", "history", "versus", "product"],
    "versus": ["versus", "skin", "hair", "history", "product"],
    "history": ["history", "skin", "hair", "versus", "product"],
    "weekly": ["weekly", "versus", "skin", "hair", "history", "product"],
    **{k: [k, "skin", "hair", "product"] for k in NEW_KINDS},
}
KIND_LABEL = {"skin": "Ingredient 101", "hair": "Hair & scalp 101", "versus": "Seoul vs. abroad",
              "history": "K-beauty history", "weekly": "This week in K-beauty", "routine": "Routine builder",
              "myth": "Myth vs. fact", "combo": "Mix & match", "season": "Seoul seasons", "words": "Speak K-beauty",
              "recap": "Monthly bestsellers", "industry": "Industry watch", "spotlight": "Around the world"}
KIND_KO = {"product": "제품 픽", "skin": "피부 성분 101", "skin_korea": "피부 성분 101 (한국에서 뜨는 것)",
           "skin_global": "피부 성분 101 (해외에서 뜨는 것)", "hair": "모발·두피 성분 101",
           "versus": "서울 vs 해외", "history": "K뷰티 연도별 변화", "weekly": "이번 주 K뷰티 TOP",
           "routine": "고민별 루틴", "myth": "오해 vs 사실", "combo": "같이 써도 될까", "season": "서울 계절 가이드",
           "words": "K뷰티 단어", "recap": "지난달 베스트셀러", "industry": "업계가 미는 성분",
           "spotlight": "일본·미국 화제 / 새 특허·원료"}
HEAT_LABEL = {"korea": "Hot in Korea", "global": "Trending abroad", "both": "Hot in Korea & abroad"}
PREFIX = {"skin": "ing-", "hair": "hair-", "versus": "vs-"}

SKIN_LISTS = {"Skincare", "Suncare", "Face Masks"}
HAIR_LISTS = {"Hair"}
CATALOG_NAME = "oy_catalog.json"
NOT_ADVICE = "Info only, not medical advice. Patch test new products."


# ---------------------------------------------------------------------------
# library
# ---------------------------------------------------------------------------
@dataclass
class Library:
    skin: list[dict] = field(default_factory=list)
    hair: list[dict] = field(default_factory=list)
    years: list[dict] = field(default_factory=list)
    versus: list[dict] = field(default_factory=list)
    routines: list[dict] = field(default_factory=list)
    seasons: list[dict] = field(default_factory=list)
    words: list[dict] = field(default_factory=list)
    industry: list[dict] = field(default_factory=list)
    spotlight: list[dict] = field(default_factory=list)

    def ingredients(self, area: str) -> list[dict]:
        return self.hair if area == "hair" else self.skin


def content_dir(cfg) -> Path:
    d = cfg.raw.get("editorial", {}).get("content_dir")
    return Path(d) if d else ROOT / "content"


def load_library(cfg) -> Library:
    base = content_dir(cfg)

    def read(name: str) -> dict:
        path = base / name
        if not path.exists():
            return {}
        try:
            with open(path, "rb") as fh:
                return tomllib.load(fh)
        except Exception as exc:  # a typo in the file shouldn't stop product posts
            warn(f"{path.name} 을 읽지 못했어요 (정보 게시물은 건너뛰어요): {exc}")
            return {}

    trends = read("trends.toml")
    return Library(
        skin=read("skin.toml").get("ingredient", []),
        hair=read("hair.toml").get("ingredient", []),
        years=sorted(trends.get("year", []), key=lambda y: int(y["year"])),
        versus=trends.get("versus", []),
        routines=read("routines.toml").get("routine", []),
        seasons=read("seasons.toml").get("season", []),
        words=read("words.toml").get("set", []),
        industry=read("industry.toml").get("issue", []),
        spotlight=read("spotlight.toml").get("issue", []),
    )


# ---------------------------------------------------------------------------
# what to post today
# ---------------------------------------------------------------------------
@dataclass
class Topic:
    kind: str            # skin | hair | versus | history
    key: str             # state key: ing-pdrn, hair-rosemary, vs-sun-care, yr-2017, tl-overview
    data: dict
    variant: str = ""    # history: "year" | "timeline"
    repeat: bool = False

    @property
    def title(self) -> str:
        if self.kind in ("skin", "hair"):
            return self.data["name"]
        if self.kind == "versus":
            return f"Seoul vs. abroad: {self.data['topic']} ({self.data['year']})"
        if self.variant == "timeline":
            first, last = self.data["years"][0]["year"], self.data["years"][-1]["year"]
            return f"K-beauty through the years, {first}–{last}"
        if self.kind == "weekly":
            return f"This week in K-beauty ({week_label(self.data)})"
        if self.kind in NEW_KINDS:
            from .series import title_of
            return title_of(self)
        return f"{self.data['year']}: {self.data['headline']}"


def week_label(d: dict) -> str:
    a, b = Date.fromisoformat(d["week_start"]), Date.fromisoformat(d["week_end"])
    return f"{a:%b} {a.day}–{b.day}" if a.month == b.month else f"{a:%b} {a.day} – {b:%b} {b.day}"


def plan_for(cfg, today: Date) -> str:
    weekly = cfg.raw.get("schedule", {}).get("weekly") or DEFAULT_WEEKLY
    token = str(weekly[today.weekday() % len(weekly)]).strip().lower()
    if token not in PLAN_TOKENS:
        warn(f"config.toml [schedule] weekly 의 '{token}' 은 모르는 종류예요 → 제품 픽으로 올려요")
        return "product"
    return token


def fallback_order(plan: str) -> list[str]:
    return FALLBACK.get(plan, FALLBACK["product"])


def all_topics(kind: str, lib: Library) -> list[Topic]:
    if kind in ("skin", "hair"):
        return [Topic(kind, PREFIX[kind] + e["id"], e) for e in lib.ingredients(kind)]
    if kind == "versus":
        return [Topic(kind, PREFIX[kind] + e["id"], e) for e in lib.versus]
    if kind == "history":
        out = []
        if len(lib.years) >= 3:
            out.append(Topic(kind, "tl-overview", {"years": lib.years}, variant="timeline"))
        out += [Topic(kind, f"yr-{y['year']}", y, variant="year") for y in lib.years]
        return out
    if kind == "routine":
        return [Topic(kind, f"rt-{r['id']}", r) for r in lib.routines if r.get("am") and r.get("pm")]
    if kind == "words":
        return [Topic(kind, f"kw-{w['id']}", w) for w in lib.words if len(w.get("words", [])) >= 2]
    return []


def last_used(state) -> dict[str, Date]:
    out: dict[str, Date] = {}
    for p in state.published:
        try:
            d = Date.fromisoformat(p.get("date", ""))
        except ValueError:
            continue
        if p["key"] not in out or d > out[p["key"]]:
            out[p["key"]] = d
    return out


def next_topic(token: str, lib: Library, state, today: Date, cfg) -> Topic | None:
    """First unused topic in library order; once all are used, the one used longest ago
    (if it was more than [schedule] repeat_after_days ago)."""
    kind = token.split("_")[0]
    used = last_used(state)
    if kind == "weekly":
        return weekly_topic(cfg, today, used)
    if kind in ("myth", "combo", "season", "recap", "industry", "spotlight"):
        from . import series
        return series.next_topic(kind, lib, state, today, cfg, used)
    heat = {"skin_korea": {"korea", "both"}, "skin_global": {"global", "both"}}.get(token)
    topics = [t for t in all_topics(kind, lib) if not heat or t.data.get("heat") in heat]
    fresh = trend_order([t for t in topics if t.key not in used], token, cfg)
    if fresh:
        return fresh[0]
    days = int(cfg.raw.get("schedule", {}).get("repeat_after_days", 120))
    old = sorted((t for t in topics if (today - used[t.key]).days >= days), key=lambda t: used[t.key])
    if old:
        old[0].repeat = True
        return old[0]
    return None


def weekly_topic(cfg, today: Date, used: dict) -> Topic | None:
    from . import weekly
    data = weekly.latest(cfg, today)
    if not data or not (data.get("korea") or data.get("products")):
        return None
    key = f"wk-{data['week_end']}"
    if key in used:
        return None
    return Topic("weekly", key, data)


def weekly_spotlight(d: dict, lib: Library) -> dict | None:
    """Biggest riser in Korea this week (among reasonably searched terms), with its library explanation."""
    rows = [r for r in d.get("korea", []) if (r.get("index") or 0) >= 10 and r.get("change") is not None]
    if not rows:
        return None
    r = max(rows, key=lambda x: x["change"])
    if r["change"] <= 0:
        return None
    entry = next((e for e in lib.skin + lib.hair if e["id"] == r["id"]), None)
    sp = {"id": r["id"], "name": r["name"], "change": r["change"]}
    if entry:
        sp.update(what_it_is=entry["what_it_is"], benefits=entry["benefits"][:2],
                  more="Full guide coming in our Ingredient 101 series")
    return sp


def trend_order(topics: list[Topic], token: str, cfg) -> list[Topic]:
    """Put this week's hot ingredients first (Korea: Naver search; abroad: Olive Young Global bestsellers)."""
    if not topics or cfg is None:
        return topics
    try:
        if token in ("skin_korea", "hair"):
            from .weekly import korea_scores
            scores = korea_scores(cfg)
        elif token == "skin_global":
            cat = load_catalog(cfg)
            scores = {t.data["id"]: sum(1.0 / (c.get("rank") or 100) for c in match_catalog(t.data, cat, limit=20, min_rating=0, min_reviews=0))
                      for t in topics} if cat else {}
        else:
            scores = {}
    except Exception:
        scores = {}
    if not any(scores.get(t.data.get("id")) for t in topics):
        return topics
    order = {id(t): i for i, t in enumerate(topics)}
    return sorted(topics, key=lambda t: (-(scores.get(t.data.get("id")) or 0), order[id(t)]))


def remaining(lib: Library, state) -> dict[str, int]:
    used = last_used(state)
    out = {k: sum(1 for t in all_topics(k, lib) if t.key not in used)
           for k in ("skin", "hair", "versus", "history", "routine", "words")}
    from .series import _group_used
    for kind, prefix, field_ in (("myth", "my-", "myth"), ("combo", "cb-", "pairs_with")):
        seen = _group_used(prefix, used)
        out[kind] = sum(1 for e in lib.skin + lib.hair if e.get(field_) and e["id"] not in seen)
    return out


# ---------------------------------------------------------------------------
# products for ingredient posts
# ---------------------------------------------------------------------------
def catalog_path(cfg) -> Path:
    return cfg.root / "data" / CATALOG_NAME


def load_catalog(cfg) -> list[dict]:
    path = catalog_path(cfg)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("items", [])
    except Exception as exc:
        warn(f"{CATALOG_NAME} 을 읽지 못했어요: {exc}")
        return []


def save_catalog(cfg, items: list[dict], today: str) -> Path:
    keep = ("brand", "product", "prdt_no", "url", "list", "rank", "store_rating", "review_count")
    path = catalog_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = {}
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            if prev.get("updated") != today:
                old = {(o.get("list"), o.get("prdt_no")): o.get("rank") for o in prev.get("items", [])}
            else:  # same day re-run: keep the earlier comparison
                old = {(o.get("list"), o.get("prdt_no")): o.get("prev_rank") for o in prev.get("items", [])}
        except Exception:
            old = {}
    rows = []
    for it in items:
        row = {k: it.get(k) for k in keep}
        row["prev_rank"] = old.get((it.get("list"), it.get("prdt_no")))
        rows.append(row)
    data = {"updated": today, "source": "Olive Young Global bestsellers", "items": rows}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    return path


def _pattern(keyword: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(keyword.lower().strip()) + r"(?:s|es)?(?![a-z0-9])")


def mentions(entry: dict, text: str) -> bool:
    text = (text or "").lower()
    return any(_pattern(k).search(text) for k in entry.get("keywords", []) if k.strip())


def match_catalog(entry: dict, catalog: list[dict], limit: int = 3, min_rating: float = 4.5,
                  min_reviews: int = 20) -> list[dict]:
    lists = HAIR_LISTS if entry.get("area") == "hair" else SKIN_LISTS
    seen, hits = set(), []
    for it in catalog:
        if it.get("list") not in lists or not it.get("url"):
            continue
        if (it.get("store_rating") or 0) < min_rating or (it.get("review_count") or 0) < min_reviews:
            continue
        ident = (it.get("brand", "").lower(), it.get("product", "").lower())
        if ident in seen or not mentions(entry, f"{it.get('brand', '')} {it.get('product', '')}"):
            continue
        seen.add(ident)
        hits.append(it)
    hits.sort(key=lambda it: (-(it.get("review_count") or 0), it.get("rank") or 999))
    picked, brands = [], set()
    for it in hits:  # different brands first
        if it["brand"].lower() not in brands:
            picked.append(it)
            brands.add(it["brand"].lower())
    for it in hits:
        if len(picked) >= limit:
            break
        if it not in picked:
            picked.append(it)
    return picked[:limit]


def find_products(topic: Topic, cfg, catalog: list[dict], ali_client=None, lib: Library | None = None) -> list[dict]:
    from .discover import _oy_link
    if topic.kind == "weekly":
        rows = topic.data.get("products", [])[:10]
        if not any(c.get("prev_rank") for c in rows):  # first list ever: no "last week" to compare with
            rows = [dict(c, prev_rank=c.get("rank")) for c in rows]
        return [{"brand": c["brand"], "name": c["product"],
                 "links": {"oliveyoung": _oy_link(cfg, {"url": c["url"], "prdt_no": c.get("prdt_no", "")})} if c.get("url") else {},
                 "rating": c.get("store_rating"), "reviews": c.get("review_count"), "rank": c.get("rank"),
                 "prev_rank": c.get("prev_rank"), "from": "catalog"} for c in rows]
    if topic.kind in NEW_KINDS:
        from . import series
        return series.products(topic, cfg, catalog, lib)
    if topic.kind not in ("skin", "hair"):
        return []

    items = match_catalog(topic.data, catalog)
    products = [{
        "brand": it["brand"], "name": it["product"],
        "links": {"oliveyoung": _oy_link(cfg, {"url": it["url"], "prdt_no": it.get("prdt_no", "")})},
        "rating": it.get("store_rating"), "reviews": it.get("review_count"), "from": "catalog",
    } for it in items]
    if not products:
        products = [{"brand": e["brand"], "name": e["product"], "links": {}, "rating": None, "reviews": None,
                     "from": "example"} for e in topic.data.get("examples", [])[:3]]
    client = ali_client
    if client is None and cfg.ali_keys:
        from .sources.ali import AliClient
        client = AliClient(*cfg.ali_keys)
    if client is not None:
        from .sources import Candidate
        from .sources.ali import auto_find
        for p in products:
            cand = Candidate(source="kbeauty", key="", brand=p["brand"], name=p["name"], link="", category="other")
            try:
                if auto_find(cand, client, cfg.ali) and cand.ali_link:
                    p["links"]["aliexpress"] = cand.ali_link  # affiliate link from the brand's official store
            except Exception as exc:
                warn(f"알리에서 {p['brand']} {p['name']} 을 찾지 못했어요: {str(exc)[:80]}")
    return products


def star_ingredient(cand, lib: Library) -> dict | None:
    """The first library ingredient named in a K-beauty product's name (e.g. Centella for
    'SKIN1004 Madagascar Centella ...'). Used for the 'Star ingredient' card on product posts."""
    if getattr(cand, "source", "") != "kbeauty":
        return None
    text = f"{cand.brand} {cand.name}"
    for e in lib.ingredients("hair" if cand.category == "hair" else "skin"):
        if mentions(e, text):
            return e
    return None


# ---------------------------------------------------------------------------
# captions + records
# ---------------------------------------------------------------------------
@dataclass
class InfoCopy:
    topic: Topic
    number: int
    hook: str
    caption: str
    bullets: list[str]
    products: list[dict] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)

    @property
    def has_links(self) -> bool:
        return any(p["links"] for p in self.products)


def _pct(ch) -> str:
    if ch is None:
        return " (new this week)"
    if ch == 0:
        return " (no change)"
    return f" ({'+' if ch > 0 else ''}{ch}% vs last week)"


def _move(p: dict) -> str:
    r, pr = p.get("rank"), p.get("prev_rank")
    if not r:
        return ""
    if pr is None:
        return " (new)"
    return f" (▲{pr - r})" if pr > r else (f" (▼{r - pr})" if pr < r else "")


def _tags(cfg, topic: Topic) -> list[str]:
    c = cfg.copy
    extra = {"skin": ["#skincareingredients", "#kbeautyingredients", "#skincarescience"],
             "hair": ["#koreanhaircare", "#scalpcare", "#haircareroutine"],
             "versus": ["#kbeautytrends", "#seoulbeauty", "#koreanbeautytrends"],
             "history": ["#kbeautyhistory", "#kbeautytrends", "#beautyhistory"],
             "weekly": ["#kbeautytrends", "#oliveyoungglobal", "#kbeautybestsellers", "#trendingnow"]}.get(topic.kind)
    if extra is None:
        from .series import TAGS
        extra = TAGS.get(topic.kind, [])
    own = topic.data.get("hashtags", []) if topic.kind in ("skin", "hair") else []
    if topic.kind == "spotlight":
        from .series import region_of
        own = region_of(topic.data)["hashtags"]
    tags = list(dict.fromkeys(own + extra + c.get("hashtags_common", [])))
    return [t for t in tags if t.startswith("#") and " " not in t][:20]


def _product_line(p: dict) -> str:
    line = f"• {p['brand']} {p['name']}"
    if p.get("rating"):
        line += f" (⭐ {p['rating']:.1f}" + (f", {p['reviews']:,} reviews" if p.get("reviews") else "") + ")"
    return line


def build_info_copy(topic: Topic, number: int, cfg, products: list[dict] | None = None, lib: Library | None = None) -> InfoCopy:
    products = products or []
    d = topic.data
    handle = cfg.handle
    lines: list[str] = []
    if topic.kind in NEW_KINDS:
        from .series import copy_lines
        hook, lines, bullets = copy_lines(topic, number, products, lib)
    elif topic.kind in ("skin", "hair"):
        area = "hair" if topic.kind == "hair" else "skin"
        hook = d["hook"]
        head = f"{KIND_LABEL[topic.kind]} · {d['name']}" + (f" ({d['full_name']})" if d.get("full_name") else "")
        lines += [f"{hook} 🧪" if area == "skin" else f"{hook} 💇‍♀️", head,
                  f"📍 {HEAT_LABEL.get(d.get('heat'), '')}: {d.get('heat_note', '')}".rstrip(": "), "",
                  d["what_it_is"], "", "✨ What it does"] + [f"• {b}" for b in d["benefits"]]
        lines += ["", f"👤 Best for: {', '.join(d['best_for'])}", f"🕐 When: {d['when']}", "", "🧴 How to use"]
        lines += [f"{i}. {s}" for i, s in enumerate(d["how_to_use"], 1)]
        if d.get("pairs_with"):
            lines.append(f"🤝 Pairs well with: {', '.join(d['pairs_with'])}")
        if d.get("avoid_with"):
            lines.append(f"🚫 Don't mix with: {', '.join(d['avoid_with'])}")
        lines += ["", "⚠️ Good to know"] + [f"• {g}" for g in d["good_to_know"]]
        if d.get("myth") and d.get("fact"):
            lines += ["", f"❌ Myth: {d['myth']}", f"✅ Fact: {d['fact']}"]
        if products:
            linked = any(p["links"] for p in products)
            title = f"🛍 Where to find it (links in bio → No.{number})" if linked else "🛍 Where you'll find it"
            lines += ["", title] + [_product_line(p) for p in products]
        bullets = list(d["benefits"][:3])
    elif topic.kind == "weekly":
        wk = week_label(d)
        hook = f"This week in K-beauty: {wk}"
        kor = [r for r in d.get("korea", []) if r.get("index")][:10]
        lines += [f"{hook} 📈", "What Korea searched and what K-beauty fans abroad bought, last week.", ""]
        if kor:
            lines.append("🇰🇷 Most-searched skincare & hair ingredients in Korea (Naver search, top = 100)")
            lines += [f"{i}. {r['name']} · {r['index']}" + _pct(r.get("change")) for i, r in enumerate(kor, 1)]
            lines.append("")
        if products:
            linked = any(p["links"] for p in products)
            lines.append(f"🛍 Top bestsellers on Olive Young Global" + (f" (links in bio → No.{number})" if linked else ""))
            lines += [f"{i}. {p['brand']} {p['name']}" + _move(p) for i, p in enumerate(products, 1)]
            lines.append("")
        lines.append("Which one are you trying next? Tell me below 👇")
        bullets = ([f"Most searched in Korea: {kor[0]['name']}"] if kor else []) + \
                  ([f"#1 on Olive Young Global: {products[0]['brand']} {products[0]['name']}"] if products else [])
    elif topic.kind == "versus":
        hook = f"{d['title']}: {d['topic'].lower()}, {d['year']}"
        lines += [f"{hook} 🇰🇷🌍", d["subtitle"], "", "🇰🇷 Hot in Seoul"]
        lines += [f"{i}. {x['name']}: {x['why']}" for i, x in enumerate(d["korea"], 1)]
        lines += ["", "🌍 Hot abroad"] + [f"{i}. {x['name']}: {x['why']}" for i, x in enumerate(d["global"], 1)]
        if d.get("both"):
            lines += ["", f"🤝 Loved on both sides: {', '.join(d['both'])}"]
        if d.get("next"):
            lines += ["", "👀 Next to watch"] + [f"• {x['name']}: {x['why']}" for x in d["next"]]
        lines += ["", f"📊 {d['basis']}", "", "Team Seoul or team abroad? Tell me in the comments 👇"]
        bullets = [f"Seoul: {', '.join(x['name'] for x in d['korea'][:3])}",
                   f"Abroad: {', '.join(x['name'] for x in d['global'][:3])}"]
    elif topic.variant == "timeline":
        ys = d["years"]
        hook = f"K-beauty through the years: {ys[0]['year']} to {ys[-1]['year']}"
        lines += [f"{hook} 🕰", "What was hot in Korean beauty, year by year.", ""]
        lines += [f"{y['year']}: {y['headline']}" for y in ys]
        lines += ["", "Which year did you discover K-beauty? Tell me below 👇",
                  "One year at a time is coming in our K-beauty time machine series."]
        bullets = [f"{y['year']}: {y['headline']}" for y in ys[-3:]]
    else:
        hook = f"{d['year']}: {d['headline']}"
        lines += [f"K-beauty time machine · {hook} 🕰", "", d["summary"], "",
                  f"🧪 Hero ingredients: {', '.join(d['hero_ingredients'])}",
                  f"🧴 It-products: {', '.join(d['hero_products'])}",
                  f"💬 Buzzwords: {', '.join(d['buzzwords'])}", "", f"📍 Where it is now: {d['now']}", "",
                  "Were you into K-beauty back then? Tell me below 👇"]
        bullets = [f"Hero ingredients: {', '.join(d['hero_ingredients'])}",
                   f"It-products: {', '.join(d['hero_products'])}", f"Buzzwords: {', '.join(d['buzzwords'])}"]
    tags = _tags(cfg, topic)
    has_links = any(p["links"] for p in products)
    tail = ["", "🔖 Save this for later · Follow @" + handle + " for daily K-beauty know-how"]
    if has_links:
        tail.append(f"#ad | affiliate links in bio → No.{number}. I may earn a small commission at no extra cost to you.")
    if topic.kind in ("skin", "hair", "routine", "myth", "combo", "season"):
        tail.append(NOT_ADVICE)
    tail += [".", " ".join(tags)]
    caption = _fit_caption(lines, tail)
    return InfoCopy(topic=topic, number=number, hook=hook, caption=caption, bullets=bullets,
                    products=products, hashtags=tags)


def _fit_caption(lines: list[str], tail: list[str], limit: int = 2200) -> str:
    """Instagram allows 2,200 characters. Drop the least important body lines if needed."""
    body = list(lines)
    while body and len("\n".join(body + tail)) > limit:
        # remove from the end of the longest section but keep the first 6 lines (hook + intro)
        idx = max(range(6, len(body)), key=lambda i: len(body[i]), default=len(body) - 1)
        body.pop(idx)
    return "\n".join(body + tail)[:limit]


def post_record(info: InfoCopy, number: int, today: Date, slides: int) -> dict:
    t = info.topic
    first_link = next((next(iter(p["links"].values())) for p in info.products if p["links"]), "")
    return {
        "number": number,
        "date": today.isoformat(),
        "source": t.kind,
        "key": t.key,
        "brand": "",
        "name": t.title,
        "link": first_link,
        "links": {},
        "products": [{"brand": p["brand"], "name": p["name"], "links": p["links"]} for p in info.products],
        **({"weekly": t.data} if t.kind == "weekly" else {}),
        **({"data": t.data} if t.kind in ("myth", "combo", "recap") else {}),
        "category": t.variant or t.kind,
        "folder": f"{number:03d}",
        "slides": slides,
        "caption": info.caption,
        "hook": info.hook,
        "bullets": info.bullets,
        "status": "prepared",
    }


# ---------------------------------------------------------------------------
# article text for the Pinterest landing page (/p/NNN.html)
# ---------------------------------------------------------------------------
def find_topic(key: str, lib: Library, post: dict | None = None) -> Topic | None:
    if key[:3] in ("my-", "cb-", "rc-", "rt-", "kw-", "ss-", "in-"):
        from .series import find_topic as series_topic
        return series_topic(key, lib, post)
    for kind in ("skin", "hair", "versus", "history"):
        for t in all_topics(kind, lib):
            if t.key == key:
                return t
    return None


def article_html(post: dict, lib: Library, products_html: str = "") -> str:
    """The guide as HTML; products_html (the 'Where to find it' block) goes before the sources."""
    esc = html.escape
    if post.get("weekly"):
        return _weekly_html(post["weekly"], products_html)
    t = find_topic(post.get("key", ""), lib, post)
    if t is not None and t.kind in NEW_KINDS:
        from . import series
        body = series.article(t, lib, products_html, NOT_ADVICE)
        return body + _sources_html(series.sources(t, lib))
    if t is None:  # removed from the library: show the caption text
        body = esc(post.get("caption", "")).split("\n.\n")[0].replace("\n", "<br>")
        return f"<p>{body}</p>{products_html}"
    d = t.data
    ul = lambda items: "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>"  # noqa: E731
    out = []
    if t.kind in ("skin", "hair"):
        out.append(f"<p class=\"lead\">{esc(d['what_it_is'])}</p>")
        out.append(f"<p><b>Comes from:</b> {esc(d['origin'])}<br><b>Best for:</b> {esc(', '.join(d['best_for']))}"
                   f"<br><b>When:</b> {esc(d['when'])}</p>")
        out.append("<h2>What it does</h2>" + ul(d["benefits"]))
        out.append("<h2>How to use it</h2><ol>" + "".join(f"<li>{esc(s)}</li>" for s in d["how_to_use"]) + "</ol>")
        if d.get("pairs_with"):
            out.append(f"<p><b>Pairs well with:</b> {esc(', '.join(d['pairs_with']))}</p>")
        if d.get("avoid_with"):
            out.append(f"<p><b>Don't mix with:</b> {esc(', '.join(d['avoid_with']))}</p>")
        out.append("<h2>Good to know</h2>" + ul(d["good_to_know"]))
        if d.get("myth"):
            out.append(f"<p><b>Myth:</b> {esc(d['myth'])}<br><b>Fact:</b> {esc(d['fact'])}</p>")
        out.append(f"<p class=\"note\">{esc(NOT_ADVICE)}</p>")
    elif t.kind == "versus":
        out.append(f"<p class=\"lead\">{esc(d['subtitle'])}</p>")
        out.append("<h2>Hot in Seoul</h2><ol>" + "".join(f"<li><b>{esc(x['name'])}</b>: {esc(x['why'])}</li>" for x in d["korea"]) + "</ol>")
        out.append("<h2>Hot abroad</h2><ol>" + "".join(f"<li><b>{esc(x['name'])}</b>: {esc(x['why'])}</li>" for x in d["global"]) + "</ol>")
        if d.get("next"):
            out.append("<h2>Next to watch</h2>" + ul([f"{x['name']}: {x['why']}" for x in d["next"]]))
        out.append(f"<p class=\"note\">{esc(d['basis'])}</p>")
    elif t.variant == "timeline":
        out.append("<ol class=\"years\">" + "".join(
            f"<li><b>{y['year']}</b> {esc(y['headline'])}<br><small>{esc(y['summary'])}</small></li>" for y in d["years"]) + "</ol>")
    else:
        out.append(f"<p class=\"lead\">{esc(d['summary'])}</p>")
        out.append(ul([f"Hero ingredients: {', '.join(d['hero_ingredients'])}",
                       f"It-products: {', '.join(d['hero_products'])}",
                       f"Buzzwords: {', '.join(d['buzzwords'])}"]))
        out.append(f"<h2>Where it is now</h2><p>{esc(d['now'])}</p>")
    if products_html:
        out.append(products_html)
    srcs = d.get("sources") or [s for y in d.get("years", []) for s in y.get("sources", [])][:8]
    return "\n".join(out) + _sources_html(srcs)


def _sources_html(srcs: list[str]) -> str:
    esc = html.escape
    if not srcs:
        return ""
    return ("\n<details><summary>Sources</summary><ul class=\"src\">" + "".join(
        f"<li><a href=\"{esc(s)}\" rel=\"nofollow noopener\" target=\"_blank\">{esc(_host(s))}</a></li>" for s in srcs)
        + "</ul></details>")


def _weekly_html(d: dict, products_html: str) -> str:
    esc = html.escape
    out = [f"<p class=\"lead\">What Korea searched and what K-beauty fans abroad bought, {esc(week_label(d))}.</p>"]
    kor = [r for r in d.get("korea", []) if r.get("index")][:10]
    if kor:
        out.append("<h2>Most-searched ingredients in Korea</h2><ol>" + "".join(
            f"<li><b>{esc(r['name'])}</b> · {r['index']}{esc(_pct(r.get('change')))}</li>" for r in kor) + "</ol>")
        out.append("<p class=\"note\">Search interest from Naver DataLab (Korea's largest search engine), last full week vs the week before. Top ingredient = 100.</p>")
    if products_html:
        out.append(products_html.replace("Where to find it", "Top bestsellers on Olive Young Global"))
    return "\n".join(out)


def _host(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else url


def describe(topic: Topic) -> str:
    return clean_space(f"{KIND_KO.get(topic.kind, topic.kind)}: {topic.title}" + (" (다시 올림)" if topic.repeat else ""))


def log_remaining(lib: Library, state) -> str:
    left = remaining(lib, state)
    text = " · ".join(f"{KIND_KO[k]} {v}개" for k, v in left.items())
    log(f"아직 안 올린 정보 글: {text}")
    return text


# ---------------------------------------------------------------------------
# checking + writing library entries (used by the Gemini research job and the tests)
# ---------------------------------------------------------------------------
ING_KEYS = ["id", "name", "full_name", "nickname", "area", "heat", "heat_note", "hot_since", "hook", "what_it_is",
            "origin", "benefits", "best_for", "when", "how_to_use", "pairs_with", "avoid_with", "good_to_know", "myth",
            "fact", "keywords", "examples", "hashtags", "sources"]
VS_KEYS = ["id", "year", "topic", "title", "subtitle", "korea", "global", "both", "next", "basis", "sources"]
LIMITS = {"name": 16, "full_name": 42, "nickname": 26, "heat_note": 50, "hook": 54, "what_it_is": 195, "origin": 62,
          "when": 18, "myth": 80, "fact": 110}
LIST_LIMITS = {"benefits": 64, "best_for": 32, "how_to_use": 70, "pairs_with": 22, "avoid_with": 30, "good_to_know": 90}
BANNED = ("cure", "cures", "treats", "treatment for", "heals", "clinically proven", "regrow", "regrows", "removes wrinkles",
          "erases", "miracle", "guaranteed", "stops hair loss", "anti-aging cure")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40]


def _has_banned(text: str) -> str:
    low = f" {text.lower()} "
    for b in BANNED:
        if re.search(r"(?<![a-z])" + re.escape(b) + r"(?![a-z])", low):
            return b
    return ""


def check_ingredient(e: dict, lib: Library, catalog: list[dict] | None = None) -> list[str]:
    """Problems that would make an entry unsafe or break the cards. Empty list = OK."""
    from .util import has_hangul
    p = []
    area = e.get("area")
    if area not in ("skin", "hair"):
        p.append("area 가 skin/hair 가 아님")
    if e.get("heat") not in ("korea", "global", "both"):
        p.append("heat 값 오류")
    for k in ("id", "name", "hook", "what_it_is", "origin", "when"):
        if not str(e.get(k, "")).strip():
            p.append(f"{k} 비어 있음")
    for k, limit in LIMITS.items():
        if len(str(e.get(k, ""))) > limit:
            p.append(f"{k} 너무 김 ({len(str(e.get(k, '')))}>{limit})")
    for k, limit in LIST_LIMITS.items():
        for x in e.get(k, []) or []:
            if len(str(x)) > limit:
                p.append(f"{k} 항목 너무 김: {str(x)[:30]}…")
    if len(e.get("benefits", []) or []) != 3 or len(e.get("how_to_use", []) or []) != 3:
        p.append("benefits / how_to_use 는 정확히 3개")
    if not e.get("keywords"):
        p.append("keywords 없음")
    srcs = [s for s in e.get("sources", []) or [] if str(s).startswith("http")]
    if len(srcs) < 2:
        p.append("출처(URL) 2개 미만")
    text = json.dumps(e, ensure_ascii=False)
    if has_hangul(text):
        p.append("한글 포함")
    bad = _has_banned(" ".join(str(e.get(k, "")) for k in ("hook", "what_it_is", "heat_note", "fact"))
                      + " " + " ".join(e.get("benefits", []) or []))
    if bad:
        p.append(f"과장·의학 표현: '{bad}'")
    names = {x["name"].lower() for x in lib.ingredients(area or "skin")} | {x["id"] for x in lib.ingredients(area or "skin")}
    if str(e.get("name", "")).lower() in names or e.get("id") in names:
        p.append("이미 자료에 있는 성분")
    if catalog is not None and catalog:
        hits = match_catalog(e, catalog, limit=10, min_rating=0, min_reviews=0)
        if not hits:
            p.append("올리브영 베스트셀러 제품명에서 이 성분을 못 찾음")
        elif not [h for h in hits if names_ingredient(e, h["product"])]:
            p.append("매칭된 제품명에 성분 이름이 없음 (키워드가 너무 넓음)")
    return p


def names_ingredient(e: dict, product: str) -> bool:
    """The product name really names this ingredient (e.g. 'Vita Serum' is NOT vitamin C)."""
    first = (str(e.get("name", "")).split() or [""])[0].lower()
    return len(first) >= 3 and _pattern(first).search(product.lower()) is not None


def check_versus(v: dict, lib: Library) -> list[str]:
    from .util import has_hangul
    p = []
    if len(v.get("korea", [])) != 5 or len(v.get("global", [])) != 5:
        p.append("korea/global 은 각각 5개")
    for side in ("korea", "global", "next"):
        for x in v.get(side, []):
            if len(x.get("name", "")) > 22 or len(x.get("why", "")) > 60 or not x.get("why"):
                p.append(f"{side} 항목 길이 오류: {x.get('name', '')[:20]}")
    names = {x["name"] for x in v.get("korea", [])} & {x["name"] for x in v.get("global", [])}
    if not set(v.get("both", [])) <= names:
        p.append("both 가 양쪽 목록에 없음")
    if len([s for s in v.get("sources", []) if str(s).startswith("http")]) < 2:
        p.append("출처(URL) 2개 미만")
    if has_hangul(json.dumps(v, ensure_ascii=False)):
        p.append("한글 포함")
    if v.get("id") in {x["id"] for x in lib.versus}:
        p.append("이미 있는 id")
    return p


def _toml_val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k} = {_toml_val(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        if not v:
            return "[]"
        inner = [_toml_val(x) for x in v]
        one = "[" + ", ".join(inner) + "]"
        if len(one) <= 100 and not any(isinstance(x, dict) for x in v):
            return one
        return "[\n" + "".join(f"  {x},\n" for x in inner) + "]"
    raise TypeError(type(v))


def toml_block(table: str, entry: dict, keys: list[str]) -> str:
    lines = [f"[[{table}]]"] + [f"{k} = {_toml_val(entry[k])}" for k in keys if k in entry and entry[k] is not None]
    return "\n".join(lines) + "\n"


def insert_blocks(path: Path, table: str, blocks: list[str], published_ids: set[str], id_key: str = "id") -> None:
    """Insert new [[table]] blocks right after the last already-published one (so they go out next)."""
    text = path.read_text(encoding="utf-8")
    marker = f"[[{table}]]"
    parts = text.split(marker)
    head, entries = parts[0], parts[1:]
    last = -1
    for i, body in enumerate(entries):
        m = re.search(rf'^{id_key}\s*=\s*"?([^"\n]+)"?', body, re.M)
        if m and m.group(1).strip() in published_ids:
            last = i
    new = [b[len(marker):] if b.startswith(marker) else b for b in blocks]
    new = [b if b.endswith("\n\n") else b.rstrip("\n") + "\n\n" for b in new]
    if entries and not entries[last if last >= 0 else 0].endswith("\n\n") and last >= 0:
        entries[last] = entries[last].rstrip("\n") + "\n\n"
    merged = entries[:last + 1] + new + entries[last + 1:]
    path.write_text(head + "".join(marker + b for b in merged), encoding="utf-8")
