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
        self.assertEqual(plan, ["skin_korea", "product", "hair", "weekly", "skin_global", "history", "product"])
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



# ---------------------------------------------------------------------------
# Gemini research (monthly drafts, compared by Claude, fallback auto-add)
# ---------------------------------------------------------------------------
def good_entry(name="Bakuchiol", **over):
    e = {"name": name, "full_name": "", "nickname": "Plant retinol alternative", "heat": "global",
         "heat_note": "In several Olive Young Global bestsellers", "hot_since": 2024,
         "hook": "The plant ingredient people call gentle retinol",
         "what_it_is": "A plant compound from babchi seeds, used in serums as a gentler option for smoother-looking skin.",
         "origin": "Seeds of the babchi plant", "benefits": ["Helps skin look smoother", "Supports an even-looking tone",
                                                              "Known for being gentle"],
         "best_for": ["Sensitive skin", "Retinol beginners"], "when": "AM & PM",
         "how_to_use": ["Apply after toner", "Use 2-3 drops", "Follow with moisturizer"],
         "pairs_with": ["Niacinamide", "Ceramides"], "avoid_with": [], "good_to_know": ["Evidence is from small studies."],
         "myth": "It works exactly like retinol.", "fact": "Small studies are promising, but it is not the same molecule.",
         "keywords": ["bakuchiol"], "hashtags": ["#bakuchiol"],
         "sources": ["https://en.wikipedia.org/wiki/Bakuchiol", "https://pubmed.ncbi.nlm.nih.gov/111/"]}
    e.update(over)
    return e


class FakeGemini:
    """generateContent (plain + google_search), Wikipedia, PubMed and redirect resolving."""

    def __init__(self, search_status=200):
        self.calls = []
        self.search_status = search_status

    def post(self, url, headers=None, json=None, timeout=None):
        from tests.test_smoke import FakeResp
        prompt = json["contents"][0]["parts"][0]["text"]
        self.calls.append(("POST", url, "tools" in json))
        if "tools" in json:
            if self.search_status != 200:
                return FakeResp({"error": {"message": "Search grounding is not available on the free tier"}}, status=self.search_status)
            body = {"skin": [dict(good_entry("Bakuchiol"), source_sites=["allure.com", "byrdie.com"]),
                             dict(good_entry("Cure-All Oil", keywords=["cure-all"], hook="The oil that cures acne"),
                                  source_sites=["allure.com"])],
                    "hair": [], "versus": {"id": "ingredients-2026-10", "year": 2026, "topic": "Ingredients",
                                           "title": "Hot in Seoul vs. hot abroad", "subtitle": "October check-in",
                                           "korea": [{"name": f"K{i}", "why": "Olive Young ranking"} for i in range(5)],
                                           "global": [{"name": f"G{i}", "why": "US coverage"} for i in range(5)],
                                           "both": [], "next": [], "basis": "Search results", "source_sites": ["allure.com", "byrdie.com"]}}
            meta = {"webSearchQueries": ["k-beauty trends"], "groundingChunks": [
                {"web": {"uri": "https://vertexaisearch.cloud.google.com/r/1", "title": "allure.com"}},
                {"web": {"uri": "https://vertexaisearch.cloud.google.com/r/2", "title": "byrdie.com"}}]}
            return FakeResp({"candidates": [{"content": {"parts": [{"text": __import__("json").dumps(body)}]}, "groundingMetadata": meta}]})
        if "Pick up to" in prompt:
            body = {"skin": [{"name": "Bakuchiol", "wiki_title": "Bakuchiol", "pubmed_query": "bakuchiol skin", "keywords": ["bakuchiol"]},
                             {"name": "Unicorn Dust", "wiki_title": "Unicorn", "pubmed_query": "x", "keywords": ["unicorn dust"]}],
                    "hair": []}
        else:
            body = good_entry("Bakuchiol", sources=["https://en.wikipedia.org/wiki/Bakuchiol", "https://pubmed.ncbi.nlm.nih.gov/111/",
                                                    "https://made-up.example/fake"])
        return FakeResp({"candidates": [{"content": {"parts": [{"text": __import__("json").dumps(body)}]}}]})

    def get(self, url, params=None, headers=None, timeout=None):
        from tests.test_smoke import FakeResp
        self.calls.append(("GET", url))
        if "wikipedia" in url:
            return FakeResp({"type": "standard", "extract": "Bakuchiol is a meroterpene from Psoralea corylifolia.",
                             "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Bakuchiol"}}})
        if "esearch" in url:
            return FakeResp({"esearchresult": {"idlist": ["111"]}})
        return FakeResp({"result": {"111": {"title": "Bakuchiol vs retinol trial", "pubdate": "2019"}}})

    def head(self, url, allow_redirects=True, timeout=None, headers=None):
        class R:
            pass
        r = R()
        r.url = {"https://vertexaisearch.cloud.google.com/r/1": "https://www.allure.com/story/bakuchiol",
                 "https://vertexaisearch.cloud.google.com/r/2": "https://www.byrdie.com/bakuchiol"}.get(url, url)
        return r


