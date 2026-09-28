import json
from datetime import date

from bot import insights
from bot.state import State
from test_smoke import FakeResp, make_cfg


class FakeInsightsIG:
    def __init__(self, deny=False):
        self.deny = deny
        self.calls = []

    def get(self, url, params=None, timeout=None):
        params = dict(params or {})
        self.calls.append((url, params))
        if self.deny and url.endswith("/insights"):
            return FakeResp({"error": {"message": "(#10) Application does not have permission", "code": 10}}, status=403)
        if url.endswith("/me"):
            return FakeResp({"user_id": "178", "username": "seoul.skin.picks"})
        if url.endswith("/178"):
            return FakeResp({"followers_count": 42, "media_count": 5})
        if url.endswith("/178/media"):
            return FakeResp({"data": [
                {"id": "m1", "media_type": "CAROUSEL_ALBUM", "media_product_type": "FEED",
                 "permalink": "https://www.instagram.com/p/AAA/", "timestamp": "2026-09-27T13:20:00+0000"},
                {"id": "m2", "media_type": "VIDEO", "media_product_type": "REELS",
                 "permalink": "https://www.instagram.com/reel/BBB/", "timestamp": "2026-09-28T13:20:00+0000"},
                {"id": "old", "media_type": "IMAGE", "media_product_type": "FEED",
                 "permalink": "x", "timestamp": "2025-01-01T00:00:00+0000"}]})
        if url.endswith("/178/insights"):
            names = params["metric"].split(",")
            return FakeResp({"data": [{"name": n, "total_value": {"value": 100}} for n in names]})
        if url.endswith("/m1/insights"):
            if "," in params["metric"] or params["metric"] == "shares":
                # one unsupported metric makes the combined call fail -> retried one by one
                return FakeResp({"error": {"message": "metric not supported", "code": 100}}, status=400)
            return FakeResp({"data": [{"name": params["metric"], "period": "lifetime", "values": [{"value": 7}]}]})
        if url.endswith("/m2/insights"):
            names = params["metric"].split(",")
            return FakeResp({"data": [{"name": n, "values": [{"value": 30}]} for n in names]})
        return FakeResp({"error": {"message": "unexpected", "code": 1}}, status=400)


def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("IG_ACCESS_TOKEN", "tok")
    monkeypatch.delenv("IG_USER_ID", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return make_cfg(tmp_path, [])


def test_insights_report_and_history(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    state = State(cfg.state_file)
    state.posts.append({"number": 3, "status": "published", "ig_media_id": "m1", "key": "k", "date": "2026-09-27"})
    fake = FakeInsightsIG()
    assert insights.run(cfg, state, date(2026, 9, 28), session=fake) == 0
    hist = json.loads((cfg.root / "data" / "insights.json").read_text())
    assert hist["account"]["2026-09-28"]["followers"] == 42
    assert hist["account"]["2026-09-28"]["last_7_days"]["reach"] == 100
    assert set(hist["media"]) == {"m1", "m2"}
    assert hist["media"]["m1"]["number"] == 3
    m1 = hist["media"]["m1"]["history"]["2026-09-28"]
    assert m1["reach"] == 7 and "shares" not in m1
    assert hist["media"]["m2"]["history"]["2026-09-28"]["ig_reels_avg_watch_time"] == 30
    # next day: growth column
    snap = insights.collect(insights.Instagram("tok", session=fake), "178", date(2026, 9, 29))
    text = insights.report(snap, {"m1": 3}, {"m1": {"reach": 2}})
    assert "+5" in text and "릴스" in text


def test_insights_permission_hint(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path, monkeypatch)
    assert insights.run(cfg, State(cfg.state_file), date(2026, 9, 28), session=FakeInsightsIG(deny=True)) == 1
    out = capsys.readouterr()
    assert "instagram_business_manage_insights" in out.out + out.err
    assert "tok" not in out.out + out.err
    assert not (cfg.root / "data" / "insights.json").exists()
