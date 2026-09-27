"""Card designs for the newer series (1080x1350 carousels + 1000x1500 pins).

  Routine builder : one color per concern, sun / moon step lists
  Myth vs. fact   : red MYTH box over a green FACT box, one ingredient per card
  Mix & match     : pairs-well-with chips and space-out warnings
  Seoul seasons   : one color per season, weather → skin swaps → hair
  Speak K-beauty  : big Hangul + how to say it + meaning
  Monthly recap   : last month's most consistent Olive Young Global bestsellers
  Industry watch  : what makers and expos are pushing
"""
from __future__ import annotations

import hashlib
import math

from .editorial import NOT_ADVICE, InfoCopy, Topic
from .render import (H, M, PH, PW, SANS, SANS_B, SANS_M, SANS_SB, SERIF, SERIF_I, W, Card, F, Theme, cap_metrics,
                     draw_lines, fit, rgb, tracked, tw, wrap)
from .render_info import (UP, _chips, _chips_height, _clock, _icon_x, _pin_footer, _swipe, _text_block, _trend_up,
                          draw_name, fit_words, ing_products, ingredient_theme, theme_from)

KO = "NotoSansKR-Bold.otf"
DOWN_RED = "#B4474F"

ROUTINE_COLORS = {"dull": "#C77D2E", "dehydrated": "#3F88C5", "sensitive": "#5B8C5A", "breakouts": "#2F8F83",
                  "dark-spots": "#C06C84", "early-aging": "#8A5FB0", "oily-scalp": "#2E8C9C", "damaged-hair": "#9C6B4E"}
SEASON_COLORS = {"spring": "#D46A92", "summer": "#1F8A8A", "autumn": "#B9772E", "winter": "#3F6FB0"}
MYTH = theme_from("#B5473A")
COMBO = theme_from("#2F7F8F")
WORDS = theme_from("#7A4FB5")
RECAP = theme_from("#A87A22")
INDUSTRY = theme_from("#2D6A7F")


def _color_theme(table: dict, ident: str) -> Theme:
    color = table.get(ident) or list(table.values())[int(hashlib.sha1(ident.encode()).hexdigest(), 16) % len(table)]
    return theme_from(color)


def series_theme(topic: Topic) -> Theme:
    k = topic.kind
    if k == "routine":
        return _color_theme(ROUTINE_COLORS, topic.data.get("id", ""))
    if k == "season":
        return _color_theme(SEASON_COLORS, topic.data.get("id", ""))
    return {"myth": MYTH, "combo": COMBO, "words": WORDS, "recap": RECAP, "industry": INDUSTRY}[k]


# ---------------------------------------------------------------------------
# small shared pieces
# ---------------------------------------------------------------------------
def _sun(c: Card, cx, cy, r, color):
    c.d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    for i in range(8):
        a = i * math.pi / 4
        c.d.line((cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35, cx + math.cos(a) * r * 1.8,
                  cy + math.sin(a) * r * 1.8), fill=color, width=max(3, int(r * 0.18)))


def _moon(c: Card, cx, cy, r, color, bg):
    c.d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    c.d.ellipse((cx - r * 0.35, cy - r * 1.05, cx + r * 1.35, cy + r * 0.55), fill=bg)


def _plus(c: Card, cx, cy, s, color, width=5):
    c.d.line((cx - s, cy, cx + s, cy), fill=color, width=width)
    c.d.line((cx, cy - s, cx, cy + s), fill=color, width=width)


def _pause(c: Card, cx, cy, s, color):
    c.d.rounded_rectangle((cx - s * 0.7, cy - s, cx - s * 0.2, cy + s), 3, fill=color)
    c.d.rounded_rectangle((cx + s * 0.2, cy - s, cx + s * 0.7, cy + s), 3, fill=color)


def _kicker(c: Card, y, text) -> float:
    t = c.t
    _, ph = c.pill(M, y, text, F(SANS_SB, 24), rgb(t.on_accent), rgb(t.accent), padx=22, pady=14)
    return y + ph


def _numbered(c: Card, y, items: list[str], bottom: float, size=50, min_size=28, circle=True) -> float:
    """Numbered rows that share the space between y and bottom."""
    t = c.t
    x = M + 96
    for s in range(size, min_size - 1, -2):
        f = F(SANS_M, s)
        blocks = [wrap(c.d, it, f, W - M - x)[:3] for it in items]
        lh = int(s * 1.3)
        total = sum(max(len(b) * lh, 64) for b in blocks) + 30 * (len(items) - 1)
        if y + total <= bottom:
            break
    gap = min(130, 30 + (bottom - y - total) / max(len(items), 1))
    for i, lines in enumerate(blocks):
        h = max(len(lines) * lh, 64)
        cy = y + min(h, 64) / 2 if len(lines) > 1 else y + h / 2
        if circle:
            c.d.ellipse((M, cy - 32, M + 64, cy + 32), fill=rgb(t.accent))
            c.d.text((M + 32, cy + 1), str(i + 1), font=F(SANS_B, 30), fill=rgb(t.on_accent), anchor="mm")
        ty = y + (h - len(lines) * lh) / 2 if len(lines) == 1 else y + 4
        draw_lines(c.d, x, ty, lines, f, c.ink, lh)
        y += h + gap
    return y


