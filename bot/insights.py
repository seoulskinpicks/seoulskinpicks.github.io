"""How far the posts are reaching: pulls Instagram insights and keeps a small history.

    python -m bot insights            # recent posts + last 7 days for the account

Needs the token to include the instagram_business_manage_insights permission (Instagram Login API).
Writes a table to the GitHub Actions run summary and saves data/insights.json:
    {"account": {date: {...}}, "media": {media_id: {"number", "type", "permalink", "posted", "history": {date: {...}}}}}
so later checks can see how each post grew.
"""
from __future__ import annotations

import json
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

from .instagram import IGError, Instagram
from .util import add_summary, log, scrub, warn

# Current metric names (v22+: "impressions"/"plays" were replaced by "views").
FEED_METRICS = ["views", "reach", "likes", "comments", "saved", "shares", "total_interactions"]
REEL_METRICS = FEED_METRICS + ["ig_reels_avg_watch_time"]
ACCOUNT_METRICS = ["reach", "views", "accounts_engaged", "total_interactions", "profile_links_taps"]
KEEP_DAYS = 120
PERMISSION_HINT = ("토큰에 인사이트 권한(instagram_business_manage_insights)이 없는 것 같아요. "
                   "Meta 개발자 앱 → Instagram → 권한에서 이 권한을 추가하고 토큰을 다시 만들어 "
                   "IG_ACCESS_TOKEN 을 바꿔주세요 (README '인사이트' 참고).")


def _value(item: dict):
    if "total_value" in item:
        return item["total_value"].get("value")
    vals = item.get("values") or []
    return vals[-1].get("value") if vals else None


def _is_permission(exc: Exception) -> bool:
    s = str(exc).lower()
    return "permission" in s or "code 10/" in s or "code 200/" in s or "(#10)" in s


def _metrics(ig: Instagram, path: str, names: list[str], **params) -> dict:
    """Asks for all metrics at once; if one isn't supported for this item, retries them one by one."""
    try:
        data = ig._req("GET", path, metric=",".join(names), **params)
        return {d["name"]: _value(d) for d in data.get("data", [])}
    except IGError as exc:
        if _is_permission(exc):
            raise
        out = {}
        for name in names:
            try:
                data = ig._req("GET", path, metric=name, **params)
                out.update({d["name"]: _value(d) for d in data.get("data", [])})
            except IGError as one:
                if _is_permission(one):
                    raise
        return out


def recent_media(ig: Instagram, ig_id: str, days: int, limit: int = 50) -> list[dict]:
    data = ig._req("GET", f"{ig_id}/media", fields="id,media_type,media_product_type,permalink,timestamp", limit=limit)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for m in data.get("data", []):
        try:
            ts = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        except (KeyError, ValueError):
            continue
        if ts >= since:
            out.append(m)
    return out


def collect(ig: Instagram, ig_id: str, today: Date, days: int = 30) -> dict:
    """Returns {"account": {...} , "followers": n, "media": [ {id, type, permalink, posted, metrics} ]}."""
    prof = ig._req("GET", ig_id, fields="followers_count,media_count")
    until = datetime.combine(today, datetime.min.time(), timezone.utc)
    account = _metrics(ig, f"{ig_id}/insights", ACCOUNT_METRICS, period="day", metric_type="total_value",
                       since=int((until - timedelta(days=7)).timestamp()), until=int(until.timestamp()))
    media = []
    for m in recent_media(ig, ig_id, days):
        reel = m.get("media_product_type") == "REELS"
        media.append({"id": m["id"], "type": "reel" if reel else ("carousel" if m.get("media_type") == "CAROUSEL_ALBUM" else "post"),
                      "permalink": m.get("permalink", ""), "posted": m.get("timestamp", "")[:10],
                      "metrics": _metrics(ig, f"{m['id']}/insights", REEL_METRICS if reel else FEED_METRICS)})
    return {"followers": prof.get("followers_count"), "media_count": prof.get("media_count"),
            "account": account, "media": media}


def _numbers(state) -> dict[str, int]:
    """media id / permalink -> our post number (for the table)."""
    out = {}
    for p in state.published:
        for key in (p.get("ig_media_id"), p.get("permalink"), (p.get("reel") or {}).get("media_id"),
                    (p.get("reel") or {}).get("permalink")):
            if key:
                out[key] = p["number"]
    return out


