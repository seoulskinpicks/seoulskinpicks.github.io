"""Draws the 5-slide Instagram carousel (1080x1350, 4:5) with Pillow."""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .images import load_image
from .knowledge import ROUTINE_STEPS

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
W, H = 1080, 1350
M = 88  # side margin

SERIF = "DMSerifDisplay-Regular.ttf"
SERIF_I = "DMSerifDisplay-Italic.ttf"
SANS = "DMSans-Regular.ttf"
SANS_M = "DMSans-Medium.ttf"
SANS_SB = "DMSans-SemiBold.ttf"
SANS_B = "DMSans-Bold.ttf"


@lru_cache(maxsize=512)
def F(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def rgb(h: str, a: int = 255) -> tuple:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


@dataclass(frozen=True)
class Theme:
    bg: str
    surface: str
    ink: str
    muted: str
    accent: str
    on_accent: str
    soft: str
    dark: str
    on_dark: str
    dark_muted: str
    line: str


THEMES = {
    "kbeauty": Theme(bg="#F7EFEA", surface="#FFFFFF", ink="#2B1D24", muted="#76626B", accent="#B8475F",
                     on_accent="#FFFFFF", soft="#F0DCDD", dark="#2B1D24", on_dark="#F7EFEA",
                     dark_muted="#BCA8AF", line="#E7D7D4"),
    "tools": Theme(bg="#EDF0E8", surface="#FFFFFF", ink="#1D2A23", muted="#586A5F", accent="#4A7A5A",
                   on_accent="#FFFFFF", soft="#D6E3D7", dark="#1D2A23", on_dark="#EDF0E8",
                   dark_muted="#A6B6AB", line="#D6DDD1"),
}


# ---------------------------------------------------------------------------
# text helpers
# ---------------------------------------------------------------------------
def tw(d: ImageDraw.ImageDraw, s: str, f) -> float:
    return d.textlength(s, font=f)


def wrap(d, text: str, f, max_w: float) -> list[str]:
    words = (text or "").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if tw(d, trial, f) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        while tw(d, w, f) > max_w and len(w) > 1:
            i = len(w) - 1
            while i > 1 and tw(d, w[:i] + "-", f) > max_w:
                i -= 1
            lines.append(w[:i] + "-")
            w = w[i:]
        cur = w
    if cur:
        lines.append(cur)
    return lines


def balanced(d, text: str, f, max_w: float) -> list[str]:
    """Same line count as greedy wrapping, but evenly filled lines (no lonely last word)."""
    lines = wrap(d, text, f, max_w)
    n = len(lines)
    if n <= 1:
        return lines
    words = (text or "").split()
    whole = " ".join(lines).split() == words  # greedy wrap kept every word intact
    w = max_w
    best = lines
    while w > max_w * 0.5:
        w -= 12
        trial = wrap(d, text, f, w)
        if len(trial) != n or (whole and " ".join(trial).split() != words):
            break  # never split a word just to even out the lines
        best = trial
    return best


def fit(d, text: str, font_name: str, max_w: float, max_lines: int, size: int, min_size: int, balance=True):
    s = size
    while True:
        f = F(font_name, s)
        lines = balanced(d, text, f, max_w) if balance else wrap(d, text, f, max_w)
        if len(lines) <= max_lines or s <= min_size:
            break
        s -= 2
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and tw(d, last + "…", f) > max_w:
            last = last[:-1].rstrip()
        lines[-1] = last.rstrip(",;:") + "…"
    return f, lines, s


def draw_lines(d, x, y, lines, f, fill, lh, align="left", width=None) -> float:
    for i, ln in enumerate(lines):
        xx = x
        if align == "center":
            xx = x + (width - tw(d, ln, f)) / 2
        elif align == "right":
            xx = x - tw(d, ln, f)
        d.text((xx, y + i * lh), ln, font=f, fill=fill, anchor="la")
    return y + len(lines) * lh


def cap_metrics(f) -> tuple[int, int]:
    x0, y0, x1, y1 = f.getbbox("H", anchor="ls")
    return -y0, 0  # cap height above baseline


def tracked_w(d, s: str, f, tr: float) -> float:
    return sum(tw(d, ch, f) for ch in s) + tr * max(len(s) - 1, 0)


def tracked(d, x, baseline, s: str, f, fill, tr: float) -> float:
    for ch in s:
        d.text((x, baseline), ch, font=f, fill=fill, anchor="ls")
        x += tw(d, ch, f) + tr
    return x


# ---------------------------------------------------------------------------
# canvas
# ---------------------------------------------------------------------------
class Card:
    def __init__(self, theme: Theme, dark: bool = False, size: tuple[int, int] = (W, H)):
        self.t = theme
        self.dark = dark
        self.w, self.h = size
        self.img = Image.new("RGB", size, rgb(theme.dark if dark else theme.bg)[:3])
        self.d = ImageDraw.Draw(self.img, "RGBA")  # RGBA mode = semi-transparent fills blend

    @property
    def ink(self):
        return rgb(self.t.on_dark if self.dark else self.t.ink)

    @property
    def muted(self):
        return rgb(self.t.dark_muted if self.dark else self.t.muted)

    def shadow_box(self, box, radius, fill, blur=26, dy=14, alpha=30):
        mask = Image.new("L", (self.w, self.h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((box[0], box[1] + dy, box[2], box[3] + dy), radius, fill=alpha)
        self.img.paste(rgb(self.t.ink)[:3], (0, 0), mask.filter(ImageFilter.GaussianBlur(blur)))
        self.d.rounded_rectangle(box, radius, fill=rgb(fill) if isinstance(fill, str) else fill)

    def pill(self, x, y, text, f, fg, bg, padx=26, pady=16, tr=2.4, align="left") -> tuple[float, float]:
        cap, _ = cap_metrics(f)
        w = tracked_w(self.d, text, f, tr) + padx * 2
        h = cap + pady * 2
        if align == "right":
            x -= w
        elif align == "center":
            x -= w / 2
        self.d.rounded_rectangle((x, y, x + w, y + h), h / 2, fill=bg)
        tracked(self.d, x + padx, y + pady + cap, text, f, fg, tr)
        return w, h

    def label(self, x, y, text, color=None, size=26, tr=3.0) -> float:
        f = F(SANS_SB, size)
        cap, _ = cap_metrics(f)
        tracked(self.d, x, y + cap, text.upper(), f, color or self.muted, tr)
        return y + cap

    def header(self, handle: str, idx: int, total: int):
        f = F(SANS_M, 28)
        self.d.text((M, 78), f"@{handle}", font=f, fill=self.muted, anchor="la")
        self.d.text((self.w - M, 78), f"{idx} / {total}", font=f, fill=self.muted, anchor="ra")

    def dots(self, idx: int, total: int):
        gap, y = 26, self.h - 70
        widths = [40 if i == idx - 1 else 12 for i in range(total)]
        x = self.w / 2 - (sum(widths) + gap * (total - 1) - 12 * (total - 1)) / 2
        for i, w in enumerate(widths):
            active = i == idx - 1
            if self.dark:
                col = rgb(self.t.on_dark) if active else rgb(self.t.dark_muted, 110)
            else:
                col = rgb(self.t.accent) if active else rgb(self.t.ink, 45)
            self.d.rounded_rectangle((x, y - 6, x + w, y + 6), 6, fill=col)
            x += w + gap - 12

    def arrow(self, x, y, length, color, width=5):
        self.d.line((x, y, x + length, y), fill=color, width=width)
        head = width * 3.2
        self.d.line((x + length - head, y - head, x + length, y), fill=color, width=width)
        self.d.line((x + length - head, y + head, x + length, y), fill=color, width=width)

    def check(self, cx, cy, s, color, width=6):
        self.d.line((cx - s * 0.45, cy, cx - s * 0.12, cy + s * 0.32, cx + s * 0.48, cy - s * 0.35), fill=color, width=width, joint="curve")

    def star(self, cx, cy, r, color):
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.45
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        self.d.polygon(pts, fill=color)

    def star_row(self, x, cy, rating: float, r: int = 22, gap: int = 10) -> float:
        """Five stars, partially filled for ratings like 4.6. Returns the x after the last star."""
        on, off = rgb(self.t.accent)[:3], rgb(self.t.line)[:3]
        size = r * 2 + 2
        for i in range(5):
            mask = Image.new("L", (size, size), 0)
            md = ImageDraw.Draw(mask)
            pts = []
            for k in range(10):
                ang = -math.pi / 2 + k * math.pi / 5
                rr = r if k % 2 == 0 else r * 0.45
                pts.append((r + 1 + rr * math.cos(ang), r + 1 + rr * math.sin(ang)))
            md.polygon(pts, fill=255)
            pos = (int(x + i * (size + gap)), int(cy - r - 1))
            self.img.paste(off, pos, mask)
            frac = max(0.0, min(1.0, rating - i))
            if frac > 0:
                part = mask.copy()
                ImageDraw.Draw(part).rectangle((int(size * frac), 0, size, size), fill=0)
                self.img.paste(on, pos, part)
        return x + 5 * (size + gap) - gap

    def bookmark(self, x, y, w, h, color):
        self.d.polygon([(x, y), (x + w, y), (x + w, y + h), (x + w / 2, y + h - w * 0.42), (x, y + h)], fill=color)

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.img.save(path, "JPEG", quality=90, optimize=True, progressive=True)


# ---------------------------------------------------------------------------
# slides
# ---------------------------------------------------------------------------


def slide_cover_kbeauty(t: Theme, cp, cand, number: int, handle: str, n_slides: int = 5) -> Card:
    c = Card(t)
    d = c.d
    # giant background numeral
    d.text((W - 40, H - 30), str(number), font=F(SERIF, 560 if number < 100 else 440), fill=rgb(t.soft), anchor="rs")
    c.header(handle, 1, n_slides)
    y = 236
    _, ph = c.pill(M, y, f"SEOUL PICK · NO.{number}", F(SANS_SB, 26), rgb(t.on_accent), rgb(t.accent))
    y += ph + 44
    c.label(M, y, cp.kicker, size=26)
    y += 74
    has_stats = bool(getattr(cp, "store_line", ""))
    f, lines, s = fit(d, cp.hook, SERIF, W - 2 * M, 3 if has_stats else 4, 118 if not has_stats else 108, 72)
    y = draw_lines(d, M, y, lines, f, c.ink, int(s * 1.08))
    y += 36
    d.rectangle((M, y, M + 96, y + 6), fill=rgb(t.accent))
    y += 46
    fb = F(SANS_B, 32)
    tracked(d, M, y + cap_metrics(fb)[0], cand.brand.upper(), fb, c.ink, 2.2)
    y += cap_metrics(fb)[0] + 26
    fn, nlines, ns = fit(d, cp.display_name, SANS, W - 2 * M - 120, 2, 44, 34, balance=False)
    y = draw_lines(d, M, y, nlines, fn, c.muted, int(ns * 1.3))
    if has_stats:
        _store_row(c, M, y + 34, cp.store_line)
        y += 60
    if y < H - 230:
        fs = F(SANS_M, 30)
        d.text((M, H - 150), "Swipe for the details", font=fs, fill=c.ink, anchor="ls")
        c.arrow(M + tw(d, "Swipe for the details", fs) + 22, H - 160, 54, c.ink, 4)
    c.dots(1, n_slides)
    return c


def _fetch_image(ref) -> Image.Image | None:
    return load_image(ref)


def slide_cover_tools(t: Theme, cp, cand, number: int, handle: str, product_img, n_slides: int = 5,
                      pill_text: str | None = None, subtitle: str | None = None) -> Card:
    """Cover with a square product image card (AliExpress product photos)."""
    c = Card(t)
    d = c.d
    c.header(handle, 1, n_slides)
    y = 170
    pw, ph = c.pill(M, y, pill_text or f"TOOL PICK · NO.{number}", F(SANS_SB, 26), rgb(t.on_accent), rgb(t.accent))
    cap = cap_metrics(F(SANS_SB, 24))[0]
    c.label(M + pw + 26, y + (ph - cap) / 2, cp.kicker, size=24)
    y += ph + 40
    f, lines, s = fit(d, cp.hook, SERIF, W - 2 * M, 3, 92, 64)
    y = draw_lines(d, M, y, lines, f, c.ink, int(s * 1.08))
    y += 14
    fn, sub, _ = fit(d, subtitle or cp.display_name, SANS_M, W - 2 * M, 1, 34, 26, balance=False)
    d.text((M, y), sub[0], font=fn, fill=c.muted, anchor="la")
    y += 70
    bottom = H - 150
    side = int(min(bottom - y, W - 2 * M, 620))
    x0 = (W - side) // 2
    box = (x0, y, x0 + side, y + side)
    c.shadow_box(box, 44, t.surface, blur=30, dy=18, alpha=34)
    img = _fetch_image(product_img)
    if img is None:
        raise RuntimeError("상품 이미지를 받지 못했어요")
    inner = side - 40
    pic = ImageOps.fit(img, (inner, inner), Image.LANCZOS)
    mask = Image.new("L", (inner, inner), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, inner, inner), 30, fill=255)
    c.img.paste(pic, (x0 + 20, y + 20), mask)
    price = cp.slide4.get("price") or (getattr(cp, "deal", None) or {}).get("price")
    if price:
        c.pill(x0 + side + 18, y + side - 92, price, F(SANS_B, 34), rgb(t.on_accent), rgb(t.accent), padx=30, pady=22, tr=0.5, align="right")
    c.dots(1, n_slides)
    return c


def _title(c: Card, label: str, title: str, y: int = 176, max_lines: int = 2, size: int = 80) -> float:
    c.label(M, y, label, color=rgb(c.t.accent), size=26)
    f, lines, s = fit(c.d, title, SERIF, W - 2 * M, max_lines, size, 60)
    return draw_lines(c.d, M, y + 56, lines, f, c.ink, int(s * 1.08))


def slide_bullets(t: Theme, label: str, title: str, items: list[str], handle: str, idx: int, icon="number", n_slides: int = 5) -> Card:
    c = Card(t)
    d = c.d
    c.header(handle, idx, n_slides)
    top = _title(c, label, title) + 56
    pad, circle, gap = 44, 68, 30
    text_w = W - 2 * M - pad * 2 - circle - 32
    for size in (46, 44, 42, 40, 38, 36, 34):
        f = F(SANS, size)
        lh = int(size * 1.36)
        blocks = [wrap(d, it, f, text_w) for it in items]
        heights = [max(circle, len(b) * lh - (lh - size) + 6) + pad * 2 for b in blocks]
        total = sum(heights) + gap * (len(items) - 1)
        if top + total <= H - 140:
            break
    y = top + max(0, (H - 150 - top - total) / 2) * 0.75
    for i, (b, h) in enumerate(zip(blocks, heights)):
        box = (M, y, W - M, y + h)
        c.shadow_box(box, 30, t.surface, blur=18, dy=8, alpha=18)
        cx, cy = M + pad + circle / 2, y + h / 2
        d.ellipse((cx - circle / 2, cy - circle / 2, cx + circle / 2, cy + circle / 2), fill=rgb(t.accent if icon == "number" else t.soft))
        if icon == "number":
            d.text((cx, cy + 2), str(i + 1), font=F(SANS_B, 32), fill=rgb(t.on_accent), anchor="mm")
        else:
            c.check(cx, cy, 30, rgb(t.accent), 6)
        text_h = len(b) * lh - (lh - size)
        draw_lines(d, M + pad + circle + 32, y + (h - text_h) / 2 - size * 0.12, b, f, c.ink, lh)
        y += h + gap
    c.dots(idx, n_slides)
    return c


def slide_steps(t: Theme, steps: list[str], handle: str, idx: int, n_slides: int = 5) -> Card:
    c = Card(t)
    d = c.d
    c.header(handle, idx, n_slides)
    top = _title(c, "Step by step", "How to use it") + 70
    circle = 76
    tx = M + circle + 40
    text_w = W - M - tx
    fl = F(SANS_SB, 24)
    for size in (46, 44, 42, 40, 38, 36):
        f = F(SANS, size)
        lh = int(size * 1.36)
        blocks = [wrap(d, s, f, text_w) for s in steps]
        heights = [48 + len(b) * lh for b in blocks]
        gap = 64
        total = sum(heights) + gap * (len(steps) - 1)
        if top + total <= H - 150:
            break
    if len(steps) > 1:
        gap = max(64, min(120, (H - 190 - top - sum(heights)) / (len(steps) - 1) * 0.75))
        total = sum(heights) + gap * (len(steps) - 1)
    y = top + max(0, (H - 170 - top - total) / 2) * 0.5
    cx = M + circle / 2
    first_cy = y + circle / 2 - 6
    centers = []
    yy = y
    for h in heights:
        centers.append(yy + circle / 2 - 6)
        yy += h + gap
    d.line((cx, first_cy, cx, centers[-1]), fill=rgb(t.accent, 90), width=4)
    for i, (b, h) in enumerate(zip(blocks, heights)):
        cy = centers[i]
        d.ellipse((cx - circle / 2, cy - circle / 2, cx + circle / 2, cy + circle / 2), fill=rgb(t.bg), outline=rgb(t.accent), width=4)
        d.text((cx, cy + 3), str(i + 1), font=F(SERIF, 40), fill=rgb(t.accent), anchor="mm")
        cap, _ = cap_metrics(fl)
        tracked(d, tx, y + cap, f"STEP {i + 1}", fl, rgb(t.accent), 2.6)
        draw_lines(d, tx, y + 48, b, f, c.ink, lh)
        y += h + gap
    c.dots(idx, n_slides)
    return c


def slide_routine(t: Theme, index: int, note: str, handle: str, idx: int, n_slides: int = 5) -> Card:
    c = Card(t)
    d = c.d
    c.header(handle, idx, n_slides)
    y = _title(c, "The Korean routine", "Where it fits in your routine") + 56
    row_h, gap = 118, 20
    for i, (name, sub) in enumerate(ROUTINE_STEPS):
        box = (M, y, W - M, y + row_h)
        on = i == index
        if on:
            c.shadow_box(box, 34, t.accent, blur=20, dy=10, alpha=40)
            fg, fg2 = rgb(t.on_accent), rgb(t.on_accent, 210)
        else:
            d.rounded_rectangle(box, 34, outline=rgb(t.line), width=3, fill=rgb(t.bg))
            fg, fg2 = rgb(t.ink, 150), rgb(t.muted, 150)
        d.text((M + 44, y + row_h / 2), f"{i + 1}", font=F(SERIF, 46), fill=fg, anchor="lm")
        d.text((M + 110, y + row_h / 2 - 17), name, font=F(SANS_SB, 38), fill=fg, anchor="lm")
        d.text((M + 110, y + row_h / 2 + 24), sub, font=F(SANS, 27), fill=fg2, anchor="lm")
        if on:
            c.pill(W - M - 36, y + row_h / 2 - 25, "THIS ONE", F(SANS_B, 22), rgb(t.accent), rgb(t.on_accent), padx=20, pady=14, tr=2, align="right")
        y += row_h + gap
    if note:
        f, lines, s = fit(d, note, SERIF_I, W - 2 * M, 2, 44, 34)
        draw_lines(d, M, y + 24, lines, f, c.muted, int(s * 1.2))
    c.dots(idx, n_slides)
    return c


def slide_take(t: Theme, text: str, handle: str, idx: int, my_rating: float | None = None, n_slides: int = 5) -> Card:
    c = Card(t)
    d = c.d
    c.header(handle, idx, n_slides)
    c.pill(M, 176, "MY HONEST TAKE", F(SANS_SB, 26), rgb(t.accent), rgb(t.soft))
    d.text((M - 8, 250), "“", font=F(SERIF, 300), fill=rgb(t.accent), anchor="la")
    f, lines, s = fit(d, text, SERIF, W - 2 * M, 7, 72, 44)
    lh = int(s * 1.16)
    block = len(lines) * lh
    y = max(520, (H - block) / 2 + 40)
    y = draw_lines(d, M, y, lines, f, c.ink, lh)
    d.rectangle((M, y + 40, M + 60, y + 44), fill=rgb(t.accent))
    d.text((M + 80, y + 42), f"@{handle}, Seoul", font=F(SANS_M, 32), fill=c.muted, anchor="lm")
    if my_rating:
        x = c.star_row(M, y + 118, my_rating, r=22)
        d.text((x + 22, y + 118), f"{_num(my_rating)} / 5  ·  my rating", font=F(SANS_M, 30), fill=c.muted, anchor="lm")
    c.dots(idx, n_slides)
    return c


def slide_deal(t: Theme, deal: dict, handle: str, idx: int, n_slides: int = 5) -> Card:
    c = Card(t)
    d = c.d
    c.header(handle, idx, n_slides)
    y = _title(c, "The numbers", "The deal") + 70
    box = (M, y, W - M, y + 340)
    c.shadow_box(box, 40, t.surface, blur=22, dy=10, alpha=22)
    c.label(M + 50, y + 50, "AliExpress price when posted", size=24)
    pf = F(SERIF, 150)
    d.text((M + 46, y + 250), deal.get("price") or "—", font=pf, fill=rgb(t.accent), anchor="ls")
    px = M + 46 + tw(d, deal.get("price") or "—", pf) + 30
    if deal.get("original"):
        of = F(SANS, 40)
        d.text((px, y + 190), deal["original"], font=of, fill=c.muted, anchor="ls")
        ow = tw(d, deal["original"], of)
        d.line((px, y + 176, px + ow, y + 176), fill=c.muted, width=3)
        if deal.get("discount"):
            c.pill(px, y + 210, deal["discount"], F(SANS_B, 28), rgb(t.on_accent), rgb(t.accent), padx=18, pady=12, tr=0.5)
    y = box[3] + 30
    col_w = (W - 2 * M - 30) / 2
    stats = [
        (deal.get("rating") or "—", "positive reviews", "star"),
        (deal.get("orders") or "—", "orders so far", "bag"),
    ]
    for i, (big, small, icon) in enumerate(stats):
        x = M + i * (col_w + 30)
        b = (x, y, x + col_w, y + 270)
        c.shadow_box(b, 36, t.surface, blur=18, dy=8, alpha=18)
        if icon == "star":
            c.star(x + 70, y + 70, 26, rgb(t.accent))
        else:
            for j, bh in enumerate((20, 34, 50)):
                bx = x + 46 + j * 18
                d.rounded_rectangle((bx, y + 96 - bh, bx + 12, y + 96), 3, fill=rgb(t.accent))
        d.text((x + 44, y + 200), big, font=F(SERIF, 80), fill=c.ink, anchor="ls")
        d.text((x + 46, y + 240), small, font=F(SANS, 30), fill=c.muted, anchor="ls")
    y += 270 + 48
    note = "Prices change often, and import fees may apply in your country."
    f, lines, s = fit(d, note, SANS, W - 2 * M, 2, 29, 24)
    draw_lines(d, M, y, lines, f, c.muted, int(s * 1.35))
    c.dots(idx, n_slides)
    return c


def slide_cta(t: Theme, number: int, shop_label: str, handle: str, idx: int, n_slides: int = 5) -> Card:
    c = Card(t, dark=True)
    d = c.d
    c.header(handle, idx, n_slides)
    d.ellipse((W - 420, -180, W + 220, 460), fill=rgb(t.accent, 255))
    d.ellipse((W - 330, -90, W + 130, 370), fill=rgb(t.dark))
    y = 330
    d.text((M, y), "Want it?", font=F(SERIF, 140), fill=c.ink, anchor="la")
    y += 190
    d.text((M, y), "Tap the link in my bio", font=F(SANS_M, 48), fill=c.ink, anchor="la")
    y += 64
    d.text((M, y), "and find this number:", font=F(SANS, 40), fill=c.muted, anchor="la")
    y += 90
    nf = F(SERIF, 96)
    label = f"No.{number}"
    bw = tw(d, label, nf) + 120 + 70
    d.rounded_rectangle((M, y, M + bw, y + 150), 75, fill=rgb(t.accent))
    d.text((M + 60, y + 75), label, font=nf, fill=rgb(t.on_accent), anchor="lm")
    c.arrow(M + 60 + tw(d, label, nf) + 30, y + 78, 50, rgb(t.on_accent), 6)
    y += 190
    sf, slines, _ = fit(d, shop_label, SANS_M, W - 2 * M, 1, 34, 26, balance=False)
    d.text((M, y), slines[0], font=sf, fill=c.muted, anchor="la")
    y += 110
    c.bookmark(M, y, 34, 46, c.ink)
    d.text((M + 60, y + 23), "Save this for your next haul", font=F(SANS_M, 36), fill=c.ink, anchor="lm")
    disc = "#ad · Affiliate link. I may earn a small commission at no extra cost to you."
    f, lines, s = fit(d, disc, SANS, W - 2 * M, 2, 26, 22)
    draw_lines(d, M, H - 190, lines, f, c.muted, int(s * 1.4))
    c.dots(idx, n_slides)
    return c


def _num(r: float) -> str:
    return f"{int(r)}" if r == int(r) else f"{r:.1f}"


def _store_row(c: Card, x: float, cy: float, text: str) -> None:
    """★ 4.8 average · 12,345 reviews on Olive Young"""
    c.star(x + 16, cy, 17, rgb(c.t.accent))
    f, lines, _ = fit(c.d, text, SANS_M, W - x - M - 44, 1, 30, 22, balance=False)
    c.d.text((x + 44, cy), lines[0], font=f, fill=c.ink, anchor="lm")


def slide_cover_kbeauty_photo(t: Theme, cp, cand, number: int, handle: str, photo: Image.Image, n_slides: int = 5) -> Card:
    """Cover with your own product photo on top and the headline underneath."""
    c = Card(t)
    d = c.d
    c.header(handle, 1, n_slides)
    bottom = H - 120
    # measure the text block first so the photo can take whatever space is left
    for max_lines, size in ((3, 84), (3, 72), (2, 64)):
        f, lines, s = fit(d, cp.hook, SERIF, W - 2 * M, max_lines, size, 56)
        lh = int(s * 1.08)
        pill_h = cap_metrics(F(SANS_SB, 24))[0] + 28
        gap_after = int(s * 0.6)
        brand_cap = cap_metrics(F(SANS_B, 28))[0]
        text_h = pill_h + 30 + len(lines) * lh + gap_after + brand_cap + (68 if cp.store_line else 0)
        photo_top, photo_bottom = 146, bottom - text_h - 34
        if photo_bottom - photo_top >= 520:
            break
    box = (M, photo_top, W - M, photo_bottom)
    c.shadow_box(box, 40, t.surface, blur=26, dy=14, alpha=30)
    pw, ph = int(box[2] - box[0]) + 1, int(box[3] - box[1]) + 1
    pic = ImageOps.fit(photo, (pw, ph), Image.LANCZOS, centering=(0.5, 0.45))
    mask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw, ph), 40, fill=255)
    c.img.paste(pic, (int(box[0]), int(box[1])), mask)

    y = photo_bottom + 34
    pwid, pht = c.pill(M, y, f"SEOUL PICK · NO.{number}", F(SANS_SB, 24), rgb(t.on_accent), rgb(t.accent), padx=22, pady=14)
    capk = cap_metrics(F(SANS_SB, 22))[0]
    if tracked_w(d, cp.kicker.upper(), F(SANS_SB, 22), 3) <= W - 2 * M - pwid - 26:
        c.label(M + pwid + 22, y + (pht - capk) / 2, cp.kicker, size=22)
    y += pht + 30
    y = draw_lines(d, M, y, lines, f, c.ink, lh)
    baseline = y + gap_after + brand_cap
    fb = F(SANS_B, 28)
    x = tracked(d, M, baseline, cand.brand.upper(), fb, c.ink, 2)
    fn, nl, _ = fit(d, cp.display_name, SANS, W - M - x - 20, 1, 32, 24, balance=False)
    d.text((x + 16, baseline), "· " + nl[0], font=fn, fill=c.muted, anchor="ls")
    if cp.store_line:
        _store_row(c, M, baseline + 54, cp.store_line)
    c.dots(1, n_slides)
    return c


