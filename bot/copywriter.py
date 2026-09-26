"""Turns a Candidate into card text + an Instagram caption.

Template mode (free) uses bot/knowledge.py. If an AI is available (see bot/ai.py: Gemini free
key, a backup OpenAI-compatible key such as Groq, or Claude), it polishes the hook and translates Korean notes (한줄평, 특징, 순위, 리뷰 요약) into English,
using only the facts given — it never invents ingredients or results.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import requests

from .knowledge import CATEGORIES, TOOLS, detect_material
from .sources import Candidate
from .util import clean_space, has_hangul, log, warn

DISCLOSURE = "I may earn a small commission if you buy through my link, at no extra cost to you."


@dataclass
class Copy:
    display_name: str
    hook: str
    kicker: str
    why_label: str
    why_title: str
    why_bullets: list[str]
    how_steps: list[str]
    slide4: dict
    shop_label: str
    caption: str = ""
    ai_used: bool = False
    ai_provider: str = ""
    hashtags: list[str] = field(default_factory=list)
    store_line: str = ""          # "4.8 · 12,345 reviews on Olive Young" (cover + caption)
    reviews: dict | None = None   # "What reviewers say" slide
    my_rating: float | None = None
    deal: dict | None = None      # price slide for K-beauty items linked to AliExpress


def _stars_text(r: float) -> str:
    return f"{r:.1f}".rstrip("0").rstrip(".") if r != int(r) else f"{int(r)}"


def _review_bits(c: Candidate, cfg) -> tuple[str, dict | None]:
    source = cfg.kbeauty.get("review_source", "Olive Young")
    line = ""
    if c.store_rating:
        line = f"{_stars_text(c.store_rating)} average"
        if c.review_count:
            line += f" · {c.review_count:,} reviews"
        line += f" on {source}"
    reviews = None
    if c.review_highlights:
        reviews = {
            "rating": c.store_rating,
            "count": f"{c.review_count:,}" if c.review_count else "",
            "items": c.review_highlights[:3],
            "source": source,
        }
    return line, reviews


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeio" else "a"


def _fmt_orders(n: int | None) -> str:
    if not n:
        return ""
    if n >= 10000:
        return f"{n // 1000}k+"
    if n >= 1000:
        return f"{n / 1000:.1f}k+".replace(".0k", "k")
    return f"{n}+"


def _deal(c: Candidate) -> dict:
    cut = bool(c.original_price and c.price and c.original_price > c.price + 0.01)
    return {
        "kind": "deal",
        "price": _money(c.price, c.currency),
        "original": _money(c.original_price, c.currency) if cut else "",
        "discount": f"-{round(100 - c.price / c.original_price * 100)}%" if cut else "",
        "rating": c.rating,
        "orders": _fmt_orders(c.orders),
    }


def _money(v: float | None, currency: str = "USD") -> str:
    if v is None:
        return ""
    sym = {"USD": "$", "GBP": "£", "EUR": "€", "AUD": "A$", "CAD": "C$"}.get(currency, "$")
    return f"{sym}{v:,.2f}"


# ---------------------------------------------------------------------------
def build_template(c: Candidate, number: int, cfg) -> Copy:
    if c.source == "kbeauty":
        return _kbeauty_template(c, number, cfg)
    return _tools_template(c, number, cfg)


def _kbeauty_template(c: Candidate, number: int, cfg) -> Copy:
    cat = CATEGORIES.get(c.category, CATEGORIES["other"])
    label = cat["label"]
    hooks = [
        f"Why Korea loves this {label}",
        f"The {label} trending in Korea right now",
        f"Korea's favorite {label}, explained",
        f"Trending in Seoul: the {label} worth knowing",
    ]
    if c.comment:
        hooks.insert(0, f"A Korean's honest take on this {label}")
    hook = c.hook or hooks[number % len(hooks)]

    if c.rank:
        kicker = c.rank if "olive" in c.rank.lower() else f"Olive Young ranking · {c.rank}"
    else:
        kicker = "Trending in Korea now"

    if c.key_points:
        why_label, why_title, bullets = "Why it's trending", "Why Korea loves it", c.key_points[:3]
    else:
        titles = {
            "spot_care": "How spot care works",
            "hair": "Korean hair care, explained",
            "other": "Why it's worth a look",
        }
        why_title = titles.get(c.category, f"What {_article(label)} {label} does")
        why_label, bullets = "The basics", cat["what"]

    if c.comment:
        slide4 = {"kind": "take", "text": c.comment}
    elif cat.get("routine") is not None:
        slide4 = {"kind": "routine", "index": cat["routine"], "note": cat.get("note", "")}
    else:
        slide4 = {"kind": "tips", "title": "Pro tips", "items": cat.get("tips", CATEGORIES["other"]["tips"])}

    store_line, reviews = _review_bits(c, cfg)
    on_ali = bool(c.ali_link) or c.store == "aliexpress"
    oy_name = cfg.kbeauty.get("shop_name", "Olive Young Global")
    if on_ali and c.oy_link:
        shop_label = f"US: AliExpress  ·  Elsewhere: {oy_name}"
    elif on_ali:
        shop_label = "Shop on AliExpress"
    else:
        shop_label = f"Shop at {oy_name}"
    return Copy(
        display_name=c.name,
        hook=hook,
        kicker=kicker,
        why_label=why_label,
        why_title=why_title,
        why_bullets=list(bullets),
        how_steps=list(cat["how"]),
        slide4=slide4,
        shop_label=shop_label,
        store_line=store_line,
        reviews=reviews,
        my_rating=c.my_rating if c.comment else None,
        deal=_deal(c) if on_ali and c.price else None,
    )


def _tools_template(c: Candidate, number: int, cfg) -> Copy:
    tool = TOOLS[c.category]
    under = int(c.price) + 1 if c.price else None
    if under:
        hooks = [h.replace("${price}", f"${under}") for h in tool["hooks"]]
        hooks.append(f"A small upgrade for your routine, under ${under}")
    else:
        hooks = [f"The {tool['name'].lower()} worth adding to your routine"]
    material = detect_material(c.raw_title)
    name = tool["name"]
    if material and material.split()[0] not in name.lower():
        name = f"{material.capitalize()} {name.lower()}"
    return Copy(
        display_name=name,
        hook=hooks[number % len(hooks)],
        kicker="K-beauty routine tool",
        why_label="The basics",
        why_title="What it does",
        why_bullets=list(tool["what"]),
        how_steps=list(tool["how"]),
        slide4=_deal(c),
        shop_label="Shop on AliExpress",
    )


# ---------------------------------------------------------------------------
def build_caption(c: Candidate, cp: Copy, number: int, cfg) -> str:
    on_ali = c.source == "tools" or bool(c.ali_link) or c.store == "aliexpress"
    on_oy = c.source == "kbeauty" and (bool(c.oy_link) or not on_ali)
    tags = list(dict.fromkeys(
        cfg.copy.get("hashtags_common", [])
        + cfg.copy.get("hashtags_kbeauty" if c.source == "kbeauty" else "hashtags_tools", [])
        + (CATEGORIES.get(c.category, {}) if c.source == "kbeauty" else TOOLS.get(c.category, {})).get("tags", [])
        + (["#aliexpressfinds"] if on_ali else [])
    ))
    if not on_oy:  # Olive Young tags would be misleading on an AliExpress-only item
        tags = [t for t in tags if "oliveyoung" not in t]
    tags = tags[:20]
    cp.hashtags = tags
    lines = [f"{cp.hook} {'🇰🇷' if c.source == 'kbeauty' else '✨'}", f"#ad | affiliate link in bio → No.{number}", ""]
    if c.source == "kbeauty":
        lines.append(f"{c.brand} {cp.display_name}")
        if c.rank:
            lines.append(f"📈 {cp.kicker}")
        if cp.store_line:
            lines.append(f"⭐ {cp.store_line}")
    else:
        lines.append(cp.display_name)
    d = cp.deal or (cp.slide4 if cp.slide4.get("kind") == "deal" else None)
    if d:
        lines.append(f"💸 {d['price']} on AliExpress when I posted (prices change; import fees may apply)")
        stats = " · ".join(x for x in [f"{d['rating']} positive reviews" if d.get("rating") else "", f"{d['orders']} orders" if d.get("orders") else ""] if x)
        if stats:
            lines.append(f"🛒 {stats} on AliExpress")
    lines += ["", f"✨ {cp.why_title}"] + [f"• {b}" for b in cp.why_bullets]
    if cp.reviews:
        lines += ["", f"🗣 What {cp.reviews['source']} reviewers mention"] + [f"• {b}" for b in cp.reviews["items"]]
    lines += ["", "🧴 How to use"] + [f"{i}. {s}" for i, s in enumerate(cp.how_steps, 1)]
    if cp.slide4.get("kind") == "take":
        rated = f" ({_stars_text(cp.my_rating)}/5)" if cp.my_rating else ""
        lines += ["", f"💬 My take{rated}: \"{cp.slide4['text']}\""]
    oy_name = cfg.kbeauty.get("shop_name", "Olive Young Global")
    if on_ali and on_oy:
        where = f"🇺🇸 US: AliExpress · 🌏 other countries: {oy_name}"
    else:
        where = "AliExpress" if on_ali else oy_name
    code = cfg.kbeauty.get("oliveyoung_code", "")
    code_line = [f"🎟 {oy_name} code: {code}"] if code and on_oy else []
    lines += [
        "",
        f"🔗 Want it? Tap the link in my bio and find No.{number} ({where})",
        *code_line,
        "🔖 Save this for your next haul",
        "",
        DISCLOSURE,
        ".",
        " ".join(tags),
    ]
    caption = "\n".join(lines)
    return caption[:2200]


# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You write short, honest English copy for an Instagram account run by a Korean K-beauty curator. "
    "Rules: use only the facts provided. Never invent ingredients, awards, rankings, prices, reviews or results. "
    "No medical or guaranteed claims (no 'cures', 'treats acne', 'removes wrinkles', 'clinically proven'). "
    "Translate any Korean faithfully into natural American English. Friendly, confident, concise. "
    "No emojis, no hashtags. Reply with one JSON object only."
)


def ai_polish(c: Candidate, cp: Copy, cfg, session=None, sleep=None) -> Copy:
    if not cfg.ai_enabled:
        return cp
    facts = {
        "source": "Korean store bestseller (Olive Young)" if c.source == "kbeauty" else "AliExpress beauty tool",
        "brand": c.brand,
        "product": c.name if c.source == "kbeauty" else c.raw_title,
        "category": c.category,
        "store_rank_note": c.rank,
        "curator_key_points": c.key_points,
        "curator_comment": c.comment,
        "curator_review_summary": c.review_highlights,
        "price": cp.slide4.get("price") if c.source == "tools" else None,
        "draft_hook": cp.hook,
    }
    instructions = {
        "hook": "cover headline, max 52 characters, grounded in the facts, no brand name",
        "brand_en": "brand in English (keep as-is if already English)",
        "product_en": "product name in English, max 45 characters (for AliExpress: a short generic name like 'Rose quartz gua sha', max 30 characters)",
        "rank_en": "store_rank_note translated to English, max 30 characters, or empty string",
        "key_points_en": "curator_key_points translated/tightened, each max 60 characters, same count, or []",
        "comment_en": "curator_comment translated to natural English in first person, max 150 characters, or empty string",
        "review_highlights_en": "curator_review_summary translated/tightened (paraphrased themes, not quotes), each max 60 characters, same count, or []",
    }
    user = "Facts:\n" + json.dumps(facts, ensure_ascii=False) + "\n\nReturn JSON with these keys:\n" + json.dumps(instructions)
    try:
        from . import ai
        kw = {"sleep": sleep} if sleep else {}
        text, provider = ai.ask(SYSTEM_PROMPT, user, cfg, session=session, **kw)
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except Exception as exc:
        warn(f"AI 카피 실패, 템플릿으로 진행: {str(exc)[:200]}")
        return cp

    def ok(value, limit):
        v = clean_space(str(value or "")).strip('"')
        return v if v and len(v) <= limit and not has_hangul(v) else ""

    if ok(data.get("hook"), 60):
        cp.hook = ok(data.get("hook"), 60)
    if c.source == "kbeauty":
        c.brand = ok(data.get("brand_en"), 40) or c.brand
        name = ok(data.get("product_en"), 60)
        if name:
            c.name = cp.display_name = name
        if c.rank:
            c.rank = ok(data.get("rank_en"), 40)
            cp.kicker = (c.rank if "olive" in c.rank.lower() else f"Olive Young ranking · {c.rank}") if c.rank else "Trending in Korea now"
        pts = [ok(p, 70) for p in (data.get("key_points_en") or [])]
        pts = [p for p in pts if p][:3]
        if c.key_points and pts:
            c.key_points = cp.why_bullets = pts
        highlights = [ok(p, 70) for p in (data.get("review_highlights_en") or [])]
        highlights = [p for p in highlights if p][:3]
        if c.review_highlights:
            c.review_highlights = highlights
            cp.store_line, cp.reviews = _review_bits(c, cfg)
        comment = ok(data.get("comment_en"), 170)
        if c.comment:
            c.comment = comment
            if comment:
                cp.slide4 = {"kind": "take", "text": comment}
            elif cp.slide4.get("kind") == "take":
                cp.slide4 = _kbeauty_template(c, 0, cfg).slide4
    else:
        name = ok(data.get("product_en"), 34)
        if name:
            cp.display_name = name
    cp.ai_used = True
    cp.ai_provider = provider
    log(f"AI 카피 적용 완료 ({provider})")
    return cp


def make_copy(c: Candidate, number: int, cfg, session=None, sleep=None) -> Copy:
    cp = build_template(c, number, cfg)
    cp = ai_polish(c, cp, cfg, session=session, sleep=sleep)
    if not cp.ai_used and c.source == "kbeauty":
        # No AI (or it failed): Korean notes can't go on English cards, so drop them.
        from .sources.kbeauty import _drop_korean
        _drop_korean(c, c.brand)
        cp = build_template(c, number, cfg)
    # Final guard: nothing Korean may reach the cards or caption.
    texts = [c.brand, cp.display_name, cp.hook, cp.kicker, *cp.why_bullets, *cp.how_steps,
             str(cp.slide4.get("text", "")), *cp.slide4.get("items", []), *((cp.reviews or {}).get("items", []))]
    if any(has_hangul(t) for t in texts):
        raise ValueError("한국어가 남아 있어요. 브랜드·제품명을 영어로 적어주세요.")
    cp.caption = build_caption(c, cp, number, cfg)
    return cp
