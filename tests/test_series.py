"""Tests for the monthly topic schedule, the newer series and the Reels."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from argparse import Namespace
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from bot import editorial as ed
from bot import reels, series
from bot.__main__ import cmd_prepare, cmd_publish
from bot.state import State
from tests.test_editorial import catalog_item, publish, write_catalog
from tests.test_smoke import FakeIG, FakeResp, make_cfg

ENV = {"KBEAUTY_SHEET_CSV_URL": "", "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "", "BACKUP_AI_KEY": "",
       "IG_ACCESS_TOKEN": "", "ALI_APP_KEY": "", "ALI_APP_SECRET": "", "ALI_TRACKING_ID": "", "GITHUB_OUTPUT": "",
       "GITHUB_STEP_SUMMARY": "", "GITHUB_ACTIONS": "", "NAVER_CLIENT_ID": "", "NAVER_CLIENT_SECRET": ""}
TUESDAY = date(2026, 10, 6)


class SeriesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict("os.environ", ENV)
        self.env.start()
        self.cfg = make_cfg(self.tmp, [], library=True, series=True)
        self.lib = ed.load_library(self.cfg)

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------ schedule
    def test_month_follows_targets(self):
        st = State(self.tmp / "sim.json")
        d, picks = date(2026, 10, 1), []
        for i in range(31):
            plan, steps = series.plan_order(self.cfg, st, d)
            if d.weekday() == 3:
                self.assertEqual(plan, "weekly")
            else:
                self.assertNotIn("weekly", steps)
            season_done = any(p["source"] == "season" for p in st.posts)
            pick = next(s for s in steps if s not in ("industry", "recap") and not (s == "season" and season_done))
            src = {"skin_korea": "skin", "skin_global": "skin", "product": "kbeauty"}.get(pick, pick)
            st.posts.append({"date": d.isoformat(), "source": src, "status": "published", "key": f"k{i}", "number": i})
            picks.append(pick)
            d += timedelta(days=1)
        count = Counter(series.series_of(p) for p in st.posts)
        self.assertEqual(count["skin"], 8)
        self.assertEqual(count["product"], 7)
        self.assertEqual(count["weekly"], 5)  # five Thursdays in Oct 2026
        self.assertEqual(count["hair"], 3)
        self.assertEqual(count["routine"], 2)
        for s in ("myth", "combo", "history", "versus", "words", "season"):
            self.assertEqual(count[s], 1, s)
        skin = [p for p in picks if p.startswith("skin")]
        self.assertEqual(skin[:4], ["skin_korea", "skin_global", "skin_korea", "skin_global"])
        # never the same series two days in a row (except fixed-day ones)
        for a, b in zip(picks, picks[1:]):
            self.assertFalse(a == b and a != "weekly", (a, b))

    def test_gap_is_respected(self):
        publish(self.cfg, "rt-dull", TUESDAY - timedelta(days=3), source="routine")
        _, steps = series.plan_order(self.cfg, State(self.cfg.state_file), TUESDAY)
        self.assertGreater(steps.index("routine"), steps.index("product"))

    def test_without_series_uses_weekday_plan(self):
        cfg = make_cfg(self.tmp / "b", [], library=True)
        self.assertIsNone(series.plan_order(cfg, State(cfg.state_file), TUESDAY))

    # ------------------------------------------------------------------ content files
    def test_new_content_files_are_card_safe(self):
        from bot.util import has_hangul
        ids = {e["id"] for e in self.lib.skin + self.lib.hair}
        self.assertGreaterEqual(len(self.lib.routines), 6)
        for r in self.lib.routines:
            self.assertTrue(set(r["key"]) <= ids, r["id"])
            self.assertLessEqual(len(r["hook"]), 54, r["id"])
            self.assertLessEqual(len(r["title"]), 28, r["id"])
            for step in r["am"] + r["pm"]:
                self.assertLessEqual(len(step), 58, step)
            self.assertTrue(3 <= len(r["am"]) <= 6 and 3 <= len(r["pm"]) <= 6, r["id"])
            self.assertFalse(has_hangul(json.dumps(r, ensure_ascii=False)), r["id"])
        self.assertEqual(sorted(m for s_ in self.lib.seasons for m in s_["months"]), list(range(1, 13)))
        for s_ in self.lib.seasons:
            self.assertTrue(set(s_["key"]) <= ids, s_["id"])
            self.assertFalse(has_hangul(json.dumps(s_, ensure_ascii=False)), s_["id"])
        for w in self.lib.words:
            self.assertTrue(2 <= len(w["words"]) <= 6, w["id"])
            for x in w["words"]:
                self.assertTrue(has_hangul(x["ko"]) and not has_hangul(x["rom"] + x["en"] + x["note"]), x)
                self.assertLessEqual(len(x["en"]), 34, x)
                self.assertLessEqual(len(x["note"]), 120, x)
        for i in self.lib.industry:
            self.assertTrue(3 <= len(i["items"]) <= 5, i["id"])
            self.assertGreaterEqual(len(i.get("sources", [])), 2, i["id"])
            self.assertLessEqual(len(i.get("hook", "")), 54, i["id"])
            for it in i["items"]:
                self.assertLessEqual(len(it["name"]), 28, it)
                self.assertLessEqual(len(it["signal"]), 70, it)
                self.assertLessEqual(len(it["why"]), 140, it)
            self.assertFalse(has_hangul(json.dumps(i, ensure_ascii=False)), i["id"])

    # ------------------------------------------------------------------ topics
    def test_myth_and_combo_groups(self):
        st = State(self.cfg.state_file)
        seen = set()
        for i in range(9):
            t = series.next_topic("myth", self.lib, st, TUESDAY, self.cfg, ed.last_used(st))
            self.assertIsNotNone(t, i)
            ids = [x["id"] for x in t.data["items"]]
            self.assertTrue(3 <= len(ids) <= 4)
            self.assertEqual(len({x["area"] for x in t.data["items"]}), 1, ids)
            self.assertFalse(seen & set(ids))
            seen |= set(ids)
            publish(self.cfg, t.key, TUESDAY - timedelta(days=200 - i), source="myth")
            st = State(self.cfg.state_file)
        self.assertEqual(seen, {e["id"] for e in self.lib.skin + self.lib.hair})
        # all used long ago -> starts over with the oldest
        again = series.next_topic("myth", self.lib, st, TUESDAY, self.cfg, ed.last_used(st))
        self.assertTrue(again.repeat)
        combo = series.next_topic("combo", self.lib, st, TUESDAY, self.cfg, {})
        self.assertTrue(combo.data["items"][0]["avoid"])  # the ones with warnings first
        found = ed.find_topic(combo.key, self.lib, {"data": combo.data})
        self.assertEqual(found.kind, "combo")

    def test_season_once_per_season(self):
        t = series.next_topic("season", self.lib, State(self.cfg.state_file), date(2026, 12, 5), self.cfg, {})
        self.assertEqual(t.key, "ss-winter-2026")
        self.assertEqual(series.next_topic("season", self.lib, None, date(2027, 1, 20), self.cfg, {})
                         .key, "ss-winter-2026")
        self.assertIsNone(series.next_topic("season", self.lib, None, date(2027, 1, 20), self.cfg,
                                            {"ss-winter-2026": date(2026, 12, 5)}))
        self.assertIsNone(series.next_topic("season", self.lib, None, date(2027, 2, 20), self.cfg, {}))  # too late
        self.assertEqual(ed.find_topic("ss-winter-2026", self.lib).data["year"], 2026)

    def test_recap_from_weekly_snapshots(self):
        weeks = ["2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28"]
        for k, day in enumerate(weeks):
            items = [catalog_item("Steady", "Always Top Cream", rank=1, no="A"),
                     catalog_item("Rising", "Climber Serum", rank=20 - k * 6, no="B"),
                     catalog_item("Other", "Middle Toner", rank=5 + k, no="C"),
                     catalog_item("Other", "Second Essence", rank=3, no="D"),
                     catalog_item("Third", "Third Cleanser", rank=4, no="E"),
                     catalog_item("Hair", "Scalp Thing", lst="Hair", rank=1, no="H")]
            series.save_snapshot(self.cfg, items, day)
        self.assertIsNone(series.recap_data(self.cfg, date(2026, 10, 12)))  # only early in the month
        d = series.recap_data(self.cfg, date(2026, 10, 2))
        self.assertEqual(d["month"], "2026-09")
        self.assertEqual(d["weeks"], 4)
        self.assertEqual(d["top"][0]["product"], "Always Top Cream")
        self.assertEqual(d["top"][0]["top10"], 4)
        self.assertEqual(d["climber"]["product"], "Climber Serum")
        self.assertEqual((d["climber"]["from"], d["climber"]["to"]), (20, 2))
        self.assertNotIn("Scalp Thing", json.dumps(d))
        t = series.next_topic("recap", self.lib, None, date(2026, 10, 2), self.cfg, {})
        prods = ed.find_products(t, self.cfg, [], lib=self.lib)
        self.assertTrue(all(p["links"] for p in prods))
        info = ed.build_info_copy(t, 50, self.cfg, prods, lib=self.lib)
        self.assertIn("September", info.caption)
        self.assertIn("#ad", info.caption)

    def test_industry_issue_and_words(self):
        (self.tmp / "content").mkdir(exist_ok=True)
        for f in ed.content_dir(self.cfg).glob("*.toml"):
            shutil.copy(f, self.tmp / "content" / f.name)
        self.cfg.raw.setdefault("editorial", {})["content_dir"] = str(self.tmp / "content")
        (self.tmp / "content" / "industry.toml").write_text(
            '[[issue]]\nid = "2026-10"\ndate = "2026-10-01"\ntitle = "What the K-beauty industry is betting on"\n'
            'hook = "Test hook"\nitems = [{ name = "Thing A", signal = "Expo", why = "Because" },'
            ' { name = "Thing B", signal = "ODM", why = "Because" }, { name = "Thing C", signal = "Press", why = "Because" }]\n'
            'sources = ["https://a.example/1", "https://b.example/2"]\n', encoding="utf-8")
        lib = ed.load_library(self.cfg)
        self.assertEqual(series.next_topic("industry", lib, None, date(2026, 10, 3), self.cfg, {}).key, "in-2026-10")
        self.assertIsNone(series.next_topic("industry", lib, None, date(2026, 12, 3), self.cfg, {}))
        # the bundled Korean font covers every word in the words series
        from PIL import ImageFont
        from bot.render import FONTS
        from bot.render_series import KO
        font = ImageFont.truetype(str(FONTS / KO), 100)
        for s in lib.words:
            for w in s["words"]:
                for ch in w["ko"].replace(" ", ""):
                    self.assertGreater(font.getmask(ch).getbbox()[2], 10, ch)

    def test_prepare_series_day_marks_source(self):
        write_catalog(self.cfg, [catalog_item("Anua", "Niacinamide 10 TXA 4 Serum", no="N1")])
        out = self.tmp / "site"
        rc = cmd_prepare(Namespace(out=str(out), dry_run=False, source="routine", date=TUESDAY.isoformat(), reel="no"),
                         cfg=self.cfg)
        self.assertEqual(rc, 0)
        post = State(self.cfg.state_file).posts[-1]
        self.assertEqual(post["source"], "routine")
        self.assertTrue(post["key"].startswith("rt-"))
        self.assertTrue((out / "p" / f"{post['folder']}.html").exists() or (out / "index.html").exists())
        self.assertNotIn("reel", post)


class ReelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict("os.environ", ENV)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prepare(self, mode):
        cfg = make_cfg(self.tmp, [], library=True, series=True, reels=mode)
        cfg.raw["reels"]["seconds_per_slide"] = 1.2
        out = self.tmp / "site"
        rc = cmd_prepare(Namespace(out=str(out), dry_run=False, source="myth", date=TUESDAY.isoformat(), reel=None), cfg=cfg)
        self.assertEqual(rc, 0)
        return cfg, out, State(cfg.state_file).posts[-1]

    def _streams(self, video):
        r = subprocess.run([reels.ffmpeg_path(), "-hide_banner", "-i", str(video)], capture_output=True, text=True)
        return r.stderr

    def test_auto_reel_then_carousel(self):
        self.assertTrue(reels.tracks(), "assets/music/ has the original tracks")
        cfg, out, post = self._prepare("auto")
        rec = post["reel"]
        self.assertEqual(rec["mode"], "auto")
        video = out / rec["video"]
        info = self._streams(video)
        self.assertIn("1080x1920", info)
        self.assertIn("h264", info)
        self.assertIn("Audio: aac", info)
        self.assertTrue((out / rec["cover"]).exists())
        ig = FakeIG()
        with mock.patch.dict("os.environ", {"IG_ACCESS_TOKEN": "TOKEN_X"}):
            rc = cmd_publish(Namespace(site_url="https://u.github.io/repo"), cfg=cfg, session=ig, sleep=lambda s: None)
        self.assertEqual(rc, 0)
        creates = [c[2] for c in ig.calls if c[0] == "POST" and c[1].endswith("/media")]
        self.assertEqual(creates[0]["media_type"], "REELS")  # Reel first ...
        self.assertTrue(creates[0]["video_url"].endswith(rec["video"]))
        self.assertEqual(creates[0]["share_to_feed"], "true")
        self.assertIn("card version", creates[0]["caption"])
        self.assertEqual(creates[0]["audio_name"], cfg.raw["reels"]["audio_name"])
        self.assertEqual(creates[-1]["media_type"], "CAROUSEL")  # ... then the same cards as a carousel
        st = State(cfg.state_file)
        self.assertEqual(st.posts[-1]["status"], "published")
        self.assertEqual(st.posts[-1]["reel"]["status"], "published")

    def test_failed_reel_does_not_block_cards(self):
        cfg, out, post = self._prepare("auto")

        class ReelFails(FakeIG):
            def post(self, url, data=None, timeout=None):
                if (data or {}).get("media_type") == "REELS":
                    self.calls.append(("POST", url, dict(data)))
                    return FakeResp({"error": {"message": "video too short", "code": 2207026}}, status=400)
                return super().post(url, data, timeout)

        ig = ReelFails()
        with mock.patch.dict("os.environ", {"IG_ACCESS_TOKEN": "TOKEN_X"}):
            rc = cmd_publish(Namespace(site_url="https://u.github.io/repo"), cfg=cfg, session=ig, sleep=lambda s: None)
        self.assertEqual(rc, 0)
        st = State(cfg.state_file)
        self.assertEqual(st.posts[-1]["status"], "published")
        self.assertEqual(st.posts[-1]["reel"]["status"], "failed")

    def test_manual_mode_makes_silent_video_and_skips_reel_publish(self):
        cfg, out, post = self._prepare("manual")
        self.assertEqual(post["reel"]["mode"], "manual")
        self.assertNotIn("Audio:", self._streams(out / post["reel"]["video"]))
        ig = FakeIG()
        with mock.patch.dict("os.environ", {"IG_ACCESS_TOKEN": "TOKEN_X"}):
            cmd_publish(Namespace(site_url="https://u.github.io/repo"), cfg=cfg, session=ig, sleep=lambda s: None)
        self.assertFalse(any(c[2].get("media_type") == "REELS" for c in ig.calls if c[0] == "POST"))

    def test_reel_days(self):
        cfg = make_cfg(self.tmp, [], library=True, series=True, reels="auto")
        days = [reels.is_reel_day(cfg, TUESDAY + timedelta(days=i)) for i in range(7)]
        self.assertEqual(days, [True, False, True, False, True, False, False])  # tue thu sat
        self.assertFalse(reels.is_reel_day(make_cfg(self.tmp / "o", [], reels="off"), TUESDAY))
        self.assertTrue(reels.is_reel_day(cfg, TUESDAY + timedelta(days=1), "yes"))


if __name__ == "__main__":
    unittest.main()