def _checks(c: Card, y, items: list[str], bottom: float, size=50, color=None) -> float:
    t = c.t
    color = color or rgb(t.accent)
    for s in range(size, 25, -2):
        f = F(SANS, s)
        lh = int(s * 1.3)
        blocks = [wrap(c.d, it, f, W - 2 * M - 70)[:3] for it in items]
        total = sum(len(b) * lh for b in blocks) + 26 * len(items)
        if y + total <= bottom:
            break
    gap = min(120, 26 + (bottom - y - total) / max(len(items), 1))
    for lines in blocks:
        c.d.ellipse((M, y + 2, M + 48, y + 50), fill=rgb(t.soft))
        c.check(M + 24, y + 26, 24, color, 4)
        draw_lines(c.d, M + 72, y + 4, lines, f, c.ink, lh)
        y += len(lines) * lh + gap
    return y


def _cta(c: Card, big: str, sub: str, handle: str, idx: int, n: int, follow: str, number: int = 0,
         linked: bool = False, disclaimer: str = "") -> Card:
    t = c.t
    c.header(handle, idx, n)
    c.d.ellipse((W - 420, -180, W + 220, 460), fill=rgb(t.accent))
    c.d.ellipse((W - 330, -90, W + 130, 370), fill=rgb(t.dark))
    fbig, bl, bs = fit(c.d, big, SERIF, W - 2 * M, 2, 120, 80)
    fsub, sl, ss = fit(c.d, sub, SANS_M, W - 2 * M, 2, 42, 30)
    need = len(bl) * int(bs * 1.02) + 44 + len(sl) * int(ss * 1.3) + 70 + 110 + 110 + (100 if linked else 0)
    y = min(500, H - 240 - need)
    y = draw_lines(c.d, M, y, bl, fbig, c.ink, int(bs * 1.02)) + 44
    y = draw_lines(c.d, M, y, sl, fsub, c.muted, int(ss * 1.3)) + 70
    c.bookmark(M, y, 34, 46, c.ink)
    c.d.text((M + 60, y + 23), "Save  ·  Share with a friend", font=F(SANS_M, 36), fill=c.ink, anchor="lm")
    y += 110
    c.d.text((M, y), f"Follow @{handle}", font=F(SANS_B, 40), fill=c.ink, anchor="la")
    c.d.text((M, y + 58), follow, font=F(SANS, 34), fill=c.muted, anchor="la")
    y += 120
    if linked:
        label = f"Products: link in bio, No.{number}"
        fl = F(SANS_B, 32)
        c.d.rounded_rectangle((M, y, M + tw(c.d, label, fl) + 80, y + 80), 40, fill=rgb(t.accent))
        c.d.text((M + 40, y + 40), label, font=fl, fill=rgb(t.on_accent), anchor="lm")
    disc = ("#ad · Affiliate links. I may earn a small commission at no extra cost to you. " if linked else "") + disclaimer
    if disc.strip():
        f, lines, s = fit(c.d, disc.strip(), SANS, W - 2 * M, 2, 26, 21)
        draw_lines(c.d, M, H - 196, lines, f, c.muted, int(s * 1.4))
    c.dots(idx, n)
    return c


def _title_block(c: Card, label: str, title: str, y=176, size=80, max_lines=2) -> float:
    c.label(M, y, label, color=rgb(c.t.accent), size=26)
    f, lines, s = fit(c.d, title, SERIF, W - 2 * M, max_lines, size, 56)
    return draw_lines(c.d, M, y + 56, lines, f, c.ink, int(s * 1.08))


# ---------------------------------------------------------------------------
# Routine builder
# ---------------------------------------------------------------------------
def rt_cover(t, d, names, number, handle, n) -> Card:
    c = Card(t)
    c.header(handle, 1, n)
    _sun(c, W - 250, 300, 62, rgb(t.accent, 200))
    _moon(c, W - 140, 450, 52, rgb(t.dark), rgb(t.bg))
    y = _kicker(c, 196, f"ROUTINE BUILDER · NO.{number}") + 40
    c.label(M, y, d["concern"], color=c.muted, size=24)
    y += 90
    fn, nl, ns = fit_words(c, d["title"], SERIF, W - 2 * M - 40, 3, 150, 90)
    y = draw_name(c, M, y, nl, fn, c.ink, int(ns * 0.98), gap=30)
    c.d.rectangle((M, y, M + 96, y + 6), fill=rgb(t.accent))
    y += 46
    y = _text_block(c, M, y, d["hook"], SERIF, W - 2 * M, 3, 60, 42, c.ink, lh=1.12) + 50
    if names and y < H - 330:
        c.label(M, y, "Key ingredients", color=rgb(t.accent), size=22)
        _chips(c, M, y + 40, names, W - 2 * M, F(SANS_M, 30), c.ink, bg=rgb(t.soft))
    _swipe(c, "Swipe for the steps")
    c.dots(1, n)
    return c


def rt_steps(t, d, when: str, handle, idx, n) -> Card:
    c = Card(t)
    c.header(handle, idx, n)
    if when == "am":
        _sun(c, W - M - 60, 250, 40, rgb(t.accent))
        y = _title_block(c, "Step by step", "Morning", size=110, max_lines=1) + 50
    else:
        _moon(c, W - M - 60, 250, 46, rgb(t.accent), rgb(t.bg))
        y = _title_block(c, "Step by step", "Night", size=110, max_lines=1) + 50
    _numbered(c, y, d[when], H - 190)
    c.dots(idx, n)
    return c