class ResearchTests(unittest.TestCase):
    tearDown = EditorialTests.tearDown

    def setUp(self):
        EditorialTests.setUp(self)
        content = self.tmp / "content"
        shutil.copytree(ed.ROOT / "content", content, ignore=shutil.ignore_patterns("drafts"))
        self.cfg.raw.setdefault("editorial", {})["content_dir"] = str(content)
        self.cfg.raw.setdefault("research", {})["search_mode"] = True  # off in config.toml (terms), tested here
        self.lib = ed.load_library(self.cfg)
        write_catalog(self.cfg, [catalog_item("Beauty of Joseon", "Revive Serum Bakuchiol", no="B1"),
                                 catalog_item("VT", "PDRN Essence 100", no="B2")])

    def run_research(self, env, last_update, search_status=200):
        from bot.research import run_research
        fake = FakeGemini(search_status)
        with mock.patch.dict("os.environ", env):
            res = run_research(self.cfg, date(2026, 10, 28), session=fake, sleep=lambda s: None, last_update=last_update)
        return res, fake

    def test_existing_library_passes_the_same_checks(self):
        for e in self.lib.skin + self.lib.hair:
            others = ed.Library()  # compare against an empty library so "already exists" doesn't fire
            self.assertEqual(ed.check_ingredient(e, others), [], e["id"])

    def test_free_and_search_drafts_are_checked_but_not_added(self):
        res, fake = self.run_research({"GEMINI_API_KEY": "KEY_FREE_123", "GEMINI_SEARCH_API_KEY": "KEY_SEARCH_456"}, date(2026, 10, 20))
        free, search = res["results"]["free"], res["results"]["search"]
        self.assertEqual([e["name"] for e in free["entries"]], ["Bakuchiol"])
        self.assertNotIn("https://made-up.example/fake", free["entries"][0]["sources"])  # only evidence URLs
        self.assertEqual(free["entries"][0]["examples"], [{"brand": "Beauty of Joseon", "product": "Revive Serum Bakuchiol"}])
        self.assertTrue(any("Unicorn" in n for n in free["notes"]))                        # not in bestsellers
        self.assertEqual(free["entries"][0]["_problems"], [])
        s_ok = next(e for e in search["entries"] if e["name"] == "Bakuchiol")
        self.assertEqual(s_ok["sources"], ["https://www.allure.com/story/bakuchiol", "https://www.byrdie.com/bakuchiol"])
        bad = next(e for e in search["entries"] if e["name"] == "Cure-All Oil")
        self.assertTrue(any("과장" in p for p in bad["_problems"]))
        self.assertTrue(any("출처" in p for p in bad["_problems"]))
        self.assertEqual(res["added"], [])
        drafts = self.lib_dir() / "drafts"
        self.assertTrue((drafts / "gemini-free-2026-10.toml").exists())
        self.assertIn("FAIL", (drafts / "gemini-search-2026-10.toml").read_text())
        import tomllib
        tomllib.loads((drafts / "gemini-search-2026-10.toml").read_text())  # valid TOML
        self.assertNotIn("Bakuchiol", (self.lib_dir() / "skin.toml").read_text())
        for f in drafts.iterdir():  # API keys never end up in the files
            self.assertNotIn("KEY_FREE_123", f.read_text())
            self.assertNotIn("KEY_SEARCH_456", f.read_text())

    def test_fallback_adds_passing_drafts_after_claude_stops(self):
        publish(self.cfg, "ing-pdrn", date(2026, 9, 28))
        res, _ = self.run_research({"GEMINI_API_KEY": "KEY_FREE_123", "GEMINI_SEARCH_API_KEY": "KEY_SEARCH_456"}, date(2026, 9, 1))
        self.assertIn("skin: Bakuchiol (search)", res["added"])
        self.assertIn("versus: ingredients-2026-10 (search)", res["added"])
        lib = ed.load_library(self.cfg)
        ids = [e["id"] for e in lib.skin]
        self.assertEqual(ids[:2], ["pdrn", "bakuchiol"])       # right after the last published one
        self.assertEqual(ids.count("bakuchiol"), 1)             # free-mode duplicate skipped
        self.assertNotIn("cure-all-oil", ids)
        st = State(self.cfg.state_file)
        self.assertEqual(ed.next_topic("skin_global", lib, st, date(2026, 10, 30), self.cfg).key, "ing-bakuchiol")

    def test_search_without_billing_is_reported_and_free_still_runs(self):
        res, _ = self.run_research({"GEMINI_API_KEY": "KEY_FREE_123", "GEMINI_SEARCH_API_KEY": "KEY_SEARCH_456"}, date(2026, 10, 20), search_status=400)
        self.assertTrue(any("결제" in n for n in res["results"]["search"]["notes"]))
        self.assertEqual(len(res["results"]["free"]["entries"]), 1)

    def lib_dir(self):
        return ed.content_dir(self.cfg)