def save(path: Path, snap: dict, today: Date, numbers: dict) -> dict:
    hist = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    hist.setdefault("account", {})
    hist.setdefault("media", {})
    iso = today.isoformat()
    hist["account"][iso] = {"followers": snap["followers"], "media_count": snap["media_count"],
                            "last_7_days": snap["account"]}
    for m in snap["media"]:
        rec = hist["media"].setdefault(m["id"], {})
        rec.update(type=m["type"], permalink=m["permalink"], posted=m["posted"],
                   number=numbers.get(m["id"]) or numbers.get(m["permalink"]))
        rec.setdefault("history", {})[iso] = m["metrics"]
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    hist["account"] = {d: v for d, v in hist["account"].items() if d >= cutoff}
    for rec in hist["media"].values():
        rec["history"] = {d: v for d, v in rec.get("history", {}).items() if d >= cutoff}
    hist["media"] = {k: v for k, v in hist["media"].items() if v["history"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hist, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return hist


def _n(v) -> str:
    return "–" if v is None else f"{v:,}"


def report(snap: dict, numbers: dict, prev: dict | None = None) -> str:
    acc = snap["account"]
    lines = ["### 📊 인스타 도달 리포트",
             f"- 팔로워 **{_n(snap['followers'])}** · 게시물 {_n(snap['media_count'])}개",
             f"- 최근 7일 계정 전체: 조회 {_n(acc.get('views'))} · 도달(본 사람) {_n(acc.get('reach'))} · "
             f"반응한 계정 {_n(acc.get('accounts_engaged'))} · 프로필 링크 클릭 {_n(acc.get('profile_links_taps'))}",
             "", "| No. | 종류 | 올린 날 | 조회 | 도달 | 좋아요 | 저장 | 공유 | 댓글 | 전일 대비 도달 |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    kind = {"reel": "릴스", "carousel": "카드", "post": "사진"}
    for m in snap["media"]:
        x = m["metrics"]
        no = numbers.get(m["id"]) or numbers.get(m["permalink"])
        label = f"[{no if no else '·'}]({m['permalink']})" if m["permalink"] else str(no or "·")
        before = ((prev or {}).get(m["id"]) or {}).get("reach")
        delta = f"+{x['reach'] - before:,}" if before is not None and x.get("reach") is not None else ""
        lines.append(f"| {label} | {kind[m['type']]} | {m['posted']} | {_n(x.get('views'))} | {_n(x.get('reach'))} | "
                     f"{_n(x.get('likes'))} | {_n(x.get('saved'))} | {_n(x.get('shares'))} | {_n(x.get('comments'))} | {delta} |")
    if not snap["media"]:
        lines.append("| – | 최근 게시물 없음 | | | | | | | | |")
    lines += ["", "조회 = 화면에 뜬 횟수, 도달 = 본 사람 수(중복 제외). 인스타 집계는 최대 48시간 늦을 수 있어요."]
    return "\n".join(lines)


def run(cfg, state, today: Date, session=None, days: int = 30) -> int:
    if not cfg.ig_token:
        log("IG_ACCESS_TOKEN 이 없어서 인사이트를 건너뛰어요.")
        return 0
    ig = Instagram(cfg.ig_token, cfg.instagram.get("api_host", "graph.instagram.com"),
                   cfg.instagram.get("api_version", "v24.0"), session=session)
    try:
        ig_id = cfg.ig_user_id or ig.account_id()[0]
        snap = collect(ig, ig_id, today, days)
    except IGError as exc:
        msg = scrub(str(exc), cfg.ig_token)
        hint = PERMISSION_HINT if _is_permission(exc) else ""
        warn(f"인사이트를 가져오지 못했어요: {msg} {hint}")
        add_summary(f"### ⚠️ 인스타 인사이트를 가져오지 못했어요\n`{msg}`\n\n{hint}")
        return 1
    path = cfg.root / "data" / "insights.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    prev = {}
    for mid, rec in old.get("media", {}).items():
        past = [d for d in rec.get("history", {}) if d < today.isoformat()]
        if past:
            prev[mid] = rec["history"][max(past)]
    numbers = _numbers(state)
    save(path, snap, today, numbers)
    text = report(snap, numbers, prev)
    log(text)
    add_summary(text)
    return 0