def rt_key(t, d, entries, handle, idx, n) -> Card:
    c = Card(t)
    c.header(handle, idx, n)
    y = _title_block(c, "Why these ingredients", "What each one does", size=76) + 40
    tips = d.get("tips", [])[:2]
    tip_f = F(SANS, 32)
    tip_lines = [wrap(c.d, x, tip_f, W - 2 * M - 80)[:3] for x in tips]
    tip_h = (80 + sum(len(tl) * 44 for tl in tip_lines) + 20 * max(len(tips) - 1, 0)) if tips else 0
    bottom = H - 190 - (tip_h + 40 if tips else 0)
    blocks = []
    for e in entries[:3]:
        fb = F(SANS, 36)
        bl = [ln for b in e.get("benefits", [])[:2] for ln in (["• " + x if i == 0 else "  " + x
                                                                   for i, x in enumerate(wrap(c.d, b, fb, W - 2 * M - 90)[:2])])]
        bs = 36
        blocks.append((e, fb, bl, bs, 78 + len(bl) * int(bs * 1.3) + 20))
    while blocks and y + sum(b[4] for b in blocks) > bottom:
        blocks.pop()
    gap = min(60, (bottom - y - sum(b[4] for b in blocks)) / max(len(blocks), 1))
    for e, fb, bl, bs, h in blocks:
        it = ingredient_theme(e)
        c.d.rounded_rectangle((M, y, M + 12, y + h - 20), 6, fill=rgb(it.accent))
        c.d.text((M + 40, y + 2), e["name"], font=F(SERIF, 58), fill=rgb(it.accent), anchor="la")
        draw_lines(c.d, M + 40, y + 78, bl, fb, c.ink, int(bs * 1.3))
        y += h + gap
    if tips:
        top = H - 190 - tip_h
        box = (M, top, W - M, H - 190)
        c.shadow_box(box, 30, t.surface, blur=18, dy=8, alpha=18)
        c.label(M + 40, top + 32, "Tips", color=rgb(t.accent), size=22)
        yy = top + 72
        for tl in tip_lines:
            c.d.ellipse((M + 40, yy + 14, M + 54, yy + 28), fill=rgb(t.accent))
            draw_lines(c.d, M + 72, yy, tl, tip_f, c.ink, 44)
            yy += len(tl) * 44 + 20
    c.dots(idx, n)
    return c


def render_routine(topic, info, number, handle, lib) -> list[Card]:
    from .series import key_names
    d = topic.data
    t = series_theme(topic)
    ids = d.get("key", [])
    entries = sorted([e for e in (lib.skin + lib.hair if lib else []) if e["id"] in ids], key=lambda e: ids.index(e["id"]))
    names = key_names(d, lib)
    plan = ["cover", "am", "pm"] + (["key"] if entries else []) + (["where"] if info.products else []) + ["cta"]
    n = len(plan)
    out = []
    for idx, name in enumerate(plan, 1):
        if name == "cover":
            out.append(rt_cover(t, d, names, number, handle, n))
        elif name in ("am", "pm"):
            out.append(rt_steps(t, d, name, handle, idx, n))
        elif name == "key":
            out.append(rt_key(t, d, entries, handle, idx, n))
        elif name == "where":
            out.append(ing_products(t, {"name": ", ".join(names[:3])}, info.products, number, handle, idx, n,
                                    title="Where to find the key ingredients"))
        else:
            out.append(_cta(Card(t, dark=True), "Save this", "and build it one product at a time.", handle, idx, n,
                            "for a new routine every other week", number, info.has_links, NOT_ADVICE))
    return out


# ---------------------------------------------------------------------------
# Myth vs. fact
# ---------------------------------------------------------------------------
def my_cover(items, number, handle, n) -> Card:
    t = MYTH
    c = Card(t)
    c.header(handle, 1, n)
    y = _kicker(c, 196, f"MYTH VS. FACT · NO.{number}") + 90
    f1 = F(SERIF, 230)
    c.d.text((M, y), "Myth", font=f1, fill=c.ink, anchor="la")
    wmyth = tw(c.d, "Myth", f1)
    c.d.line((M - 10, y + 150, M + wmyth + 10, y + 120), fill=rgb(DOWN_RED), width=14)
    y += 250
    c.d.text((M, y), "or fact?", font=F(SERIF_I, 150), fill=rgb(t.accent), anchor="la")
    y += 210
    y = _text_block(c, M, y, f"{len(items)} K-beauty beliefs, checked against the research", SANS_M, W - 2 * M, 2, 40, 30,
                    c.muted, lh=1.3) + 40
    _chips(c, M, y, [i["name"] for i in items], W - 2 * M, F(SANS_M, 30), c.ink, bg=rgb(t.soft))
    _swipe(c, "Guess first, then swipe")
    c.dots(1, n)
    return c


