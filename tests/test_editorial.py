"""Tests for the information posts (Ingredient 101, Seoul vs. abroad, K-beauty history)."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from bot import editorial as ed
from bot.__main__ import cmd_prepare
from bot.state import State
from bot.util import has_hangul
from tests.test_smoke import FakeAli, ali_product, make_cfg

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY = (date(2026, 9, 28) + timedelta(days=i) for i in range(6))

LIMITS = {  # field -> max characters on the cards
    "name": 16, "full_name": 42, "nickname": 26, "heat_note": 50, "hook": 54, "what_it_is": 195, "origin": 62,
    "when": 18, "myth": 80, "fact": 110,
}
LIST_LIMITS = {"benefits": 64, "best_for": 32, "how_to_use": 70, "pairs_with": 22, "avoid_with": 30, "good_to_know": 90}


def catalog_item(brand, product, lst="Skincare", rank=1, rating=4.8, reviews=500, no="GA1"):
    return {"brand": brand, "product": product, "prdt_no": no, "url": f"https://global.oliveyoung.com/product/detail?prdtNo={no}",
            "list": lst, "rank": rank, "store_rating": rating, "review_count": reviews}


def write_catalog(cfg, items):
    ed.save_catalog(cfg, items, "2026-09-28")


def publish(cfg, post_key, day, source="skin", number=None):
    st = State(cfg.state_file)
    n = number or st.next_number()
    st.posts.append({"number": n, "date": day.isoformat(), "source": source, "key": post_key, "name": post_key,
                     "link": "", "links": {}, "folder": f"{n:03d}", "slides": 5, "status": "published"})
    st.save()


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict("os.environ", {"KBEAUTY_SHEET_CSV_URL": "", "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "",
                                                   "BACKUP_AI_KEY": "", "IG_ACCESS_TOKEN": "", "ALI_APP_KEY": "",
                                                   "ALI_APP_SECRET": "", "ALI_TRACKING_ID": "", "GITHUB_OUTPUT": "",
                                                   "GITHUB_STEP_SUMMARY": "", "GITHUB_ACTIONS": ""})
        self.env.start()
        self.cfg = make_cfg(self.tmp, [], library=True)
        self.lib = ed.load_library(self.cfg)

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def prepare(self, day, dry=False, source=None, ali=None, published=True):
        out = self.tmp / "site"
        rc = cmd_prepare(Namespace(out=str(out), dry_run=dry, source=source, date=day.isoformat()), cfg=self.cfg, ali_client=ali)
        self.assertEqual(rc, 0)
        if published and not dry and self.cfg.state_file.exists():  # pretend Instagram accepted it
            st = State(self.cfg.state_file)
            if st.posts:
                st.posts[-1]["status"] = "published"
                st.save()
        return out

    # ------------------------------------------------------------------ library
    def test_library_is_complete_and_card_safe(self):
        lib = self.lib
        self.assertGreaterEqual(len(lib.skin), 20)
        self.assertGreaterEqual(len(lib.hair), 10)
        self.assertGreaterEqual(len(lib.versus), 5)
        self.assertEqual([y["year"] for y in lib.years], list(range(2012, 2027)))
        ids = set()
        for e in lib.skin + lib.hair:
            where = f"{e.get('area')}:{e.get('id')}"
            self.assertNotIn((e["area"], e["id"]), ids, where)
            ids.add((e["area"], e["id"]))
            self.assertIn(e["heat"], ("korea", "global", "both"), where)
            for k, limit in LIMITS.items():
                self.assertLessEqual(len(e.get(k, "")), limit, f"{where}.{k}: {e.get(k)}")
            for k, limit in LIST_LIMITS.items():
                for x in e.get(k, []):
                    self.assertLessEqual(len(x), limit, f"{where}.{k}: {x}")
            self.assertEqual(len(e["benefits"]), 3, where)
            self.assertEqual(len(e["how_to_use"]), 3, where)
            self.assertTrue(e["keywords"] and e["sources"], where)
            text = json.dumps(e, ensure_ascii=False)
            self.assertFalse(has_hangul(text), where)
            for bad in ("cures", "clinically proven", "regrows hair", "removes wrinkles"):
                self.assertNotIn(bad, " ".join(e["benefits"]).lower(), where)
        for v in lib.versus:
            self.assertEqual((len(v["korea"]), len(v["global"])), (5, 5), v["id"])
            names = {x["name"] for x in v["korea"]} & {x["name"] for x in v["global"]}
            self.assertTrue(set(v.get("both", [])) <= names, v["id"])
            self.assertFalse(has_hangul(json.dumps(v, ensure_ascii=False)), v["id"])
        for y in lib.years:
            self.assertLessEqual(len(y["headline"]), 34, y["year"])
            self.assertLessEqual(len(y["summary"]), 152, y["year"])

    def test_every_topic_renders_and_caption_fits(self):
        from bot.render_info import render_info_pin, render_info_post
        for kind in ed.INFO_KINDS:
            for t in ed.all_topics(kind, self.lib):
                prods = [{"brand": "Brand", "name": "A fairly long product name for layout checks 50ml",
                          "links": {"oliveyoung": "https://x.example/p"}, "rating": 4.8, "reviews": 12345}] * 3
                info = ed.build_info_copy(t, 123, self.cfg, prods if kind in ("skin", "hair") else [])
                self.assertLessEqual(len(info.caption), 2200, t.key)
                self.assertLessEqual(len(info.hashtags), 20, t.key)
                self.assertFalse(has_hangul(info.caption), t.key)
                paths = render_info_post(t, info, 123, "seoul.skin.picks", self.tmp / "r" / t.key, lib_years=self.lib.years)
                self.assertGreaterEqual(len(paths), 5, t.key)
                self.assertLessEqual(len(paths), 10, t.key)
                render_info_pin(t, info, 123, "seoul.skin.picks", self.tmp / "r" / f"{t.key}.jpg")

    # ------------------------------------------------------------------ plan
    def test_weekly_plan_and_topic_order(self):
        plan = [ed.plan_for(self.cfg, MONDAY + timedelta(days=i)) for i in range(7)]
        self.assertEqual(plan, ["skin_korea", "product", "hair", "versus", "skin_global", "history", "product"])
        st = State(self.cfg.state_file)
        self.assertEqual(ed.next_topic("skin_korea", self.lib, st, MONDAY, self.cfg).key, "ing-pdrn")
        self.assertEqual(ed.next_topic("skin_global", self.lib, st, MONDAY, self.cfg).key, "ing-pdrn")  # 'both'
        self.assertEqual(ed.next_topic("history", self.lib, st, MONDAY, self.cfg).key, "tl-overview")
        self.assertEqual(ed.next_topic("versus", self.lib, st, MONDAY, self.cfg).key, "vs-ingredients-2026")
        publish(self.cfg, "ing-pdrn", MONDAY)
        publish(self.cfg, "tl-overview", MONDAY)
        st = State(self.cfg.state_file)
        self.assertEqual(ed.next_topic("skin_global", self.lib, st, FRIDAY, self.cfg).key, "ing-nad")
        nxt = ed.next_topic("skin_korea", self.lib, st, FRIDAY, self.cfg)
        self.assertIn(nxt.data["heat"], ("korea", "both"))
        self.assertNotEqual(nxt.key, "ing-pdrn")
        self.assertEqual(ed.next_topic("history", self.lib, st, FRIDAY, self.cfg).key, "yr-2012")

    def test_repeats_only_after_the_waiting_period(self):
        for i, t in enumerate(ed.all_topics("versus", self.lib)):
            publish(self.cfg, t.key, date(2026, 1, 1 + i), source="versus")
        st = State(self.cfg.state_file)
        self.assertIsNone(ed.next_topic("versus", self.lib, st, date(2026, 3, 1), self.cfg))
        again = ed.next_topic("versus", self.lib, st, date(2026, 6, 1), self.cfg)
        self.assertEqual(again.key, "vs-ingredients-2026")  # used longest ago
        self.assertTrue(again.repeat)

    # ------------------------------------------------------------------ products
    def test_catalog_matching_is_strict(self):
        pdrn = next(e for e in self.lib.skin if e["id"] == "pdrn")
        retinal = next(e for e in self.lib.skin if e["id"] == "retinal")
        rice = next(e for e in self.lib.skin if e["id"] == "rice")
        rosemary = next(e for e in self.lib.hair if e["id"] == "rosemary")
        cat = [
            catalog_item("medicube", "PDRN Pink Peptide Serum 30ml", reviews=900, no="1"),
            catalog_item("medicube", "PDRN Pink Collagen Capsule Cream", reviews=800, no="2"),
            catalog_item("VT", "PDRN Essence 100", reviews=700, no="3"),
            catalog_item("Anua", "PDRN Hyaluronic Acid Capsule 100 Serum", reviews=10, no="4"),   # too few reviews
            catalog_item("Low", "PDRN Cream", rating=4.1, no="5"),                                 # low rating
            catalog_item("Some", "Retinol Shot Serum", no="6"),
            catalog_item("Brand", "Best Price Toner", no="7"),
            catalog_item("AROMATICA", "Rosemary Scalp Scaling Shampoo", lst="Hair", no="8"),
            catalog_item("Face", "Rosemary Face Mist", lst="Skincare", no="9"),
        ]
        got = ed.match_catalog(pdrn, cat)
        self.assertEqual([g["prdt_no"] for g in got], ["1", "3", "2"])  # other brands first, then fill
        self.assertEqual(ed.match_catalog(retinal, cat), [])            # retinol is not retinal
        self.assertEqual(ed.match_catalog(rice, cat), [])               # "price" is not rice
        self.assertEqual([g["prdt_no"] for g in ed.match_catalog(rosemary, cat)], ["8"])  # hair list only

    def test_ingredient_day_with_catalog_products(self):
        write_catalog(self.cfg, [catalog_item("medicube", "PDRN Pink Peptide Serum", no="GA9"),
                                 catalog_item("VT", "PDRN Essence 100", reviews=4000, no="GA8")])
        out = self.prepare(MONDAY)
        slides = sorted((out / "posts" / "001").glob("*.jpg"))
        self.assertEqual(len(slides), 7)
        st = State(self.cfg.state_file)
        post = st.posts[-1]
        self.assertEqual((post["source"], post["key"], post["name"]), ("skin", "ing-pdrn", "PDRN"))
        self.assertEqual([p["brand"] for p in post["products"]], ["VT", "medicube"])  # most reviews first
        self.assertIn("#ad", post["caption"])
        self.assertIn("No.1", post["caption"])
        self.assertIn("Not medical advice".lower(), post["caption"].lower())
        page = (out / "index.html").read_text()
        self.assertIn("Ingredient 101", page)
        self.assertIn("PDRN Essence 100", page)
        self.assertIn("prdtNo=GA8", page)
        art = (out / "p" / "001.html").read_text()
        self.assertIn("What it does", art)
        self.assertIn("Sources", art)
        self.assertIn("#ad", art)
        self.assertIn("p/001.html", (out / "feed.xml").read_text())
        self.assertTrue((self.cfg.root / "pins" / "001.jpg").exists())

    def test_ingredient_without_catalog_shows_examples_without_ad(self):
        out = self.prepare(MONDAY, dry=True)
        self.assertEqual(len(list((out / "posts" / "001").glob("*.jpg"))), 7)
        self.assertFalse(self.cfg.state_file.exists())
        page = (out / "index.html").read_text()
        self.assertIn("Read →", page)
        art = (out / "p" / "001.html").read_text()
        self.assertIn("Where you&#x27;ll find it", art)
        self.assertNotIn("#ad", art)
        cap = (out / "p" / "001.html")  # caption lives in state only for real runs; rebuild to check
        topic = ed.next_topic("skin_korea", self.lib, State(self.cfg.state_file), MONDAY, self.cfg)
        info = ed.build_info_copy(topic, 1, self.cfg, ed.find_products(topic, self.cfg, []))
        self.assertTrue(info.products and not info.has_links)
        self.assertNotIn("#ad", info.caption)
        self.assertTrue(cap.exists())

    def test_each_kind_of_day(self):
        out = self.prepare(WEDNESDAY)  # hair
        self.assertEqual(State(self.cfg.state_file).posts[-1]["key"], "hair-rosemary")
        out = self.prepare(THURSDAY)   # versus
        post = State(self.cfg.state_file).posts[-1]
        self.assertEqual((post["source"], len(list((out / "posts" / "002").glob("*.jpg")))), ("versus", 5))
        self.assertIn("Team Seoul", post["caption"])
        out = self.prepare(SATURDAY)   # history: the full timeline comes first
        post = State(self.cfg.state_file).posts[-1]
        self.assertEqual(post["key"], "tl-overview")
        self.assertIn("2012", post["caption"])
        self.assertIn("K-beauty history", (out / "index.html").read_text())

    def test_empty_product_day_falls_back_to_info(self):
        self.prepare(TUESDAY)  # product day, but no sheet rows and no Ali keys
        post = State(self.cfg.state_file).posts[-1]
        self.assertEqual(post["source"], "skin")

    def test_manual_source_overrides_plan(self):
        self.prepare(TUESDAY, source="history")
        self.assertEqual(State(self.cfg.state_file).posts[-1]["key"], "tl-overview")

    def test_product_day_gets_star_ingredient_and_alternation_ignores_info(self):
        cfg = make_cfg(self.tmp, ["SKIN1004,Madagascar Centella Ampoule,serum,https://shop.example.org/c,,,,,"], library=True)
        self.cfg = cfg
        publish(cfg, "ali-1", date(2026, 9, 20), source="tools")
        publish(cfg, "ing-pdrn", date(2026, 9, 21), source="skin")
        self.assertEqual(State(cfg.state_file).last_source(), "tools")
        out = self.prepare(TUESDAY)
        post = State(cfg.state_file).posts[-1]
        self.assertEqual(post["source"], "kbeauty")
        self.assertIn("Star ingredient: Centella", post["caption"])
        self.assertEqual(len(list((out / "posts" / f"{post['number']:03d}").glob("*.jpg"))), 6)  # 5 + star

    def test_ali_links_for_ingredient_products(self):
        write_catalog(self.cfg, [catalog_item("VT", "PDRN Essence 100", no="GA8")])
        fake = FakeAli([])
        official = ali_product("77", "VT PDRN Essence 100 30ml")
        official["shop_name"] = "VT Official Store"
        fake.found = [official]
        self.prepare(MONDAY, ali=fake)
        prod = State(self.cfg.state_file).posts[-1]["products"][0]
        self.assertEqual(prod["links"]["aliexpress"], "https://s.click.aliexpress.com/e/_77")
        self.assertIn("oliveyoung", prod["links"])

    # ------------------------------------------------------------------ weekly job
    def test_discover_saves_catalog_with_hair(self):
        from bot.discover import run_discover
        from tests.test_smoke import FakeResp

        robots = (Path(__file__).parent / "fixtures" / "oy_robots.txt").read_text()
        skincare = json.loads((Path(__file__).parent / "fixtures" / "oy_skincare.json").read_text())
        hair = [{"brandName": "AROMATICA", "prdtName": "AROMATICA Rosemary Scalp Scaling Shampoo 400ml",
                 "prdtNo": "GA777", "avgScore": "4.8", "reviewCnt": "321", "saleAmt": "18", "soldOutYn": "N"}]

        class Session:
            def get(self, url, params=None, timeout=None, headers=None):
                if url.endswith("robots.txt"):
                    r = FakeResp(None)
                    r.text = robots
                    return r
                return FakeResp(hair if params["ctgrNo"] == "1000000070" else skincare)

        run_discover(self.cfg, State(self.cfg.state_file), "2026-09-28", session=Session(), sleep=lambda s: None)
        cat = ed.load_catalog(self.cfg)
        self.assertIn("Hair", {c["list"] for c in cat})
        self.assertTrue(any(c["prdt_no"] == "GA777" for c in cat))
        queue = (self.cfg.root / "data" / "auto_queue.csv").read_text()
        self.assertNotIn("Rosemary", queue)  # hair isn't in the product queue lists


if __name__ == "__main__":
    unittest.main()
