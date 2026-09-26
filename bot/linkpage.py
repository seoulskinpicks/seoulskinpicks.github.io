"""Builds the "link in bio" page (GitHub Pages): every post, newest first, with its number.

Product picks get shop buttons. Information posts (ingredients, trends, history) list the products
they mention with shop buttons, or link to the full guide page when there's nothing to buy."""
from __future__ import annotations

import html
from pathlib import Path

from .pinterest import verify_meta

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Picks & guides</title>
<meta name="description" content="{tagline}">
<meta name="robots" content="index,follow">
{verify}
<link rel="alternate" type="application/rss+xml" title="{title}" href="feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,600;9..40,700&family=DM+Serif+Display&display=swap" rel="stylesheet">
<style>
:root{{--bg:#F7EFEA;--card:#FFFFFF;--ink:#2B1D24;--muted:#76626B;--accent:#B8475F;--soft:#F0DCDD;--sage:#3F6E4F;--sage-soft:#D6E3D7;--line:#E7D7D4}}
@media (prefers-color-scheme: dark){{:root{{--bg:#1C1418;--card:#291F24;--ink:#F7EFEA;--muted:#BCA8AF;--accent:#E88AA0;--soft:#3D2A31;--sage:#94C4A4;--sage-soft:#25342B;--line:#3A2D33}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:'DM Sans',system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:560px;margin:0 auto;padding:40px 16px 64px}}
header{{text-align:center}}
.mark{{width:76px;height:76px;border-radius:50%;background:var(--accent);color:#fff;display:grid;place-items:center;font-family:'DM Serif Display',serif;font-size:34px;margin:0 auto 14px}}
h1{{font-family:'DM Serif Display',serif;font-weight:400;font-size:34px;line-height:1.1;margin:0}}
.handle{{color:var(--muted);margin:6px 0 0;font-size:15px}}
.handle a{{color:inherit}}
.tagline{{margin:10px 0 0;font-size:16px}}
.note{{font-size:13px;line-height:1.45;color:var(--muted);background:var(--card);border-radius:14px;padding:12px 14px;margin:22px 0 16px}}
.search{{width:100%;padding:14px 16px;border-radius:14px;border:1.5px solid var(--line);background:var(--card);color:var(--ink);font:inherit;font-size:16px}}
.search:focus{{outline:2px solid var(--accent);outline-offset:1px}}
ul{{list-style:none;padding:0;margin:14px 0 0;display:grid;gap:10px}}
li a{{display:flex;align-items:center;gap:14px;background:var(--card);border-radius:18px;padding:14px 16px;text-decoration:none;color:inherit;border:1px solid var(--line)}}
li a:active{{transform:scale(.99)}}
li .card{{display:flex;align-items:flex-start;gap:14px;background:var(--card);border-radius:18px;padding:14px 16px;border:1px solid var(--line)}}
.btns{{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}}
.btns a{{display:block;flex:1 1 140px;max-width:100%;border:0;padding:10px 12px;border-radius:12px;font-weight:700;font-size:14px;line-height:1.25;text-align:center;background:var(--soft);color:var(--accent);text-decoration:none}}
.btns a small{{display:block;font-weight:500;font-size:12px;opacity:.85}}
.btns a.ali{{background:var(--sage-soft);color:var(--sage)}}
.num{{font-family:'DM Serif Display',serif;font-size:26px;min-width:66px;color:var(--accent)}}
li.tools .num{{color:var(--sage)}}
.meta{{flex:1;min-width:0}}
.tag{{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:3px 8px;border-radius:999px;background:var(--soft);color:var(--accent)}}
li.tools .tag{{background:var(--sage-soft);color:var(--sage)}}
.new{{margin-left:6px;background:var(--ink);color:var(--bg)}}
.name{{font-weight:600;font-size:16px;line-height:1.3;margin-top:5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.brand{{font-size:13px;color:var(--muted);margin-top:2px}}
.go{{font-weight:700;font-size:14px;color:var(--accent);white-space:nowrap}}
li.tools .go{{color:var(--sage)}}
li.guide .num{{color:var(--ink)}}
li.guide .tag{{background:var(--ink);color:var(--bg)}}
.prod{{display:block;margin-top:10px;padding-top:10px;border-top:1px solid var(--line)}}
.prod .pname{{display:block;font-size:14px;font-weight:600;line-height:1.3}}
.brand a{{color:var(--accent);font-weight:600}}
.prod .btns{{margin-top:6px}}
.empty{{text-align:center;color:var(--muted);padding:36px 0}}
footer{{text-align:center;font-size:12px;color:var(--muted);margin-top:28px}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="mark" aria-hidden="true">{initial}</div>
  <h1>{title}</h1>
  <p class="handle"><a href="https://www.instagram.com/{handle}/">@{handle}</a></p>
  <p class="tagline">{tagline}</p>
</header>
<p class="note">Find the number from the post (like <b>No.12</b>) below. Guides (ingredients, trends) list the products they mention. These are affiliate links: I may earn a small commission if you buy, at no extra cost to you. Prices and availability can change.{us_note}</p>
<input class="search" id="q" type="search" inputmode="search" placeholder="Search a number or product…" aria-label="Search picks">
<ul id="list">
{items}
</ul>
<p class="empty" id="empty" hidden>No match. Try just the number, like 12.</p>
<footer>Updated {updated}</footer>
</div>
<script>
const q=document.getElementById('q'),items=[...document.querySelectorAll('#list li')],empty=document.getElementById('empty');
q.addEventListener('input',()=>{{const v=q.value.toLowerCase().replace(/no\\.?\\s*/,'').trim();let n=0;
items.forEach(li=>{{const ok=!v||li.dataset.num===v||li.dataset.s.includes(v);li.hidden=!ok;if(ok)n++;}});empty.hidden=n>0;}});
</script>
</body>
</html>
"""


def build_link_page(posts: list[dict], cfg, out_dir: Path, updated: str) -> Path:
    esc = html.escape
    rows = []
    oy_name = cfg.kbeauty.get("shop_name", "Olive Young Global")
    ordered = sorted(posts, key=lambda p: p["number"], reverse=True)
    any_oy = any((p.get("links") or {}).get("oliveyoung") for p in posts) or any(
        (x.get("links") or {}).get("oliveyoung") for p in posts for x in p.get("products") or [])
    us_note = (f" <b>In the US?</b> Use the AliExpress button: {esc(oy_name)} doesn't ship to the US." if any_oy else "")
    code = cfg.kbeauty.get("oliveyoung_code", "")
    if code and any_oy:
        us_note += f" {esc(oy_name)} code: <b>{esc(code)}</b>"
    from .editorial import INFO_KINDS, KIND_LABEL
    for i, p in enumerate(ordered):
        if p["source"] in INFO_KINDS:
            rows.append(_guide_row(p, i == 0, KIND_LABEL.get(p["source"], "Guide"), oy_name))
            continue
        tools = p["source"] == "tools"
        tag = "Tool pick" if tools else "K-beauty"
        brand = p.get("brand") or ("AliExpress" if tools else "")
        search = f"{p['number']} {brand} {p['name']}".lower()
        new_tag = '<span class="tag new">New</span>' if i == 0 else ""
        kind = "tools" if tools else "kbeauty"
        links = p.get("links") or {}
        if links.get("aliexpress") and links.get("oliveyoung"):
            rows.append(
                f'<li class="{kind}" data-num="{p["number"]}" data-s="{esc(search)}"><div class="card">'
                f'<span class="num">No.{p["number"]}</span>'
                f'<span class="meta"><span class="tag">{tag}</span>{new_tag}'
                f'<span class="name">{esc(p["name"])}</span>'
                f'<span class="brand">{esc(brand)} · {esc(p.get("date", ""))}</span>'
                f'<span class="btns">'
                f'<a class="ali" href="{esc(links["aliexpress"])}" target="_blank" rel="sponsored noopener">AliExpress →<small>US · worldwide</small></a>'
                f'<a href="{esc(links["oliveyoung"])}" target="_blank" rel="sponsored noopener">{esc(oy_name)} →<small>outside the US</small></a>'
                f'</span></span></div></li>'
            )
            continue
        rows.append(
            f'<li class="{kind}" data-num="{p["number"]}" data-s="{esc(search)}">'
            f'<a href="{esc(p["link"])}" target="_blank" rel="sponsored noopener">'
            f'<span class="num">No.{p["number"]}</span>'
            f'<span class="meta"><span class="tag">{tag}</span>{new_tag}'
            f'<span class="name">{esc(p["name"])}</span>'
            f'<span class="brand">{esc(brand)} · {esc(p.get("date", ""))}</span></span>'
            f'<span class="go">Shop →</span></a></li>'
        )
    if not rows:
        rows.append('<li class="empty">First picks are coming soon.</li>')
    page = TEMPLATE.format(
        title=esc(cfg.brand_name),
        tagline=esc(cfg.tagline),
        handle=esc(cfg.handle),
        initial=esc(cfg.brand_name[:1].upper() or "K"),
        items="\n".join(rows),
        updated=esc(updated),
        us_note=us_note,
        verify=verify_meta(cfg),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(page, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return path


def _guide_row(p: dict, newest: bool, tag: str, oy_name: str) -> str:
    esc = html.escape
    folder = p.get("folder") or f"{p['number']:03d}"
    products = p.get("products") or []
    search = " ".join([str(p["number"]), p["name"]] + [f"{x['brand']} {x['name']}" for x in products]).lower()
    new_tag = '<span class="tag new">New</span>' if newest else ""
    def head(read_link: bool) -> str:
        read = f' · <a href="p/{folder}.html">Read the guide</a>' if read_link else ""
        return (f'<span class="num">No.{p["number"]}</span>'
                f'<span class="meta"><span class="tag">{esc(tag)}</span>{new_tag}'
                f'<span class="name">{esc(p["name"])}</span>'
                f'<span class="brand">{esc(p.get("date", ""))}{read}</span>')
    blocks = []
    for x in products:
        links = x.get("links") or {}
        btns = []
        if links.get("aliexpress"):
            btns.append(f'<a class="ali" href="{esc(links["aliexpress"])}" target="_blank" rel="sponsored noopener">AliExpress →<small>US · worldwide</small></a>')
        if links.get("oliveyoung"):
            btns.append(f'<a href="{esc(links["oliveyoung"])}" target="_blank" rel="sponsored noopener">{esc(oy_name)} →<small>outside the US</small></a>')
        if btns:
            blocks.append(f'<span class="prod"><span class="pname">{esc(x["brand"])} {esc(x["name"])}</span>'
                          f'<span class="btns">{"".join(btns)}</span></span>')
    if blocks:
        return (f'<li class="guide" data-num="{p["number"]}" data-s="{esc(search)}"><div class="card">{head(True)}'
                + "".join(blocks) + "</span></div></li>")
    return (f'<li class="guide" data-num="{p["number"]}" data-s="{esc(search)}"><a href="p/{folder}.html">{head(False)}</span>'
            f'<span class="go">Read →</span></a></li>')
