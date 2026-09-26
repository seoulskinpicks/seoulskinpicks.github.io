"""Command line entry point.

  python -m bot demo                 # preview cards with sample data (no keys needed)
  python -m bot check                # test sheet / AliExpress / Instagram connections
  python -m bot prepare [--dry-run]  # pick today's product, write site/ (cards + link page)
  python -m bot publish --site-url https://you.github.io/repo/
  python -m bot refresh-token --out token.txt
"""
from __future__ import annotations

import argparse
import copy
import os
import shutil
import sys
from datetime import date as Date
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_config
from .copywriter import make_copy
from .instagram import Instagram, wait_for_urls
from .linkpage import build_link_page
from .pinterest import build_pinterest
from .render import contact_sheet, render_pin, render_post
from .sources import ali as ali_source
from .sources import kbeauty as kb_source
from .state import State
from .util import add_summary, log, scrub, set_output, warn

SLIDES = 5


def _today(cfg, override: str | None) -> Date:
    if override:
        return Date.fromisoformat(override)
    return datetime.now(ZoneInfo(cfg.timezone)).date()


def source_order(mode: str, last: str | None, forced: str | None) -> list[str]:
    if forced in ("kbeauty", "tools"):
        return [forced]
    if mode == "kbeauty_first":
        return ["kbeauty", "tools"]
    if mode == "tools_first":
        return ["tools", "kbeauty"]
    first = "tools" if last == "kbeauty" else "kbeauty"
    return [first, "kbeauty" if first == "tools" else "tools"]


def _fetch(src: str, cfg, state, today: Date, ali_client=None):
    if src == "kbeauty":
        return kb_source.next_candidate(cfg, state, today, can_translate=bool(cfg.anthropic_key), ali_client=ali_client)
    return ali_source.next_candidate(cfg, state, client=ali_client)


def _post_record(cand, cp, number: int, today: Date, slides: int) -> dict:
    return {
        "number": number,
        "date": today.isoformat(),
        "source": cand.source,
        "key": cand.key,
        "brand": cand.brand,
        "name": cp.display_name if cand.source == "tools" else cand.name,
        "link": cand.link,
        "links": {k: v for k, v in (("oliveyoung", cand.oy_link), ("aliexpress", cand.ali_link)) if v},
        "category": cand.category,
        "folder": f"{number:03d}",
        "slides": slides,
        "caption": cp.caption,
        "hook": cp.hook,
        "bullets": list(cp.why_bullets[:3]),
        "status": "prepared",
    }


def _site_url(cfg) -> str:
    return os.environ.get("SITE_URL", "").strip() or cfg.raw.get("pinterest", {}).get("site_url", "")


def _render_pin(cand, cp, number: int, cfg, out: Path, dry_run: bool, product_img=None) -> None:
    """Pinterest image, kept in the repo (pins/) so older Pins stay online."""
    target = (out / "pins" if dry_run else cfg.root / "pins") / f"{number:03d}.jpg"
    try:
        render_pin(cand, cp, number, cfg.handle, target, product_img=product_img)
    except Exception as exc:
        warn(f"핀터레스트 이미지를 만들지 못했어요 (인스타 게시는 계속): {exc}")


# ---------------------------------------------------------------------------
def cmd_prepare(args, cfg=None, ali_client=None) -> int:
    cfg = cfg or load_config()
    state = State(cfg.state_file)
    today = _today(cfg, args.date)
    set_output("has_post", "false")
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    if not args.dry_run and state.published_on(today.isoformat()):
        log(f"{today} 에는 이미 게시했어요 (하루 1개). 건너뜀.")
        return 0
    state.drop_unpublished()
    number = state.next_number()

    chosen = None
    for src in source_order(cfg.mode, state.last_source(), args.source):
        try:
            cand = _fetch(src, cfg, state, today, ali_client)
            if not cand:
                continue
            cp = make_copy(cand, number, cfg)
            paths = render_post(cand, cp, number, cfg.handle, out / "posts" / f"{number:03d}")
            chosen = (cand, cp, paths)
            break
        except Exception as exc:
            warn(f"{'K뷰티' if src == 'kbeauty' else '알리 도구'} 준비 중 오류, 다른 쪽으로 넘어가요: {exc}")
    if not chosen:
        warn("오늘 올릴 상품이 없어요. 구글 시트에 K뷰티 제품을 추가하거나 알리 API 키를 확인해주세요.")
        add_summary("### 오늘은 게시할 상품이 없어요\n구글 시트(K뷰티 목록)에 새 제품을 추가하거나, 알리 API 키 설정을 확인해주세요.")
        return 0

    cand, cp, paths = chosen
    post = _post_record(cand, cp, number, today, len(paths))
    _render_pin(cand, cp, number, cfg, out, args.dry_run)
    build_link_page(state.published + [post], cfg, out, updated=today.isoformat())
    build_pinterest(state.published + [post], cfg, out, _site_url(cfg), pins_dir=None if args.dry_run else cfg.root / "pins")
    if not args.dry_run:
        state.posts.append(post)
        if cand.source == "tools":
            state.remember_tool(cand.category, cand.product_id)
        state.save()
    set_output("has_post", "true")
    set_output("number", str(number))
    kind = "K뷰티" if cand.source == "kbeauty" else "알리 도구"
    log(f"No.{number} 준비 완료 ({kind}): {post['brand']} {post['name']}")
    add_summary(
        f"### {'[미리보기] ' if args.dry_run else ''}No.{number} · {kind}\n"
        f"- 제품: **{post['brand']} {post['name']}**\n- 링크: {post['link']}\n"
        f"- 카피: {'Claude AI' if cp.ai_used else '템플릿'}\n\n"
        f"카드 이미지는 이 페이지 아래 **Artifacts → preview-images** 에서 받을 수 있어요.\n\n"
        f"<details><summary>캡션 보기</summary>\n\n```\n{cp.caption}\n```\n</details>\n"
    )
    return 0


