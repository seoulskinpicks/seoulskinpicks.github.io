"""Beauty tools from the AliExpress Affiliate API (Open Platform, api-sg.aliexpress.com).

Needs secrets ALI_APP_KEY, ALI_APP_SECRET, ALI_TRACKING_ID.
Searches one tool type at a time (least recently used first), filters out
counterfeit-risk brands, skin-applied products and electronics, then picks the
best-selling well-rated item that hasn't been posted before.
"""
from __future__ import annotations

import hashlib
import re
import time

import requests

from ..knowledge import TOOLS, blocked_reason, matches_tool
from ..util import log, scrub, warn
from . import Candidate

API_URL = "https://api-sg.aliexpress.com/sync"


class AliError(RuntimeError):
    pass


class AliClient:
    def __init__(self, app_key: str, app_secret: str, tracking_id: str, session=None):
        self.app_key = app_key
        self.app_secret = app_secret
        self.tracking_id = tracking_id
        self.http = session or requests.Session()

    def _sign(self, params: dict) -> str:
        base = "".join(f"{k}{params[k]}" for k in sorted(params))
        return hashlib.md5(f"{self.app_secret}{base}{self.app_secret}".encode("utf-8")).hexdigest().upper()

    def call(self, method: str, **app_params) -> dict:
        system = {
            "app_key": self.app_key,
            "method": method,
            "sign_method": "md5",
            "timestamp": str(int(time.time() * 1000)),
            "format": "json",
            "v": "2.0",
        }
        body = {k: str(v) for k, v in app_params.items() if v not in (None, "")}
        system["sign"] = self._sign({**system, **body})
        try:
            resp = self.http.post(API_URL, params=system, data=body, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise AliError(scrub(str(exc), self.app_secret)) from None
        if "error_response" in payload:
            err = payload["error_response"]
            raise AliError(f"{err.get('code')} {err.get('msg')} {err.get('sub_msg', '')}".strip())
        key = method.replace(".", "_") + "_response"
        result = payload.get(key, {}).get("resp_result", {})
        code = int(result.get("resp_code", 0) or 0)
        if code == 405:
            return {}   # "The result is empty": the key worked, the search simply found nothing
        if code != 200:
            raise AliError(f"resp_code {result.get('resp_code')}: {result.get('resp_msg')}")
        return result.get("result") or {}

    # ------------------------------------------------------------------
    def search(self, keywords: str, country: str, currency: str, language: str, max_price_usd: float) -> list[dict]:
        common = dict(
            keywords=keywords,
            max_sale_price=int(max_price_usd * 100),   # API expects cents
            page_no=1,
            page_size=50,
            ship_to_country=country,
            sort="LAST_VOLUME_DESC",
            target_currency=currency,
            target_language=language,
            tracking_id=self.tracking_id,
        )
        products: list[dict] = []
        for method in ("aliexpress.affiliate.hotproduct.query", "aliexpress.affiliate.product.query"):
            try:
                result = self.call(method, **common)
            except AliError as exc:
                warn(f"알리 API ({method.split('.')[-2]}) 오류: {exc}")
                continue
            items = (result.get("products") or {}).get("product") or []
            products.extend(items)
            if len(products) >= 10:
                break
        return products

    def find(self, keywords: str, country: str, currency: str, language: str) -> list[dict]:
        """Keyword search without a price cap (used to find a K-beauty product's official listing)."""
        result = self.call(
            "aliexpress.affiliate.product.query",
            keywords=keywords,
            page_no=1,
            page_size=30,
            ship_to_country=country,
            sort="LAST_VOLUME_DESC",
            target_currency=currency,
            target_language=language,
            tracking_id=self.tracking_id,
        )
        return (result.get("products") or {}).get("product") or []

    def product_detail(self, product_id: str, country: str, currency: str, language: str) -> dict | None:
        result = self.call(
            "aliexpress.affiliate.productdetail.get",
            product_ids=product_id,
            country=country,
            target_currency=currency,
            target_language=language,
            tracking_id=self.tracking_id,
        )
        items = (result.get("products") or {}).get("product") or []
        return items[0] if items else None

    def affiliate_link(self, url: str) -> str | None:
        result = self.call(
            "aliexpress.affiliate.link.generate",
            promotion_link_type=0,
            source_values=url,
            tracking_id=self.tracking_id,
        )
        links = (result.get("promotion_links") or {}).get("promotion_link") or []
        return links[0].get("promotion_link") if links else None


ALI_HOST = re.compile(r"^https?://([\w-]+\.)*(aliexpress\.(com|us|ru)|aliexpress\.[a-z.]+|ali\.ski)/", re.I)


def is_ali_url(url: str) -> bool:
    return bool(ALI_HOST.match((url or "").strip()))


def product_id_from_url(url: str, session=None) -> str | None:
    """Finds the product id in an AliExpress link; follows short links (a.aliexpress.com/_xxx, s.click...)."""
    pat = re.compile(r"/item/(?:[\w-]+/)?(\d{8,})\.html|[?&](?:productId|product_id|itemId|item_id)=(\d{8,})")
    m = pat.search(url or "")
    if m:
        return m.group(1) or m.group(2)
    try:
        http = session or requests
        r = http.get(url, timeout=20, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        for candidate in [getattr(r, "url", "")] + [h.headers.get("location", "") for h in getattr(r, "history", [])]:
            m = pat.search(candidate or "")
            if m:
                return m.group(1) or m.group(2)
        m = pat.search(r.text[:200000] if hasattr(r, "text") else "")
        if m:
            return m.group(1) or m.group(2)
    except Exception:
        pass
    return None


def enrich_from_ali(cand: Candidate, client, cfg_ali: dict, session=None) -> bool:
    """Fill a sheet row that points at an AliExpress product: photo, price, rating, orders, affiliate link."""
    pid = product_id_from_url(cand.link, session=session)
    if not pid:
        warn(f"{cand.brand}: 알리 주소에서 상품 번호를 찾지 못했어요 → {cand.link[:80]}")
        return False
    p = client.product_detail(pid, cfg_ali.get("ship_to_country", "US"), cfg_ali.get("currency", "USD"), cfg_ali.get("language", "EN"))
    if not p:
        warn(f"{cand.brand}: 알리 상품 정보를 가져오지 못했어요 (제휴 대상이 아니거나 판매 중지일 수 있어요)")
        return False
    shop = str(p.get("shop_name") or "")
    if shop and "official" not in shop.lower():
        warn(f"{cand.brand}: 판매처 '{shop}' 이름에 'Official'이 없어요. 공식 스토어가 맞는지 꼭 확인해주세요.")
    p.setdefault("product_id", pid)
    return _apply_product(cand, p, client, cfg_ali)


_MATCH_NOISE = {"set", "the", "and", "for", "with", "ml", "ea", "pcs", "mini", "new", "special", "limited", "edition"}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def auto_find(cand: Candidate, client, cfg_ali: dict) -> bool:
    """Look for the same product in the brand's OFFICIAL AliExpress store. Strict on purpose:
    the seller name must contain the brand and 'official', and most words of the product name
    must appear in the title. Anything less -> no AliExpress link (never guess)."""
    brand = _norm(cand.brand).replace(" ", "")
    words = [w for w in _norm(cand.name).split()
             if len(w) > 1 and w not in _MATCH_NOISE and not re.fullmatch(r"\d+(ml|g|ea|oz|pcs|sheets?)?", w)]
    if not brand or not words:
        return False
    results: list[dict] = []
    # Full names rarely match the API's keyword search, so also try shorter queries.
    queries = [f"{cand.brand} {cand.name}", f"{cand.brand} {' '.join(words[:3])}", cand.brand]
    for q in dict.fromkeys(queries):
        results = client.find(q, cfg_ali.get("ship_to_country", "US"),
                              cfg_ali.get("currency", "USD"), cfg_ali.get("language", "EN"))
        if results:
            break
    if results and not any(r.get("shop_name") for r in results):
        log(f"  {cand.brand}: 알리 API가 판매자 이름을 주지 않아 공식 스토어를 확인할 수 없어요 → 올리브영만")
        return False
    best, best_score = None, 0.0
    for p in results:
        shop = _norm(p.get("shop_name", ""))
        title = _norm(p.get("product_title", ""))
        if "official" not in shop or brand not in shop.replace(" ", ""):
            continue
        if brand not in title.replace(" ", ""):
            continue
        title_words = set(title.split())
        hit = sum(1 for w in words if w in title_words) / len(words)
        if hit < 0.6:
            continue
        rating = _num(p.get("evaluate_rate")) or 0
        if rating and rating < 85:
            continue
        score = hit * 10 + (_num(p.get("lastest_volume")) or 0) ** 0.25
        if score > best_score:
            best, best_score = p, score
    if not best:
        log(f"  {cand.brand}: 알리 공식 스토어에서 같은 제품을 못 찾았어요 → 올리브영만")
        return False
    log(f"  {cand.brand}: 알리 공식 스토어 상품을 찾았어요 ({best.get('shop_name')})")
    return _apply_product(cand, best, client, cfg_ali)


def _apply_product(cand: Candidate, p: dict, client, cfg_ali: dict) -> bool:
    pid = str(p.get("product_id", ""))
    link = p.get("promotion_link") or client.affiliate_link(p.get("product_detail_url") or f"https://www.aliexpress.com/item/{pid}.html")
    if not link:
        warn(f"{cand.brand}: 제휴 링크를 만들지 못했어요")
        return False
    cand.store = "aliexpress"
    cand.link = link
    cand.ali_link = link
    cand.product_id = pid
    cand.image_url = p.get("product_main_image_url")
    cand.price = _num(p.get("target_sale_price"))
    cand.original_price = _num(p.get("target_original_price"))
    cand.currency = p.get("target_sale_price_currency") or cfg_ali.get("currency", "USD")
    cand.rating = str(p.get("evaluate_rate") or "")
    cand.orders = int(_num(p.get("lastest_volume")) or 0) or None
    cand.raw_title = p.get("product_title", "")
    return True


def _num(value) -> float | None:
    try:
        return float(str(value).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def pick_product(products: list[dict], tool_key: str, cfg_ali: dict, used_ids: set[str]) -> dict | None:
    min_rating = float(cfg_ali.get("min_rating_percent", 90))
    min_orders = int(cfg_ali.get("min_orders", 200))
    max_price = float(cfg_ali.get("max_price_usd", 25))
    extra = cfg_ali.get("extra_blocked_words", [])
    best, best_score = None, -1.0
    seen = set()
    for p in products:
        pid = str(p.get("product_id", ""))
        if not pid or pid in seen or pid in used_ids:
            continue
        seen.add(pid)
        title = p.get("product_title", "")
        if not matches_tool(title, tool_key):
            continue
        if blocked_reason(title, extra):
            continue
        rating = _num(p.get("evaluate_rate"))
        orders = _num(p.get("lastest_volume")) or 0
        price = _num(p.get("target_sale_price"))
        if rating is None or rating < min_rating or orders < min_orders:
            continue
        if price is None or price <= 0 or price > max_price:
            continue
        if not p.get("product_main_image_url"):
            continue
        score = orders * (rating / 100) ** 4
        if score > best_score:
            best, best_score = p, score
    return best


def next_candidate(cfg, state, client: AliClient | None = None) -> Candidate | None:
    keys = cfg.ali_keys
    if not keys and client is None:
        log("알리 API 키가 아직 없어서 알리 도구는 건너뛰어요.")
        return None
    client = client or AliClient(*keys)
    ali = cfg.ali
    tools = [t for t in ali.get("tools", list(TOOLS)) if t in TOOLS]
    used_ids = set(state.data.get("ali_used", []))
    for tool_key in state.tool_order(tools):
        tool = TOOLS[tool_key]
        log(f"알리 검색: {tool['query']}")
        products = client.search(
            tool["query"],
            ali.get("ship_to_country", "US"),
            ali.get("currency", "USD"),
            ali.get("language", "EN"),
            float(ali.get("max_price_usd", 25)),
        )
        p = pick_product(products, tool_key, ali, used_ids)
        if not p:
            log(f"  조건에 맞는 상품 없음 ({len(products)}개 검토)")
            continue
        link = p.get("promotion_link")
        if not link:
            try:
                link = client.affiliate_link(p.get("product_detail_url") or f"https://www.aliexpress.com/item/{p['product_id']}.html")
            except AliError as exc:
                warn(f"제휴 링크 생성 실패: {exc}")
                continue
        if not link:
            continue
        orders = int(_num(p.get("lastest_volume")) or 0)
        cand = Candidate(
            source="tools",
            key=f"ali-{p['product_id']}",
            brand="",
            name=tool["name"],
            link=link,
            category=tool_key,
            image_url=p.get("product_main_image_url"),
            raw_title=p.get("product_title", ""),
            price=_num(p.get("target_sale_price")),
            original_price=_num(p.get("target_original_price")),
            currency=p.get("target_sale_price_currency") or ali.get("currency", "USD"),
            rating=str(p.get("evaluate_rate", "")),
            orders=orders,
            product_id=str(p["product_id"]),
            ali_link=link,
        )
        log(f"알리 선택: {cand.raw_title[:70]}… ${cand.price} / {cand.rating} / {orders}건")
        return cand
    return None
