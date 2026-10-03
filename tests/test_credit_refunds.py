"""Credits must only be kept for work that actually succeeded."""
from fastapi.testclient import TestClient

from app import main


async def _ok_urls(urls):
    return None


def _setup(monkeypatch):
    charges, refunds, header_calls = [], [], []
    monkeypatch.setattr(main, "_validate_urls", _ok_urls)
    monkeypatch.setattr(
        main, "_charge",
        lambda api_key, endpoint, credits=1: charges.append((endpoint, credits)) or {"credits_used": credits, "credits_remaining": 100 - credits},
    )
    monkeypatch.setattr(
        main, "refund_credit",
        lambda api_key, endpoint, credits: refunds.append((endpoint, credits)) or {"credits_refunded": credits, "credits_remaining": 100},
    )
    monkeypatch.setattr(
        main, "_usage_headers",
        lambda request, api_key, credits_used=None: header_calls.append(credits_used) or {"X-EC-Credits-Used": str(credits_used)},
    )
    main.app.dependency_overrides[main.get_api_key] = lambda: "test-key"
    return charges, refunds, header_calls


def _teardown():
    main.app.dependency_overrides.pop(main.get_api_key, None)


def test_product_fetch_failure_refunds_credit(monkeypatch):
    charges, refunds, _ = _setup(monkeypatch)

    async def failing_fetch(url):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(main, "fetch_product_cached", failing_fetch)
    try:
        response = TestClient(main.app).get("/v1/products", params={"url": "https://example.com/p"})
    finally:
        _teardown()
    assert response.status_code == 502
    assert charges == [("GET /v1/products", 1)]
    assert refunds == [("GET /v1/products", 1)]


def test_product_fetch_success_keeps_credit_and_sets_integer_header(monkeypatch):
    charges, refunds, header_calls = _setup(monkeypatch)

    async def ok_fetch(url):
        return {"product": {"title": "x"}}, False

    monkeypatch.setattr(main, "fetch_product_cached", ok_fetch)
    try:
        response = TestClient(main.app).post("/v1/products", json={"url": "https://example.com/p"})
    finally:
        _teardown()
    assert response.status_code == 200
    assert refunds == []
    assert header_calls == [1]
    assert response.headers["X-EC-Credits-Used"] == "1"


def test_search_failure_refunds_full_charge(monkeypatch):
    charges, refunds, _ = _setup(monkeypatch)

    async def failing_search(query, marketplaces, limit):
        raise TimeoutError()

    monkeypatch.setattr(main, "search_products", failing_search)
    try:
        response = TestClient(main.app).post("/v1/products/search", json={"query": "q", "marketplaces": ["amazon", "yahoo"], "limit": 3})
    finally:
        _teardown()
    assert response.status_code == 502
    assert charges == [("POST /v1/products/search", 6)]
    assert refunds == [("POST /v1/products/search", 6)]


def test_compare_refunds_only_failed_urls(monkeypatch):
    charges, refunds, _ = _setup(monkeypatch)

    async def mixed_fetch(url):
        if url.endswith("/bad"):
            raise RuntimeError("boom")
        return {"pricing": {"price": 1}, "source": {"url": url}}, False

    monkeypatch.setattr(main, "fetch_product_cached", mixed_fetch)
    try:
        response = TestClient(main.app).post(
            "/v1/products/compare",
            json={"urls": ["https://example.com/a", "https://example.com/bad", "https://example.com/c"]},
        )
    finally:
        _teardown()
    assert response.status_code == 200
    body = response.json()
    assert refunds == [("POST /v1/products/compare", 1)]
    assert body["credits"]["credits_used"] == 2
    assert body["credits"]["credits_refunded"] == 1


def test_compare_all_success_has_no_refund(monkeypatch):
    _, refunds, _ = _setup(monkeypatch)

    async def ok_fetch(url):
        return {"pricing": {"price": 1}, "source": {"url": url}}, False

    monkeypatch.setattr(main, "fetch_product_cached", ok_fetch)
    try:
        response = TestClient(main.app).post("/v1/products/compare", json={"urls": ["https://example.com/a", "https://example.com/b"]})
    finally:
        _teardown()
    assert response.status_code == 200
    assert refunds == []


def test_research_ingest_refunds_failed_urls(monkeypatch):
    _, refunds, _ = _setup(monkeypatch)

    async def mixed_comments(url, max_comments):
        if "bad" in url:
            raise ConnectionError()
        return {"url": url, "source": "example.com", "comments": [], "market": "GLOBAL"}

    monkeypatch.setattr(main, "fetch_public_comments", mixed_comments)
    try:
        response = TestClient(main.app).post(
            "/v1/research/ingest",
            json={"urls": ["https://example.com/ok", "https://example.com/bad"]},
        )
    finally:
        _teardown()
    assert response.status_code == 200
    assert refunds == [("POST /v1/research/ingest", 1)]
    assert response.json()["credits"]["credits_used"] == 1


def test_refund_failure_does_not_break_error_response(monkeypatch):
    _setup(monkeypatch)

    def broken_refund(api_key, endpoint, credits):
        raise RuntimeError("db down")

    async def failing_fetch(url):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(main, "refund_credit", broken_refund)
    monkeypatch.setattr(main, "fetch_product_cached", failing_fetch)
    try:
        response = TestClient(main.app).get("/v1/products", params={"url": "https://example.com/p"})
    finally:
        _teardown()
    assert response.status_code == 502
