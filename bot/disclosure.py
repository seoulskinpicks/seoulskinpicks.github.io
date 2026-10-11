"""Which links really earn a commission? Only those get '#ad' / 'I may earn a small commission'.

  - AliExpress: links from the Affiliate API (s.click.aliexpress.com) are tracked. A plain aliexpress.com item address is not.
  - Olive Young Global: a plain product link earns nothing. It counts only once config.toml [kbeauty]
    has an affiliate oliveyoung_link_template (not just "{url}") or an oliveyoung_code.
  - Any other address (e.g. a link you pasted into the sheet yourself) is assumed to be your own affiliate link.
"""
from __future__ import annotations

from urllib.parse import urlparse


def is_affiliate_url(url: str, cfg) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    host = (urlparse(url).netloc or "").lower()
    if host.endswith("aliexpress.com") or host.endswith("aliexpress.us"):
        return host.startswith("s.click.") or "aff_" in url
    if host.endswith("oliveyoung.com"):
        kb = cfg.kbeauty if cfg is not None else {}
        template = (kb.get("oliveyoung_link_template") or "{url}").strip()
        return template != "{url}" or bool(str(kb.get("oliveyoung_code", "")).strip())
    return True


def any_affiliate(links, cfg) -> bool:
    """links: dict of store -> url, or a list of urls."""
    values = links.values() if isinstance(links, dict) else (links or [])
    return any(is_affiliate_url(u, cfg) for u in values if u)


def candidate_affiliate(cand, cfg) -> bool:
    return any_affiliate([getattr(cand, "link", ""), getattr(cand, "oy_link", ""), getattr(cand, "ali_link", "")], cfg)


def post_affiliate(post: dict, cfg) -> bool:
    """A saved post record: any of its shop links earns a commission."""
    urls = [post.get("link", "")] + list((post.get("links") or {}).values())
    for p in post.get("products") or []:
        urls += list((p.get("links") or {}).values())
    return any_affiliate(urls, cfg)