def my_item(it, handle, idx, n) -> Card:
    t = MYTH
    c = Card(t)
    c.header(handle, idx, n)
    it_t = ingredient_theme(it)
    y = 170
    _, ph = c.pill(M, y, it["name"].upper(), F(SANS_SB, 26), rgb(it_t.on_accent), rgb(it_t.accent), padx=24, pady=16)
    y += ph + 40
    bottom = H - 190
    for scale in (1.0, 0.92, 0.84, 0.76, 0.68):
        fm, ml, ms = fit(c.d, it["myth"], SERIF, W - 2 * M - 100, 4, int(72 * scale), 36)
        ff, fl, fs = fit(c.d, it["fact"], SANS_M, W - 2 * M - 100, 7, int(52 * scale), 28, balance=False)
        mh = 116 + len(ml) * int(ms * 1.12) + 44
        fh = 116 + len(fl) * int(fs * 1.34) + 44
        if y + mh + 36 + fh <= bottom:
            break
    y += max(0, (bottom - y - mh - 36 - fh) * 0.35)
    c.d.rounded_rectangle((M, y, W - M, y + mh), 34, fill=rgb("#FBE9E7"))
    _icon_x(c, M + 60, y + 60, 16, rgb(DOWN_RED), 7)
    tracked(c.d, M + 100, y + 72, "MYTH", F(SANS_B, 28), rgb(DOWN_RED), 4)
    draw_lines(c.d, M + 50, y + 116, ml, fm, rgb("#5A1F1B"), int(ms * 1.12))
    y += mh + 36
    c.d.rounded_rectangle((M, y, W - M, min(y + fh, bottom)), 34, fill=rgb("#E3F2EA"))
    c.check(M + 60, y + 58, 30, rgb(UP), 7)
    tracked(c.d, M + 100, y + 72, "FACT", F(SANS_B, 28), rgb(UP), 4)
    draw_lines(c.d, M + 50, y + 116, fl, ff, rgb("#133A27"), int(fs * 1.34))
    c.dots(idx, n)
    return c


def render_myth(topic, info, number, handle) -> list[Card]:
    items = topic.data["items"]
    n = len(items) + 2
    out = [my_cover(items, number, handle, n)]
    out += [my_item(it, handle, i + 2, n) for i, it in enumerate(items)]
    out.append(_cta(Card(MYTH, dark=True), "Which one fooled you?", "Tell me in the comments.", handle, n, n,
                    "for fact-checked K-beauty", disclaimer=NOT_ADVICE))
    return out


# ---------------------------------------------------------------------------
# Mix & match
# ---------------------------------------------------------------------------
def cb_cover(items, number, handle, n) -> Card:
    t = COMBO
    c = Card(t)
    c.header(handle, 1, n)
    c.d.ellipse((W - 420, 170, W - 170, 420), fill=rgb(t.accent, 150))
    c.d.ellipse((W - 290, 250, W - 40, 500), fill=rgb(t.dark, 150))
    y = _kicker(c, 196, f"MIX & MATCH · NO.{number}") + 120
    y = _text_block(c, M, y, "What to layer, what to space out", SERIF, W - 2 * M, 3, 124, 84, c.ink, lh=1.02) + 44
    y = _text_block(c, M, y, "A pairing cheat sheet for:", SANS_M, W - 2 * M, 1, 38, 30, c.muted) + 30
    _chips(c, M, y, [i["name"] for i in items], W - 2 * M, F(SANS_M, 32), c.ink, bg=rgb(t.soft))
    _swipe(c, "Swipe for the pairings")
    c.dots(1, n)
    return c


def _combo_box(c: Card, y, title, chips, good: bool, size=36, draw=True) -> float:
    t = c.t
    fch = F(SANS_M, size)
    h = 130 + _chips_height(c, chips, W - 2 * M - 80, fch, padx=28, pady=18) + 44
    if not draw:
        return y + h
    c.shadow_box((M, y, W - M, y + h), 32, t.surface, blur=18, dy=8, alpha=18)
    c.d.ellipse((M + 40, y + 38, M + 90, y + 88), fill=rgb(UP if good else DOWN_RED))
    if good:
        _plus(c, M + 65, y + 63, 13, rgb("#FFFFFF"), 6)
    else:
        _pause(c, M + 65, y + 63, 13, rgb("#FFFFFF"))
    c.d.text((M + 112, y + 63), title, font=F(SANS_B, 38), fill=c.ink, anchor="lm")
    _chips(c, M + 40, y + 124, chips, W - 2 * M - 80, fch, c.ink, bg=rgb("#E3F2EA" if good else "#FBE9E7"), padx=28, pady=18)
    return y + h


def cb_item(it, handle, idx, n) -> Card:
    t = COMBO
    c = Card(t)
    c.header(handle, idx, n)
    it_t = ingredient_theme(it)
    note = "No clashes flagged in our notes. Still, add one new active at a time."
    bottom = H - 170
    for name_size, chip, show_benefit in ((150, 36, True), (130, 32, True), (120, 30, False), (100, 28, False)):
        fn, nl, ns = fit_words(c, it["name"], SERIF, W - 2 * M, 2, name_size, 72)
        name_h = (len(nl) - 1) * int(ns * 0.98) + ns * 0.75 + 20
        fb, bl, bs = fit(c.d, it.get("benefit", ""), SANS, W - 2 * M, 2, 38, 30)
        ben_h = (len(bl) * int(bs * 1.3) + 26) if show_benefit and it.get("benefit") else 0
        when_h = 90 if it.get("when") else 0
        boxes = _combo_box(c, 0, "", it["pairs"], True, chip, draw=False) + 40
        boxes += _combo_box(c, 0, "", it["avoid"], False, chip, draw=False) if it.get("avoid") else 110
        total = name_h + ben_h + when_h + 20 + boxes
        if 190 + total <= bottom:
            break
    y = 190 + max(0, (bottom - 190 - total) * 0.3)
    y = draw_name(c, M, y, nl, fn, rgb(it_t.accent), int(ns * 0.98), gap=20)
    if ben_h:
        y = draw_lines(c.d, M, y, bl, fb, c.muted, int(bs * 1.3)) + 26
    if it.get("when"):
        _clock(c, M + 22, y + 22, 22, rgb(t.accent))
        c.d.text((M + 62, y + 22), f"When: {it['when']}", font=F(SANS_SB, 36), fill=c.ink, anchor="lm")
        y += 90
    y += 20
    y = _combo_box(c, y, "Pairs well with", it["pairs"], True, chip) + 40
    if it.get("avoid"):
        _combo_box(c, y, "Space these out", it["avoid"], False, chip)
    else:
        _text_block(c, M, y, note, SANS, W - 2 * M, 2, 36, 28, c.muted, lh=1.35)
    c.dots(idx, n)
    return c