def slide_reviews(t: Theme, rv: dict, handle: str, idx: int, n_slides: int = 5) -> Card:
    """'What reviewers say': store rating + themes you summarized (not quotes)."""
    c = Card(t)
    d = c.d
    c.header(handle, idx, n_slides)
    y = _title(c, f"From {rv['source']} reviews", "What reviewers say") + 50
    if rv.get("rating"):
        box = (M, y, W - M, y + 210)
        c.shadow_box(box, 36, t.surface, blur=20, dy=8, alpha=20)
        big = _num(rv["rating"])
        bf = F(SERIF, 128)
        d.text((M + 48, y + 160), big, font=bf, fill=rgb(t.accent), anchor="ls")
        sx = M + 48 + tw(d, big, bf) + 40
        c.star_row(sx, y + 84, rv["rating"], r=24, gap=10)
        sub = f"{rv['count']} reviews" if rv.get("count") else "average rating"
        d.text((sx, y + 158), sub, font=F(SANS, 32), fill=c.muted, anchor="ls")
        y = box[3] + 40
    items = rv.get("items", [])
    pad, circle, gap = 40, 60, 24
    text_w = W - 2 * M - pad * 2 - circle - 30
    limit = H - 210
    for size in (42, 40, 38, 36, 34, 32):
        f = F(SANS, size)
        lh = int(size * 1.36)
        blocks = [wrap(d, it, f, text_w) for it in items]
        heights = [max(circle, len(b) * lh - (lh - size) + 6) + pad * 2 for b in blocks]
        if y + sum(heights) + gap * (len(items) - 1) <= limit:
            break
    for b, h in zip(blocks, heights):
        box = (M, y, W - M, y + h)
        c.shadow_box(box, 30, t.surface, blur=16, dy=6, alpha=16)
        cx, cy = M + pad + circle / 2, y + h / 2
        d.ellipse((cx - circle / 2, cy - circle / 2, cx + circle / 2, cy + circle / 2), fill=rgb(t.soft))
        c.check(cx, cy, 26, rgb(t.accent), 5)
        text_h = len(b) * lh - (lh - size)
        draw_lines(d, M + pad + circle + 30, y + (h - text_h) / 2 - size * 0.12, b, f, c.ink, lh)
        y += h + gap
    note = "Themes summarized from public reviews, not direct quotes."
    d.text((M, H - 150), note, font=F(SANS, 26), fill=c.muted, anchor="ls")
    c.dots(idx, n_slides)
    return c