def cmd_publish(args, cfg=None, session=None, sleep=None) -> int:
    cfg = cfg or load_config()
    state = State(cfg.state_file)
    post = state.pending()
    if not post:
        log("게시할 준비된 글이 없어요.")
        return 0
    if not cfg.ig_token:
        warn("IG_ACCESS_TOKEN 이 없어서 인스타 게시는 건너뛰었어요 (카드·링크 페이지만 준비됨).")
        return 0
    site = args.site_url.rstrip("/") + "/"
    urls = [f"{site}posts/{post['folder']}/{i}.jpg" for i in range(1, post["slides"] + 1)]
    kw = {"sleep": sleep} if sleep else {}
    try:
        wait_for_urls(urls, session=session, **kw)
        ig = Instagram(cfg.ig_token, cfg.instagram.get("api_host", "graph.instagram.com"),
                       cfg.instagram.get("api_version", "v24.0"), session=session, **kw)
        ig_id = cfg.ig_user_id or ig.account_id()[0]
        res = ig.publish_carousel(ig_id, urls, post["caption"])
    except Exception as exc:
        msg = scrub(str(exc), cfg.ig_token)
        post.update(status="failed", error=msg[:300])
        state.save()
        print(f"::error::인스타 게시 실패: {msg}" if os.environ.get("GITHUB_ACTIONS") else f"인스타 게시 실패: {msg}")
        add_summary(f"### ❌ 인스타 게시 실패\n`{msg}`\n\n내일 같은 상품으로 다시 시도해요. README의 '문제 해결'을 참고하세요.")
        return 1
    post.update(status="published", ig_media_id=res["media_id"], permalink=res["permalink"],
                published_at=datetime.now(ZoneInfo(cfg.timezone)).isoformat(timespec="minutes"))
    post.pop("error", None)
    state.save()
    add_summary(f"### ✅ 인스타 게시 완료: No.{post['number']}\n{res['permalink'] or res['media_id']}")
    return 0


def cmd_check(args, cfg=None) -> int:
    cfg = cfg or load_config()
    state = State(cfg.state_file)
    today = _today(cfg, None)
    ok = True
    lines = ["### 연결 점검"]

    rows = []
    try:
        rows = kb_source.read_rows(cfg)
        src = "구글 시트" if cfg.sheet_csv_url else "data/kbeauty_queue.csv"
        lines.append(f"- K뷰티 목록 ({src}): {len(rows)}줄 읽음")
        cand = kb_source.next_candidate(cfg, state, today, can_translate=bool(cfg.anthropic_key))
        lines.append(f"  - 다음 K뷰티: {cand.brand + ' ' + cand.name if cand else '없음 (목록이 비었거나 모두 게시됨)'}")
    except Exception as exc:
        ok = False
        lines.append(f"- ❌ K뷰티 목록 오류: {exc}")

    if cfg.ali_keys:
        try:
            client = ali_source.AliClient(*cfg.ali_keys)
            found = client.search("gua sha", cfg.ali.get("ship_to_country", "US"), "USD", "EN", 25)
            lines.append(f"- 알리 API: 연결됨 (테스트 검색 {len(found)}개)")
        except Exception as exc:
            ok = False
            lines.append(f"- ❌ 알리 API 오류: {exc}")
    else:
        lines.append("- 알리 API: 키 없음 → 알리 도구는 건너뜀 (승인 후 추가)")

    lines.append(f"- Claude AI 카피: {'켜짐' if cfg.anthropic_key else '꺼짐 (템플릿 사용)'}")

    if cfg.ig_token:
        try:
            ig = Instagram(cfg.ig_token, cfg.instagram.get("api_host", "graph.instagram.com"), cfg.instagram.get("api_version", "v24.0"))
            ig_id, username = ig.account_id()
            lines.append(f"- 인스타: @{username} 연결됨")
        except Exception as exc:
            ok = False
            lines.append(f"- ❌ 인스타 토큰 오류: {scrub(str(exc), cfg.ig_token)}")
    else:
        lines.append("- 인스타: 토큰 없음 → 게시 없이 미리보기만")

    lines.append(f"- 지금까지 게시: {len(state.published)}개")
    text = "\n".join(lines)
    log(text)
    add_summary(text)
    return 0 if ok else 1