def render_combo(topic, info, number, handle) -> list[Card]:
    items = topic.data["items"]
    n = len(items) + 2
    out = [cb_cover(items, number, handle, n)]
    out += [cb_item(it, handle, i + 2, n) for i, it in enumerate(items)]
    out.append(_cta(Card(COMBO, dark=True), "Save your cheat sheet", "for the next time you layer.", handle, n, n,
                    "for ingredient know-how", disclaimer=NOT_ADVICE))
    return out


# ---------------------------------------------------------------------------
# Seoul seasons
# ---------------------------------------------------------------------------
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()


def _season_deco(c: Card, sid: str, t: Theme):
    if sid == "summer":
        _sun(c, W - 200, 300, 80, rgb(t.accent, 170))
    elif sid == "winter":
        for i in range(6):
            a = i * math.pi / 3
            c.d.line((W - 200, 300, W - 200 + math.cos(a) * 120, 300 + math.sin(a) * 120), fill=rgb(t.accent, 170), width=10)
        c.d.ellipse((W - 225, 275, W - 175, 325), fill=rgb(t.accent, 170))
    elif sid == "autumn":
        for i, (x, y, r) in enumerate(((W - 260, 250, 70), (W - 150, 360, 50), (W - 290, 410, 40))):
            c.d.ellipse((x - r, y - r * 0.6, x + r, y + r * 0.6), fill=rgb(t.accent, 130 + i * 40))
    else:
        for i in range(5):
            a = i * 2 * math.pi / 5 - math.pi / 2
            cx, cy = W - 200 + math.cos(a) * 60, 300 + math.sin(a) * 60
            c.d.ellipse((cx - 55, cy - 55, cx + 55, cy + 55), fill=rgb(t.accent, 110))
        c.d.ellipse((W - 235, 265, W - 165, 335), fill=rgb(t.dark, 200))


def ss_cover(t, d, number, handle, n) -> Card:
    c = Card(t)
    c.header(handle, 1, n)
    _season_deco(c, d["id"], t)
    y = _kicker(c, 196, f"SEOUL SEASONS · NO.{number}") + 30
    months = d.get("months", [])
    if months:
        c.label(M, y, f"{MONTHS[months[0] - 1]} – {MONTHS[months[-1] - 1]}", size=24)
    y = 470
    c.d.text((M, y), d["name"], font=F(SERIF, 190), fill=c.ink, anchor="la")
    y += 200
    c.d.text((M, y), "in Seoul", font=F(SERIF_I, 110), fill=rgb(t.accent), anchor="la")
    y += 170
    c.d.rectangle((M, y, M + 96, y + 6), fill=rgb(t.accent))
    y += 46
    _text_block(c, M, y, d["hook"], SERIF, W - 2 * M, 3, 58, 42, c.ink, lh=1.12)
    _swipe(c, "Swipe for your season plan")
    c.dots(1, n)
    return c


def ss_list(t, label, title, items, handle, idx, n, numbered=False, extra=None) -> Card:
    c = Card(t)
    c.header(handle, idx, n)
    y = _title_block(c, label, title, size=86) + 50
    bottom = H - 190 - (170 if extra else 0)
    if numbered:
        _numbered(c, y, items, bottom)
    else:
        _checks(c, y, items, bottom, size=40)
    if extra:
        lbl, chips = extra
        c.label(M, H - 330, lbl, color=rgb(t.accent), size=22)
        _chips(c, M, H - 290, chips, W - 2 * M, F(SANS_M, 30), c.ink, bg=rgb(t.soft))
    c.dots(idx, n)
    return c


def render_season(topic, info, number, handle, lib) -> list[Card]:
    from .series import key_names
    d = topic.data
    t = series_theme(topic)
    names = key_names(d, lib)
    plan = ["cover", "weather", "skin", "hair"] + (["where"] if info.products else []) + ["cta"]
    n = len(plan)
    out = []
    for idx, name in enumerate(plan, 1):
        if name == "cover":
            out.append(ss_cover(t, d, number, handle, n))
        elif name == "weather":
            out.append(ss_list(t, "The season", "What it does to skin", d["weather"], handle, idx, n, numbered=True))
        elif name == "skin":
            out.append(ss_list(t, "Your skin plan", "Swap this in", d["skin"], handle, idx, n))
        elif name == "hair":
            out.append(ss_list(t, "Hair & scalp", "Don't forget your scalp", d["hair"], handle, idx, n,
                               extra=("Ingredients to reach for", names) if names else None))
        elif name == "where":
            out.append(ing_products(t, {"name": d["name"]}, info.products, number, handle, idx, n,
                                    title=f"{d['name']} picks"))
        else:
            out.append(_cta(Card(t, dark=True), "Save for the season", f"and check back when {d['name'].lower()} ends.",
                            handle, idx, n, "for Seoul-tested skin know-how", number, info.has_links, NOT_ADVICE))
    return out


# ---------------------------------------------------------------------------
# Speak K-beauty
# ---------------------------------------------------------------------------
def _ko_fit(c: Card, text: str, max_w: float, size: int, min_size: int):
    for s in range(size, min_size - 1, -4):
        f = F(KO, s)
        if tw(c.d, text, f) <= max_w:
            return f
    return F(KO, min_size)


