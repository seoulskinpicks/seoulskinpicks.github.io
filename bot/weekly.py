"""'This week in K-beauty' (Thursday post) and trend-aware topic order.

Korea  : Naver search trend API via NAVER API HUB (official, free up to 30,000 calls:
         NAVER_CLIENT_ID / NAVER_CLIENT_SECRET = the API HUB Client ID / Client Secret).
         Weekly search interest for ~40 ingredients (content/keywords.toml), last full week (Mon-Sun)
         vs the week before. Every request carries PDRN as an anchor so all terms share one scale.
Abroad : Olive Young Global bestsellers (weekly list saved by 'Find bestsellers'), with rank moves
         vs the previous week.
The weekly job (Monday) saves data/trend_latest.json; the Thursday post and the ingredient order read it.
"""
from __future__ import annotations

import json
import tomllib
from datetime import date as Date
from datetime import timedelta
from pathlib import Path

import requests

from .util import log, scrub, warn

NAVER_URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"  # NAVER API HUB (Naver Cloud)
ANCHOR = "pdrn"


def trend_path(cfg) -> Path:
    return cfg.root / "data" / "trend_latest.json"


def load_terms(cfg) -> list[dict]:
    from .editorial import content_dir
    path = content_dir(cfg) / "keywords.toml"
    if not path.exists():
        return []
    with open(path, "rb") as fh:
        return [t for t in tomllib.load(fh).get("term", []) if t.get("keywords")]


def last_full_week(today: Date) -> tuple[Date, Date]:
    """Monday..Sunday of the last complete week before `today`."""
    end = today - timedelta(days=today.weekday() + 1)
    return end - timedelta(days=6), end


def naver_trends(cfg, today: Date, session=None) -> list[dict]:
    keys = cfg.naver_keys
    if not keys:
        return []
    http = session or requests
    terms = load_terms(cfg)
    anchor = next((t for t in terms if t["id"] == ANCHOR), terms[0] if terms else None)
    if anchor is None:
        return []
    start_week, end = last_full_week(today)
    start = end - timedelta(days=34)
    this_days = {(end - timedelta(days=i)).isoformat() for i in range(7)}
    prev_days = {(end - timedelta(days=i)).isoformat() for i in range(7, 14)}
    others = [t for t in terms if t is not anchor]
    out: dict[str, dict] = {}
    for i in range(0, len(others), 4):
        batch = [anchor] + others[i:i + 4]
        body = {"startDate": start.isoformat(), "endDate": end.isoformat(), "timeUnit": "date",
                "keywordGroups": [{"groupName": t["id"], "keywords": t["keywords"][:20]} for t in batch]}
        try:
            r = http.post(NAVER_URL, json=body, timeout=30, headers={
                "X-NCP-APIGW-API-KEY-ID": keys[0], "X-NCP-APIGW-API-KEY": keys[1], "Content-Type": "application/json"})
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code} {str(getattr(r, 'text', ''))[:120]}")
            results = r.json().get("results", [])
        except Exception as exc:
            warn(f"네이버 검색 트렌드를 가져오지 못했어요: {scrub(str(exc), *keys)[:160]}")
            return []
        sums = {}
        for res in results:
            data = res.get("data", [])
            sums[res.get("title")] = (sum(d["ratio"] for d in data if d.get("period") in this_days),
                                      sum(d["ratio"] for d in data if d.get("period") in prev_days))
        a_now = sums.get(anchor["id"], (0, 0))[0]
        for t in batch:
            now, prev = sums.get(t["id"], (0.0, 0.0))
            if t["id"] in out and t is anchor:
                continue
            out[t["id"]] = {
                "id": t["id"], "name": t["name"], "area": t.get("area", "skin"),
                "level": (now / a_now) if a_now else None, "this_week": round(now, 2), "last_week": round(prev, 2),
                "change": round((now / prev - 1) * 100) if prev else None,
            }
    rows = [r for r in out.values() if r["level"]]
    top = max((r["level"] for r in rows), default=0)
    for r in out.values():
        r["index"] = round(r["level"] / top * 100) if (r["level"] and top) else 0
    log(f"네이버 검색 트렌드: {len(rows)}개 성분 ({start_week}~{end})")
    return sorted(out.values(), key=lambda r: -r["index"])


def product_moves(catalog: list[dict], lists=("Skincare",), n: int = 10) -> list[dict]:
    rows = [c for c in catalog if c.get("list") in lists]
    rows.sort(key=lambda c: (c.get("rank") or 999))
    return rows[:n]


def compute(cfg, today: Date, session=None) -> dict:
    from .editorial import load_catalog
    start, end = last_full_week(today)
    data = {"week_start": start.isoformat(), "week_end": end.isoformat(), "made": today.isoformat(),
            "korea": naver_trends(cfg, today, session)}
    catalog = load_catalog(cfg)
    data["products"] = [{k: c.get(k) for k in ("brand", "product", "prdt_no", "url", "rank", "prev_rank", "store_rating",
                                                "review_count", "list")} for c in product_moves(catalog)]
    return data


def save(cfg, data: dict) -> None:
    p = trend_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load(cfg) -> dict | None:
    p = trend_path(cfg)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def latest(cfg, today: Date, session=None) -> dict | None:
    """Saved weekly data if it's for last week; otherwise compute it now (and keep it)."""
    start, end = last_full_week(today)
    data = load(cfg)
    if data and data.get("week_end") == end.isoformat() and (data.get("korea") or not cfg.naver_keys):
        return data
    try:
        data = compute(cfg, today, session)
    except Exception as exc:
        warn(f"이번 주 트렌드 계산 실패: {exc}")
        return data
    if data.get("korea") or data.get("products"):
        save(cfg, data)
    return data


def korea_scores(cfg) -> dict[str, float]:
    """id -> score for ordering ingredient topics (search interest, boosted when rising)."""
    data = load(cfg) or {}
    out = {}
    for r in data.get("korea", []):
        if r.get("index"):
            ch = r.get("change")
            boost = 1 + max(-0.5, min(1.0, (ch or 0) / 100))
            out[r["id"]] = r["index"] * boost
    return out