# ---------------------------------------------------------------------------
def render_post(cand, cp, number: int, handle: str, out_dir: Path, product_img=None) -> list[Path]:
    """Render the carousel (5-8 slides: optional star ingredient, reviews and price slides). Returns image paths."""
    t = THEMES["kbeauty" if cand.source == "kbeauty" else "tools"]
    reviews = getattr(cp, "reviews", None)
    s4 = cp.slide4
    kind = s4.get("kind")

    deal = getattr(cp, "deal", None)
    star = getattr(cp, "star", None)
    plan = (["cover", "why"] + (["star"] if star else []) + (["reviews"] if reviews else []) + ["how", "s4"]
            + (["deal"] if deal else []) + ["cta"])
    n = len(plan)
    slides = []
    for idx, name in enumerate(plan, 1):
        if name == "cover":
            if cand.source == "kbeauty":
                from .util import warn
                own = cand.photo or None
                ref = product_img if (product_img is not None and not cand.image_url) else own
                photo = _fetch_image(ref) if ref is not None else None
                if own and photo is None:
                    warn(f"사진을 불러오지 못했어요: {own}")
                shop_img = None
                if photo is None and cand.image_url:
                    shop_img = _fetch_image(product_img if product_img is not None else cand.image_url)
                    if shop_img is None:
                        warn("알리 상품 사진을 불러오지 못해서 디자인 표지로 만들었어요")
                if photo is not None:
                    card = slide_cover_kbeauty_photo(t, cp, cand, number, handle, photo, n_slides=n)
                elif shop_img is not None:  # AliExpress product photo -> square product card
                    card = slide_cover_tools(t, cp, cand, number, handle, shop_img, n_slides=n,
                                             pill_text=f"SEOUL PICK · NO.{number}",
                                             subtitle=f"{cand.brand} · {cp.display_name}")
                else:
                    card = slide_cover_kbeauty(t, cp, cand, number, handle, n_slides=n)
            else:
                card = slide_cover_tools(t, cp, cand, number, handle,
                                         product_img if product_img is not None else cand.image_url, n_slides=n)
        elif name == "why":
            card = slide_bullets(t, cp.why_label, cp.why_title, cp.why_bullets, handle, idx, n_slides=n)
        elif name == "star":
            from .render_info import slide_star
            card = slide_star(t, star, handle, idx, n)
        elif name == "deal":
            card = slide_deal(t, deal, handle, idx, n_slides=n)
        elif name == "reviews":
            card = slide_reviews(t, reviews, handle, idx, n_slides=n)
        elif name == "how":
            card = slide_steps(t, cp.how_steps, handle, idx, n_slides=n)
        elif name == "s4":
            if kind == "take":
                card = slide_take(t, s4["text"], handle, idx, my_rating=getattr(cp, "my_rating", None), n_slides=n)
            elif kind == "routine":
                card = slide_routine(t, s4["index"], s4.get("note", ""), handle, idx, n_slides=n)
            elif kind == "deal":
                card = slide_deal(t, s4, handle, idx, n_slides=n)
            else:
                card = slide_bullets(t, "Good to know", s4.get("title", "Pro tips"), s4.get("items", []), handle, idx,
                                     icon="check", n_slides=n)
        else:
            card = slide_cta(t, number, cp.shop_label, handle, idx, n_slides=n)
        slides.append(card)
    paths = []
    for i, card in enumerate(slides, 1):
        p = out_dir / f"{i}.jpg"
        card.save(p)
        paths.append(p)
    return paths