def kw_cover(d, number, handle, n) -> Card:
    t = WORDS
    c = Card(t)
    c.header(handle, 1, n)
    y = _kicker(c, 196, f"SPEAK K-BEAUTY · NO.{number}") + 90
    y = _text_block(c, M, y, d["title"], SERIF, W - 2 * M, 2, 150, 96, c.ink, lh=1.0) + 30
    y = _text_block(c, M, y, d["hook"], SANS_M, W - 2 * M, 2, 42, 32, c.muted, lh=1.3) + 60
    words = d["words"][:4]
    cols = 2
    cw = (W - 2 * M - 30) / cols
    rh = 170
    for i, w in enumerate(words):
        x = M + (i % cols) * (cw + 30)
        yy = y + (i // cols) * (rh + 26)
        if yy + rh > H - 180:
            break
        c.d.rounded_rectangle((x, yy, x + cw, yy + rh), 30, fill=rgb(t.surface))
        f = _ko_fit(c, w["ko"], cw - 60, 76, 40)
        c.d.text((x + 34, yy + 70), w["ko"], font=f, fill=rgb(t.accent), anchor="lm")
        fr, rl, _ = fit(c.d, w["rom"], SANS_M, cw - 68, 1, 28, 20, balance=False)
        c.d.text((x + 34, yy + 132), rl[0], font=fr, fill=c.muted, anchor="lm")
    _swipe(c, "Swipe to learn them")
    c.dots(1, n)
    return c


def kw_word(w, handle, idx, n) -> Card:
    t = WORDS
    c = Card(t)
    c.header(handle, idx, n)
    c.d.rounded_rectangle((M, 170, W - M, 650), 44, fill=rgb(t.surface))
    f = _ko_fit(c, w["ko"], W - 2 * M - 120, 240, 90)
    c.d.text((W / 2, 385), w["ko"], font=f, fill=rgb(t.accent), anchor="mm")
    say = f"say: {w['rom']}"
    fs, sl, _ = fit(c.d, say, SERIF_I, W - 2 * M - 80, 1, 64, 36, balance=False)
    c.d.text((W / 2, 570), sl[0], font=fs, fill=c.muted, anchor="mm")
    fe, el, es = fit(c.d, w["en"], SERIF, W - 2 * M, 2, 112, 64)
    fnote, nl, ns = fit(c.d, w["note"], SANS, W - 2 * M, 4, 46, 32)
    block = 50 + len(el) * int(es * 1.05) + 34 + 46 + len(nl) * int(ns * 1.36)
    y = 650 + max(60, (H - 190 - 650 - block) / 2)
    c.label(M, y, "It means", color=rgb(t.accent), size=24)
    y += 50
    y = draw_lines(c.d, M, y, el, fe, c.ink, int(es * 1.05)) + 34
    c.d.rectangle((M, y, M + 96, y + 6), fill=rgb(t.accent))
    y += 46
    draw_lines(c.d, M, y, nl, fnote, c.ink, int(ns * 1.36))
    c.dots(idx, n)
    return c


def render_words(topic, info, number, handle) -> list[Card]:
    d = topic.data
    words = d["words"][:6]
    n = len(words) + 2
    out = [kw_cover(d, number, handle, n)]
    out += [kw_word(w, handle, i + 2, n) for i, w in enumerate(words)]
    out.append(_cta(Card(WORDS, dark=True), "Which word will you use first?", "Tell me in the comments.", handle, n, n,
                    "for a new K-beauty word set every month"))
    return out


# ---------------------------------------------------------------------------
# Monthly bestseller recap
# ---------------------------------------------------------------------------
def rc_cover(d, products, number, handle, n) -> Card:
    t = RECAP
    c = Card(t)
    c.header(handle, 1, n)
    # podium motif
    for i, (h, lbl) in enumerate(((170, "2"), (240, "1"), (120, "3"))):
        x = W - M - 3 * 96 + i * 96
        c.d.rounded_rectangle((x, 470 - h, x + 84, 470), 14, fill=rgb(t.accent, 110 + (60 if lbl == "1" else 0)))
        c.d.text((x + 42, 470 - h + 40), lbl, font=F(SERIF, 44), fill=rgb(t.on_accent), anchor="mm")
    y = _kicker(c, 196, f"MONTHLY RECAP · NO.{number}") + 30
    c.label(M, y, f"{d['label']} {d['year']}", size=24)
    y = 520
    y = _text_block(c, M, y, f"{d['label']}'s bestsellers", SERIF, W - 2 * M, 2, 140, 90, c.ink, lh=1.0) + 30
    y = _text_block(c, M, y, f"The products that stayed on top all month on Olive Young Global, across {d['weeks']} weekly lists",
                    SANS_M, W - 2 * M, 3, 38, 30, c.muted, lh=1.3) + 40
    top = [p for p in products if not p.get("climber")]
    if top:
        box = (M, y, W - M, y + 128)
        c.shadow_box(box, 30, t.surface, blur=18, dy=8, alpha=18)
        c.label(M + 36, y + 30, "Most consistent", color=rgb(t.accent), size=21)
        fv, vl, _ = fit(c.d, f"{top[0]['brand']} {top[0]['name']}", SANS_B, W - 2 * M - 72, 1, 40, 26, balance=False)
        c.d.text((M + 36, y + 88), vl[0], font=fv, fill=c.ink, anchor="lm")
    _swipe(c, "Swipe for the top 5")
    c.dots(1, n)
    return c


def rc_list(d, products, number, handle, idx, n) -> Card:
    t = RECAP
    c = Card(t)
    c.header(handle, idx, n)
    y = _title_block(c, f"{d['label']} · top 10 streaks", "Month's most consistent", size=76, max_lines=1) + 40
    items = [p for p in products if not p.get("climber")][:5]
    linked = any(p["links"] for p in items)
    bottom = H - (240 if linked else 190)
    row_h = (bottom - y) / max(len(items), 1)
    weeks = d["weeks"]
    for i, p in enumerate(items):
        top = y + row_h * i
        c.d.rounded_rectangle((M - 16, top + 6, W - M + 16, top + row_h - 6), 24, fill=rgb(t.surface, 200))
        cy = top + row_h / 2
        c.d.text((M + 20, cy), str(i + 1), font=F(SERIF, 70), fill=rgb(t.accent), anchor="lm")
        x = M + 110
        tracked(c.d, x, cy - 30, p["brand"].upper()[:28], F(SANS_B, 22), c.muted, 1.6)
        f, nl, _ = fit(c.d, p["name"], SANS_M, W - M - x - 20, 1, 32, 22, balance=False)
        c.d.text((x, cy - 16), nl[0], font=f, fill=c.ink, anchor="la")
        # week dots
        dx = x
        for k in range(weeks):
            on = k < (p.get("top10") or 0)
            c.d.ellipse((dx, cy + 34, dx + 18, cy + 52), fill=rgb(t.accent) if on else rgb(t.line))
            dx += 28
        c.d.text((dx + 10, cy + 43), f"top 10 for {p.get('top10', 0)} of {weeks} weeks", font=F(SANS, 24), fill=c.muted, anchor="lm")
    if linked:
        label = f"Links in my bio: No.{number}"
        fl = F(SANS_B, 32)
        yy = H - 215
        c.d.rounded_rectangle((M, yy, M + tw(c.d, label, fl) + 140, yy + 80), 40, fill=rgb(t.accent))
        c.d.text((M + 40, yy + 40), label, font=fl, fill=rgb(t.on_accent), anchor="lm")
        c.arrow(M + 40 + tw(c.d, label, fl) + 22, yy + 41, 44, rgb(t.on_accent), 5)
    c.dots(idx, n)
    return c


def rc_climber(d, handle, idx, n) -> Card:
    t = RECAP
    cl = d["climber"]
    c = Card(t)
    c.header(handle, idx, n)
    y = _title_block(c, "Biggest climber", "The one that rose all month", size=80) + 70
    _trend_up(c, M, y, 120, rgb(UP))
    y += 190
    fr = F(SERIF, 150)
    a = f"#{cl['from']}" if cl.get("from") else "30+"
    c.d.text((M, y), a, font=fr, fill=c.muted, anchor="la")
    ax = M + tw(c.d, a, fr) + 30
    c.arrow(ax, y + 85, 120, rgb(UP), 8)
    c.d.text((ax + 150, y), f"#{cl['to']}", font=fr, fill=rgb(UP), anchor="la")
    y += 220
    tracked(c.d, M, y, cl["brand"].upper()[:30], F(SANS_B, 28), c.muted, 2)
    _text_block(c, M, y + 24, cl["product"], SERIF, W - 2 * M, 3, 64, 44, c.ink, lh=1.1)
    c.dots(idx, n)
    return c


def render_recap(topic, info, number, handle) -> list[Card]:
    d = topic.data
    plan = ["cover", "list"] + (["climber"] if d.get("climber") else []) + ["cta"]
    n = len(plan)
    out = []
    for idx, name in enumerate(plan, 1):
        if name == "cover":
            out.append(rc_cover(d, info.products, number, handle, n))
        elif name == "list":
            out.append(rc_list(d, info.products, number, handle, idx, n))
        elif name == "climber":
            out.append(rc_climber(d, handle, idx, n))
        else:
            out.append(_cta(Card(RECAP, dark=True), "Did any make your cart?", "Tell me your best buy of the month.",
                            handle, idx, n, "for the weekly and monthly top lists", number, info.has_links,
                            "Rankings: Olive Young Global weekly bestseller lists."))
    return out


# ---------------------------------------------------------------------------
# Industry watch
# ---------------------------------------------------------------------------
def in_cover(d, number, handle, n) -> Card:
    from .series import month_label
    t = INDUSTRY
    c = Card(t)
    c.header(handle, 1, n)
    for i in range(4):  # radar rings
        r = 50 + i * 45
        c.d.ellipse((W - 250 - r, 360 - r, W - 250 + r, 360 + r), outline=rgb(t.accent, 180 - i * 35), width=6)
    c.d.ellipse((W - 270, 340, W - 230, 380), fill=rgb(t.accent))
    y = _kicker(c, 196, f"INDUSTRY WATCH · NO.{number}") + 30
    c.label(M, y, month_label(d), size=24)
    y = 560
    y = _text_block(c, M, y, d.get("title") or "What the K-beauty industry is betting on", SERIF, W - 2 * M, 3, 112, 80,
                    c.ink, lh=1.02) + 40
    y = _text_block(c, M, y, d.get("hook", ""), SANS_M, W - 2 * M, 2, 40, 30, c.muted, lh=1.3) + 40
    names = [i["name"] for i in d["items"][:4]]
    if y + _chips_height(c, names, W - 2 * M, F(SANS_M, 30)) < H - 200:
        _chips(c, M, y, names, W - 2 * M, F(SANS_M, 30), c.ink, bg=rgb(t.soft))
    _swipe(c, "Swipe for the signals")
    c.dots(1, n)
    return c


def in_item(it, k, handle, idx, n) -> Card:
    t = INDUSTRY
    c = Card(t)
    c.header(handle, idx, n)
    y = 180
    c.d.text((M, y), f"{k:02d}", font=F(SERIF, 120), fill=rgb(t.accent), anchor="la")
    y += 170
    fn, nl, ns = fit_words(c, it["name"], SERIF, W - 2 * M, 3, 120, 64)
    y = draw_name(c, M, y, nl, fn, c.ink, int(ns * 0.98), gap=40)
    fs, sl, ss = fit(c.d, it["signal"], SANS_M, W - 2 * M - 80, 3, 34, 26, balance=False)
    h = 90 + len(sl) * int(ss * 1.3) + 30
    c.shadow_box((M, y, W - M, y + h), 30, t.surface, blur=18, dy=8, alpha=18)
    c.label(M + 40, y + 34, "Spotted at", color=rgb(t.accent), size=22)
    draw_lines(c.d, M + 40, y + 80, sl, fs, c.ink, int(ss * 1.3))
    y += h + 50
    c.label(M, y, "Why it matters", color=rgb(t.accent), size=22)
    _text_block(c, M, y + 46, it["why"], SANS, W - 2 * M, 5, 40, 30, c.ink, lh=1.36)
    c.dots(idx, n)
    return c


def render_industry(topic, info, number, handle) -> list[Card]:
    d = topic.data
    items = d["items"][:5]
    n = len(items) + 2
    out = [in_cover(d, number, handle, n)]
    out += [in_item(it, k, handle, k + 1, n) for k, it in enumerate(items, 1)]
    out.append(_cta(Card(INDUSTRY, dark=True), "Early signals, not guarantees", "Which one would you try first?",
                    handle, n, n, "to see what's next in K-beauty",
                    disclaimer="From public trade press and expo pages. Some ideas never leave the lab."))
    return out


# ---------------------------------------------------------------------------
def render_series_post(topic: Topic, info: InfoCopy, number: int, handle: str, lib=None) -> list[Card]:
    k = topic.kind
    if k == "routine":
        return render_routine(topic, info, number, handle, lib)
    if k == "myth":
        return render_myth(topic, info, number, handle)
    if k == "combo":
        return render_combo(topic, info, number, handle)
    if k == "season":
        return render_season(topic, info, number, handle, lib)
    if k == "words":
        return render_words(topic, info, number, handle)
    if k == "recap":
        return render_recap(topic, info, number, handle)
    return render_industry(topic, info, number, handle)


PIN_KICKER = {"routine": "ROUTINE BUILDER", "myth": "MYTH VS. FACT", "combo": "MIX & MATCH", "season": "SEOUL SEASONS",
              "words": "SPEAK K-BEAUTY", "recap": "MONTHLY RECAP", "industry": "INDUSTRY WATCH"}


def render_series_pin(topic: Topic, info: InfoCopy, number: int, handle: str) -> Card:
    d = topic.data
    t = series_theme(topic)
    c = Card(t, size=(PW, PH))
    y = 110
    c.pill(M, y, PIN_KICKER[topic.kind], F(SANS_SB, 24), rgb(t.on_accent), rgb(t.accent), padx=22, pady=14)
    y += 100
    head = {"routine": d.get("title", ""), "myth": "Myth or fact?", "combo": "What to layer, what to space out",
            "season": d.get("title", ""), "words": f"Speak K-beauty: {d.get('title', '').lower()}",
            "recap": f"{d.get('label', '')}'s bestsellers", "industry": "What K-beauty makers are betting on"}[topic.kind]
    y = _text_block(c, M, y, head, SERIF, PW - 2 * M, 3, 96, 64, c.ink, lh=1.03) + 40
    if topic.kind == "words":
        for w in d["words"][:4]:
            f = _ko_fit(c, w["ko"], 360, 72, 40)
            c.d.text((M, y + 40), w["ko"], font=f, fill=rgb(t.accent), anchor="lm")
            fr, rl, _ = fit(c.d, f"{w['rom']} · {w['en']}", SANS_M, PW - 2 * M - 400, 2, 30, 22, balance=False)
            draw_lines(c.d, M + 400, y + 40 - len(rl) * 20, rl, fr, c.ink, 40)
            y += 130
    else:
        k_ = topic.kind
        its = d.get("items", [])
        if k_ == "routine":
            rows = d.get("am", [])
        elif k_ == "myth":
            rows = [f"{i['name']}: {i['fact']}" for i in its]
        elif k_ == "combo":
            rows = [f"{i['name']} + {', '.join(i['pairs'][:2])}" for i in its]
        elif k_ == "season":
            rows = d.get("skin", [])
        elif k_ == "recap":
            rows = [f"{p['brand']} {p['product']}" for p in d.get("top", [])]
        else:
            rows = [i["name"] for i in its]
        fb = F(SANS, 34)
        for k, r in enumerate(rows[:5], 1):
            bl = wrap(c.d, r, fb, PW - 2 * M - 70)[:3]
            if y + len(bl) * 46 > PH - 210:
                break
            c.d.text((M, y + 22), str(k), font=F(SERIF, 44), fill=rgb(t.accent), anchor="lm")
            draw_lines(c.d, M + 66, y, bl, fb, c.ink, 46)
            y += len(bl) * 46 + 28
    _pin_footer(c, "Tap for the full guide", handle, "#ad affiliate links" if info.has_links else "K-beauty 101")
    return c
