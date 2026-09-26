"""Olive Young GLOBAL bestsellers (global.oliveyoung.com).

Uses the same JSON the public "Bestsellers" page loads. Olive Young Global's robots.txt
explicitly allows /display for general bots ("User-agent: * / Allow: /display"), so this
stays within the site's rules. We identify ourselves, ask for a handful of lists once a
week, and pause between requests.

The Korean site (oliveyoung.co.kr) disallows all automated access, so it is never used.
Product images from Olive Young are NOT used (no permission to reuse them).
"""
from __future__ import annotations

import re
import time

import requests

from ..knowledge import match_category
from ..util import clean_space, log, warn

BASE = "https://global.oliveyoung.com"
LIST_URL = BASE + "/display/product/best-seller/order-best"
ROBOTS_URL = BASE + "/robots.txt"
USER_AGENT = "Mozilla/5.0 (compatible; KBeautyPicksBot/1.0; weekly bestseller check)"

# Category numbers used by the Bestsellers page
CATEGORIES = {
    "Skincare": "1000000008",
    "Suncare": "1000000011",
    "Face Masks": "1000000003",
    "Makeup": "1000000031",
    "Hair": "1000000070",
    "Bath & Body": "1000000052",
}
CATEGORY_FALLBACK = {
    "Suncare": "sunscreen",
    "Face Masks": "sheet_mask",
    "Hair": "hair",
    "Makeup": "other",
    "Skincare": "other",
    "Bath & Body": "other",
}
_TRAILING_NOISE = {"set", "duo", "special", "limited", "edition", "triple", "double", "kit", "trio", "bundle", "only"}


def product_url(prdt_no: str) -> str:
    return f"{BASE}/product/detail?prdtNo={prdt_no}"


def clean_name(brand: str, name: str) -> str:
    """'[Sanrio EDITION] S.NATURE Aqua Squalane Cream 60ml+60ml (2 Options)' -> 'Aqua Squalane Cream 60ml'"""
    s = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", name or "")
    s = re.sub(r"(\d+(?:\.\d+)?\s?(?:ml|mL|g|ea|pcs|sheets?))\s?[+*x]\s?\d+(?:\.\d+)?\s?(?:ml|mL|g|ea|pcs|sheets?)", r"\1", s)
    s = clean_space(s)
    if brand and s.lower().startswith(brand.lower()):
        s = s[len(brand):].strip(" -:·")
    words = s.split()
    while words and words[-1].lower().strip(",.+") in _TRAILING_NOISE:
        words.pop()
    return clean_space(" ".join(words)) or clean_space(name)


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def robots_allows_display(session=None) -> bool:
    """Re-check robots.txt every run, so the bot stops by itself if the rules change."""
    http = session or requests
    try:
        text = http.get(ROBOTS_URL, timeout=20, headers={"User-Agent": USER_AGENT}).text
    except Exception:
        return False
    applies = False
    allowed = True
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = [x.strip() for x in line.split(":", 1)]
        field = field.lower()
        if field == "user-agent":
            applies = value == "*"
        elif applies and field == "disallow" and value and ("/display".startswith(value) or value.startswith("/display/product")):
            allowed = False
    return allowed


def fetch_bestsellers(categories: list[str], top_n: int = 20, session=None, pause: float = 3.0, sleep=time.sleep) -> list[dict]:
    http = session or requests
    out: list[dict] = []
    for i, cat in enumerate(categories):
        ctgr = CATEGORIES.get(cat)
        if not ctgr:
            warn(f"알 수 없는 올리브영 카테고리: {cat}")
            continue
        if i:
            sleep(pause)
        params = {"ctgrNo": ctgr, "acesCntryCode": "00", "dispPageTypeCode": "30", "langCode": "en", "showSoldoutProduct": "false"}
        try:
            r = http.get(LIST_URL, params=params, timeout=30,
                         headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Referer": BASE + "/display/page/best-seller"})
            r.raise_for_status()
            items = r.json()
        except Exception as exc:
            warn(f"올리브영 글로벌 {cat} 베스트셀러를 가져오지 못했어요: {exc}")
            continue
        if not isinstance(items, list):
            warn(f"올리브영 글로벌 응답 형식이 바뀌었어요 ({cat}). 봇 업데이트가 필요해요.")
            continue
        rank = 0
        for p in items:
            if p.get("soldOutYn") == "Y" or not p.get("prdtNo") or not p.get("prdtName"):
                continue
            rank += 1
            if rank > top_n:
                break
            brand = clean_space(p.get("brandName"))
            name = clean_name(brand, p.get("prdtName", ""))
            category = match_category(name)
            if category == "other":
                category = CATEGORY_FALLBACK.get(cat, "other")
            out.append({
                "brand": brand,
                "product": name,
                "raw_name": p.get("prdtName", ""),
                "prdt_no": p["prdtNo"],
                "url": product_url(p["prdtNo"]),
                "list": cat,
                "rank": rank,
                "category": category,
                "store_rating": _num(p.get("avgScore")),
                "review_count": int(_num(p.get("reviewCnt")) or 0) or None,
                "price": _num(p.get("saleAmt")),
            })
        log(f"올리브영 글로벌 {cat}: {rank}개 확인")
    return out
