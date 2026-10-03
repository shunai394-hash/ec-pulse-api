"""Parser regressions driven through the real fetch_product path.

Each fixture is served by an httpx MockTransport, so the response goes
through the production redirect loop, size checks, read_response_bytes and
BeautifulSoup parsing.
"""
import asyncio
from pathlib import Path

import httpx
import pytest

from app.services import product_parser, product_search

FIXTURES = Path(__file__).parent / "fixtures" / "product_pages"


@pytest.fixture
def serve(public_dns, monkeypatch):
    pages = {}

    def handler(request):
        name = pages.get(request.url.path)
        if name is None:
            return httpx.Response(404)
        return httpx.Response(200, content=(FIXTURES / name).read_bytes(), headers={"Content-Type": "text/html"})

    monkeypatch.setattr(
        product_parser, "safe_async_client",
        lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kw),
    )

    def fetch(fixture):
        pages["/item"] = fixture
        return asyncio.run(product_parser.fetch_product("https://shop.example.com/item"))

    return fetch


def test_full_width_price_is_not_truncated(serve):
    data = serve("fullwidth_price.html")
    # Previously 1.0: the full-width comma split the number.
    assert data["pricing"] == {"price": 1980.0, "list_price": None, "currency": "JPY"}
    assert data["product"]["gtin"] == "4901234567894"
    assert data["availability"]["status"] == "https://schema.org/InStock"


def test_negative_price_is_not_reported_as_a_price(serve):
    assert serve("negative_price.html")["pricing"]["price"] is None


def test_graph_product_with_malformed_block_and_multiple_offers(serve):
    data = serve("multiple_offers_graph.html")
    assert data["product"]["title"] == "Graph Kettle"
    assert data["product"]["brand"] == "Acme"
    assert data["product"]["gtin"] == "14901234567891"
    assert data["pricing"]["price"] == 2480.0 and data["pricing"]["currency"] == "JPY"
    assert data["seller"]["name"] == "Acme Store"
    assert data["rating"] == {"score": 4.5, "count": 1234}


def test_page_without_product_data_has_no_price(serve):
    data = serve("no_structured_data.html")
    assert data["pricing"]["price"] is None
    assert data["pricing"]["currency"] is None
    assert data["product"]["product_id"] is None


def test_aggregate_offer_range_is_not_guessed_as_a_price(serve):
    data = serve("aggregate_offer.html")
    assert data["pricing"]["price"] is None
    assert data["pricing"]["list_price"] is None


@pytest.mark.parametrize(("raw", "expected"), [
    ("１，９８０円", 1980.0), ("１２．５", 12.5), ("¥1,980", 1980.0), ("1,980円（税込）", 1980.0),
    (2480, 2480.0), (True, None), (float("nan"), None), ("-500", None), ("無料", None),
    # Unchanged from before: zero is reported as 0.0 (policy for 0 is an open issue).
    ("0", 0.0), ("0円", 0.0), (0, 0.0),
])
def test_price_normalisation(raw, expected):
    assert product_parser._price(raw) == expected


def test_marketplace_api_items_do_not_invent_prices_or_stock():
    yahoo = product_search._yahoo_item({"name": "x", "price": True})
    assert yahoo["product"]["pricing"]["price"] is None
    assert yahoo["product"]["availability"]["status"] == "Unknown"
    assert product_search._yahoo_item({"price": 0, "inStock": False})["product"]["availability"]["status"] == "OutOfStock"

    sold_out = product_search._rakuten_item({"itemName": "x", "itemPrice": 980, "availability": 0})
    assert sold_out["product"]["pricing"]["price"] == 980.0
    assert sold_out["product"]["availability"]["status"] == "OutOfStock"
    assert product_search._rakuten_item({"itemPrice": 980, "availability": 1})["product"]["availability"]["status"] == "InStock"
    assert product_search._rakuten_item({"itemPrice": 980})["product"]["availability"]["status"] == "Unknown"
