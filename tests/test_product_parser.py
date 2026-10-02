from app.services.product_parser import _find_product, _offers_dict


def test_offers_dict_accepts_list_and_prefers_priced_offer():
    offers = [{"availability": "InStock"}, {"price": "1980", "priceCurrency": "JPY"}]
    assert _offers_dict(offers)["price"] == "1980"


def test_find_product_accepts_array_type_and_graph():
    items = [
        {"@graph": [{"@type": ["Product", "Thing"], "name": "Test Product"}]}
    ]
    assert _find_product(items)["name"] == "Test Product"


def test_product_parser_does_not_treat_high_price_as_list_price(monkeypatch):
    import app.services.product_parser as parser

    class FakeResponse:
        url = "https://example.com/item"

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        def stream(self, *args, **kwargs):
            class Stream:
                async def __aenter__(self):
                    return self
                async def __aexit__(self, *args):
                    return None
                headers = {}
                status_code = 200
                url = "https://example.com/item"
                def raise_for_status(self):
                    return None
            return Stream()

    async def fake_validate(url):
        return url

    async def fake_read(response, max_bytes):
        return b'''<script type="application/ld+json">
        {"@type":"Product","name":"Range Product",
         "offers":{"price":"1000","highPrice":"2000","priceCurrency":"JPY"}}
        </script>'''

    monkeypatch.setattr(parser, "validate_public_url", fake_validate)
    monkeypatch.setattr(parser, "safe_async_client", lambda **kwargs: FakeClient())
    monkeypatch.setattr(parser, "read_response_bytes", fake_read)

    result = __import__("asyncio").run(parser.fetch_product("https://example.com/item"))
    assert result["pricing"]["price"] == 1000
    assert result["pricing"]["list_price"] is None