PW, PH = 1000, 1500  # Pinterest's recommended 2:3


def render_pin(cand, cp, number: int, handle: str, out_path: Path, product_img=None) -> Path:
    """One tall 2:3 image for Pinterest: photo (if any), headline, 3 reasons, 'tap to shop'."""
    t = THEMES["kbeauty" if cand.source == "kbeauty" else "tools"]
    c = Card(t, size=(PW, PH))
    d = c.d
    pill = f"{'TOOL' if cand.source == 'tools' else 'SEOUL'} PICK · NO.{number}"
    own = getattr(cand, "photo", "") or None
    photo = _fetch_image(product_img if product_img is not None else (own or cand.image_url))
    y = 80
    if photo is not None:
        box = (M, y, PW - M, y + 600)
        c.shadow_box(box, 40, t.surface, blur=24, dy=12, alpha=28)
        bw, bh = int(box[2] - box[0]) + 1, int(box[3] - box[1]) + 1
        is_square_shop_photo = not own and photo.width == photo.height
        if is_square_shop_photo:  # AliExpress product shot on white: show it whole
            inner = bh - 40
            pic = ImageOps.fit(photo, (inner, inner), Image.LANCZOS)
            px = int(box[0] + (bw - inner) / 2)
            mask = Image.new("L", (inner, inner), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, inner, inner), 28, fill=255)
            c.img.paste(pic, (px, int(box[1]) + 20), mask)
        else:
            pic = ImageOps.fit(photo, (bw, bh), Image.LANCZOS, centering=(0.5, 0.45))
            mask = Image.new("L", (bw, bh), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, bw, bh), 40, fill=255)
            c.img.paste(pic, (int(box[0]), int(box[1])), mask)
        y = box[3] + 40
    else:  # no photo: big editorial type, numeral in the corner
        d.text((PW - 30, PH - 190), str(number), font=F(SERIF, 520), fill=rgb(t.soft), anchor="rs")
        y = 230
    _, ph = c.pill(M, y, pill, F(SANS_SB, 24), rgb(t.on_accent), rgb(t.accent), padx=22, pady=14)
    y += ph + 30
    f, lines, s = fit(d, cp.hook, SERIF, PW - 2 * M, 3 if photo is not None else 4, 88 if photo is not None else 116, 56)
    y = draw_lines(d, M, y, lines, f, c.ink, int(s * 1.08)) + int(s * 0.35)
    sub = f"{cand.brand} · {cp.display_name}" if cand.brand else cp.display_name
    fs, sl, _ = fit(d, sub, SANS_M, PW - 2 * M, 1, 32, 24, balance=False)
    d.text((M, y), sl[0], font=fs, fill=c.muted, anchor="la")
    y += 58
    stats = getattr(cp, "store_line", "")
    deal = getattr(cp, "deal", None) or (cp.slide4 if cp.slide4.get("kind") == "deal" else None)
    if deal and deal.get("price"):
        stats = f"{deal['price']} on AliExpress" + (f" · {deal['rating']} positive" if deal.get("rating") else "")
    if stats:
        _store_row(c, M, y + 18, stats)
        y += 66
    footer_top = PH - 170
    big = photo is None
    fb = F(SANS, 38 if big else 34)
    lh = 52 if big else 46
    if big:
        y += 30
    for b in cp.why_bullets[:3]:
        bl = wrap(d, b, fb, PW - 2 * M - 70)[:2]
        need = len(bl) * lh + (30 if big else 22)
        if y + need > footer_top - 20:
            break
        d.ellipse((M, y + 4, M + 40, y + 44), fill=rgb(t.soft))
        c.check(M + 20, y + 24, 20, rgb(t.accent), 4)
        draw_lines(d, M + 64, y, bl, fb, c.ink, lh)
        y += need
    d.rectangle((0, footer_top, PW, PH), fill=rgb(t.dark))
    d.text((M, footer_top + 62), "Tap to see where to buy", font=F(SERIF, 52), fill=rgb(t.on_dark), anchor="lm")
    c.arrow(M + tw(d, "Tap to see where to buy", F(SERIF, 52)) + 26, footer_top + 64, 44, rgb(t.on_dark), 5)
    d.text((M, footer_top + 122), f"@{handle}  ·  #ad affiliate links", font=F(SANS, 26), fill=rgb(t.dark_muted), anchor="lm")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c.img.save(out_path, "JPEG", quality=88, optimize=True, progressive=True)
    return out_path


def contact_sheet(paths: list[Path], out: Path, cols: int = 5, thumb_w: int = 360) -> Path:
    thumbs = [Image.open(p).convert("RGB").resize((thumb_w, int(thumb_w * H / W)), Image.LANCZOS) for p in paths]
    rows = math.ceil(len(thumbs) / cols)
    th = thumbs[0].height
    gap = 16
    sheet = Image.new("RGB", (cols * thumb_w + (cols + 1) * gap, rows * th + (rows + 1) * gap), (230, 230, 230))
    for i, im in enumerate(thumbs):
        r, col = divmod(i, cols)
        sheet.paste(im, (gap + col * (thumb_w + gap), gap + r * (th + gap)))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, "JPEG", quality=88)
    return out
