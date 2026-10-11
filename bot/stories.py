"""Instagram Story for each new post: the post's cover on a soft blurred 9:16 background.

The API can publish a story image but cannot add stickers (link, poll, ...), so the image itself carries the message:
"NEW POST" on top and a pointer to the profile underneath. Instagram covers roughly the top 250 px and the bottom
300 px of a story with its own buttons, so everything sits in between.
config.toml [stories]: enabled (default true).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .reels import RH, RW, frame
from .render import SANS, SANS_B, SANS_SB, F, rgb, tracked, tracked_w, cap_metrics

SCALE, TOP = 0.80, 360


def enabled(cfg) -> bool:
    return bool(cfg.raw.get("stories", {}).get("enabled", True))


def make_story(slide: Path, out: Path, handle: str, kind_label: str = "NEW POST") -> Path:
    tmp = out.with_suffix(".png")
    frame(slide, tmp, scale=SCALE, top=TOP)
    img = Image.open(tmp).convert("RGB")
    tmp.unlink(missing_ok=True)
    d = ImageDraw.Draw(img, "RGBA")
    ink, soft = (255, 255, 255), (255, 255, 255, 215)
    # pill with the label, centred under Instagram's own top bar
    f = F(SANS_SB, 34)
    cap, _ = cap_metrics(f)
    tr = 4.0
    w = tracked_w(d, kind_label, f, tr) + 76
    h = cap + 40
    x0, y0 = (RW - w) / 2, 262
    d.rounded_rectangle((x0, y0, x0 + w, y0 + h), h / 2, fill=(20, 12, 16, 190))
    tracked(d, x0 + 38, y0 + 20 + cap, kind_label, f, ink, tr)
    # pointer under the card
    card_bottom = TOP + int(1350 * SCALE)
    y = card_bottom + 56
    for text, font, fill in (("Read it on our profile", F(SANS_B, 46), (255, 255, 255, 255)),
                             (f"@{handle.lstrip('@')}", F(SANS, 38), soft)):
        w2 = d.textlength(text, font=font)
        # soft dark plate keeps white text readable on any background colour
        d.rounded_rectangle(((RW - w2) / 2 - 30, y - 8, (RW + w2) / 2 + 30, y + 62), 35, fill=(20, 12, 16, 150))
        d.text(((RW - w2) / 2, y), text, font=font, fill=fill)
        y += 86
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=90)
    return out