def cmd_refresh_token(args) -> int:
    cfg = load_config()
    if not cfg.ig_token:
        print("IG_ACCESS_TOKEN 이 없어요.", file=sys.stderr)
        return 1
    ig = Instagram(cfg.ig_token, cfg.instagram.get("api_host", "graph.instagram.com"))
    data = ig.refresh_token()
    new = data["access_token"]
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::add-mask::{new}")
    Path(args.out).write_text(new, encoding="utf-8")
    days = int(data.get("expires_in", 0)) // 86400
    log(f"토큰 갱신 완료: 앞으로 약 {days}일 유효 ({'새 토큰' if new != cfg.ig_token else '같은 토큰 연장'})")
    return 0


def cmd_discover(args, cfg=None, ali_client=None, session=None, sleep=None) -> int:
    from .discover import run_discover

    cfg = cfg or load_config()
    state = State(cfg.state_file)
    kw = {"sleep": sleep} if sleep else {}
    added = run_discover(cfg, state, _today(cfg, None).isoformat(), ali_client=ali_client, session=session,
                         dry_run=args.dry_run, **kw)
    set_output("added", str(len(added)))
    return 0


def cmd_demo(args) -> int:
    from . import demo

    cfg = load_config()
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    records, all_paths = [], []
    samples = [(1, demo.DEMO_KBEAUTY[0]), (2, demo.DEMO_TOOL), (3, demo.DEMO_KBEAUTY[1]), (4, demo.DEMO_KBEAUTY_ALI)]
    for number, sample in samples:
        cand = copy.deepcopy(sample)
        cp = make_copy(cand, number, cfg)
        if cand.source == "tools":
            img = demo.demo_product_image()
        elif cand.store == "aliexpress":
            img = demo.demo_bottle_photo().crop((0, 150, 1200, 1350))
        else:
            img = demo.demo_bottle_photo() if number == 1 else None
        paths = render_post(cand, cp, number, cfg.handle, out / "posts" / f"{number:03d}", product_img=img)
        contact_sheet(paths, out / f"preview_No{number}.jpg")
        (out / f"caption_No{number}.txt").write_text(cp.caption, encoding="utf-8")
        render_pin(cand, cp, number, cfg.handle, out / "pins" / f"{number:03d}.jpg", product_img=img)
        records.append(_post_record(cand, cp, number, _today(cfg, None), len(paths)))
        all_paths += paths
    build_link_page(records, cfg, out, updated=_today(cfg, None).isoformat())
    build_pinterest(records, cfg, out, _site_url(cfg) or "https://your-name.github.io/")
    log(f"데모 완료 → {out}/ (카드 {len(all_paths)}장, 링크 페이지 index.html)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m bot")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("--out", default="site")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--source", default="auto", choices=["auto", "kbeauty", "tools"])
    a.add_argument("--date", default=None, help="YYYY-MM-DD (테스트용)")
    b = sub.add_parser("publish")
    b.add_argument("--site-url", required=True)
    sub.add_parser("check")
    r = sub.add_parser("refresh-token")
    r.add_argument("--out", required=True)
    ds = sub.add_parser("discover")
    ds.add_argument("--dry-run", action="store_true")
    dm = sub.add_parser("demo")
    dm.add_argument("--out", default="demo_output")
    args = p.parse_args(argv)
    if getattr(args, "source", None) == "auto":
        args.source = None
    return {
        "prepare": cmd_prepare,
        "publish": cmd_publish,
        "check": cmd_check,
        "refresh-token": cmd_refresh_token,
        "demo": cmd_demo,
        "discover": cmd_discover,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
