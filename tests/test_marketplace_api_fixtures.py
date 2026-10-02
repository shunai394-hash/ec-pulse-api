"""Official marketplace API responses (JSON fixtures) through the production
search functions: httpx streaming, size-capped read, JSON parsing and mapping.
Only the network is replaced by an httpx MockTransport."""
import asyncio
import time
from pathlib import Path

import httpx
import pytest

from app.services import product_search

FIXTURES = Path(__file__).parent / "fixtures" / "marketplace_api"


@pytest.fixture
def api(monkeypatch):
    requests = []

    def serve(fixture):
        def handler(request):
            requests.append((time.monotonic(), request))
            return httpx.Response(200, content=(FIXTURES / fixture).read_bytes(),
                                  headers={"Content-Type": "application/json"})
        monkeypatch.setattr(product_search, "safe_async_client",
                            lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kw))
    serve.requests = requests
    return serve


def stock_and_price(items):
    return [(i["product"]["pricing"]["price"], i["product"]["availability"]["status"]) for i in items]


def test_rakuten_availability_flag_is_respected(api, monkeypatch):
    monkeypatch.setenv("RAKUTEN_APPLICATION_ID", "app")
    monkeypatch.setenv("RAKUTEN_ACCESS_KEY", "key")
    api("rakuten_search.json")

    items = asyncio.run(product_search._search_rakuten_official("ケトル", 10))

    # Previously every Rakuten item was reported "InStock".
    assert stock_and_price(items) == [(2980.0, "InStock"), (1980.0, "OutOfStock"), (3480.0, "Unknown")]


def test_yahoo_missing_stock_flag_is_unknown_not_out_of_stock(api, monkeypatch):
    monkeypatch.setenv("YAHOO_SHOPPING_APP_ID", "app")
    api("yahoo_search.json")

    items = asyncio.run(product_search._search_yahoo_official("ケトル", 10))

    assert stock_and_price(items) == [(2480.0, "InStock"), (1780.0, "OutOfStock"), (3180.0, "Unknown")]
    assert items[0]["product"]["product"]["gtin"] == "4901234567894"


def test_yahoo_requests_are_spaced(api, monkeypatch):
    monkeypatch.setenv("YAHOO_SHOPPING_APP_ID", "app")
    monkeypatch.setattr(product_search, "_YAHOO_MIN_INTERVAL_SECONDS", 0.3)
    monkeypatch.setattr(product_search, "_yahoo_last_request_at", 0.0)
    api("yahoo_search.json")

    async def two_calls():
        await product_search._search_yahoo_official("a", 1)
        await product_search._search_yahoo_official("b", 1)

    asyncio.run(two_calls())

    first, second = (t for t, _ in api.requests)
    assert second - first >= 0.25
