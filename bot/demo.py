"""Demo data so you can preview the cards without any API keys (python -m bot demo)."""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

from .sources import Candidate

DEMO_KBEAUTY = [
    Candidate(
        source="kbeauty", key="demo-1", brand="Hanbit Lab", name="Rice Water Glow Toner",
        link="https://example.com/demo", category="toner", rank="#1 Toner",
        key_points=["Watery texture that sinks in fast", "Rice-water base, a classic Korean ingredient", "Big bottle that lasts for months"],
        comment="My go-to after a long day. Light, never sticky, and my skin feels calm the next morning.",
        my_rating=4.5, store_rating=4.8, review_count=12345,
        review_highlights=["Absorbs fast with no sticky layer", "Gentle enough for daily use", "Big bottle, great value"],
    ),
    Candidate(
        source="kbeauty", key="demo-2", brand="Maeil Skin", name="Daily Airy Sun Serum SPF50+ PA++++",
        link="https://example.com/demo", category="sunscreen", store_rating=4.7, review_count=3280,
    ),
]

DEMO_KBEAUTY_ALI = Candidate(
    source="kbeauty", key="demo-4", brand="Hanbit Lab", name="Rice Water Glow Toner",
    link="https://example.com/demo-oy", category="toner", store="aliexpress", image_url="demo",
    oy_link="https://example.com/demo-oy", ali_link="https://example.com/demo-ali",
    raw_title="Hanbit Lab Official Rice Water Glow Toner 300ml", price=14.90, original_price=19.80,
    currency="USD", rating="98.1%", orders=2310, product_id="demo",
    store_rating=4.8, review_count=12345,
)

DEMO_TOOL = Candidate(
    source="tools", key="demo-3", brand="", name="Gua sha stone", link="https://example.com/demo",
    category="gua_sha", raw_title="Natural Rose Quartz Gua Sha Board Facial Massage Scraping Tool",
    price=5.87, original_price=11.20, currency="USD", rating="97.4%", orders=12840, product_id="demo",
)


def demo_product_image(size: int = 800) -> Image.Image:
    """Draws a stand-in rose-quartz gua sha (demo only — real posts use the AliExpress photo)."""
    img = Image.new("RGB", (size, size), (246, 244, 242))
    pts = []
    for i in range(360):
        t = math.radians(i)
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((x, y))
    ang = math.radians(-28)
    s = size / 44
    pts = [(size / 2 + s * (x * math.cos(ang) - y * math.sin(ang)), size / 2 + 20 + s * (x * math.sin(ang) + y * math.cos(ang))) for x, y in pts]

    shadow = Image.new("L", (size, size), 0)
    ImageDraw.Draw(shadow).polygon([(x + 18, y + 26) for x, y in pts], fill=90)
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    img.paste((150, 120, 125), (0, 0), shadow)

    grad = Image.new("RGB", (size, size))
    gd = ImageDraw.Draw(grad)
    for yy in range(size):
        k = yy / size
        gd.line((0, yy, size, yy), fill=(int(246 - 26 * k), int(208 - 40 * k), int(212 - 34 * k)))
    rnd = random.Random(7)
    for _ in range(900):
        x, y = rnd.randrange(size), rnd.randrange(size)
        r = rnd.randrange(2, 9)
        c = rnd.randrange(-14, 14)
        base = grad.getpixel((x, y))
        gd.ellipse((x - r, y - r, x + r, y + r), fill=tuple(max(0, min(255, v + c)) for v in base))
    grad = grad.filter(ImageFilter.GaussianBlur(3))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    img.paste(grad, (0, 0), mask)

    hl = Image.new("L", (size, size), 0)
    ImageDraw.Draw(hl).ellipse((size * 0.30, size * 0.26, size * 0.52, size * 0.40), fill=150)
    hl = hl.filter(ImageFilter.GaussianBlur(26))
    hl = Image.composite(hl, Image.new("L", (size, size), 0), mask)
    img.paste((255, 255, 255), (0, 0), hl)
    return img


def demo_bottle_photo(w: int = 1200, h: int = 1500) -> Image.Image:
    """A stand-in 'phone photo' of a toner bottle (demo only — real posts use YOUR photo)."""
    from PIL import ImageFont
    from .render import FONTS

    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        k = y / h
        d.line((0, y, w, y), fill=(int(236 - 18 * k), int(226 - 22 * k), int(214 - 24 * k)))
    d.rectangle((0, int(h * 0.70), w, h), fill=(221, 204, 188))
    light = Image.new("L", (w, h), 0)
    ImageDraw.Draw(light).polygon([(0, 0), (w * 0.55, 0), (w * 0.2, h), (0, h)], fill=70)
    img.paste((255, 250, 240), (0, 0), light.filter(ImageFilter.GaussianBlur(120)))

    cx, base = w // 2 + 40, int(h * 0.80)
    bw, bh = 380, 720
    sh = Image.new("L", (w, h), 0)
    ImageDraw.Draw(sh).ellipse((cx - bw * 0.62, base - 40, cx + bw * 0.9, base + 60), fill=130)
    img.paste((150, 128, 112), (0, 0), sh.filter(ImageFilter.GaussianBlur(30)))

    body = (cx - bw // 2, base - bh, cx + bw // 2, base)
    glass = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(glass)
    for x in range(body[0], body[2] + 2):
        k = (x - body[0]) / bw
        v = 1 - abs(k - 0.35) * 1.2
        gd.line((x, 0, x, h), fill=(int(214 + 30 * v), int(226 + 24 * v), int(232 + 20 * v)))
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle(body, 70, fill=255)
    img.paste(glass, (0, 0), m)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((cx - 120, body[1] - 190, cx + 120, body[1] + 10), 36, fill=(250, 248, 244))
    d.rounded_rectangle((cx - 120, body[1] - 20, cx + 120, body[1] + 10), 8, fill=(232, 228, 222))
    d.rounded_rectangle((body[0] + 44, base - 470, body[2] - 44, base - 190), 18, fill=(252, 250, 246))
    f1 = ImageFont.truetype(str(FONTS / "DMSans-Bold.ttf"), 30)
    f2 = ImageFont.truetype(str(FONTS / "DMSerifDisplay-Regular.ttf"), 50)
    f3 = ImageFont.truetype(str(FONTS / "DMSans-Regular.ttf"), 24)
    d.text((cx, base - 420), "HANBIT LAB", font=f1, fill=(60, 50, 50), anchor="mm")
    d.text((cx, base - 350), "Rice Water", font=f2, fill=(40, 34, 36), anchor="mm")
    d.text((cx, base - 298), "glow toner", font=f3, fill=(110, 100, 100), anchor="mm")
    d.text((cx, base - 240), "300 ml", font=f3, fill=(140, 130, 130), anchor="mm")
    hl = Image.new("L", (w, h), 0)
    ImageDraw.Draw(hl).rounded_rectangle((body[0] + 36, body[1] + 60, body[0] + 70, base - 80), 16, fill=120)
    img.paste((255, 255, 255), (0, 0), hl.filter(ImageFilter.GaussianBlur(8)))
    for (lx, ly, rot) in [(cx - 330, base - 30, -30), (cx - 270, base - 70, 10), (cx + 300, base - 10, 25)]:
        leaf = Image.new("L", (w, h), 0)
        ImageDraw.Draw(leaf).ellipse((lx - 70, ly - 26, lx + 70, ly + 26), fill=255)
        leaf = leaf.rotate(rot, center=(lx, ly))
        img.paste((120, 150, 110), (0, 0), leaf)
    return img
