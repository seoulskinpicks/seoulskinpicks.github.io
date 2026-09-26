"""Loads product photos from the repo's photos/ folder, an image URL or a Google Drive link.

Handles iPhone HEIC photos and phone rotation (EXIF) automatically.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import requests
from PIL import Image, ImageOps

try:  # iPhone photos (.heic)
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # pragma: no cover - optional dependency
    pass

ROOT = Path(__file__).resolve().parent.parent
PHOTOS = ROOT / "photos"


def direct_url(url: str) -> str:
    """Turn share links into direct-download links."""
    m = re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?(?:.*&)?id=)([\w-]{10,})", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    if "dropbox.com" in url:
        stripped = re.sub(r"[?&]dl=[01]", "", url)
        return stripped + ("&" if "?" in stripped else "?") + "raw=1"
    return url


def _open(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def load_image(ref, root: Path | None = None) -> Image.Image | None:
    """Returns an RGB image or None. `ref` can be a PIL image, URL or a filename in photos/."""
    if ref is None or ref == "":
        return None
    if isinstance(ref, Image.Image):
        return ref.convert("RGB")
    ref = str(ref).strip()
    try:
        if re.match(r"^https?://", ref):
            r = requests.get(direct_url(ref), timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            return _open(r.content)
        base = root or ROOT
        for candidate in (base / "photos" / ref, base / ref):
            if candidate.is_file():
                return _open(candidate.read_bytes())
    except Exception:
        return None
    return None
