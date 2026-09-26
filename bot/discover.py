"""Weekly discovery: Olive Young Global bestsellers -> check AliExpress official stores -> data/auto_queue.csv.

The daily post job reads this file after your own Google Sheet rows (your picks always go first).
You can delete any row on GitHub to skip it.

The same run also saves the full bestseller lists (incl. Hair) to data/oy_catalog.json, which the
ingredient posts use for their "Where to find it" card.
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

from .sources import Candidate
from .sources import ali
from .sources import oliveyoung as oy
from .util import add_summary, log, short_hash, warn

AUTO_COLUMNS = ["brand", "product", "category", "oliveyoung_link", "aliexpress_link", "rank",
                "store_rating", "review_count", "ali_check", "found_date"]


def auto_queue_path(cfg) -> Path:
    return cfg.root / "data" / "auto_queue.csv"


def read_auto_queue(cfg) -> list[dict]:
    path = auto_queue_path(cfg)
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def write_auto_queue(cfg, rows: list[dict]) -> None:
    path = auto_queue_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=AUTO_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in AUTO_COLUMNS})


def _oy_link(cfg, item: dict) -> str:
    template = cfg.kbeauty.get("oliveyoung_link_template") or "{url}"
    try:
        return template.format(url=item["url"], prdt_no=item["prdt_no"])
    except (KeyError, IndexError, ValueError):
        warn("oliveyoung_link_template 형식이 잘못됐어요. 상품 주소를 그대로 써요.")
        return item["url"]


def _check_ali(cand: Candidate, client, cfg) -> tuple[str, str]:
    """Returns (aliexpress_product_url, ali_check_text)."""
    try:
        if ali.auto_find(cand, client, cfg.ali):
            price = f" ${cand.price:.2f}" if cand.price else ""
            return f"https://www.aliexpress.com/item/{cand.product_id}.html", f"found (official store){price}"
        return "", "not found"
    except Exception as exc:
        return "", f"error: {str(exc)[:60]}"


def run_discover(cfg, state, today: str, ali_client=None, session=None, sleep=time.sleep, dry_run: bool = False) -> list[dict]:
    d = cfg.raw.get("discover", {})
    if not d.get("enabled", True):
        log("자동 수집이 꺼져 있어요 (config.toml [discover] enabled = false)")
        return []
    if not oy.robots_allows_display(session):
        warn("올리브영 글로벌 robots.txt 가 더 이상 수집을 허용하지 않거나 읽을 수 없어요. 자동 수집을 멈춰요.")
        return []

    queue_lists = d.get("lists", ["Skincare", "Suncare", "Face Masks"])
    catalog_lists = d.get("catalog_lists", ["Skincare", "Suncare", "Face Masks", "Hair"])
    top_n = int(d.get("top_n", 20))
    fetched = oy.fetch_bestsellers(list(dict.fromkeys(queue_lists + catalog_lists)), int(d.get("catalog_top_n", 100)),
                                   session=session, sleep=sleep)
    if fetched and not dry_run:
        from .editorial import save_catalog
        save_catalog(cfg, [it for it in fetched if it["list"] in catalog_lists], today)
        log(f"성분 글용 제품 목록 저장: {sum(1 for it in fetched if it['list'] in catalog_lists)}개 (data/oy_catalog.json)")
    items = [it for it in fetched if it["list"] in queue_lists and it["rank"] <= top_n]
    min_rating = float(d.get("min_rating", 4.5))
    min_reviews = int(d.get("min_reviews", 30))
    skip = {b.lower() for b in d.get("skip_brands", [])}
    max_new = int(d.get("max_new", 10))

    from .sources.kbeauty import read_rows  # manual sheet rows
    try:
        manual = read_rows(cfg)
    except Exception:
        manual = []
    queue = read_auto_queue(cfg)
    known = state.used_keys()
    known |= {"kb-" + short_hash(r.get("brand", ""), r.get("product", "")) for r in manual + queue}

    client = ali_client or (ali.AliClient(*cfg.ali_keys) if cfg.ali_keys else None)

    # Rows found earlier while there was no Ali key: check them now.
    if client is not None:
        for r in queue:
            if r.get("ali_check", "").startswith("not checked") and not r.get("aliexpress_link"):
                cand = Candidate(source="kbeauty", key="", brand=r["brand"], name=r["product"], link="", category=r.get("category", "other"))
                r["aliexpress_link"], r["ali_check"] = _check_ali(cand, client, cfg)
                sleep(1)

    # Best ranks first, mixing the lists (Skincare #1, Suncare #1, Masks #1, Skincare #2 ...)
    items.sort(key=lambda x: x["rank"])
    added: list[dict] = []
    for it in items:
        if len(added) >= max_new:
            break
        key = "kb-" + short_hash(it["brand"], it["product"])
        if key in known:
            continue
        if it["brand"].lower() in skip:
            continue
        if (it["store_rating"] or 0) < min_rating or (it["review_count"] or 0) < min_reviews:
            continue
        row = {
            "brand": it["brand"],
            "product": it["product"],
            "category": it["category"],
            "oliveyoung_link": _oy_link(cfg, it),
            "aliexpress_link": "",
            "rank": f"Olive Young Global · #{it['rank']} {it['list']}",
            "store_rating": f"{it['store_rating']:.1f}" if it["store_rating"] else "",
            "review_count": str(it["review_count"] or ""),
            "ali_check": "not checked (no Ali key yet)",
            "found_date": today,
        }
        if client is not None:
            cand = Candidate(source="kbeauty", key=key, brand=it["brand"], name=it["product"], link=it["url"], category=it["category"])
            row["aliexpress_link"], row["ali_check"] = _check_ali(cand, client, cfg)
            sleep(1)
        added.append(row)
        known.add(key)

    if not dry_run:
        write_auto_queue(cfg, queue + added)

    found = sum(1 for r in added if r["ali_check"].startswith("found"))
    log(f"새로 추가: {len(added)}개 (알리 공식 스토어에서 찾음: {found}개)")
    lines = [f"### {'[미리보기] ' if dry_run else ''}올리브영 글로벌 베스트셀러 → 새로 {len(added)}개 추가", "",
             "| 순위 | 브랜드 | 제품 | 평점 (리뷰) | 알리 |", "|---|---|---|---|---|"]
    for r in added:
        lines.append(f"| {r['rank'].split('· ')[-1]} | {r['brand']} | {r['product']} | {r['store_rating']} ({r['review_count']}) | {r['ali_check']} |")
    if not added:
        lines.append("| - | 새 제품 없음 (이미 목록에 있거나 조건 미달) | | | |")
    add_summary("\n".join(lines))
    return added
