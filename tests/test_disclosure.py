from types import SimpleNamespace

from bot.disclosure import any_affiliate, is_affiliate_url


def cfg(template="{url}", code=""):
    return SimpleNamespace(kbeauty={"oliveyoung_link_template": template, "oliveyoung_code": code})


def test_aliexpress_tracking_link_is_affiliate_plain_item_is_not():
    assert is_affiliate_url("https://s.click.aliexpress.com/e/_abc", cfg())
    assert not is_affiliate_url("https://www.aliexpress.com/item/1005006.html", cfg())


def test_olive_young_is_affiliate_only_with_template_or_code():
    url = "https://global.oliveyoung.com/product/detail?prdtNo=GA1"
    assert not is_affiliate_url(url, cfg())
    assert is_affiliate_url(url + "&ref=ME", cfg(template="{url}&ref=ME"))
    assert is_affiliate_url(url, cfg(code="SEOUL10"))


def test_other_hosts_count_as_your_own_affiliate_link_and_empty_does_not():
    assert is_affiliate_url("https://shop.example.org/1", cfg())
    assert not is_affiliate_url("", cfg())
    assert not any_affiliate({"oliveyoung": "https://global.oliveyoung.com/p/1"}, cfg())
