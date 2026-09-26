"""Pinterest without the API: an RSS feed + one landing page per post, on your GitHub Pages site.

Pinterest (business account, claimed website) checks the feed and publishes new items as Pins
within ~24 hours. Every Pin links to /p/NNN.html on your site, which shows the pick and the shop
buttons (AliExpress for the US, Olive Young Global elsewhere) with the affiliate disclosure.
"""
from __future__ import annotations

import html
import shutil
from datetime import datetime, time as dtime
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>No.{number} {title} · {site}</title>
<meta name="description" content="{desc}">
{verify}<meta property="og:title" content="{title}">
<meta property="og:image" content="{image_abs}">
<meta property="og:description" content="{desc}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,600;9..40,700&family=DM+Serif+Display&display=swap" rel="stylesheet">
<style>
:root{{--bg:#F7EFEA;--card:#FFFFFF;--ink:#2B1D24;--muted:#76626B;--accent:#B8475F;--soft:#F0DCDD;--sage:#3F6E4F;--sage-soft:#D6E3D7;--line:#E7D7D4}}
@media (prefers-color-scheme: dark){{:root{{--bg:#1C1418;--card:#291F24;--ink:#F7EFEA;--muted:#BCA8AF;--accent:#E88AA0;--soft:#3D2A31;--sage:#94C4A4;--sage-soft:#25342B;--line:#3A2D33}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:'DM Sans',system-ui,-apple-system,sans-serif}}
.wrap{{max-width:560px;margin:0 auto;padding:28px 16px 56px}}
.back{{color:var(--muted);text-decoration:none;font-size:14px}}
img{{width:100%;height:auto;border-radius:18px;display:block;margin:16px 0}}
.tag{{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:4px 10px;border-radius:999px;background:var(--soft);color:var(--accent)}}
h1{{font-family:'DM Serif Display',serif;font-weight:400;font-size:32px;line-height:1.15;margin:12px 0 6px}}
.sub{{color:var(--muted);margin:0 0 14px}}
ul{{padding-left:20px;line-height:1.55}}
.btns{{display:grid;gap:10px;margin:20px 0}}
.btns a{{display:block;text-align:center;padding:14px;border-radius:14px;font-weight:700;text-decoration:none;background:var(--soft);color:var(--accent)}}
.btns a.ali{{background:var(--sage-soft);color:var(--sage)}}
.btns small{{display:block;font-weight:500;font-size:12px;opacity:.85}}
.note{{font-size:13px;color:var(--muted);line-height:1.45}}
</style>
</head>
<body><div class="wrap">
<a class="back" href="../">← All picks from @{handle}</a>
<img src="../pins/{folder}.jpg" alt="{title}">
<span class="tag">{tag} · No.{number}</span>
<h1>{title}</h1>
<p class="sub">{brand_name}</p>
<ul>{bullets}</ul>
<div class="btns">{buttons}</div>
<p class="note">#ad · These are affiliate links: I may earn a small commission if you buy, at no extra cost to you. Prices and availability can change.{extra_note}</p>
</div></body></html>
"""


def _buttons(p: dict, cfg) -> tuple[str, str]:
    esc = html.escape
    oy_name = cfg.kbeauty.get("shop_name", "Olive Young Global")
    links = p.get("links") or {}
    out, note = [], ""
    if links.get("aliexpress"):
        out.append(f'<a class="ali" href="{esc(links["aliexpress"])}" target="_blank" rel="sponsored noopener">AliExpress →<small>US · worldwide</small></a>')
    if links.get("oliveyoung"):
        out.append(f'<a href="{esc(links["oliveyoung"])}" target="_blank" rel="sponsored noopener">{esc(oy_name)} →<small>outside the US</small></a>')
        code = cfg.kbeauty.get("oliveyoung_code", "")
        if code:
            note = f" {esc(oy_name)} code: <b>{esc(code)}</b>"
    if not out:
        label = "AliExpress" if p.get("source") == "tools" else "Shop"
        out.append(f'<a href="{esc(p["link"])}" target="_blank" rel="sponsored noopener">{label} →</a>')
    return "".join(out), note


def build_pinterest(posts: list[dict], cfg, out_dir: Path, site_url: str, pins_dir: Path | None = None) -> None:
    """Writes out_dir/p/NNN.html, out_dir/feed.xml and copies pin images into out_dir/pins/."""
    esc = html.escape
    base = (site_url or "").rstrip("/") + "/"
    verify = cfg.raw.get("pinterest", {}).get("domain_verify", "")
    verify_tag = f'<meta name="p:domain_verify" content="{esc(verify)}">\n' if verify else ""
    (out_dir / "p").mkdir(parents=True, exist_ok=True)
    (out_dir / "pins").mkdir(parents=True, exist_ok=True)

    if pins_dir and pins_dir.exists():
        for f in pins_dir.glob("*.jpg"):
            shutil.copy2(f, out_dir / "pins" / f.name)

    ordered = sorted(posts, key=lambda p: p["number"], reverse=True)
    items = []
    tz = ZoneInfo(cfg.timezone)
    for p in ordered:
        folder = p.get("folder") or f"{p['number']:03d}"
        if not (out_dir / "pins" / f"{folder}.jpg").exists():
            continue  # posts from before Pinterest was set up
        title = p.get("hook") or p["name"]
        brand_name = " ".join(x for x in [p.get("brand", ""), p["name"]] if x)
        bullets = p.get("bullets") or []
        desc = f"{brand_name}. " + " ".join(f"{b}." for b in bullets[:3]) + " #ad affiliate link"
        buttons, extra = _buttons(p, cfg)
        page = PAGE.format(
            number=p["number"], title=esc(title), site=esc(cfg.brand_name), desc=esc(desc[:300]), verify=verify_tag,
            image_abs=esc(f"{base}pins/{folder}.jpg"), handle=esc(cfg.handle), folder=folder,
            tag="Tool pick" if p["source"] == "tools" else "K-beauty", brand_name=esc(brand_name),
            bullets="".join(f"<li>{esc(b)}</li>" for b in bullets[:3]), buttons=buttons, extra_note=extra,
        )
        (out_dir / "p" / f"{folder}.html").write_text(page, encoding="utf-8")
        day = datetime.combine(datetime.fromisoformat(p["date"]).date(), dtime(12, 0), tz)
        items.append(
            "<item>"
            f"<title>{esc(title[:100])}</title>"
            f"<link>{esc(base)}p/{folder}.html</link>"
            f"<guid isPermaLink=\"true\">{esc(base)}p/{folder}.html</guid>"
            f"<description>{esc(desc[:480])}</description>"
            f"<pubDate>{format_datetime(day)}</pubDate>"
            f"<enclosure url=\"{esc(base)}pins/{folder}.jpg\" type=\"image/jpeg\" length=\"{(out_dir / 'pins' / f'{folder}.jpg').stat().st_size}\"/>"
            f"<media:content url=\"{esc(base)}pins/{folder}.jpg\" medium=\"image\" type=\"image/jpeg\"/>"
            "</item>"
        )
        if len(items) >= 25:
            break
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">'
        f"<channel><title>{esc(cfg.brand_name)}</title><link>{esc(base)}</link>"
        f"<description>{esc(cfg.tagline)}</description><language>en</language>"
        + "".join(items) + "</channel></rss>\n"
    )
    (out_dir / "feed.xml").write_text(feed, encoding="utf-8")


def verify_meta(cfg) -> str:
    verify = cfg.raw.get("pinterest", {}).get("domain_verify", "")
    return f'<meta name="p:domain_verify" content="{html.escape(verify)}">' if verify else ""
