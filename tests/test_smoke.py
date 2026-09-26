"""End-to-end smoke tests with fake APIs.  Run:  python -m unittest discover tests -v"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from bot.__main__ import cmd_prepare, cmd_publish, source_order
from bot.config import Config, load_config
from bot.copywriter import make_copy
from bot.demo import DEMO_KBEAUTY, demo_product_image
from bot.instagram import IGError, Instagram
from bot.sources import ali as ali_source
from bot.sources import kbeauty as kb_source
from bot.state import State

ROOT = Path(__file__).resolve().parent.parent


class FakeResp:
    def __init__(self, data=None, status=200, headers=None, raw=b"x"):
        self._data = data
        self.status_code = status
        self.headers = headers or {"content-type": "application/json"}
        self.content = json.dumps(data).encode() if data is not None else raw

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeIG:
    """Pretends to be graph.instagram.com + GitHub Pages."""

    def __init__(self):
        self.calls = []
        self.n = 0
        self.polls = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append(("GET", url, dict(params or {})))
        if url.endswith(".jpg"):
            return FakeResp(None, headers={"content-type": "image/jpeg"})
        if url.endswith("/me"):
            return FakeResp({"user_id": "17840000", "username": "seoul.skin.picks", "id": "app1"})
        if params and params.get("fields") == "status_code,status":
            cid = url.rsplit("/", 1)[-1]
            self.polls[cid] = self.polls.get(cid, 0) + 1
            return FakeResp({"status_code": "IN_PROGRESS" if self.polls[cid] == 1 else "FINISHED"})
        if params and params.get("fields") == "permalink":
            return FakeResp({"permalink": "https://www.instagram.com/p/ABC123/"})
        return FakeResp({"error": {"message": "unexpected", "code": 1}}, status=400)

    def post(self, url, data=None, timeout=None):
        self.calls.append(("POST", url, dict(data or {})))
        self.n += 1
        if url.endswith("/media_publish"):
            return FakeResp({"id": "media999"})
        return FakeResp({"id": f"c{self.n}"})


class FakeAli:
    def __init__(self, products, details=None):
        self.products = products
        self.details = details or {}

    def search(self, *a, **k):
        return self.products

    def product_detail(self, pid, *a, **k):
        return self.details.get(pid)

    def find(self, keywords, *a, **k):
        self.last_find = keywords
        return getattr(self, "found", [])

    def affiliate_link(self, url):
        return "https://s.click.aliexpress.com/e/_fake"


def ali_product(pid, title, price="5.80", rating="97.0%", orders=5000, link=True):
    p = {
        "product_id": pid, "product_title": title, "product_main_image_url": "https://ae01.alicdn.com/x.jpg",
        "target_sale_price": price, "target_original_price": "11.00", "target_sale_price_currency": "USD",
        "evaluate_rate": rating, "lastest_volume": orders, "product_detail_url": f"https://www.aliexpress.com/item/{pid}.html",
    }
    if link:
        p["promotion_link"] = f"https://s.click.aliexpress.com/e/_{pid}"
    return p


HEADER = "brand,product,category,link,rank,key_points,my_comment,hook,date\n"


def make_cfg(tmp: Path, rows: list[str], header: str = HEADER, **env) -> Config:
    base = load_config()
    raw = json.loads(json.dumps(base.raw))
    raw["kbeauty"]["sheet_csv_url"] = ""
    (tmp / "data").mkdir(parents=True, exist_ok=True)
    (tmp / "data" / "kbeauty_queue.csv").write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    return Config(raw=raw, root=tmp)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict("os.environ", {"KBEAUTY_SHEET_CSV_URL": "", "ANTHROPIC_API_KEY": "", "IG_ACCESS_TOKEN": "",
                                                   "ALI_APP_KEY": "", "ALI_APP_SECRET": "", "ALI_TRACKING_ID": "",
                                                   "GITHUB_OUTPUT": "", "GITHUB_STEP_SUMMARY": "", "GITHUB_ACTIONS": ""})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    def test_source_order(self):
        self.assertEqual(source_order("alternate", None, None), ["kbeauty", "tools"])
        self.assertEqual(source_order("alternate", "kbeauty", None), ["tools", "kbeauty"])
        self.assertEqual(source_order("alternate", "tools", None), ["kbeauty", "tools"])
        self.assertEqual(source_order("kbeauty_first", "kbeauty", None), ["kbeauty", "tools"])
        self.assertEqual(source_order("alternate", "tools", "tools"), ["tools"])

    def test_queue_rules(self):
        cfg = make_cfg(self.tmp, [
            "# 예시,skip,toner,https://x.com,,,,,",
            "NoLink Brand,Some Toner,toner,,,,,,",
            "라운드랩,독도 토너,토너,https://shop.example.org/a,,,,,",
            "Future Brand,Later Serum,serum,https://shop.example.org/f,,,,,2999-01-01",
            "Round Lab,1025 Dokdo Toner,토너,https://shop.example.org/b,스킨케어 1위,Light texture; 순한 사용감,매일 쓰는 토너예요,,",
        ])
        st = State(cfg.state_file)
        from datetime import date
        c = kb_source.next_candidate(cfg, st, date(2026, 9, 26), can_translate=False)
        self.assertEqual((c.brand, c.name, c.category), ("Round Lab", "1025 Dokdo Toner", "toner"))
        self.assertEqual(c.comment, "")               # Korean comment dropped without AI
        self.assertEqual(c.rank, "")
        self.assertEqual(c.key_points, ["Light texture"])

    def test_full_cycle_alternates_and_publishes(self):
        cfg = make_cfg(self.tmp, [
            "Hanbit Lab,Rice Water Glow Toner,toner,https://shop.example.org/1,#1 Toner,Watery texture; Rice-water base,My go-to after a long day.,,",
            "Maeil Skin,Airy Sun Serum,sunscreen,https://shop.example.org/2,,,,,",
        ])
        fake_ali = FakeAli([
            ali_product("1", "FOREO style silicone face brush gua sha"),           # brand -> blocked
            ali_product("2", "Electric Gua Sha Massager USB"),                      # electric -> blocked
            ali_product("3", "Rose Quartz Gua Sha Stone Facial Tool", rating="85.0%"),  # low rating
            ali_product("4", "Natural Rose Quartz Gua Sha Board Face Massage", orders=3000, link=False),
            ali_product("5", "Jade Gua Sha Scraping Tool", orders=900),
        ])
        out = self.tmp / "site"
        ig = FakeIG()
        env = {"IG_ACCESS_TOKEN": "TOKEN_SECRET_123"}
        with mock.patch("bot.render._fetch_image", return_value=demo_product_image(400)), \
             mock.patch.dict("os.environ", env):
            args = lambda d: Namespace(out=str(out), dry_run=False, source=None, date=d)
            # Day 1 -> K-beauty
            self.assertEqual(cmd_prepare(args("2026-09-26"), cfg=cfg, ali_client=fake_ali), 0)
            self.assertEqual(len(list((out / "posts" / "001").glob("*.jpg"))), 5)
            self.assertIn("No.1", (out / "index.html").read_text())
            self.assertEqual(cmd_publish(Namespace(site_url="https://u.github.io/repo"), cfg=cfg, session=ig, sleep=lambda s: None), 0)
            # Same day again -> skipped
            cmd_prepare(args("2026-09-26"), cfg=cfg, ali_client=fake_ali)
            self.assertFalse((out / "posts").exists())
            # Day 2 -> AliExpress tool, best eligible = product 4 (link generated)
            cmd_prepare(args("2026-09-27"), cfg=cfg, ali_client=fake_ali)
            cmd_publish(Namespace(site_url="https://u.github.io/repo/"), cfg=cfg, session=ig, sleep=lambda s: None)
            # Day 3 -> back to K-beauty, second row
            cmd_prepare(args("2026-09-28"), cfg=cfg, ali_client=fake_ali)

        st = State(cfg.state_file)
        pub = st.published
        self.assertEqual([(p["number"], p["source"]) for p in pub], [(1, "kbeauty"), (2, "tools")])
        self.assertEqual(pub[1]["key"], "ali-4")
        self.assertEqual(pub[1]["link"], "https://s.click.aliexpress.com/e/_fake")
        self.assertEqual(pub[0]["permalink"], "https://www.instagram.com/p/ABC123/")
        self.assertEqual(st.pending()["name"], "Airy Sun Serum")
        self.assertIn("gua_sha", st.data["tool_history"])
        # Instagram calls: 5 children + carousel with caption, publish; images checked first
        posts = [c for c in ig.calls if c[0] == "POST"]
        self.assertEqual(sum(1 for c in posts if c[2].get("is_carousel_item") == "true"), 10)
        carousel = [c for c in posts if c[2].get("media_type") == "CAROUSEL"][0]
        self.assertIn("#ad", carousel[2]["caption"])
        self.assertTrue(carousel[2]["children"].count(",") == 4)
        self.assertTrue(any(c[1] == "https://u.github.io/repo/posts/002/5.jpg" for c in ig.calls))

    def test_publish_failure_is_recorded_without_token(self):
        cfg = make_cfg(self.tmp, ["Hanbit Lab,Rice Water Glow Toner,toner,https://shop.example.org/1,,,,,"])

        class BadIG(FakeIG):
            def post(self, url, data=None, timeout=None):
                return FakeResp({"error": {"message": "Invalid token TOKEN_SECRET_123", "code": 190}}, status=400)

        with mock.patch.dict("os.environ", {"IG_ACCESS_TOKEN": "TOKEN_SECRET_123"}):
            cmd_prepare(Namespace(out=str(self.tmp / "site"), dry_run=False, source=None, date="2026-09-26"), cfg=cfg)
            rc = cmd_publish(Namespace(site_url="https://u.github.io/r/"), cfg=cfg, session=BadIG(), sleep=lambda s: None)
        self.assertEqual(rc, 1)
        saved = cfg.state_file.read_text()
        self.assertIn("failed", saved)
        self.assertNotIn("TOKEN_SECRET_123", saved)
        # next day the same item is retried under the same number
        cmd_prepare(Namespace(out=str(self.tmp / "site"), dry_run=False, source=None, date="2026-09-27"), cfg=cfg)
        st = State(cfg.state_file)
        self.assertEqual(st.pending()["number"], 1)
        self.assertEqual(len(st.posts), 1)

    def test_dry_run_does_not_touch_state(self):
        cfg = make_cfg(self.tmp, ["Hanbit Lab,Rice Water Glow Toner,toner,https://shop.example.org/1,,,,,"])
        cmd_prepare(Namespace(out=str(self.tmp / "site"), dry_run=True, source=None, date="2026-09-26"), cfg=cfg)
        self.assertTrue((self.tmp / "site" / "posts" / "001" / "1.jpg").exists())
        self.assertFalse(cfg.state_file.exists())

    def test_ai_translates_korean_comment(self):
        import copy
        cfg = make_cfg(self.tmp, [])
        cand = copy.deepcopy(DEMO_KBEAUTY[0])
        cand.comment = "자기 전에 바르면 다음날 피부가 편안해요"
        reply = {"hook": "The toner Seoul keeps restocking", "brand_en": "Hanbit Lab", "product_en": "Rice Water Glow Toner",
                 "rank_en": "#1 Toner", "key_points_en": ["Watery, fast-absorbing", "Rice-water base", "Lasts for months"],
                 "comment_en": "I use it before bed and my skin feels calm the next day."}

        class FakeAnthropic:
            def post(self, url, headers=None, json=None, timeout=None):
                assert headers["x-api-key"] == "sk-test"
                return FakeResp({"content": [{"type": "text", "text": "Here you go:\n" + __import__("json").dumps(reply)}]})

        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            cp = make_copy(cand, 7, cfg, session=FakeAnthropic())
        self.assertTrue(cp.ai_used)
        self.assertEqual(cp.hook, "The toner Seoul keeps restocking")
        self.assertEqual(cp.slide4, {"kind": "take", "text": reply["comment_en"]})
        self.assertIn("My take", cp.caption)

    def test_ai_failure_falls_back_to_template(self):
        import copy
        cfg = make_cfg(self.tmp, [])
        cand = copy.deepcopy(DEMO_KBEAUTY[0])
        cand.comment = "한국어 한줄평"

        class Down:
            def post(self, *a, **k):
                raise RuntimeError("503")

        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            cp = make_copy(cand, 7, cfg, session=Down())
        self.assertFalse(cp.ai_used)
        self.assertEqual(cp.slide4["kind"], "routine")   # Korean comment dropped, routine slide instead

    def test_ali_signature_and_request(self):
        sent = {}

        class S:
            def post(self, url, params=None, data=None, timeout=None):
                sent.update(url=url, params=params, data=data)
                return FakeResp({"aliexpress_affiliate_hotproduct_query_response": {"resp_result": {
                    "resp_code": 200, "resp_msg": "ok",
                    "result": {"current_record_count": 1, "products": {"product": [ali_product("9", "Gua Sha")]}}}}})

        client = ali_source.AliClient("KEY", "SECRET", "TRACK", session=S())
        res = client.call("aliexpress.affiliate.hotproduct.query", keywords="gua sha", max_sale_price=2500)
        self.assertEqual(res["products"]["product"][0]["product_id"], "9")
        params = dict(sent["params"])
        sign = params.pop("sign")
        allp = {**params, **sent["data"]}
        expect = hashlib.md5(("SECRET" + "".join(f"{k}{allp[k]}" for k in sorted(allp)) + "SECRET").encode()).hexdigest().upper()
        self.assertEqual(sign, expect)
        self.assertEqual(sent["url"], "https://api-sg.aliexpress.com/sync")

    def test_ig_error_message_is_scrubbed(self):
        class S(FakeIG):
            def get(self, url, params=None, timeout=None):
                return FakeResp({"error": {"message": "bad access_token=TOKEN_SECRET_123", "code": 190}}, status=400)

        ig = Instagram("TOKEN_SECRET_123", session=S(), sleep=lambda s: None)
        with self.assertRaises(IGError) as ctx:
            ig.account_id()
        self.assertNotIn("TOKEN_SECRET_123", str(ctx.exception))


    # ---- photos & reviews ------------------------------------------------
    def test_rating_and_count_parsing(self):
        self.assertEqual(kb_source._rating("★4.8"), 4.8)
        self.assertEqual(kb_source._rating("4,5/5"), 4.5)
        self.assertIsNone(kb_source._rating("48"))
        self.assertEqual(kb_source._count("12,345"), 12345)
        self.assertEqual(kb_source._count("1.2만"), 12000)
        self.assertEqual(kb_source._count("3k"), 3000)
        self.assertIsNone(kb_source._count(""))

    def test_drive_link_conversion(self):
        from bot.images import direct_url
        self.assertEqual(direct_url("https://drive.google.com/file/d/1AbCdEfGhIjK_lm/view?usp=sharing"),
                         "https://drive.google.com/uc?export=download&id=1AbCdEfGhIjK_lm")
        self.assertEqual(direct_url("https://drive.google.com/open?id=1AbCdEfGhIjK_lm"),
                         "https://drive.google.com/uc?export=download&id=1AbCdEfGhIjK_lm")
        self.assertEqual(direct_url("https://www.dropbox.com/s/x/a.jpg?dl=0"), "https://www.dropbox.com/s/x/a.jpg?raw=1")

    def test_heic_and_rotated_photos_load(self):
        from PIL import Image
        from bot.images import load_image
        (self.tmp / "photos").mkdir()
        # iPhone-style HEIC
        Image.new("RGB", (300, 400), (200, 150, 150)).save(self.tmp / "photos" / "a.heic", format="HEIF")
        img = load_image("a.heic", root=self.tmp)
        self.assertEqual(img.size, (300, 400))
        # JPEG stored sideways with EXIF orientation = 6 (rotate 90°)
        exif = Image.Exif(); exif[0x0112] = 6
        Image.new("RGB", (400, 300), (10, 10, 10)).save(self.tmp / "photos" / "b.jpg", exif=exif)
        self.assertEqual(load_image("b.jpg", root=self.tmp).size, (300, 400))

    def test_photo_and_reviews_make_six_slides(self):
        from PIL import Image
        header = "brand,product,category,link,photo,my_comment,my_rating,store_rating,review_count,review_highlights\n"
        cfg = make_cfg(self.tmp, [
            'Hanbit Lab,Rice Water Toner,toner,https://shop.example.org/1,me.jpg,Love it.,4.5,4.8,"12,345",Absorbs fast; Gentle daily',
        ], header=header)
        (self.tmp / "photos").mkdir()
        Image.new("RGB", (900, 1200), (180, 200, 220)).save(self.tmp / "photos" / "me.jpg")
        out = self.tmp / "site"
        cmd_prepare(Namespace(out=str(out), dry_run=False, source=None, date="2026-09-26"), cfg=cfg)
        imgs = sorted((out / "posts" / "001").glob("*.jpg"))
        self.assertEqual(len(imgs), 6)
        post = State(cfg.state_file).pending()
        self.assertEqual(post["slides"], 6)
        cap = post["caption"]
        self.assertIn("4.8 average · 12,345 reviews on Olive Young", cap)
        self.assertIn("What Olive Young reviewers mention", cap)
        self.assertIn("My take (4.5/5)", cap)
        ig = FakeIG()
        with mock.patch.dict("os.environ", {"IG_ACCESS_TOKEN": "T"}):
            self.assertEqual(cmd_publish(Namespace(site_url="https://u.github.io/r/"), cfg=cfg, session=ig, sleep=lambda s: None), 0)
        children = [c for c in ig.calls if c[0] == "POST" and c[2].get("is_carousel_item") == "true"]
        self.assertEqual(len(children), 6)
        self.assertEqual(children[-1][2]["image_url"], "https://u.github.io/r/posts/001/6.jpg")

    def test_missing_photo_falls_back_to_text_cover(self):
        header = "brand,product,category,link,photo\n"
        cfg = make_cfg(self.tmp, ["Hanbit Lab,Rice Water Toner,toner,https://shop.example.org/1,nope.jpg"], header=header)
        out = self.tmp / "site"
        cmd_prepare(Namespace(out=str(out), dry_run=True, source=None, date="2026-09-26"), cfg=cfg)
        self.assertEqual(len(list((out / "posts" / "001").glob("*.jpg"))), 5)


    # ---- K-beauty rows that link to AliExpress ------------------------------
    def test_ali_product_id_parsing(self):
        f = ali_source.product_id_from_url
        self.assertEqual(f("https://www.aliexpress.com/item/1005006123456789.html?spm=a2g0o"), "1005006123456789")
        self.assertEqual(f("https://ko.aliexpress.com/item/1005006123456789.html"), "1005006123456789")
        self.assertEqual(f("https://m.aliexpress.us/item/1005006123456789.html"), "1005006123456789")
        self.assertTrue(ali_source.is_ali_url("https://a.aliexpress.com/_mKxYz12"))
        self.assertFalse(ali_source.is_ali_url("https://global.oliveyoung.com/product/detail?prdtNo=1"))

        class Redirect:
            def get(self, url, **k):
                r = FakeResp({})
                r.url = "https://www.aliexpress.com/item/1005009999999999.html?aff=1"
                r.history = []
                r.text = ""
                return r

        self.assertEqual(f("https://a.aliexpress.com/_mKxYz12", session=Redirect()), "1005009999999999")

    def test_kbeauty_row_linked_to_aliexpress(self):
        cfg = make_cfg(self.tmp, [
            "COSRX,Snail Mucin Essence,essence,https://www.aliexpress.com/item/1005006123456789.html?spm=x,,,,,",
            "Hanbit Lab,Rice Water Toner,toner,https://shop.example.org/1,,,,,",
        ])
        detail = ali_product("1005006123456789", "COSRX Official Advanced Snail 96 Mucin Power Essence", price="12.40", link=False)
        detail["shop_name"] = "COSRX Official Store"
        fake = FakeAli([], details={"1005006123456789": detail})
        out = self.tmp / "site"
        with mock.patch("bot.render._fetch_image", side_effect=lambda ref: demo_product_image(300) if ref else None):
            cmd_prepare(Namespace(out=str(out), dry_run=False, source="kbeauty", date="2026-09-26"), cfg=cfg, ali_client=fake)
        post = State(cfg.state_file).pending()
        self.assertEqual(post["brand"], "COSRX")
        self.assertEqual(post["link"], "https://s.click.aliexpress.com/e/_fake")   # affiliate link, not the raw URL
        self.assertEqual(post["slides"], 6)                                       # + price slide
        self.assertIn("$12.40 on AliExpress", post["caption"])
        self.assertIn("find No.1 (AliExpress)", post["caption"])
        self.assertNotIn("#oliveyoung", post["caption"])

    def test_ali_row_without_keys_is_skipped(self):
        cfg = make_cfg(self.tmp, [
            "COSRX,Snail Mucin Essence,essence,https://www.aliexpress.com/item/1005006123456789.html,,,,,",
            "Hanbit Lab,Rice Water Toner,toner,https://shop.example.org/1,,,,,",
        ])
        from datetime import date
        c = kb_source.next_candidate(cfg, State(cfg.state_file), date(2026, 9, 26), can_translate=False)
        self.assertEqual(c.brand, "Hanbit Lab")


    # ---- Olive Young + AliExpress on the same post ---------------------------
    def test_both_links_and_auto_find_official_store(self):
        header = "brand,product,category,oliveyoung_link,aliexpress_link\n"
        cfg = make_cfg(self.tmp, [
            "COSRX,Advanced Snail 96 Mucin Power Essence,essence,https://global.oliveyoung.com/p/1,",
            "Round Lab,1025 Dokdo Toner,toner,https://global.oliveyoung.com/p/2,",
        ], header=header)
        fake = FakeAli([])
        good = ali_product("1005000000000001", "COSRX Advanced Snail 96 Mucin Power Essence 100ml", price="13.20")
        good["shop_name"] = "COSRX Official Store"
        knockoff = ali_product("1005000000000002", "COSRX Snail 96 Mucin Power Essence 100ml", price="3.10", orders=90000)
        knockoff["shop_name"] = "Beauty Wholesale Store"          # not official -> must be ignored
        fake.found = [knockoff, good]
        from datetime import date
        c = kb_source.next_candidate(cfg, State(cfg.state_file), date(2026, 9, 26), can_translate=False, ali_client=fake)
        self.assertEqual(c.oy_link, "https://global.oliveyoung.com/p/1")
        self.assertEqual(c.ali_link, "https://s.click.aliexpress.com/e/_1005000000000001")
        self.assertEqual(c.price, 13.2)
        # nothing official found -> Olive Young only
        fake.found = [knockoff]
        st = State(cfg.state_file)
        st.posts.append({"number": 1, "key": c.key, "status": "published", "source": "kbeauty", "date": "2026-09-26"})
        c2 = kb_source.next_candidate(cfg, st, date(2026, 9, 27), can_translate=False, ali_client=fake)
        self.assertEqual(c2.brand, "Round Lab")
        self.assertEqual((c2.ali_link, c2.store, c2.link), ("", "", "https://global.oliveyoung.com/p/2"))

    def test_both_links_reach_caption_and_link_page(self):
        header = "brand,product,category,oliveyoung_link,aliexpress_link\n"
        cfg = make_cfg(self.tmp, [
            "COSRX,Snail Mucin Essence,essence,https://global.oliveyoung.com/p/1,https://www.aliexpress.com/item/1005006123456789.html",
        ], header=header)
        detail = ali_product("1005006123456789", "COSRX Official Snail Mucin Essence", price="12.40")
        fake = FakeAli([], details={"1005006123456789": detail})
        out = self.tmp / "site"
        with mock.patch("bot.render._fetch_image", side_effect=lambda ref: demo_product_image(300) if ref else None):
            cmd_prepare(Namespace(out=str(out), dry_run=False, source="kbeauty", date="2026-09-26"), cfg=cfg, ali_client=fake)
        post = State(cfg.state_file).pending()
        self.assertEqual(post["links"], {"oliveyoung": "https://global.oliveyoung.com/p/1",
                                         "aliexpress": "https://s.click.aliexpress.com/e/_1005006123456789"})
        self.assertIn("US: AliExpress", post["caption"])
        self.assertIn("#oliveyoung", post["caption"])
        page = (out / "index.html").read_text()
        self.assertIn("AliExpress →<small>US · worldwide</small>", page)
        self.assertIn("global.oliveyoung.com/p/1", page)

    def test_ali_link_failure_keeps_olive_young(self):
        header = "brand,product,category,oliveyoung_link,aliexpress_link\n"
        cfg = make_cfg(self.tmp, [
            "COSRX,Snail Mucin Essence,essence,https://global.oliveyoung.com/p/1,https://www.aliexpress.com/item/1005006123456789.html",
        ], header=header)
        from datetime import date
        c = kb_source.next_candidate(cfg, State(cfg.state_file), date(2026, 9, 26), can_translate=False, ali_client=FakeAli([]))
        self.assertEqual((c.link, c.ali_link), ("https://global.oliveyoung.com/p/1", ""))


    # ---- weekly discovery: Olive Young Global -> AliExpress check -> auto queue --------------
    class OYSession:
        """Fake global.oliveyoung.com (robots.txt + bestseller JSON per category)."""
        def __init__(self, robots=None):
            fx = Path(__file__).parent / "fixtures"
            self.robots = robots if robots is not None else (fx / "oy_robots.txt").read_text()
            self.lists = {"1000000008": json.loads((fx / "oy_skincare.json").read_text()),
                          "1000000011": json.loads((fx / "oy_suncare.json").read_text())}
            self.calls = []

        def get(self, url, params=None, timeout=None, headers=None):
            self.calls.append((url, params, headers))
            if url.endswith("robots.txt"):
                r = FakeResp(None, headers={"content-type": "text/plain"})
                r.text = self.robots
                return r
            return FakeResp(self.lists.get((params or {}).get("ctgrNo"), []))

    def test_clean_name_and_robots(self):
        from bot.sources import oliveyoung as oy
        self.assertEqual(oy.clean_name("S.NATURE", "[Sanrio EDITION] S.NATURE Aqua Squalane Moisturizing Cream 60ml+60ml (2 Options)"),
                         "Aqua Squalane Moisturizing Cream 60ml")
        self.assertEqual(oy.clean_name("AESTURA", "AESTURA Atobarrier 365 Cream 80ml Triple Limited Set"), "Atobarrier 365 Cream 80ml")
        self.assertTrue(oy.robots_allows_display(self.OYSession()))
        self.assertFalse(oy.robots_allows_display(self.OYSession(robots="User-agent: *\nDisallow: /\n")))
        self.assertFalse(oy.robots_allows_display(self.OYSession(robots="User-agent: *\nDisallow: /display\n")))

    def test_discover_checks_aliexpress_and_fills_queue(self):
        from bot.__main__ import cmd_discover
        from bot.discover import read_auto_queue
        cfg = make_cfg(self.tmp, ["Dr. Althea,345 Relief Cream 50ml,moisturizer,https://global.oliveyoung.com/x,,,,,"])
        cfg.raw["discover"] = {"lists": ["Skincare", "Suncare"], "top_n": 20, "max_new": 10, "min_rating": 4.5, "min_reviews": 30}
        cfg.raw["kbeauty"]["oliveyoung_link_template"] = "{url}&ref=ME"
        fake = FakeAli([])
        boj = ali_product("1005001111111111", "Beauty of Joseon Relief Sun Rice Probiotics SPF50 Sunscreen 50ml", price="12.90")
        boj["shop_name"] = "Beauty of Joseon Official Store"
        fake.found = [boj]
        oy_http = self.OYSession()
        cmd_discover(Namespace(dry_run=False), cfg=cfg, ali_client=fake, session=oy_http, sleep=lambda s: None)
        rows = read_auto_queue(cfg)
        names = [(r["brand"], r["product"]) for r in rows]
        # Dr. Althea already in my sheet, AESTURA has too few reviews, sold-out skipped
        self.assertEqual(names, [("Beauty of Joseon", "Relief Sun Rice + Probiotics SPF50+ PA++++ 50ml"),
                                 ("S.NATURE", "Aqua Squalane Moisturizing Cream 60ml"),
                                 ("celimax", "The Vita A Retinal Shot Tightening Booster 15ml")])
        boj_row = rows[0]
        self.assertEqual(boj_row["category"], "sunscreen")
        self.assertEqual(boj_row["aliexpress_link"], "https://www.aliexpress.com/item/1005001111111111.html")
        self.assertTrue(boj_row["ali_check"].startswith("found"))
        self.assertEqual(boj_row["oliveyoung_link"], "https://global.oliveyoung.com/product/detail?prdtNo=GA220000001&ref=ME")
        self.assertEqual(boj_row["rank"], "Olive Young Global · #1 Suncare")
        self.assertEqual(rows[1]["ali_check"], "not found")
        self.assertTrue(all("KBeautyPicksBot" in c[2]["User-Agent"] for c in oy_http.calls))
        # running again adds nothing new
        cmd_discover(Namespace(dry_run=False), cfg=cfg, ali_client=fake, session=oy_http, sleep=lambda s: None)
        self.assertEqual(len(read_auto_queue(cfg)), 3)

    def test_discover_without_ali_key_then_recheck(self):
        from bot.__main__ import cmd_discover
        from bot.discover import read_auto_queue
        cfg = make_cfg(self.tmp, [])
        cfg.raw["discover"] = {"lists": ["Suncare"], "top_n": 5, "max_new": 5}
        cmd_discover(Namespace(dry_run=False), cfg=cfg, session=self.OYSession(), sleep=lambda s: None)
        self.assertTrue(read_auto_queue(cfg)[0]["ali_check"].startswith("not checked"))
        fake = FakeAli([])
        boj = ali_product("1005001111111111", "Beauty of Joseon Relief Sun Rice Probiotics SPF50 50ml")
        boj["shop_name"] = "Beauty of Joseon Official Store"
        fake.found = [boj]
        cmd_discover(Namespace(dry_run=False), cfg=cfg, ali_client=fake, session=self.OYSession(), sleep=lambda s: None)
        self.assertTrue(read_auto_queue(cfg)[0]["ali_check"].startswith("found"))

    def test_daily_post_uses_my_sheet_first_then_auto_queue(self):
        from bot.discover import write_auto_queue
        cfg = make_cfg(self.tmp, ["My Pick,Hand Picked Toner,toner,https://global.oliveyoung.com/p/9,,,,,"])
        write_auto_queue(cfg, [{"brand": "Beauty of Joseon", "product": "Relief Sun Rice SPF50+", "category": "sunscreen",
                                "oliveyoung_link": "https://global.oliveyoung.com/product/detail?prdtNo=GA220000001",
                                "rank": "Olive Young Global · #1 Suncare", "store_rating": "4.8", "review_count": "25000",
                                "ali_check": "not found"}])
        from datetime import date
        st = State(cfg.state_file)
        c1 = kb_source.next_candidate(cfg, st, date(2026, 9, 26), can_translate=False)
        self.assertEqual(c1.brand, "My Pick")
        st.posts.append({"number": 1, "key": c1.key, "status": "published", "source": "kbeauty", "date": "2026-09-26"})
        fake = FakeAli([])
        fake.found = [{"should": "not be searched"}]
        c2 = kb_source.next_candidate(cfg, st, date(2026, 9, 28), can_translate=False, ali_client=fake)
        self.assertEqual((c2.brand, c2.store_rating, c2.review_count), ("Beauty of Joseon", 4.8, 25000))
        self.assertEqual(c2.rank, "Olive Young Global · #1 Suncare")
        self.assertFalse(hasattr(fake, "last_find"))   # already checked as "not found" -> no repeat search


    # ---- Pinterest: pin image + landing page + RSS feed ------------------------------------
    def test_pinterest_feed_pages_and_pins(self):
        import xml.etree.ElementTree as ET
        header = "brand,product,category,oliveyoung_link,aliexpress_link\n"
        cfg = make_cfg(self.tmp, [
            "COSRX,Snail Mucin Essence,essence,https://global.oliveyoung.com/p/1,https://www.aliexpress.com/item/1005006123456789.html",
            "Round Lab,Dokdo Toner,toner,https://global.oliveyoung.com/p/2,",
        ], header=header)
        cfg.raw["pinterest"] = {"domain_verify": "abc123verify"}
        detail = ali_product("1005006123456789", "COSRX Official Snail Mucin Essence", price="12.40")
        fake = FakeAli([], details={"1005006123456789": detail})
        out = self.tmp / "site"
        env = {"SITE_URL": "https://seoulskin.github.io/", "IG_ACCESS_TOKEN": "T"}
        with mock.patch("bot.render._fetch_image", side_effect=lambda ref: demo_product_image(300) if ref else None), \
             mock.patch.dict("os.environ", env):
            cmd_prepare(Namespace(out=str(out), dry_run=False, source="kbeauty", date="2026-09-26"), cfg=cfg, ali_client=fake)
            self.assertTrue((self.tmp / "pins" / "001.jpg").exists())          # kept in the repo
            cmd_publish(Namespace(site_url="https://seoulskin.github.io/"), cfg=cfg, session=FakeIG(), sleep=lambda s: None)
            cmd_prepare(Namespace(out=str(out), dry_run=False, source="kbeauty", date="2026-09-27"), cfg=cfg, ali_client=fake)
        feed = ET.parse(out / "feed.xml").getroot()
        items = feed.findall(".//item")
        self.assertEqual([i.find("link").text for i in items],
                         ["https://seoulskin.github.io/p/002.html", "https://seoulskin.github.io/p/001.html"])
        self.assertEqual(items[1].find("enclosure").get("url"), "https://seoulskin.github.io/pins/001.jpg")
        self.assertIn("#ad", items[0].find("description").text)
        self.assertTrue((out / "pins" / "001.jpg").exists() and (out / "pins" / "002.jpg").exists())
        page1 = (out / "p" / "001.html").read_text()
        self.assertIn("s.click.aliexpress.com", page1)
        self.assertIn("global.oliveyoung.com/p/1", page1)
        self.assertIn('rel="sponsored noopener"', page1)
        self.assertIn('content="abc123verify"', (out / "index.html").read_text())
        from PIL import Image
        self.assertEqual(Image.open(out / "pins" / "002.jpg").size, (1000, 1500))


if __name__ == "__main__":
    unittest.main()
