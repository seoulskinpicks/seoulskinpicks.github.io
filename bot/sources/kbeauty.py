"""K-beauty picks from a Google Sheet (published as CSV) or data/kbeauty_queue.csv.

Each row = one post. Rows already posted are skipped automatically.
Columns (English or Korean headers both work):
  brand/브랜드, product/제품명, category/카테고리            <- required
  oliveyoung_link and/or aliexpress_link (or a single `link`)  <- at least one
  If only the Olive Young link is given, the bot tries to find the same product
  in the brand's *official* AliExpress store and adds that link too.
  photo/사진, rank/순위, key_points/특징, my_comment/한줄평, my_rating/내별점,
  store_rating/평점, review_count/리뷰수, review_highlights/리뷰요약, hook/훅, date/날짜  <- optional
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date as Date

import requests

from ..knowledge import match_category
from ..util import clean_space, has_hangul, is_http_url, log, short_hash, warn
from . import Candidate
from . import ali

HEADER_ALIASES = {
    "brand": ["brand", "브랜드"],
    "product": ["product", "product name", "name", "제품", "제품명", "상품명"],
    "category": ["category", "type", "카테고리", "종류"],
    "link": ["link", "url", "affiliate link", "링크", "제휴링크", "제휴 링크"],
    "oliveyoung_link": ["oliveyoung_link", "olive young link", "oy_link", "올리브영링크", "올리브영 링크"],
    "aliexpress_link": ["aliexpress_link", "aliexpress link", "ali_link", "알리링크", "알리 링크"],
    "rank": ["rank", "ranking", "순위", "랭킹"],
    "key_points": ["key_points", "key points", "points", "features", "특징", "포인트"],
    "my_comment": ["my_comment", "my comment", "comment", "review", "한줄평", "코멘트", "후기"],
    "hook": ["hook", "headline", "훅", "제목"],
    "date": ["date", "post date", "날짜", "게시일"],
    "photo": ["photo", "image", "picture", "사진", "이미지"],
    "my_rating": ["my_rating", "my rating", "내별점", "내 별점"],
    "store_rating": ["store_rating", "store rating", "rating", "평점", "평균평점", "평균 평점"],
    "review_count": ["review_count", "review count", "reviews", "리뷰수", "리뷰 수"],
    "review_highlights": ["review_highlights", "review highlights", "review_summary", "리뷰요약", "리뷰 요약"],
}


def _rating(value: str) -> float | None:
    """'4.8', '★4.8', '4.8/5', '4,8' -> 4.8 (only 0-5 accepted)."""
    m = re.search(r"\d+(?:[.,]\d+)?", (value or "").replace("★", ""))
    if not m:
        return None
    v = float(m.group(0).replace(",", "."))
    return v if 0 < v <= 5 else None


def _count(value: str) -> int | None:
    """'12,345', '1.2만', '12k', '3천' -> int."""
    s = (value or "").strip().lower().replace(",", "").replace(" ", "")
    m = re.match(r"^(\d+(?:\.\d+)?)(만|천|k|m)?", s)
    if not m:
        return None
    mult = {"만": 10000, "천": 1000, "k": 1000, "m": 1000000}.get(m.group(2) or "", 1)
    return int(float(m.group(1)) * mult) or None


def _normalize_header(h: str) -> str:
    h = (h or "").strip().lower().lstrip("﻿")
    for key, aliases in HEADER_ALIASES.items():
        if h in aliases:
            return key
    return h


def read_rows(cfg) -> list[dict]:
    url = cfg.sheet_csv_url
    if url:
        log("K뷰티 목록: 구글 시트에서 읽는 중")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        text = resp.content.decode("utf-8-sig")
    elif cfg.queue_file.exists():
        log(f"K뷰티 목록: {cfg.queue_file.name} 에서 읽는 중")
        text = cfg.queue_file.read_text(encoding="utf-8-sig")
    else:
        return []
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    headers = [_normalize_header(h) for h in rows[0]]
    out = []
    for line_no, values in enumerate(rows[1:], start=2):
        row = {headers[i]: (values[i] if i < len(values) else "") for i in range(len(headers))}
        row["_line"] = line_no
        out.append(row)
    return out


def _links(row: dict, where: str) -> tuple[str, str]:
    """Returns (olive_young_link, aliexpress_link); a plain `link` column goes to the right one."""
    def ok(u: str) -> bool:
        return is_http_url(u) and "example.com" not in u

    oy = (row.get("oliveyoung_link") or "").strip()
    al = (row.get("aliexpress_link") or "").strip()
    plain = (row.get("link") or "").strip()
    if plain:
        if ali.is_ali_url(plain):
            al = al or plain
        else:
            oy = oy or plain
    if al and not ali.is_ali_url(al):
        warn(f"{where}: aliexpress_link 칸에 알리 주소가 아닌 링크가 있어요. 무시할게요.")
        al = ""
    if oy and ali.is_ali_url(oy):
        al, oy = al or oy, ""
    return (oy if ok(oy) else ""), (al if ok(al) else "")


def _split_points(value: str) -> list[str]:
    parts = [clean_space(p) for p in (value or "").replace("\n", ";").split(";")]
    return [p for p in parts if p][:3]


def next_candidate(cfg, state, today: Date, can_translate: bool, ali_client=None) -> Candidate | None:
    try:
        rows = read_rows(cfg)
    except Exception as exc:  # network / sheet not published
        warn(f"K뷰티 목록을 읽지 못했어요: {exc}")
        rows = []
    # then the weekly Olive Young Global bestsellers (your own rows always come first)
    from ..discover import read_auto_queue
    for i, r in enumerate(read_auto_queue(cfg), start=2):
        r["_line"] = f"자동목록 {i}"
        rows.append(r)

    used = state.used_keys()
    for row in rows:
        brand = clean_space(row.get("brand"))
        product = clean_space(row.get("product"))
        where = f"{row['_line']}번째 줄"
        if not brand and not product:
            continue
        if brand.startswith("#"):
            continue  # comment / example row
        if not (brand and product):
            warn(f"{where}: 브랜드와 제품명이 모두 필요해요. 건너뜀")
            continue
        oy, al = _links(row, where)
        if not (oy or al):
            warn(f"{where} ({brand}): 올리브영 링크나 알리 주소 중 하나는 있어야 해요. 건너뜀")
            continue
        key = "kb-" + short_hash(brand, product)
        if key in used:
            continue
        when = (row.get("date") or "").strip()
        if when:
            try:
                if Date.fromisoformat(when) > today:
                    continue  # scheduled for later
            except ValueError:
                warn(f"{where}: 날짜는 2026-10-01 형식으로 적어주세요 (무시하고 진행)")
        if not can_translate and (has_hangul(brand) or has_hangul(product)):
            warn(f"{where}: 브랜드·제품명은 영어로 적어주세요 (카드뉴스가 영어라서요). 건너뜀")
            continue

        cand = Candidate(
            source="kbeauty",
            key=key,
            brand=brand,
            name=product,
            link=oy or al,
            oy_link=oy,
            category=match_category(row.get("category", "")),
            rank=clean_space(row.get("rank")),
            key_points=_split_points(row.get("key_points", "")),
            comment=clean_space(row.get("my_comment")),
            hook=clean_space(row.get("hook")),
            photo=(row.get("photo") or "").strip(),
            my_rating=_rating(row.get("my_rating", "")),
            store_rating=_rating(row.get("store_rating", "")),
            review_count=_count(row.get("review_count", "")),
            review_highlights=_split_points(row.get("review_highlights", "")),
        )
        if cand.my_rating and not cand.comment:
            warn(f"{where}: 내 별점은 한줄평(my_comment)과 함께 적어야 표시돼요.")
        if cand.photo and not is_http_url(cand.photo):
            local = cfg.root / "photos" / cand.photo
            if local.is_file():
                cand.photo = str(local)
            else:
                warn(f"{where}: photos 폴더에 '{cand.photo}' 파일이 없어요. 사진 없이 만들게요.")
                cand.photo = ""
        client = ali_client or (ali.AliClient(*cfg.ali_keys) if cfg.ali_keys else None)
        if al:
            attached = False
            if client is None:
                warn(f"{where} ({brand}): 알리 주소는 알리 API 키가 있어야 제휴 링크로 바꿀 수 있어요.")
            else:
                cand.link = al
                try:
                    attached = ali.enrich_from_ali(cand, client, cfg.ali)
                except ali.AliError as exc:
                    warn(f"{where} ({brand}): 알리 API 오류: {exc}")
            if not attached:
                if not oy:
                    warn(f"{where} ({brand}): 올릴 수 있는 링크가 없어서 건너뜀")
                    continue
                log(f"  {brand}: 알리 링크는 빼고 올리브영 링크만 올려요")
        elif (client is not None and cfg.kbeauty.get("auto_find_aliexpress", True)
              and not (row.get("ali_check") or "").startswith(("not found", "error"))):
            try:
                ali.auto_find(cand, client, cfg.ali)
            except Exception as exc:  # never let the optional lookup cost us the post
                warn(f"{where} ({brand}): 알리 자동 찾기 실패 (올리브영만 올려요): {exc}")
        if cand.store != "aliexpress":
            cand.link = oy
        if not can_translate:
            _drop_korean(cand, where)
        kinds = " + ".join(x for x in ["올리브영" if cand.oy_link else "", "알리" if cand.store == "aliexpress" else ""] if x)
        log(f"K뷰티 선택: {brand} {product} ({where}) · 링크: {kinds}")
        return cand
    return None


def _drop_korean(c: Candidate, where: str) -> None:
    """Without AI translation, Korean text can't go on English cards — drop it with a note."""
    if has_hangul(c.comment):
        warn(f"{where}: 한줄평이 한국어라 뺐어요. 영어로 적거나 ANTHROPIC_API_KEY 를 설정하면 자동 번역돼요.")
        c.comment = ""
    if has_hangul(c.rank):
        warn(f"{where}: 순위 문구가 한국어라 뺐어요 (예: '#1 Toner' 처럼 영어로).")
        c.rank = ""
    if has_hangul(c.hook):
        c.hook = ""
    kept = [p for p in c.key_points if not has_hangul(p)]
    if len(kept) != len(c.key_points):
        warn(f"{where}: 한국어 특징은 뺐어요.")
    c.key_points = kept
    kept = [p for p in c.review_highlights if not has_hangul(p)]
    if len(kept) != len(c.review_highlights):
        warn(f"{where}: 한국어 리뷰 요약은 뺐어요 (영어로 적거나 ANTHROPIC_API_KEY 설정).")
    c.review_highlights = kept
