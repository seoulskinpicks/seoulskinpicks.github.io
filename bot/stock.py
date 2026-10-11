"""Cover photos for the ingredient posts.

Order of preference:
  1. photos/library/<ingredient id>.jpg (or .png/.webp): a picture you (or an AI image tool) added by hand.
     Optional credit/AI note in photos/library/credits.json: {"niacinamide": {"credit": "...", "ai": true}}
  2. A free Pexels photo (Pexels license: free for commercial use, no attribution required; we credit anyway).
     Needs the PEXELS_API_KEY secret (free at pexels.com/api). Without the key this step is simply skipped.

Everything fails soft: no photo -> the normal illustrated cover is used.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "photos" / "library"
API = "https://api.pexels.com/v1/search"

# Generic, pretty and face-free search phrases; one is picked per ingredient (stable per id).
QUERIES = {
    "skin": ["skincare serum dropper", "face cream texture", "skincare flat lay pastel", "glass serum bottle aesthetic",
             "natural skincare ingredients", "water droplets glossy skin product"],
    "hair": ["hair care shampoo bottle", "shiny healthy hair texture", "hair oil dropper", "hair brush aesthetic"],
}


@dataclass
class Photo:
    image: Image.Image
    credit: str = ""      # caption line, e.g. "📷 Photo: Jane Doe / Pexels"
    ai: bool = False


def _h(text: str) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest(), 16)


def _open(data: bytes) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")


def from_library(ident: str, root: Path | None = None) -> Photo | None:
    lib = (root or ROOT) / "photos" / "library"
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        f = lib / f"{ident}{ext}"
        if f.is_file():
            try:
                img = _open(f.read_bytes())
            except Exception:
                return None
            meta = {}
            try:
                meta = json.loads((lib / "credits.json").read_text(encoding="utf-8")).get(ident, {})
            except Exception:
                pass
            return Photo(img, str(meta.get("credit", "")), bool(meta.get("ai", False)))
    return None


def from_pexels(ident: str, area: str, key: str, session=None) -> Photo | None:
    sess = session or requests
    queries = QUERIES.get(area) or QUERIES["skin"]
    query = queries[_h(ident) % len(queries)]
    try:
        r = sess.get(API, params={"query": query, "orientation": "portrait", "per_page": 15, "size": "large"},
                     headers={"Authorization": key}, timeout=20)
        r.raise_for_status()
        photos = r.json().get("photos") or []
        if not photos:
            return None
        pick = photos[_h(ident + query) % len(photos)]
        src = pick.get("src", {})
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url:
            return None
        img_r = sess.get(url, timeout=30)
        img_r.raise_for_status()
        img = _open(img_r.content)
    except Exception:
        return None
    if img.width < 700:
        return None
    who = (pick.get("photographer") or "").strip()
    return Photo(img, f"📷 Photo: {who} / Pexels" if who else "📷 Photo: Pexels")


def find(data: dict, cfg=None, session=None, root: Path | None = None) -> Photo | None:
    """Photo for an ingredient entry (dict with id/name/area), or None."""
    if cfg is not None and not bool(cfg.raw.get("photos", {}).get("stock", True)):
        return None
    ident = str(data.get("id") or data.get("name") or "").strip()
    if not ident:
        return None
    photo = from_library(ident, root)
    if photo:
        return photo
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    return from_pexels(ident, data.get("area", "skin"), key, session)


def add_credit(caption: str, photo: Photo | None, limit: int = 2200) -> str:
    """Put the credit (and an AI note) just above the lone '.' line that precedes the hashtags."""
    if photo is None:
        return caption
    extra = [x for x in (photo.credit, "🤖 Image created with AI" if photo.ai else "") if x]
    if not extra:
        return caption
    block = "\n".join(extra)
    marker = "\n.\n"
    out = caption.replace(marker, f"\n{block}{marker}", 1) if marker in caption else caption + "\n" + block
    return out if len(out) <= limit else caption


def cover_bg(photo: Image.Image, size: tuple[int, int], flat: int | None = None, mirror: bool = False) -> Image.Image:
    """Photo cropped to fill the card, darkened from the middle down so white text stays readable."""
    w, h = size
    if mirror:  # last card: same photo, flipped, so the pair does not look like a copy
        photo = ImageOps.mirror(photo)
    pic = ImageOps.fit(photo, size, Image.LANCZOS, centering=(0.5, 0.4 if flat is None else 0.65))
    def alpha(y: int) -> int:
        if flat is not None:  # even dark veil: the whole card carries text
            return flat
        f = y / h
        if f < 0.14:
            return int(150 - f / 0.14 * 100)          # soft top shade keeps the @handle readable
        return int(50 + min(1.0, max(0.0, (f - 0.30) / 0.52)) ** 0.9 * 170)

    col = Image.new("L", (1, h))
    col.putdata([alpha(y) for y in range(h)])
    shade = col.resize(size)
    black = Image.new("RGB", size, (14, 8, 12))
    return Image.composite(black, pic, shade)
