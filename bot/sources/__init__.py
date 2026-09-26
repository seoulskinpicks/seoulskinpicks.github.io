"""Where today's product comes from: the K-beauty sheet or AliExpress tools."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candidate:
    source: str                 # "kbeauty" or "tools"
    key: str                    # unique id, used to avoid posting the same thing twice
    brand: str                  # brand (K-beauty) or "" (tools)
    name: str                   # product name shown on the cards
    link: str                   # affiliate link
    category: str               # knowledge.CATEGORIES key or knowledge.TOOLS key
    image_url: str | None = None
    rank: str = ""
    key_points: list[str] = field(default_factory=list)
    comment: str = ""
    hook: str = ""
    raw_title: str = ""
    price: float | None = None
    original_price: float | None = None
    currency: str = "USD"
    rating: str = ""            # "97.1%"
    orders: int | None = None
    product_id: str = ""
    store: str = ""            # "aliexpress" when a K-beauty row links to an AliExpress product
    oy_link: str = ""          # Olive Young Global affiliate link (K-beauty rows)
    ali_link: str = ""         # AliExpress affiliate link (set when an AliExpress listing is attached)
    # K-beauty extras (all optional)
    photo: str = ""             # file in photos/, an image URL, or a Google Drive share link
    my_rating: float | None = None       # your own rating 0-5 (only if you used it)
    store_rating: float | None = None    # store average, copied from the product page
    review_count: int | None = None      # number of store reviews
    review_highlights: list[str] = field(default_factory=list)  # themes YOU summarized from reviews
