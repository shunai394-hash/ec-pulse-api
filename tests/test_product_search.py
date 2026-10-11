import pytest

from app.services import product_search
from app.services.product_search import _amazon_item, _rakuten_item, _yahoo_item


def test_amazon_item_normalization():
    item = {
        "asin": "B012345678",
        "detailPageURL": "https://www.amazon.co.jp/dp/B012345678",
        "itemInfo": {
            "title": {"displayValue": "Test Product"},
            "byLineInfo": {"brand": {"displayValue": "Test Brand"}},
        },
        "offersV2": {
            "listings": [{
                "price": {"money": {"amount": 1980, "currency": "JPY"}},
                "availability": {"type": "IN_STOCK"},
                "merchantInfo": {"name": "Amazon.co.jp"},
            }]
        },
    }
    result = _amazon_item(item)
    assert result["product"]["product"]["title"] == "Test Product"
    assert result["product"]["pricing"]["price"] == 1980
    assert result["product"]["pricing"]["currency"] == "JPY"
    assert result["product"]["source"]["product_id"] == "B012345678"


def test_yahoo_item_normalization():
    item = {
        "code": "Y123",
        "name": "Yahoo Product",
        "price": 1280,
        "inStock": True,
        "url": "https://shopping.yahoo.co.jp/example",
        "brand": {"name": "Brand"},
        "review": {"rate": 4.5, "count": 12},
        "seller": {"name": "Store"},
    }
    result = _yahoo_item(item)
    assert result["product"]["product"]["title"] == "Yahoo Product"
    assert result["product"]["pricing"]["price"] == 1280
    assert result["product"]["rating"]["count"] == 12


def test_rakuten_item_normalization():
    item = {
        "itemCode": "shop:123",
        "itemName": "Rakuten Product",
        "itemPrice": 980,
        "itemUrl": "https://item.rakuten.co.jp/shop/123",
        "shopName": "Shop",
        "reviewAverage": 4.2,
        "reviewCount": 8,
    }
    result = _rakuten_item(item)
    assert result["product"]["product"]["title"] == "Rakuten Product"
    assert result["product"]["pricing"]["price"] == 980
    assert result["product"]["source"]["product_id"] == "shop:123"



@pytest.mark.asyncio
async def test_unofficial_html_search_fallback_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("EC_PULSE_ENABLE_UNOFFICIAL_HTML_SCRAPING", raising=False)
    for name in (
        "AMAZON_CLIENT_ID",
        "AMAZON_CLIENT_SECRET",
        "AMAZON_PARTNER_TAG",
        "YAHOO_SHOPPING_APP_ID",
        "RAKUTEN_APPLICATION_ID",
        "RAKUTEN_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    async def forbidden(*args, **kwargs):
        raise AssertionError("unofficial HTML fallback must not be called")

    monkeypatch.setattr(product_search, "_search_marketplace", forbidden)
    monkeypatch.setattr(product_search, "_search_bing_marketplace", forbidden)
    result = await product_search.search_products("test product", ["amazon"], 1)

    assert result["count"] == 0
    assert result["results"] == []
    assert result["marketplace_errors"][0]["marketplace"] == "amazon"
    assert result["marketplace_errors"][0]["error"] == "RuntimeError"
