"""Card designs for the information posts (1080x1350 carousels + 1000x1500 Pinterest pins).

  Ingredient 101 (skin / hair) : each ingredient gets its own color, with a molecule or
                                 hair-strand motif. Cover → what it is → what it does →
                                 how to use → good to know → where to find it → save
  Seoul vs. abroad             : rose (Seoul) and blue (abroad) split cover, two lists, a Venn
  K-beauty history             : dark "time machine" look with gold years
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from PIL import Image, ImageDraw

from .editorial import HEAT_LABEL, NOT_ADVICE, InfoCopy, Topic
from .render import (H, M, PH, PW, SANS, SANS_B, SANS_M, SANS_SB, SERIF, SERIF_I, W, Card, Theme, F, _title,
                     balanced, cap_metrics, draw_lines, fit, rgb, slide_bullets, tracked, tracked_w, tw, wrap)

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# One color per ingredient (anything not listed gets a stable color from its name).
COLORS = {
    "pdrn": "#E0735A", "pn": "#D9735B", "nad": "#6B5BD2", "bdrn": "#C9A227", "snail-mucin": "#7A9E9F",
    "spicule": "#3E8FB0", "txa": "#C06C84", "mugwort": "#6A8D4E", "glutathione": "#D4A017",
    "heartleaf": "#4F9D69", "retinal": "#D9822B", "panthenol": "#4A90A4", "galactomyces": "#B08968",
    "centella": "#5B8C5A", "beta-glucan": "#A68A64", "green-tea": "#5E8C31", "exosome": "#8A6FDF",
    "peptide": "#D46A92", "rice": "#B7A57A", "niacinamide": "#3D7DCA", "collagen": "#E07A8B",
    "ceramides": "#8C7AA9", "propolis": "#D39B2A", "azelaic-acid": "#B5566B",
    "rosemary": "#557A5C", "lpp-protein": "#9C6B4E", "rice-water": "#A89A74", "salicylic-acid": "#4C8DAE",
    "dexpanthenol": "#4A90A4", "caffeine": "#7B5236", "menthol": "#2E9C8F", "scalp-peptides": "#B5657F",
    "ginseng": "#B0793A", "probiotics": "#6C8EBF", "biotin": "#8C6BB1", "argan-oil": "#C08A3E",
    "copper-peptide": "#2C6FB5", "nmn": "#A0527A",
}
FALLBACK_COLORS = ["#C0584F", "#3F7F9F", "#6E8B3D", "#8A5FB0", "#C0873A", "#3E8E7E", "#B25C84"]

SEOUL, ABROAD = "#B8475F", "#2F5D8C"
SEOUL_LIGHT, ABROAD_LIGHT = "#F08FA6", "#8FB9E6"
VERSUS = Theme(bg="#F5F0EA", surface="#FFFFFF", ink="#221A1F", muted="#6B5F65", accent=SEOUL, on_accent="#FFFFFF",
               soft="#EFE3DC", dark="#221A1F", on_dark="#F5F0EA", dark_muted="#B9ADB3", line="#E2D7CF")
HISTORY = Theme(bg="#17162A", surface="#222040", ink="#F3EEE3", muted="#A9A4BD", accent="#E2B65C",
                on_accent="#17162A", soft="#2D2A4E", dark="#0E0D1C", on_dark="#F3EEE3", dark_muted="#A9A4BD",
                line="#3A3760")


# ---------------------------------------------------------------------------
# color helpers
# ---------------------------------------------------------------------------
def _mix(a, b, t: float) -> tuple:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _hex(c) -> str:
    return "#%02X%02X%02X" % tuple(c[:3])


def _lum(c) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def theme_from(accent_hex: str) -> Theme:
    """A full, readable palette from one color (white text on the accent, dark text on the tints)."""
    a = rgb(accent_hex)[:3]
    while contrast(a, WHITE) < 4.6:
        a = _mix(a, BLACK, 0.06)
    bg = _mix(a, WHITE, 0.93)
    muted = _mix(a, (70, 70, 70), 0.55)
    while contrast(muted, bg) < 5.0:
        muted = _mix(muted, BLACK, 0.08)
    return Theme(bg=_hex(bg), surface="#FFFFFF", ink=_hex(_mix(a, BLACK, 0.80)), muted=_hex(muted), accent=_hex(a),
                 on_accent="#FFFFFF", soft=_hex(_mix(a, WHITE, 0.82)), dark=_hex(_mix(a, BLACK, 0.72)),
                 on_dark=_hex(bg), dark_muted=_hex(_mix(a, WHITE, 0.55)), line=_hex(_mix(a, WHITE, 0.72)))


def ingredient_theme(entry: dict) -> Theme:
    ident = entry.get("id", entry.get("name", ""))
    color = COLORS.get(ident) or FALLBACK_COLORS[int(hashlib.sha1(ident.encode()).hexdigest(), 16) % len(FALLBACK_COLORS)]
    return theme_from(color)


# ---------------------------------------------------------------------------
# small drawing helpers
# ---------------------------------------------------------------------------
def _outline_pill(c: Card, x, y, text, f, color, width=3, padx=22, pady=14, tr=2.2) -> tuple[float, float]:
    cap, _ = cap_metrics(f)
    w = tracked_w(c.d, text, f, tr) + padx * 2
    h = cap + pady * 2
    c.d.rounded_rectangle((x, y, x + w, y + h), h / 2, outline=color, width=width)
    tracked(c.d, x + padx, y + pady + cap, text, f, color, tr)
    return w, h


def _chips(c: Card, x, y, items, max_w, f, fg, bg=None, outline=None, gap=14, padx=24, pady=14) -> float:
    """Pills that wrap onto new rows. Returns the y below the last row."""
    cap, _ = cap_metrics(f)
    h = cap + pady * 2 + 6
    cx, cy = x, y
    for it in items:
        w = tw(c.d, it, f) + padx * 2
        if cx > x and cx + w > x + max_w:
            cx, cy = x, cy + h + gap
        box = (cx, cy, cx + w, cy + h)
        if bg is not None:
            c.d.rounded_rectangle(box, h / 2, fill=bg)
        if outline is not None:
            c.d.rounded_rectangle(box, h / 2, outline=outline, width=3)
        c.d.text((cx + padx, cy + h / 2), it, font=f, fill=fg, anchor="lm")
        cx += w + gap
    return cy + h


def _chips_height(c: Card, items, max_w, f, gap=14, padx=24, pady=14) -> float:
    cap, _ = cap_metrics(f)
    h = cap + pady * 2 + 6
    rows, cx = 1, 0
    for it in items:
        w = tw(c.d, it, f) + padx * 2
        if cx > 0 and cx + w > max_w:
            rows, cx = rows + 1, 0
        cx += w + gap
    return rows * h + (rows - 1) * gap


def _swipe(c: Card, text="Swipe to learn", y=None, color=None):
    fs = F(SANS_M, 30)
    y = y or c.h - 150
    color = color or c.ink
    c.d.text((M, y), text, font=fs, fill=color, anchor="ls")
    c.arrow(M + tw(c.d, text, fs) + 22, y - 10, 54, color, 4)


def _molecule(c: Card, cx, cy, r):
    t = c.t
    c.d.ellipse((cx - r * 1.9, cy - r * 1.9, cx + r * 1.9, cy + r * 1.9), fill=rgb(t.soft))
    pts = [(cx + r * math.cos(math.pi / 6 + i * math.pi / 3), cy + r * math.sin(math.pi / 6 + i * math.pi / 3)) for i in range(6)]
    col = rgb(t.accent, 170)
    c.d.line(pts + [pts[0]], fill=col, width=7, joint="curve")
    c.d.ellipse((cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55), outline=rgb(t.accent, 110), width=5)
    branches = [(pts[5], (pts[5][0] + r * 0.9, pts[5][1] - r * 0.5)), (pts[2], (pts[2][0] - r * 0.95, pts[2][1] + r * 0.45)),
                (pts[1], (pts[1][0] + r * 0.1, pts[1][1] + r * 0.95))]
    for a, b in branches:
        c.d.line((a, b), fill=col, width=7)
        c.d.ellipse((b[0] - r * 0.2, b[1] - r * 0.2, b[0] + r * 0.2, b[1] + r * 0.2), fill=rgb(t.accent, 200))
    for (px, py) in pts:
        c.d.ellipse((px - r * 0.13, py - r * 0.13, px + r * 0.13, py + r * 0.13), fill=rgb(t.accent))


def _strands(c: Card, x0, y0, w, h):
    t = c.t
    c.d.ellipse((x0 + w * 0.15, y0 - h * 0.1, x0 + w * 1.1, y0 + h * 0.95), fill=rgb(t.soft))
    for i in range(6):
        pts = []
        base = y0 + h * 0.15 + i * h * 0.12
        for k in range(0, 61):
            px = x0 + w * k / 60
            py = base + math.sin(k / 60 * math.pi * 2.2 + i * 0.5) * h * 0.09 + (k / 60) ** 2 * h * 0.12
            pts.append((px, py))
        c.d.line(pts, fill=rgb(t.accent, 90 + i * 22), width=6, joint="curve")


def _motif(c: Card, area: str, scale: float = 1.0):
    if area == "hair":
        _strands(c, c.w - 470 * scale, 96, 470 * scale, 340 * scale)
    else:
        _molecule(c, c.w - 215 * scale, 250 * scale, 92 * scale)


def _text_block(c: Card, x, y, text, font, max_w, max_lines, size, min_size, color, lh=1.2, balance=True):
    f, lines, s = fit(c.d, text, font, max_w, max_lines, size, min_size, balance=balance)
    return draw_lines(c.d, x, y, lines, f, color, int(s * lh))


def fit_words(c: Card, text, font, max_w, max_lines, size, min_size):
    """Like fit(), but never breaks a word in two (for big names like 'Salicylic acid')."""
    for s_ in range(size, min_size - 1, -2):
        f = F(font, s_)
        if all(tw(c.d, w, f) <= max_w for w in text.split()):
            lines = balanced(c.d, text, f, max_w)
            if len(lines) <= max_lines:
                return f, lines, s_
    return fit(c.d, text, font, max_w, max_lines, min_size, min_size)


def draw_name(c: Card, x, y, lines, f, fill, lh, gap=26) -> float:
    """Big display text; returns the y just below the lowest ink (descenders of g/p/y included) + gap."""
    draw_lines(c.d, x, y, lines, f, fill, lh)
    bottom = f.getbbox(lines[-1], anchor="la")[3] if lines else 0
    return y + (len(lines) - 1) * lh + max(bottom, f.size * 0.75) + gap


def _fits(c: Card, text, font, max_w, max_lines, size) -> bool:
    return len(wrap(c.d, text, F(font, size), max_w)) <= max_lines


def _icon_bang(c: Card, cx, cy, r, color):
    c.d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=4)
    c.d.text((cx, cy + 2), "!", font=F(SANS_B, int(r * 1.3)), fill=color, anchor="mm")


def _icon_x(c: Card, cx, cy, s, color, width=6):
    c.d.line((cx - s, cy - s, cx + s, cy + s), fill=color, width=width)
    c.d.line((cx - s, cy + s, cx + s, cy - s), fill=color, width=width)


def _clock(c: Card, cx, cy, r, color):
    c.d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=4)
    c.d.line((cx, cy, cx, cy - r * 0.6), fill=color, width=4)
    c.d.line((cx, cy, cx + r * 0.45, cy + r * 0.2), fill=color, width=4)


def _trend_up(c: Card, x, y, s, color):
    c.d.line((x, y + s, x + s * 0.45, y + s * 0.45, x + s * 0.7, y + s * 0.7, x + s * 1.2, y), fill=color, width=4, joint="curve")
    c.d.polygon([(x + s * 1.25, y - 4), (x + s * 0.85, y), (x + s * 1.2, y + s * 0.4)], fill=color)


# ---------------------------------------------------------------------------
# Ingredient 101
# ---------------------------------------------------------------------------
def ing_cover(t: Theme, d: dict, number: int, handle: str, n: int, photo=None) -> Card:
    area = d.get("area", "skin")
    if photo is not None:  # photo cover: full-bleed picture, shaded, light text
        from .stock import cover_bg
        c = Card(t, dark=True)
        c.img.paste(cover_bg(photo, (W, H)), (0, 0))
        c.d = ImageDraw.Draw(c.img, "RGBA")
    else:
        c = Card(t)
        _motif(c, area)
    c.header(handle, 1, n)
    y = 196
    kind = "HAIR & SCALP 101" if area == "hair" else "INGREDIENT 101"
    _, ph = c.pill(M, y, f"{kind} · NO.{number}", F(SANS_SB, 24), rgb(t.on_accent), rgb(t.accent), padx=22, pady=14)
    y += ph + 18
    heat = HEAT_LABEL.get(d.get("heat", ""), "")
    if heat:
        _, h2 = _outline_pill(c, M, y, heat.upper(), F(SANS_SB, 22), c.ink if photo is not None else rgb(t.accent))
        y += h2
    y += 56
    limit = H - 270
    for name_size, hook_size in ((220, 68), (196, 64), (172, 60), (150, 56), (128, 52), (110, 48)):
        fn, nl, ns = fit_words(c, d["name"], SERIF, W - 2 * M, 2, name_size, 90)
        sub_h = (50 if d.get("full_name") else 0) + (62 if d.get("nickname") else 0)
        fh, hl, hs = fit(c.d, d["hook"], SERIF, W - 2 * M, 3, hook_size, 44)
        total = len(nl) * int(ns * 0.98) + 34 + sub_h + 30 + 50 + len(hl) * int(hs * 1.1)
        if y + total <= limit:
            break
    y += max(0, (limit - y - total) * 0.4)
    y = draw_name(c, M, y, nl, fn, c.ink, int(ns * 0.98), gap=22)
    if d.get("full_name"):
        ff, fl, _ = fit(c.d, d["full_name"], SANS_M, W - 2 * M, 1, 36, 26, balance=False)
        c.d.text((M, y), fl[0], font=ff, fill=c.muted, anchor="la")
        y += 50
    if d.get("nickname"):
        fk, kl, _ = fit(c.d, f"a.k.a. {d['nickname']}", SERIF_I, W - 2 * M, 1, 46, 32, balance=False)
        c.d.text((M, y), kl[0], font=fk, fill=c.ink if photo is not None else rgb(t.accent), anchor="la")
        y += 62
    y += 30
    c.d.rectangle((M, y, M + 96, y + 6), fill=rgb(t.accent))
    y += 50
    draw_lines(c.d, M, y, hl, fh, c.ink, int(hs * 1.1))
    if d.get("heat_note"):
        _trend_up(c, M, H - 232, 30, c.ink if photo is not None else rgb(t.accent))
        fnote, nl2, _ = fit(c.d, d["heat_note"], SANS_M, W - 2 * M - 60, 1, 28, 22, balance=False)
        c.d.text((M + 52, H - 214), nl2[0], font=fnote, fill=c.muted, anchor="lm")
    _swipe(c)
    c.dots(1, n)
    return c


def ing_what(t: Theme, d: dict, handle: str, idx: int, n: int) -> Card:
    c = Card(t)
    c.header(handle, idx, n)
    y = _title(c, "What is it?", f"Meet {d['name']}", max_lines=1, size=84) + 40
    chips_f = F(SANS_M, 30)
    best = d.get("best_for", [])[:3]
    chips_h = _chips_height(c, best, W - 2 * M, chips_f)
    fo, ol, os_ = fit(c.d, d.get("origin", ""), SANS, W - 2 * M - 80, 2, 34, 26, balance=False)
    origin_h = 72 + len(ol) * int(os_ * 1.25) + 34
    rest = origin_h + 50 + 40 + chips_h + 40 + 44
    size = 64
    while size > 38 and len(wrap(c.d, d["what_it_is"], F(SERIF, size), W - 2 * M)) * int(size * 1.18) > H - 170 - y - rest - 60:
        size -= 2
    f_def = F(SERIF, size)
    def_lines = balanced(c.d, d["what_it_is"], f_def, W - 2 * M)
    used = len(def_lines) * int(size * 1.18) + 60 + rest
    gap = max(0, (H - 170 - y - used) / 3)
    y = draw_lines(c.d, M, y + gap * 0.5, def_lines, f_def, c.ink, int(size * 1.18)) + 60 + gap
    box = (M, y, W - M, y + origin_h)
    c.shadow_box(box, 32, t.surface, blur=18, dy=8, alpha=18)
    c.label(M + 40, y + 34, "Comes from", color=rgb(t.accent), size=22)
    draw_lines(c.d, M + 40, y + 72, ol, fo, c.ink, int(os_ * 1.25))
    y = box[3] + 50 + gap
    c.label(M, y, "Best for", color=rgb(t.accent), size=22)
    y = _chips(c, M, y + 40, best, W - 2 * M, chips_f, c.ink, bg=rgb(t.soft)) + 40
    _clock(c, M + 20, y + 20, 20, rgb(t.accent))
    fw = F(SANS_SB, 32)
    c.d.text((M + 56, y + 20), f"When: {d.get('when', '')}", font=fw, fill=c.ink, anchor="lm")
    c.dots(idx, n)
    return c


def ing_how(t: Theme, d: dict, handle: str, idx: int, n: int) -> Card:
    c = Card(t)
    c.header(handle, idx, n)
    y = _title(c, "How to use it", "Add it to your routine", max_lines=2, size=80) + 44
    fw = F(SANS_SB, 30)
    pw = tw(c.d, d.get("when", ""), fw) + 110
    c.d.rounded_rectangle((M, y, M + pw, y + 70), 35, fill=rgb(t.soft))
    _clock(c, M + 40, y + 35, 17, rgb(t.accent))
    c.d.text((M + 72, y + 35), d.get("when", ""), font=fw, fill=c.ink, anchor="lm")
    y += 116
    pairs, avoid = d.get("pairs_with", [])[:3], d.get("avoid_with", [])[:2]
    chip_f = F(SANS_M, 30)
    bottom_h = 0
    if pairs:
        bottom_h += 44 + _chips_height(c, pairs, W - 2 * M - 80, chip_f) + 40
    if avoid:
        bottom_h += 44 + _chips_height(c, avoid, W - 2 * M - 80, chip_f) + 30
    bottom_h += 40 if bottom_h else 0
    steps = d.get("how_to_use", [])[:3]
    circle, tx = 64, M + 64 + 34
    for size in (46, 44, 42, 40, 38, 36, 34, 32):
        f = F(SANS, size)
        lh = int(size * 1.34)
        blocks = [wrap(c.d, s, f, W - M - tx) for s in steps]
        heights = [max(circle, len(b) * lh) for b in blocks]
        if y + sum(heights) + 38 * (len(steps) - 1) <= H - 150 - bottom_h - 30:
            break
    step_gap = 38
    if len(steps) > 1:
        step_gap = max(38, min(96, (H - 150 - bottom_h - 60 - y - sum(heights)) / (len(steps) - 1)))
    for i, (b, h) in enumerate(zip(blocks, heights)):
        cy = y + circle / 2
        c.d.ellipse((M, cy - circle / 2, M + circle, cy + circle / 2), fill=rgb(t.accent))
        c.d.text((M + circle / 2, cy + 1), str(i + 1), font=F(SANS_B, 30), fill=rgb(t.on_accent), anchor="mm")
        text_h = len(b) * lh
        draw_lines(c.d, tx, y + (circle - min(text_h, circle)) / 2 - size * 0.1 if len(b) == 1 else y - 4, b, f, c.ink, lh)
        y += h + step_gap
    if bottom_h:
        top = H - 150 - bottom_h
        box = (M, top, W - M, H - 150)
        c.shadow_box(box, 32, t.surface, blur=18, dy=8, alpha=18)
        yy = top + 40
        if pairs:
            c.label(M + 40, yy, "Pairs well with", color=rgb(t.accent), size=22)
            yy = _chips(c, M + 40, yy + 40, pairs, W - 2 * M - 80, chip_f, rgb(t.accent), bg=rgb(t.soft)) + 40
        if avoid:
            c.label(M + 40, yy, "Don't mix with (same routine)", color=c.muted, size=22)
            _chips(c, M + 40, yy + 40, avoid, W - 2 * M - 80, chip_f, c.ink, outline=rgb(t.ink, 150))
    c.dots(idx, n)
    return c


def ing_know(t: Theme, d: dict, handle: str, idx: int, n: int) -> Card:
    c = Card(t)
    c.header(handle, idx, n)
    y = _title(c, "Good to know", "Before you try it", max_lines=1, size=84) + 40
    notes = d.get("good_to_know", [])[:3]
    myth, fact = d.get("myth", ""), d.get("fact", "")
    inner = W - 2 * M - 80
    for size in (38, 36, 34, 32, 30, 28):
        f = F(SANS, size)
        lh = int(size * 1.32)
        myth_l = wrap(c.d, myth, F(SERIF_I, size + 4), inner) if myth else []
        fact_l = wrap(c.d, fact, F(SANS_M, size), inner) if fact else []
        note_l = [wrap(c.d, s, f, W - 2 * M - 70) for s in notes]
        mh = (80 + len(myth_l) * int((size + 4) * 1.25) + 30) if myth else 0
        fh = (80 + len(fact_l) * lh + 30) if fact else 0
        nh = sum(len(b) * lh + 26 for b in note_l)
        total = mh + (18 if myth else 0) + fh + (40 if fact else 0) + nh
        if y + total <= H - 150:
            break
    if myth:
        box = (M, y, W - M, y + mh)
        c.d.rounded_rectangle(box, 30, fill=rgb(t.surface), outline=rgb(t.line), width=3)
        _icon_x(c, M + 52, y + 50, 11, c.muted, 5)
        c.label(M + 80, y + 38, "Myth", color=c.muted, size=24)
        draw_lines(c.d, M + 40, y + 80, myth_l, F(SERIF_I, size + 4), c.muted, int((size + 4) * 1.25))
        y += mh + 18
    if fact:
        box = (M, y, W - M, y + fh)
        c.d.rounded_rectangle(box, 30, fill=rgb(t.accent))
        c.check(M + 52, y + 50, 26, rgb(t.on_accent), 5)
        c.label(M + 80, y + 38, "Fact", color=rgb(t.on_accent), size=24)
        draw_lines(c.d, M + 40, y + 80, fact_l, F(SANS_M, size), rgb(t.on_accent), lh)
        y += fh + 40
    for b in note_l:
        _icon_bang(c, M + 20, y + size * 0.55, 18, rgb(t.accent))
        draw_lines(c.d, M + 62, y, b, f, c.ink, lh)
        y += len(b) * lh + 26
    c.dots(idx, n)
    return c


def ing_products(t: Theme, d: dict, products: list[dict], number: int, handle: str, idx: int, n: int,
                 title: str | None = None) -> Card:
    c = Card(t)
    c.header(handle, idx, n)
    linked = any(p["links"] for p in products)
    y = _title(c, "Where to find it", title or f"Products with {d['name']}", max_lines=2, size=76) + 44
    items = products[:3]
    avail = H - 150 - y - (130 if linked else 100)
    gap = 26
    box_h = min(250, (avail - gap * (len(items) - 1)) / max(len(items), 1))
    for i, p in enumerate(items):
        box = (M, y, W - M, y + box_h)
        c.shadow_box(box, 32, t.surface, blur=18, dy=8, alpha=18)
        c.d.text((M + 40, y + box_h / 2), f"{i + 1:02d}", font=F(SERIF, 74), fill=rgb(t.accent), anchor="lm")
        x = M + 170
        fb = F(SANS_B, 26)
        brand = p["brand"].upper()
        bl = fit(c.d, brand, SANS_B, W - M - x - 40, 1, 26, 20, balance=False)
        rows = 1 + (1 if p.get("rating") else 0)
        fn, nl, ns = fit(c.d, p["name"], SANS_M, W - M - x - 40, 2 if box_h > 200 else 1, 36, 26, balance=False)
        block = cap_metrics(fb)[0] + 18 + len(nl) * int(ns * 1.25) + (48 if rows > 1 else 0)
        yy = y + (box_h - block) / 2
        tracked(c.d, x, yy + cap_metrics(bl[0])[0], bl[1][0], bl[0], c.muted, 2)
        yy += cap_metrics(fb)[0] + 18
        yy = draw_lines(c.d, x, yy, nl, fn, c.ink, int(ns * 1.25))
        if p.get("rating"):
            c.star(x + 14, yy + 24, 15, rgb(t.accent))
            txt = f"{p['rating']:.1f}" + (f" · {p['reviews']:,} reviews" if p.get("reviews") else "")
            c.d.text((x + 40, yy + 24), txt, font=F(SANS, 28), fill=c.muted, anchor="lm")
        y += box_h + gap
    y += 20
    if linked:
        label = f"Links in my bio: No.{number}"
        fl = F(SANS_B, 34)
        pw = tw(c.d, label, fl) + 150
        c.d.rounded_rectangle((M, y, M + pw, y + 86), 43, fill=rgb(t.accent))
        c.d.text((M + 40, y + 43), label, font=fl, fill=rgb(t.on_accent), anchor="lm")
        c.arrow(M + 40 + tw(c.d, label, fl) + 24, y + 44, 44, rgb(t.on_accent), 5)
    else:
        note = "Spotted on Olive Young Global and other K-beauty shops. Not sponsored."
        _text_block(c, M, y, note, SANS, W - 2 * M, 2, 30, 24, c.muted, lh=1.35)
    c.dots(idx, n)
    return c


def ing_cta(t: Theme, d: dict, number: int, handle: str, idx: int, n: int, linked: bool) -> Card:
    c = Card(t, dark=True)
    c.header(handle, idx, n)
    c.d.ellipse((W - 420, -180, W + 220, 460), fill=rgb(t.accent))
    c.d.ellipse((W - 330, -90, W + 130, 370), fill=rgb(t.dark))
    y = 330
    c.d.text((M, y), "Save this", font=F(SERIF, 140), fill=c.ink, anchor="la")
    y += 180
    c.d.text((M, y), f"so you remember {d['name']}", font=fit(c.d, f"so you remember {d['name']}", SANS_M, W - 2 * M, 1, 46, 30)[0], fill=c.ink, anchor="la")
    y += 76
    c.d.text((M, y), "next time you shop.", font=F(SANS, 40), fill=c.muted, anchor="la")
    y += 120
    c.bookmark(M, y, 34, 46, c.ink)
    c.d.text((M + 60, y + 23), "Save  ·  Share with a friend", font=F(SANS_M, 36), fill=c.ink, anchor="lm")
    y += 110
    c.d.text((M, y), f"Follow @{handle}", font=F(SANS_B, 40), fill=c.ink, anchor="la")
    c.d.text((M, y + 58), "for a K-beauty lesson every day", font=F(SANS, 34), fill=c.muted, anchor="la")
    y += 150
    if linked:
        label = f"Shop: link in bio → No.{number}"
        fl = F(SANS_B, 38)
        c.d.rounded_rectangle((M, y, M + tw(c.d, label, fl) + 90, y + 96), 48, fill=rgb(t.accent))
        c.d.text((M + 45, y + 48), label, font=fl, fill=rgb(t.on_accent), anchor="lm")
    disc = ("#ad · Affiliate links. I may earn a small commission at no extra cost to you. " if linked else "") + NOT_ADVICE
    f, lines, s = fit(c.d, disc, SANS, W - 2 * M, 2, 26, 21)
    draw_lines(c.d, M, H - 196, lines, f, c.muted, int(s * 1.4))
    c.dots(idx, n)
    return c


def render_ingredient(topic: Topic, info: InfoCopy, number: int, handle: str, photo=None) -> list[Card]:
    d = topic.data
    t = ingredient_theme(d)
    plan = ["cover", "what", "does", "how", "know"] + (["where"] if info.products else []) + ["cta"]
    n = len(plan)
    area_word = "hair" if d.get("area") == "hair" else "skin"
    out = []
    for idx, name in enumerate(plan, 1):
        if name == "cover":
            out.append(ing_cover(t, d, number, handle, n, photo))
        elif name == "what":
            out.append(ing_what(t, d, handle, idx, n))
        elif name == "does":
            title = f"What it does for {area_word}" if len(d["name"]) > 12 else f"What {d['name']} can do"
            out.append(slide_bullets(t, "What it does", title, d["benefits"][:3], handle, idx, n_slides=n))
        elif name == "how":
            out.append(ing_how(t, d, handle, idx, n))
        elif name == "know":
            out.append(ing_know(t, d, handle, idx, n))
        elif name == "where":
            out.append(ing_products(t, d, info.products, number, handle, idx, n))
        else:
            out.append(ing_cta(t, d, number, handle, idx, n, info.has_links))
    return out


# ---------------------------------------------------------------------------
# Seoul vs. abroad
# ---------------------------------------------------------------------------
def vs_cover(d: dict, number: int, handle: str, n: int) -> Card:
    t = VERSUS
    c = Card(t)
    c.header(handle, 1, n)
    y = 190
    _, ph = c.pill(M, y, f"SEOUL VS. ABROAD · {d['year']}", F(SANS_SB, 24), rgb(t.on_dark), rgb(t.ink), padx=22, pady=14)
    c.label(M, y + ph + 34, d["topic"], size=24)
    y += ph + 96
    y = _text_block(c, M, y, d["title"], SERIF, W - 2 * M, 3, 104, 70, c.ink, lh=1.04) + 34
    y = _text_block(c, M, y, d["subtitle"], SANS, W - 2 * M, 2, 36, 28, c.muted, lh=1.3)
    top = max(y + 50, 720)
    bottom = H - 140
    half = (W - 2 * M - 24) / 2
    for i, (side, color, label, first) in enumerate(((0, SEOUL, "SEOUL", d["korea"][0]["name"]),
                                                     (1, ABROAD, "ABROAD", d["global"][0]["name"]))):
        x0 = M + i * (half + 24)
        c.d.rounded_rectangle((x0, top, x0 + half, bottom), 40, fill=rgb(color))
        tracked(c.d, x0 + 40, top + 70, label, F(SANS_SB, 28), rgb("#FFFFFF", 225), 4)
        c.d.text((x0 + 40, bottom - 150), "NO.1 BUZZ", font=F(SANS_SB, 22), fill=rgb("#FFFFFF", 190), anchor="ls")
        f, lines, s = fit(c.d, first, SERIF, half - 80, 2, 62, 40)
        draw_lines(c.d, x0 + 40, bottom - 136, lines, f, rgb("#FFFFFF"), int(s * 1.02))
    cy = (top + bottom) / 2 - 40
    c.d.ellipse((W / 2 - 66, cy - 66, W / 2 + 66, cy + 66), fill=rgb(t.ink), outline=rgb(t.bg), width=10)
    c.d.text((W / 2, cy + 4), "VS", font=F(SERIF, 54), fill=rgb(t.on_dark), anchor="mm")
    c.dots(1, n)
    return c


def vs_list(d: dict, side: str, handle: str, idx: int, n: int) -> Card:
    t = VERSUS
    c = Card(t)
    color = SEOUL if side == "korea" else ABROAD
    c.d.rectangle((0, 0, W, 360), fill=rgb(color))
    f = F(SANS_M, 28)
    c.d.text((M, 78), f"@{handle}", font=f, fill=rgb("#FFFFFF", 200), anchor="la")
    c.d.text((W - M, 78), f"{idx} / {n}", font=f, fill=rgb("#FFFFFF", 200), anchor="ra")
    c.label(M, 176, "Hot in Seoul" if side == "korea" else "Hot abroad", color=rgb("#FFFFFF", 220), size=26)
    title = "Seoul's buzz list" if side == "korea" else "The buzz abroad"
    c.d.text((M, 222), title, font=F(SERIF, 88), fill=rgb("#FFFFFF"), anchor="la")
    items = d[side][:5]
    both = {b.lower() for b in d.get("both", [])}
    y, bottom = 410, H - 150
    row = (bottom - y) / max(len(items), 1)
    for i, it in enumerate(items):
        yy = y + i * row
        c.d.text((M, yy + 58), str(i + 1), font=F(SERIF, 70), fill=rgb(color), anchor="ls")
        x = M + 90
        fn = F(SANS_B, 40)
        c.d.text((x, yy + 50), it["name"], font=fn, fill=c.ink, anchor="ls")
        if it["name"].lower() in both:
            _outline_pill(c, x + tw(c.d, it["name"], fn) + 20, yy + 14, "BOTH", F(SANS_SB, 18), rgb(t.muted), width=2, padx=14, pady=9, tr=2)
        fw, wl, ws = fit(c.d, it["why"], SANS, W - M - x, 2, 30, 24, balance=False)
        draw_lines(c.d, x, yy + 66, wl, fw, c.muted, int(ws * 1.3))
        if i < len(items) - 1:
            c.d.line((M, yy + row - 12, W - M, yy + row - 12), fill=rgb(t.line), width=2)
    c.dots(idx, n)
    return c


def vs_venn(d: dict, handle: str, idx: int, n: int) -> Card:
    t = VERSUS
    c = Card(t)
    c.header(handle, idx, n)
    title_bottom = _title(c, "Where they meet", "The overlap", max_lines=1, size=84)
    nxt = d.get("next", [])[:2]
    item_h = 100
    box_h = (78 + item_h * len(nxt) + 10) if nxt else 0
    box_top = H - 140 - box_h
    r = int(min(285, (box_top - 80 - (title_bottom + 30)) / 2))
    cy = title_bottom + 30 + r
    off = int(r * 0.6)
    cxl, cxr = W / 2 - off, W / 2 + off
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.ellipse((cxl - r, cy - r, cxl + r, cy + r), fill=rgb(SEOUL, 58))
    ld.ellipse((cxr - r, cy - r, cxr + r, cy + r), fill=rgb(ABROAD, 58))
    c.img.paste(layer, (0, 0), layer)
    c.d = ImageDraw.Draw(c.img, "RGBA")
    c.d.ellipse((cxl - r, cy - r, cxl + r, cy + r), outline=rgb(SEOUL), width=5)
    c.d.ellipse((cxr - r, cy - r, cxr + r, cy + r), outline=rgb(ABROAD), width=5)
    both = [b for b in d.get("both", [])][:3]
    bl = {b.lower() for b in both}
    left = [x["name"] for x in d["korea"] if x["name"].lower() not in bl][:4]
    right = [x["name"] for x in d["global"] if x["name"].lower() not in bl][:4]

    def column(names, cx, max_w, color, font):
        blocks = [wrap(c.d, s, font, max_w) for s in names]
        lh = int(font.size * 1.18)
        total = sum(len(b) * lh for b in blocks) + 22 * (len(blocks) - 1)
        yy = cy - total / 2
        for b in blocks:
            for ln in b:
                c.d.text((cx, yy + lh / 2), ln, font=font, fill=color, anchor="mm")
                yy += lh
            yy += 22

    column(left, cxl - int(r * 0.42), int(r * 0.74), rgb(t.ink), F(SANS_SB, 31))
    column(right, cxr + int(r * 0.42), int(r * 0.74), rgb(t.ink), F(SANS_SB, 31))
    if both:
        column(both, W / 2, int(r * 0.62), rgb(t.ink), F(SANS_B, 30))
    else:
        c.d.text((W / 2, cy), "none!", font=F(SERIF_I, 38), fill=c.muted, anchor="mm")
    tracked(c.d, cxl - tracked_w(c.d, "SEOUL", F(SANS_SB, 26), 4) / 2, cy + r + 48, "SEOUL", F(SANS_SB, 26), rgb(SEOUL), 4)
    tracked(c.d, cxr - tracked_w(c.d, "ABROAD", F(SANS_SB, 26), 4) / 2, cy + r + 48, "ABROAD", F(SANS_SB, 26), rgb(ABROAD), 4)
    if nxt:
        box = (M, box_top, W - M, H - 140)
        c.shadow_box(box, 32, t.surface, blur=18, dy=8, alpha=18)
        c.label(M + 40, box_top + 34, "Next to watch", color=rgb(SEOUL), size=22)
        yy = box_top + 82
        for x in nxt:
            fn = F(SANS_B, 34)
            c.d.text((M + 40, yy), x["name"], font=fn, fill=c.ink, anchor="la")
            fw, wl, ws = fit(c.d, x["why"], SANS, W - 2 * M - 80, 1, 29, 22, balance=False)
            c.d.text((M + 40, yy + 46), wl[0], font=fw, fill=c.muted, anchor="la")
            yy += item_h
    c.dots(idx, n)
    return c


def vs_cta(d: dict, handle: str, idx: int, n: int) -> Card:
    t = VERSUS
    c = Card(t, dark=True)
    c.header(handle, idx, n)
    y = 300
    c.d.text((M, y), "Team Seoul", font=F(SERIF, 124), fill=rgb(SEOUL_LIGHT), anchor="la")
    y += 140
    c.d.text((M, y), "or team", font=F(SERIF, 124), fill=c.ink, anchor="la")
    y += 140
    c.d.text((M, y), "abroad?", font=F(SERIF, 124), fill=rgb(ABROAD_LIGHT), anchor="la")
    y += 200
    c.d.text((M, y), "Tell me in the comments", font=F(SANS_M, 44), fill=c.ink, anchor="la")
    y += 64
    c.d.text((M, y), "and save this for your next haul.", font=F(SANS, 38), fill=c.muted, anchor="la")
    y += 110
    c.bookmark(M, y, 34, 46, c.ink)
    c.d.text((M + 60, y + 23), f"Follow @{handle} for more", font=F(SANS_M, 36), fill=c.ink, anchor="lm")
    f, lines, s = fit(c.d, d.get("basis", ""), SANS, W - 2 * M, 2, 26, 21)
    draw_lines(c.d, M, H - 196, lines, f, c.muted, int(s * 1.4))
    c.dots(idx, n)
    return c


def render_versus(topic: Topic, info: InfoCopy, number: int, handle: str) -> list[Card]:
    d = topic.data
    n = 5
    return [vs_cover(d, number, handle, n), vs_list(d, "korea", handle, 2, n), vs_list(d, "global", handle, 3, n),
            vs_venn(d, handle, 4, n), vs_cta(d, handle, 5, n)]


# ---------------------------------------------------------------------------
# K-beauty history ("time machine")
# ---------------------------------------------------------------------------
def _year_bar(c: Card, years: list[int], current: int, y: float):
    t = c.t
    x0, x1 = M + 10, W - M - 10
    c.d.line((x0, y, x1, y), fill=rgb(t.line), width=4)
    span = max(years[-1] - years[0], 1)
    for yr in years:
        x = x0 + (x1 - x0) * (yr - years[0]) / span
        if yr == current:
            c.d.ellipse((x - 15, y - 15, x + 15, y + 15), fill=rgb(t.accent))
        else:
            c.d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=rgb(t.muted, 160))
    f = F(SANS_M, 24)
    c.d.text((x0, y + 30), str(years[0]), font=f, fill=c.muted, anchor="la")
    c.d.text((x1, y + 30), str(years[-1]), font=f, fill=c.muted, anchor="ra")


def hist_year_cover(d: dict, part: int, total: int, years: list[int], number: int, handle: str, n: int) -> Card:
    t = HISTORY
    c = Card(t)
    c.header(handle, 1, n)
    y = 190
    pw, ph = c.pill(M, y, "K-BEAUTY TIME MACHINE", F(SANS_SB, 24), rgb(t.on_accent), rgb(t.accent), padx=22, pady=14)
    c.label(M + pw + 24, y + (ph - cap_metrics(F(SANS_SB, 22))[0]) / 2, f"Part {part} of {total}", size=22)
    y += ph + 40
    fh, hl, hs = fit_words(c, d["headline"], SERIF, W - 2 * M, 3, 100, 60)
    block = 380 + len(hl) * int(hs * 1.05)
    y += max(0, (H - 300 - y - block) * 0.45)
    c.d.text((M - 12, y - 40), str(d["year"]), font=F(SERIF, 350), fill=rgb(t.accent), anchor="la")
    y += 380
    draw_lines(c.d, M, y, hl, fh, c.ink, int(hs * 1.05))
    _year_bar(c, years, int(d["year"]), H - 250)
    _swipe(c, "Swipe back in time")
    c.dots(1, n)
    return c


def hist_story(d: dict, handle: str, idx: int, n: int) -> Card:
    t = HISTORY
    c = Card(t)
    c.header(handle, idx, n)
    y = _title(c, "The story", f"What happened in {d['year']}", max_lines=1, size=80) + 50
    words = d.get("buzzwords", [])[:3]
    chip_f = F(SANS_M, 32)
    chips_h = _chips_height(c, words, W - 2 * M, chip_f)
    size = 68
    while size > 40 and len(wrap(c.d, d["summary"], F(SERIF, size), W - 2 * M)) * size * 1.2 > H - 170 - y - chips_h - 140:
        size -= 2
    body = len(balanced(c.d, d["summary"], F(SERIF, size), W - 2 * M)) * int(size * 1.2) + 70 + 42 + chips_h
    y += max(0, (H - 170 - y - body) * 0.35)
    y = _text_block(c, M, y, d["summary"], SERIF, W - 2 * M, 8, size, 38, c.ink, lh=1.2) + 70
    c.label(M, y, "Buzzwords", color=rgb(t.accent), size=22)
    _chips(c, M, y + 42, words, W - 2 * M, chip_f, rgb(t.accent), outline=rgb(t.accent))
    c.dots(idx, n)
    return c


def hist_heroes(d: dict, handle: str, idx: int, n: int) -> Card:
    t = HISTORY
    c = Card(t)
    c.header(handle, idx, n)
    y = _title(c, "The heroes", "What everyone wanted", max_lines=1, size=80) + 66
    sections = [("Hero ingredients", d.get("hero_ingredients", [])[:3]), ("It-products", d.get("hero_products", [])[:3])]
    rows = sum(len(s[1]) for s in sections)
    row_h = min(116, (H - 150 - y - 2 * 70 - 40) / max(rows, 1) - 16)
    for label, items in sections:
        c.label(M, y, label, color=rgb(t.accent), size=22)
        y += 44
        for it in items:
            box = (M, y, W - M, y + row_h)
            c.d.rounded_rectangle(box, 26, fill=rgb(t.surface))
            c.d.ellipse((M + 36, y + row_h / 2 - 10, M + 56, y + row_h / 2 + 10), fill=rgb(t.accent))
            f, lines, _ = fit(c.d, it, SANS_SB, W - 2 * M - 120, 1, 42, 28, balance=False)
            c.d.text((M + 86, y + row_h / 2), lines[0], font=f, fill=c.ink, anchor="lm")
            y += row_h + 16
        y += 40
    c.dots(idx, n)
    return c


def hist_now(d: dict, handle: str, idx: int, n: int, now_year: int) -> Card:
    t = HISTORY
    c = Card(t)
    c.header(handle, idx, n)
    y = _title(c, f"{now_year} check-in", "Where is it now?", max_lines=1, size=80) + 60
    cy = y + 90
    a, b = M + 110, W - M - 110
    for i in range(int(a + 70), int(b - 70), 26):
        c.d.line((i, cy, i + 12, cy), fill=rgb(t.muted, 160), width=4)
    for x, label, filled in ((a, str(d["year"]), False), (b, str(now_year), True)):
        c.d.ellipse((x - 90, cy - 90, x + 90, cy + 90), fill=rgb(t.accent) if filled else rgb(t.surface),
                    outline=rgb(t.accent), width=5)
        c.d.text((x, cy + 4), label, font=F(SERIF, 56), fill=rgb(t.on_accent) if filled else rgb(t.accent), anchor="mm")
    y = cy + 150
    f, lines, s_ = fit(c.d, d["now"], SERIF, W - 2 * M, 6, 70, 40)
    y += max(0, (H - 170 - y - len(lines) * int(s_ * 1.2)) * 0.4)
    draw_lines(c.d, M, y, lines, f, c.ink, int(s_ * 1.2))
    c.dots(idx, n)
    return c


def hist_cta(handle: str, idx: int, n: int) -> Card:
    t = HISTORY
    c = Card(t)
    c.header(handle, idx, n)
    c.d.ellipse((W - 400, -160, W + 200, 440), fill=rgb(t.soft))
    y = 320
    y = _text_block(c, M, y, "When did you discover K-beauty?", SERIF, W - 2 * M, 3, 112, 80, c.ink, lh=1.04) + 40
    c.d.text((M, y), "Tell me the year in the comments.", font=F(SANS_M, 40), fill=rgb(t.accent), anchor="la")
    y += 140
    c.bookmark(M, y, 34, 46, c.ink)
    c.d.text((M + 60, y + 23), "Save the series", font=F(SANS_M, 36), fill=c.ink, anchor="lm")
    y += 100
    c.d.text((M, y), f"Follow @{handle}", font=F(SANS_B, 40), fill=c.ink, anchor="la")
    c.d.text((M, y + 58), "for the next stop in the time machine", font=F(SANS, 34), fill=c.muted, anchor="la")
    c.dots(idx, n)
    return c


def tl_cover(years: list[dict], number: int, handle: str, n: int) -> Card:
    t = HISTORY
    c = Card(t)
    c.header(handle, 1, n)
    y = 200
    c.pill(M, y, "K-BEAUTY TIME MACHINE", F(SANS_SB, 24), rgb(t.on_accent), rgb(t.accent), padx=22, pady=14)
    y += 130
    y = _text_block(c, M, y, "K-beauty through the years", SERIF, W - 2 * M, 3, 128, 90, c.ink, lh=1.02) + 50
    fy = F(SERIF, 120)
    a, b = str(years[0]["year"]), str(years[-1]["year"])
    c.d.text((M, y), a, font=fy, fill=rgb(t.accent), anchor="la")
    ax = M + tw(c.d, a, fy) + 30
    c.arrow(ax, y + 70, 110, rgb(t.accent), 7)
    c.d.text((ax + 140, y), b, font=fy, fill=rgb(t.accent), anchor="la")
    y += 190
    _text_block(c, M, y, f"{len(years)} years of what Korea (and the world) wanted, one year at a time.", SANS, W - 2 * M, 3, 38, 30, c.muted, lh=1.35)
    _swipe(c, "Swipe to time travel")
    c.dots(1, n)
    return c


def tl_years(chunk: list[dict], handle: str, idx: int, n: int) -> Card:
    t = HISTORY
    c = Card(t)
    c.header(handle, idx, n)
    top, bottom = 190, H - 160
    row = (bottom - top) / len(chunk)
    lx = M + 22
    c.d.line((lx, top + 40, lx, bottom - 40), fill=rgb(t.line), width=5)
    for i, y in enumerate(chunk):
        yy = top + i * row
        c.d.ellipse((lx - 16, yy + 44, lx + 16, yy + 76), fill=rgb(t.accent), outline=rgb(t.bg), width=6)
        x = M + 90
        c.d.text((x, yy + 90), str(y["year"]), font=F(SERIF, 84), fill=rgb(t.accent), anchor="ls")
        fh, hl, hs = fit(c.d, y["headline"], SANS_SB, W - M - x, 2, 42, 32, balance=False)
        yy2 = draw_lines(c.d, x, yy + 112, hl, fh, c.ink, int(hs * 1.22))
        fs, sl, ss = fit(c.d, y.get("summary", ""), SANS, W - M - x, 3, 29, 23, balance=False)
        draw_lines(c.d, x, yy2 + 12, sl, fs, c.muted, int(ss * 1.35))
    c.dots(idx, n)
    return c


def render_history(topic: Topic, info: InfoCopy, number: int, handle: str, lib_years: list[dict]) -> list[Card]:
    if topic.variant == "timeline":
        years = topic.data["years"]
        chunks = [years[i:i + 3] for i in range(0, len(years), 3)][:7]
        n = len(chunks) + 2
        cards = [tl_cover(years, number, handle, n)]
        cards += [tl_years(ch, handle, i + 2, n) for i, ch in enumerate(chunks)]
        cards.append(hist_cta(handle, n, n))
        return cards
    d = topic.data
    all_years = [int(y["year"]) for y in lib_years] or [int(d["year"])]
    part = all_years.index(int(d["year"])) + 1 if int(d["year"]) in all_years else 1
    n = 5
    return [hist_year_cover(d, part, len(all_years), all_years, number, handle, n), hist_story(d, handle, 2, n),
            hist_heroes(d, handle, 3, n), hist_now(d, handle, 4, n, max(all_years[-1], int(d["year"]))),
            hist_cta(handle, 5, n)]


# ---------------------------------------------------------------------------
def render_info_post(topic: Topic, info: InfoCopy, number: int, handle: str, out_dir: Path, lib_years=None,
                     lib=None, photo=None) -> list[Path]:
    from .editorial import NEW_KINDS
    if topic.kind in NEW_KINDS:
        from .render_series import render_series_post
        cards = render_series_post(topic, info, number, handle, lib)
    elif topic.kind in ("skin", "hair"):
        cards = render_ingredient(topic, info, number, handle, photo)
    elif topic.kind == "versus":
        cards = render_versus(topic, info, number, handle)
    elif topic.kind == "weekly":
        cards = render_weekly(topic, info, number, handle)
    else:
        cards = render_history(topic, info, number, handle, lib_years or [])
    paths = []
    for i, card in enumerate(cards, 1):
        p = out_dir / f"{i}.jpg"
        card.save(p)
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# "Star ingredient" card inside a product post
# ---------------------------------------------------------------------------
def slide_star(t: Theme, e: dict, handle: str, idx: int, n: int) -> Card:
    c = Card(t)
    c.header(handle, idx, n)
    it = ingredient_theme(e)
    c.d.ellipse((W - 330, 120, W + 60, 510), fill=rgb(it.soft))
    y = 180
    _, ph = c.pill(M, y, "STAR INGREDIENT", F(SANS_SB, 24), rgb(it.on_accent), rgb(it.accent), padx=22, pady=14)
    y += ph + 50
    fn, nl, ns = fit_words(c, e["name"], SERIF, W - 2 * M, 2, 150, 80)
    y = draw_name(c, M, y, nl, fn, rgb(it.accent), int(ns * 0.98), gap=24)
    sub = " · ".join(x for x in [e.get("full_name", ""), f"a.k.a. {e['nickname']}" if e.get("nickname") else ""] if x)
    if sub:
        fs, sl, _ = fit(c.d, sub, SANS_M, W - 2 * M, 1, 34, 24, balance=False)
        c.d.text((M, y), sl[0], font=fs, fill=c.muted, anchor="la")
        y += 60
    y += 20
    y = _text_block(c, M, y, e["what_it_is"], SANS, W - 2 * M, 5, 42, 30, c.ink, lh=1.36) + 50
    fb = F(SANS, 38)
    for b in e.get("benefits", [])[:2]:
        bl = wrap(c.d, b, fb, W - 2 * M - 70)[:2]
        if y + len(bl) * 48 > H - 190:
            break
        c.d.ellipse((M, y + 2, M + 44, y + 46), fill=rgb(it.soft))
        c.check(M + 22, y + 24, 22, rgb(it.accent), 4)
        draw_lines(c.d, M + 66, y, bl, fb, c.ink, 48)
        y += len(bl) * 48 + 22
    if e.get("heat_note"):
        _trend_up(c, M, H - 200, 26, rgb(it.accent))
        fnote, nl2, _ = fit(c.d, e["heat_note"], SANS_M, W - 2 * M - 60, 1, 26, 20, balance=False)
        c.d.text((M + 46, H - 184), nl2[0], font=fnote, fill=c.muted, anchor="lm")
    c.dots(idx, n)
    return c


# ---------------------------------------------------------------------------
# Pinterest pins (1000 x 1500)
# ---------------------------------------------------------------------------
def _pin_footer(c: Card, text: str, handle: str, note: str):
    t = c.t
    top = PH - 170
    c.d.rectangle((0, top, PW, PH), fill=rgb(t.dark))
    f = F(SERIF, 52)
    c.d.text((M, top + 62), text, font=f, fill=rgb(t.on_dark), anchor="lm")
    c.arrow(M + tw(c.d, text, f) + 26, top + 64, 44, rgb(t.on_dark), 5)
    c.d.text((M, top + 122), f"@{handle}  ·  {note}", font=F(SANS, 26), fill=rgb(t.dark_muted), anchor="lm")


def render_info_pin(topic: Topic, info: InfoCopy, number: int, handle: str, out_path: Path) -> Path:
    from .editorial import NEW_KINDS
    d = topic.data
    if topic.kind in NEW_KINDS:
        from .render_series import render_series_pin
        c = render_series_pin(topic, info, number, handle)
    elif topic.kind in ("skin", "hair"):
        t = ingredient_theme(d)
        c = Card(t, size=(PW, PH))
        _motif(c, d.get("area", "skin"), scale=0.95)
        y = 150
        kind = "HAIR & SCALP 101" if topic.kind == "hair" else "INGREDIENT 101"
        _, ph = c.pill(M, y, kind, F(SANS_SB, 24), rgb(t.on_accent), rgb(t.accent), padx=22, pady=14)
        y += ph + 18
        heat = HEAT_LABEL.get(d.get("heat", ""), "")
        if heat:
            y += _outline_pill(c, M, y, heat.upper(), F(SANS_SB, 22), rgb(t.accent))[1]
        y += 60
        fn, nl, ns = fit_words(c, d["name"], SERIF, PW - 2 * M, 2, 190, 90)
        y = draw_name(c, M, y, nl, fn, c.ink, int(ns * 0.98), gap=22)
        if d.get("full_name"):
            ff, fl, _ = fit(c.d, d["full_name"], SANS_M, PW - 2 * M, 1, 34, 24, balance=False)
            c.d.text((M, y), fl[0], font=ff, fill=c.muted, anchor="la")
            y += 60
        y = _text_block(c, M, y + 10, d["hook"], SERIF, PW - 2 * M, 3, 60, 44, c.ink, lh=1.1) + 44
        fb = F(SANS, 36)
        for b in d["benefits"][:3]:
            bl = wrap(c.d, b, fb, PW - 2 * M - 70)[:2]
            if y + len(bl) * 48 > PH - 200:
                break
            c.d.ellipse((M, y + 2, M + 44, y + 46), fill=rgb(t.soft))
            c.check(M + 22, y + 24, 22, rgb(t.accent), 4)
            draw_lines(c.d, M + 66, y, bl, fb, c.ink, 48)
            y += len(bl) * 48 + 24
        _pin_footer(c, "Tap for the full guide", handle, "#ad affiliate links" if info.has_links else "K-beauty 101")
    elif topic.kind == "versus":
        t = VERSUS
        c = Card(t, size=(PW, PH))
        y = 110
        c.pill(M, y, f"SEOUL VS. ABROAD · {d['year']}", F(SANS_SB, 24), rgb(t.on_dark), rgb(t.ink), padx=22, pady=14)
        y += 100
        y = _text_block(c, M, y, d["title"], SERIF, PW - 2 * M, 2, 92, 64, c.ink, lh=1.04) + 30
        c.label(M, y, d["topic"], size=24)
        y += 64
        half = (PW - 2 * M - 24) / 2
        col_top = y
        for i, (side, color, label) in enumerate((("korea", SEOUL, "SEOUL"), ("global", ABROAD, "ABROAD"))):
            x0 = M + i * (half + 24)
            c.d.rounded_rectangle((x0, col_top, x0 + half, PH - 210), 32, fill=rgb(t.surface))
            c.d.rounded_rectangle((x0, col_top, x0 + half, col_top + 96), 32, fill=rgb(color))
            c.d.rectangle((x0, col_top + 60, x0 + half, col_top + 96), fill=rgb(color))
            tracked(c.d, x0 + 30, col_top + 62, label, F(SANS_SB, 28), rgb("#FFFFFF"), 4)
            yy = col_top + 140
            for k, it in enumerate(d[side][:5], 1):
                c.d.text((x0 + 30, yy + 36), str(k), font=F(SERIF, 48), fill=rgb(color), anchor="ls")
                f, lines, s = fit(c.d, it["name"], SANS_SB, half - 100, 2, 34, 24, balance=False)
                draw_lines(c.d, x0 + 80, yy, lines, f, c.ink, int(s * 1.2))
                yy += max(96, len(lines) * int(s * 1.2) + 50)
        _pin_footer(c, "Tap to see why", handle, "K-beauty trends")
    elif topic.kind == "weekly":
        from .editorial import week_label
        t = WEEKLY
        c = Card(t, size=(PW, PH))
        y = 110
        c.pill(M, y, f"THIS WEEK · {week_label(d).upper()}", F(SANS_SB, 24), rgb(t.on_accent), rgb(t.accent), padx=22, pady=14)
        y += 100
        y = _text_block(c, M, y, "This week in K-beauty", SERIF, PW - 2 * M, 2, 96, 64, c.ink, lh=1.02) + 30
        sections = []
        kor = [r for r in d.get("korea", []) if r.get("index")][:5]
        if kor:
            sections.append(("Most searched in Korea", [r["name"] for r in kor]))
        if info.products:
            sections.append(("Top sellers abroad", [f"{p['brand']} {p['name']}" for p in info.products[:5]]))
        for label, names in sections:
            c.label(M, y, label, color=rgb(t.accent), size=24)
            y += 50
            for k, nm in enumerate(names, 1):
                c.d.text((M, y + 22), str(k), font=F(SERIF, 40), fill=rgb(t.accent), anchor="lm")
                f, lines, _ = fit(c.d, nm, SANS_M, PW - 2 * M - 60, 1, 32, 22, balance=False)
                c.d.text((M + 56, y + 22), lines[0], font=f, fill=c.ink, anchor="lm")
                y += 58
            y += 30
        _pin_footer(c, "Tap for the full top 10", handle, "#ad affiliate links" if info.has_links else "K-beauty trends")
    elif topic.variant == "timeline":
        t = HISTORY
        c = Card(t, size=(PW, PH))
        y = 110
        c.pill(M, y, "K-BEAUTY TIME MACHINE", F(SANS_SB, 24), rgb(t.on_accent), rgb(t.accent), padx=22, pady=14)
        y += 100
        y = _text_block(c, M, y, "K-beauty through the years", SERIF, PW - 2 * M, 2, 84, 60, c.ink, lh=1.04) + 30
        years = d["years"]
        row = (PH - 200 - y) / len(years)
        fs = F(SANS_M, min(32, int(row * 0.5)))
        for i, yr in enumerate(years):
            yy = y + i * row + row / 2
            c.d.text((M, yy), str(yr["year"]), font=F(SERIF, min(44, int(row * 0.7))), fill=rgb(t.accent), anchor="lm")
            f, lines, _ = fit(c.d, yr["headline"], SANS_M, PW - 2 * M - 150, 1, fs.size, 20, balance=False)
            c.d.text((M + 150, yy), lines[0], font=f, fill=c.ink, anchor="lm")
        _pin_footer(c, "Tap for the full story", handle, "K-beauty history")
    else:
        t = HISTORY
        c = Card(t, size=(PW, PH))
        y = 110
        c.pill(M, y, "K-BEAUTY TIME MACHINE", F(SANS_SB, 24), rgb(t.on_accent), rgb(t.accent), padx=22, pady=14)
        c.d.text((M - 10, y + 90), str(d["year"]), font=F(SERIF, 320), fill=rgb(t.accent), anchor="la")
        y += 470
        y = _text_block(c, M, y, d["headline"], SERIF, PW - 2 * M, 3, 88, 60, c.ink, lh=1.05) + 40
        fb = F(SANS, 34)
        for b in info.bullets[:3]:
            bl = wrap(c.d, b, fb, PW - 2 * M - 50)[:2]
            if y + len(bl) * 46 > PH - 210:
                break
            c.d.ellipse((M, y + 12, M + 20, y + 32), fill=rgb(t.accent))
            draw_lines(c.d, M + 44, y, bl, fb, c.ink, 46)
            y += len(bl) * 46 + 22
        _pin_footer(c, "Tap for the full story", handle, "K-beauty history")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c.img.save(out_path, "JPEG", quality=88, optimize=True, progressive=True)
    return out_path


# ---------------------------------------------------------------------------
# This week in K-beauty (Thursday): Korea search chart + Olive Young Global bestsellers
# ---------------------------------------------------------------------------
WEEKLY = theme_from("#3A56C5")
UP, DOWN = "#1E8E5A", "#B4474F"


def _tri(c: Card, x, cy, s, up: bool, color):
    pts = [(x, cy + s * 0.5), (x + s, cy + s * 0.5), (x + s / 2, cy - s * 0.5)] if up else \
          [(x, cy - s * 0.5), (x + s, cy - s * 0.5), (x + s / 2, cy + s * 0.5)]
    c.d.polygon(pts, fill=rgb(color))


def _delta(c: Card, x_right, cy, text, up: bool | None, f):
    """Right-aligned '▲ 12%' / '▼ 3' / 'NEW' label."""
    if up is None:
        w = tw(c.d, text, f) + 24
        c.d.rounded_rectangle((x_right - w, cy - 17, x_right, cy + 17), 17, fill=rgb(c.t.accent))
        c.d.text((x_right - w / 2, cy + 1), text, font=f, fill=rgb(c.t.on_accent), anchor="mm")
        return
    color = UP if up else DOWN
    tw_ = tw(c.d, text, f)
    c.d.text((x_right, cy + 1), text, font=f, fill=rgb(color), anchor="rm")
    _tri(c, x_right - tw_ - 26, cy, 18, up, color)


def wk_cover(d: dict, number: int, handle: str, n: int, products: list[dict]) -> Card:
    from .editorial import week_label
    t = WEEKLY
    c = Card(t)
    c.header(handle, 1, n)
    # rising bars motif
    for i, h in enumerate((90, 150, 120, 210, 280)):
        x = W - M - 5 * 58 + i * 58
        c.d.rounded_rectangle((x, 400 - h, x + 40, 400), 12, fill=rgb(t.accent, 90 + i * 30))
    y = 190
    _, ph = c.pill(M, y, f"THIS WEEK · NO.{number}", F(SANS_SB, 24), rgb(t.on_accent), rgb(t.accent), padx=22, pady=14)
    c.label(M, y + ph + 34, week_label(d), size=24)
    y = 430
    y = _text_block(c, M, y, "This week in K-beauty", SERIF, W - 2 * M, 2, 124, 90, c.ink, lh=1.0) + 26
    y = _text_block(c, M, y, "What Korea searched and what K-beauty fans abroad bought", SANS, W - 2 * M, 2, 36, 28, c.muted, lh=1.3) + 40
    kor = [r for r in d.get("korea", []) if r.get("index")]
    stats = []
    if kor:
        stats.append(("Most searched in Korea", kor[0]["name"]))
    if products:
        stats.append(("#1 bestseller abroad", f"{products[0]['brand']} {products[0]['name']}"))
    for label, value in stats:
        box = (M, y, W - M, y + 128)
        c.shadow_box(box, 30, t.surface, blur=18, dy=8, alpha=18)
        c.label(M + 36, y + 30, label, color=rgb(t.accent), size=21)
        fv, vl, _ = fit(c.d, value, SANS_B, W - 2 * M - 72, 1, 40, 26, balance=False)
        c.d.text((M + 36, y + 88), vl[0], font=fv, fill=c.ink, anchor="lm")
        y += 146
    if y < H - 175:
        _swipe(c, "Swipe for the full top 10")
    c.dots(1, n)
    return c


def wk_korea(d: dict, handle: str, idx: int, n: int) -> Card:
    from .editorial import week_label
    t = WEEKLY
    c = Card(t)
    c.header(handle, idx, n)
    y = _title(c, "Korea · search interest", "Most-searched ingredients", max_lines=1, size=74) + 30
    rows = [r for r in d.get("korea", []) if r.get("index")][:10]
    bottom = H - 190
    row_h = (bottom - y) / max(len(rows), 1)
    fn, fr, fd = F(SANS_SB, 34), F(SERIF, 44), F(SANS_B, 26)
    bar_x0, bar_x1 = M + 380, W - M - 170
    for i, r in enumerate(rows):
        cy = y + row_h * i + row_h / 2
        c.d.text((M, cy + 2), str(i + 1), font=fr, fill=rgb(t.accent), anchor="lm")
        f, nl, _ = fit(c.d, r["name"], SANS_SB, bar_x0 - M - 90, 1, 34, 24, balance=False)
        c.d.text((M + 70, cy), nl[0], font=f, fill=c.ink, anchor="lm")
        c.d.rounded_rectangle((bar_x0, cy - 11, bar_x1, cy + 11), 11, fill=rgb(t.soft))
        c.d.rounded_rectangle((bar_x0, cy - 11, bar_x0 + max(22, (bar_x1 - bar_x0) * r["index"] / 100), cy + 11), 11, fill=rgb(t.accent))
        ch = r.get("change")
        if ch is None:
            _delta(c, W - M, cy, "NEW", None, F(SANS_B, 20))
        elif ch == 0:
            c.d.text((W - M, cy), "0%", font=fd, fill=c.muted, anchor="rm")
        else:
            _delta(c, W - M, cy, f"{abs(ch)}%", ch > 0, fd)
    note = f"Naver search data (Korea), {week_label(d)} vs the week before. Top ingredient = 100."
    ff, lines, s = fit(c.d, note, SANS, W - 2 * M, 2, 25, 20)
    draw_lines(c.d, M, H - 175, lines, ff, c.muted, int(s * 1.35))
    c.dots(idx, n)
    return c


def wk_products(products: list[dict], number: int, handle: str, idx: int, n: int) -> Card:
    t = WEEKLY
    c = Card(t)
    c.header(handle, idx, n)
    y = _title(c, "Abroad · Olive Young Global", "Top bestsellers this week", max_lines=1, size=74) + 30
    items = products[:10]
    linked = any(p["links"] for p in items)
    bottom = H - (230 if linked else 190)
    row_h = (bottom - y) / max(len(items), 1)
    fr, fb, fd = F(SERIF, 44), F(SANS_B, 20), F(SANS_B, 26)
    for i, p in enumerate(items):
        top = y + row_h * i
        cy = top + row_h / 2
        if i % 2 == 0:
            c.d.rounded_rectangle((M - 16, top + 3, W - M + 16, top + row_h - 3), 18, fill=rgb(t.surface, 170))
        c.d.text((M, cy + 2), str(p.get("rank") or i + 1), font=fr, fill=rgb(t.accent), anchor="lm")
        x = M + 80
        tracked(c.d, x, cy - 10, p["brand"].upper()[:28], fb, c.muted, 1.6)
        f, nl, _ = fit(c.d, p["name"], SANS_M, W - M - x - 150, 1, 29, 22, balance=False)
        c.d.text((x, cy + 2), nl[0], font=f, fill=c.ink, anchor="la")
        r, pr = p.get("rank"), p.get("prev_rank")
        if r and pr is None:
            _delta(c, W - M, cy, "NEW", None, F(SANS_B, 20))
        elif r and pr and pr != r:
            _delta(c, W - M, cy, str(abs(pr - r)), pr > r, fd)
        else:
            c.d.text((W - M, cy), "–", font=fd, fill=c.muted, anchor="rm")
    if linked:
        label = f"Links in my bio: No.{number}"
        fl = F(SANS_B, 32)
        yy = H - 205
        c.d.rounded_rectangle((M, yy, M + tw(c.d, label, fl) + 140, yy + 80), 40, fill=rgb(t.accent))
        c.d.text((M + 40, yy + 40), label, font=fl, fill=rgb(t.on_accent), anchor="lm")
        c.arrow(M + 40 + tw(c.d, label, fl) + 22, yy + 41, 44, rgb(t.on_accent), 5)
    else:
        c.d.text((M, H - 170), "Olive Young Global bestseller list, this week.", font=F(SANS, 25), fill=c.muted, anchor="la")
    c.dots(idx, n)
    return c


def wk_spotlight(sp: dict, handle: str, idx: int, n: int) -> Card:
    t = WEEKLY
    c = Card(t)
    c.header(handle, idx, n)
    y = _title(c, "Rising this week", "Why everyone's searching it", max_lines=2, size=74) + 50
    c.pill(M, y, f"+{sp['change']}% IN KOREA" if sp.get("change") is not None else "NEW IN KOREA", F(SANS_B, 26),
           rgb(t.on_accent), rgb(UP), padx=24, pady=16, tr=1.5)
    y += 110
    fn, nl, ns = fit_words(c, sp["name"], SERIF, W - 2 * M, 2, 150, 80)
    y = draw_name(c, M, y, nl, fn, rgb(t.accent), int(ns * 0.98), gap=30)
    if sp.get("what_it_is"):
        y = _text_block(c, M, y, sp["what_it_is"], SANS, W - 2 * M, 5, 42, 30, c.ink, lh=1.36) + 40
    for b in sp.get("benefits", [])[:2]:
        fb = F(SANS, 36)
        bl = wrap(c.d, b, fb, W - 2 * M - 70)[:2]
        if y + len(bl) * 48 > H - 220:
            break
        c.d.ellipse((M, y + 2, M + 44, y + 46), fill=rgb(t.soft))
        c.check(M + 22, y + 24, 22, rgb(t.accent), 4)
        draw_lines(c.d, M + 66, y, bl, fb, c.ink, 48)
        y += len(bl) * 48 + 22
    if sp.get("more"):
        c.d.text((M, H - 180), sp["more"], font=F(SANS_M, 28), fill=c.muted, anchor="la")
    c.dots(idx, n)
    return c


def wk_cta(handle: str, idx: int, n: int, linked: bool, number: int = 0) -> Card:
    t = WEEKLY
    c = Card(t, dark=True)
    c.header(handle, idx, n)
    for i, h in enumerate((120, 200, 160, 280, 360)):
        x = W - M - 5 * 64 + i * 64
        c.d.rounded_rectangle((x, 520 - h, x + 44, 520), 14, fill=rgb(t.accent, 120 + i * 25))
    y = 600
    c.d.text((M, y), "See you next", font=F(SERIF, 110), fill=c.ink, anchor="la")
    c.d.text((M, y + 120), "Thursday", font=F(SERIF, 110), fill=rgb(t.dark_muted), anchor="la")
    y += 290
    c.bookmark(M, y, 34, 46, c.ink)
    c.d.text((M + 60, y + 23), "Save this week's list", font=F(SANS_M, 36), fill=c.ink, anchor="lm")
    c.d.text((M, y + 90), f"Follow @{handle} for the weekly top 10", font=F(SANS_B, 36), fill=c.ink, anchor="la")
    if linked:
        label = "Shop the top 10: link in bio → " + f"No.{number}" if number else "Shop the top 10: link in bio"
        fl = F(SANS_B, 38)
        c.d.rounded_rectangle((M, y + 148, M + tw(c.d, label, fl) + 90, y + 240), 46, fill=rgb(t.accent))
        c.d.text((M + 45, y + 194), label, font=fl, fill=rgb(t.on_accent), anchor="lm")
    disc = "#ad · Product links are affiliate links; I may earn a small commission at no extra cost to you." if linked else \
        "Rankings come from public data: Naver search trends and Olive Young Global bestsellers."
    f, lines, s = fit(c.d, disc, SANS, W - 2 * M, 2, 26, 21)
    draw_lines(c.d, M, H - 196, lines, f, c.muted, int(s * 1.4))
    c.dots(idx, n)
    return c


def render_weekly(topic: Topic, info: InfoCopy, number: int, handle: str) -> list[Card]:
    d = topic.data
    has_kor = any(r.get("index") for r in d.get("korea", []))
    sp = d.get("spotlight")
    plan = ["cover"] + (["korea"] if has_kor else []) + (["products"] if info.products else []) + (["spot"] if sp else []) + ["cta"]
    n = len(plan)
    out = []
    for idx, name in enumerate(plan, 1):
        if name == "cover":
            out.append(wk_cover(d, number, handle, n, info.products))
        elif name == "korea":
            out.append(wk_korea(d, handle, idx, n))
        elif name == "products":
            out.append(wk_products(info.products, number, handle, idx, n))
        elif name == "spot":
            out.append(wk_spotlight(sp, handle, idx, n))
        else:
            out.append(wk_cta(handle, idx, n, info.has_links, number))
    return out