class FakeNaver:
    """Naver DataLab: every group gets a flat daily series; PDRN (anchor) = 10/day, others differ."""

    def __init__(self):
        self.bodies = []

    def post(self, url, json=None, headers=None, timeout=None):
        from datetime import date as D, timedelta as TD
        from tests.test_smoke import FakeResp
        assert headers["X-Naver-Client-Id"] == "NID" and len(json["keywordGroups"]) <= 5
        self.bodies.append(json)
        end = D.fromisoformat(json["endDate"])
        per = {"pdrn": (10, 5), "spicule": (6, 3), "mugwort": (2, 4), "exosome": (20, 20)}
        results = []
        for g in json["keywordGroups"]:
            now, prev = per.get(g["groupName"], (1, 1))
            data = [{"period": (end - TD(days=i)).isoformat(), "ratio": now if i < 7 else prev} for i in range(14)]
            results.append({"title": g["groupName"], "keywords": g["keywords"], "data": data})
        return FakeResp({"results": results})


class WeeklyTests(unittest.TestCase):
    tearDown = EditorialTests.tearDown

    def setUp(self):
        EditorialTests.setUp(self)
        ed.save_catalog(self.cfg, [catalog_item("VT", f"Product {i}", rank=i, no=f"P{i}") for i in range(1, 13)], "2026-09-21")
        ed.save_catalog(self.cfg, [catalog_item("VT", "Product 3", rank=1, no="P3"), catalog_item("VT", "Product 1", rank=2, no="P1"),
                                   catalog_item("NEWB", "New Serum", rank=3, no="PN")], "2026-09-28")
        self.fake = FakeNaver()

    def test_naver_ranking_uses_anchor_and_week_change(self):
        from bot import weekly
        with mock.patch.dict("os.environ", {"NAVER_CLIENT_ID": "NID", "NAVER_CLIENT_SECRET": "SEC"}):
            rows = weekly.naver_trends(self.cfg, THURSDAY, session=self.fake)
        by = {r["id"]: r for r in rows}
        self.assertEqual(rows[0]["id"], "exosome")                 # 20/day vs PDRN 10/day
        self.assertEqual(by["exosome"]["index"], 100)
        self.assertEqual(by["pdrn"]["index"], 50)
        self.assertEqual(by["pdrn"]["change"], 100)                 # 10 vs 5 per day
        self.assertEqual(by["mugwort"]["change"], -50)
        self.assertTrue(all(b["keywordGroups"][0]["groupName"] == "pdrn" for b in self.fake.bodies))
        self.assertEqual(self.fake.bodies[0]["endDate"], "2026-09-27")  # last full week (Mon-Sun)

    def test_thursday_post_with_links_then_versus_next_time(self):
        from bot import weekly
        with mock.patch.dict("os.environ", {"NAVER_CLIENT_ID": "NID", "NAVER_CLIENT_SECRET": "SEC"}), \
             mock.patch.object(weekly, "requests", self.fake):
            out = EditorialTests.prepare(self, THURSDAY)
        post = State(self.cfg.state_file).posts[-1]
        self.assertEqual((post["source"], post["key"]), ("weekly", "wk-2026-09-27"))
        self.assertEqual(len(list((out / "posts" / "001").glob("*.jpg"))), 5)  # cover, Korea, products, riser, cta
        self.assertIn("Exosomes · 100", post["caption"])
        self.assertIn("VT Product 3 (▲2)", post["caption"])   # #3 last week -> #1
        self.assertIn("VT Product 1 (▼1)", post["caption"])
        self.assertIn("(new)", post["caption"])
        self.assertIn("#ad", post["caption"])
        self.assertEqual(post["weekly"]["spotlight"]["id"], "pdrn")  # +100%
        self.assertIn("prdtNo=P3", (out / "index.html").read_text())
        self.assertIn("Most-searched ingredients in Korea", (out / "p" / "001.html").read_text())
        # same week again -> the researched comparison instead
        out = EditorialTests.prepare(self, FRIDAY, source="weekly")
        self.assertEqual(State(self.cfg.state_file).posts[-1]["source"], "versus")

    def test_without_naver_key_shows_bestsellers_only(self):
        out = EditorialTests.prepare(self, THURSDAY)
        post = State(self.cfg.state_file).posts[-1]
        self.assertEqual(post["source"], "weekly")
        self.assertEqual(len(list((out / "posts" / "001").glob("*.jpg"))), 3)  # cover, products, cta

    def test_korea_trends_reorder_ingredient_days(self):
        from bot import weekly
        weekly.save(self.cfg, {"week_start": "2026-09-21", "week_end": "2026-09-27",
                               "korea": [{"id": "mugwort", "name": "Mugwort", "index": 90, "change": 40},
                                         {"id": "pdrn", "name": "PDRN", "index": 40, "change": -10}], "products": []})
        st = State(self.cfg.state_file)
        self.assertEqual(ed.next_topic("skin_korea", self.lib, st, MONDAY, self.cfg).key, "ing-mugwort")


if __name__ == "__main__":
    unittest.main()
