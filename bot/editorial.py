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

INFO_KINDS = ("skin", "hair", "versus", "history")
PLAN_TOKENS = ("product", "skin", "skin_korea", "skin_global", "hair", "versus", "history")
DEFAULT_WEEKLY = ["skin_korea", "product", "hair", "versus", "skin_global", "history", "product"]
FALLBACK = {
    "product": ["product", "skin", "hair", "history", "versus"],
    "skin": ["skin", "hair", "history", "versus", "product"],
    "skin_korea": ["skin_korea", "skin", "hair", "history", "versus", "product"],
    "skin_global": ["skin_global", "skin", "hair", "history", "versus", "product"],
    "hair": ["hair", "skin", "history", "versus", "product"],
    "versus": ["versus", "skin", "hair", "history", "product"],
    "history": ["history", "skin", "hair", "versus", "product"],
}
KIND_LABEL = {"skin": "Ingredient 101", "hair": "Hair & scalp 101", "versus": "Seoul vs. abroad",
              "history": "K-beauty history"}
KIND_KO = {"product": "제품 픽", "skin": "피부 성분 101", "skin_korea": "피부 성분 101 (한국에서 뜨는 것)",
           "skin_global": "피부 성분 101 (해외에서 뜨는 것)", "hair": "모발·두피 성분 101",
           "versus": "서울 vs 해외", "history": "K뷰티 연도별 변화"}
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
        return f"{self.data['year']}: {self.data['headline']}"


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
    heat = {"skin_korea": {"korea", "both"}, "skin_global": {"global", "both"}}.get(token)
    topics = [t for t in all_topics(kind, lib) if not heat or t.data.get("heat") in heat]
    used = last_used(state)
    for t in topics:
        if t.key not in used:
            return t
    days = int(cfg.raw.get("schedule", {}).get("repeat_after_days", 120))
    old = sorted((t for t in topics if (today - used[t.key]).days >= days), key=lambda t: used[t.key])
    if old:
        old[0].repeat = True
        return old[0]
    return None


def remaining(lib: Library, state) -> dict[str, int]:
    used = last_used(state)
    return {k: sum(1 for t in all_topics(k, lib) if t.key not in used) for k in INFO_KINDS}


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
    data = {"updated": today, "source": "Olive Young Global bestsellers",
            "items": [{k: it.get(k) for k in keep} for it in items]}
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


def find_products(topic: Topic, cfg, catalog: list[dict], ali_client=None) -> list[dict]:
    if topic.kind not in ("skin", "hair"):
        return []
    from .discover import _oy_link

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


def _tags(cfg, topic: Topic) -> list[str]:
    c = cfg.copy
    extra = {"skin": ["#skincareingredients", "#kbeautyingredients", "#skincarescience"],
             "hair": ["#koreanhaircare", "#scalpcare", "#haircareroutine"],
             "versus": ["#kbeautytrends", "#seoulbeauty", "#koreanbeautytrends"],
             "history": ["#kbeautyhistory", "#kbeautytrends", "#beautyhistory"]}[topic.kind]
    own = topic.data.get("hashtags", []) if topic.kind in ("skin", "hair") else []
    tags = list(dict.fromkeys(own + extra + c.get("hashtags_common", [])))
    return [t for t in tags if t.startswith("#") and " " not in t][:20]


def _product_line(p: dict) -> str:
    line = f"• {p['brand']} {p['name']}"
    if p.get("rating"):
        line += f" (⭐ {p['rating']:.1f}" + (f", {p['reviews']:,} reviews" if p.get("reviews") else "") + ")"
    return line


def build_info_copy(topic: Topic, number: int, cfg, products: list[dict] | None = None) -> InfoCopy:
    products = products or []
    d = topic.data
    handle = cfg.handle
    lines: list[str] = []
    if topic.kind in ("skin", "hair"):
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
    if topic.kind in ("skin", "hair"):
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
def find_topic(key: str, lib: Library) -> Topic | None:
    for kind in INFO_KINDS:
        for t in all_topics(kind, lib):
            if t.key == key:
                return t
    return None


def article_html(post: dict, lib: Library, products_html: str = "") -> str:
    """The guide as HTML; products_html (the 'Where to find it' block) goes before the sources."""
    esc = html.escape
    t = find_topic(post.get("key", ""), lib)
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
    if srcs:
        out.append("<details><summary>Sources</summary><ul class=\"src\">" + "".join(
            f"<li><a href=\"{esc(s)}\" rel=\"nofollow noopener\" target=\"_blank\">{esc(_host(s))}</a></li>" for s in srcs)
            + "</ul></details>")
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
