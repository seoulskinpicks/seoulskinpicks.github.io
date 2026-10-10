import io
import json

from PIL import Image

from bot import stock


def _jpeg(w=900, h=1200) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (w, h), (200, 150, 140)).save(b, "JPEG")
    return b.getvalue()


class FakeResp:
    def __init__(self, js=None, content=b""):
        self._js, self.content = js, content

    def raise_for_status(self):
        pass

    def json(self):
        return self._js


class FakeSession:
    def __init__(self, big=True):
        self.urls = []
        self.big = big

    def get(self, url, **kw):
        self.urls.append(url)
        if "pexels.com/v1" in url:
            return FakeResp({"photos": [{"photographer": "Jane Doe", "src": {"large2x": "https://img/x.jpg"}}]})
        return FakeResp(content=_jpeg() if self.big else _jpeg(300, 400))


def test_pexels_photo_has_credit(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    p = stock.find({"id": "niacinamide", "area": "skin"}, session=FakeSession(), root=None)
    assert p and p.credit == "📷 Photo: Jane Doe / Pexels" and not p.ai


def test_no_key_means_no_photo(monkeypatch, tmp_path):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert stock.find({"id": "niacinamide"}, session=FakeSession(), root=tmp_path) is None


def test_small_photo_is_rejected(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    assert stock.find({"id": "x", "area": "hair"}, session=FakeSession(big=False)) is None


def test_library_photo_wins_and_ai_note(monkeypatch, tmp_path):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    lib = tmp_path / "photos" / "library"
    lib.mkdir(parents=True)
    (lib / "pdrn.jpg").write_bytes(_jpeg())
    (lib / "credits.json").write_text(json.dumps({"pdrn": {"ai": True}}), encoding="utf-8")
    sess = FakeSession()
    p = stock.find({"id": "pdrn"}, session=sess, root=tmp_path)
    assert p and p.ai and sess.urls == []
    cap = stock.add_credit("hello\n.\n#a #b", p)
    assert "🤖 Image created with AI" in cap and cap.endswith("\n.\n#a #b")


def test_credit_goes_above_hashtags_and_respects_limit():
    p = stock.Photo(Image.new("RGB", (10, 10)), "📷 Photo: A / Pexels")
    assert stock.add_credit("body\n.\n#x", p) == "body\n📷 Photo: A / Pexels\n.\n#x"
    long = "a" * 2200
    assert stock.add_credit(long, p) == long
