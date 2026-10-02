"""Credit charge/refund consistency through the real FastAPI routes and a real
PostgreSQL database. Only upstream network calls (product fetch, comment
fetch, marketplace search) are replaced.

For every request the balance, the api_usage ledger, the response body and
the X-EC-Credits-* headers must agree.
"""
import hashlib
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app import main
from tests.conftest import pg_exec, pg_query


@pytest.fixture
def api(pg_store, public_dns, monkeypatch):
    monkeypatch.delenv("EC_PULSE_REQUIRE_REQUEST_SIGNATURE", raising=False)
    key = pg_store.provision_customer_api_key(f"user-{uuid.uuid4()}")["api_key"]
    return TestClient(main.app), key


def key_hash(key):
    return hashlib.sha256(key.encode()).hexdigest()


def set_balance(key, credits):
    pg_exec("UPDATE api_accounts SET credits_balance = %s WHERE api_key_hash = %s", (credits, key_hash(key)))


def balance(key):
    return pg_query("SELECT credits_balance FROM api_accounts WHERE api_key_hash = %s", (key_hash(key),))[0][0]


def ledger(key):
    return pg_query("SELECT endpoint, credits FROM api_usage WHERE api_key_hash = %s ORDER BY id", (key_hash(key),))


def product(url, price=1000.0):
    return {
        "product": {"title": "item"},
        "pricing": {"price": price, "currency": "JPY"},
        "source": {"url": url, "marketplace": "web"},
    }


def assert_consistent(response, key, used):
    assert response.headers["X-EC-Credits-Used"] == str(used)
    assert response.headers["X-EC-Credits-Remaining"] == str(balance(key))
    assert sum(c for _, c in ledger(key)) == used
    assert balance(key) == 100 - used


def test_compare_partial_failure_refunds_failed_urls(api, monkeypatch):
    client, key = api

    async def fetch(url):
        if "broken" in url:
            raise RuntimeError("upstream down")
        return product(url), False

    monkeypatch.setattr(main, "fetch_product_cached", fetch)
    urls = ["https://a.example.com/1", "https://b.example.com/broken", "https://c.example.com/3"]

    response = client.post("/v1/products/compare", json={"urls": urls}, headers={"X-API-Key": key})

    assert response.status_code == 200
    body = response.json()
    assert body["successful"] == 2
    assert body["credits"]["credits_used"] == 2
    assert body["credits"]["credits_refunded"] == 1
    assert body["credits"]["credits_remaining"] == 98
    assert ledger(key) == [("POST /v1/products/compare", 3), ("POST /v1/products/compare (refund)", -1)]
    assert_consistent(response, key, 2)

    account = client.get("/v1/account", headers={"X-API-Key": key}).json()
    assert account["credits_balance"] == 98
    assert account["total_credits_used"] == 2
    # The refund ledger row is not a second request.
    assert account["period_usage"]["last_24_hours"] == {"credits": 2, "requests": 1}


def test_product_fetch_failure_refunds_and_hides_internal_error(api, monkeypatch):
    client, key = api

    async def fetch(url):
        raise RuntimeError("connect to postgresql://admin:hunter2@db.internal failed")

    monkeypatch.setattr(main, "fetch_product_cached", fetch)

    response = client.get("/v1/products", params={"url": "https://shop.example.com/x"}, headers={"X-API-Key": key})

    assert response.status_code == 502
    assert response.json() == {"detail": "Unable to retrieve product page: RuntimeError"}
    assert "hunter2" not in response.text
    assert balance(key) == 100
    assert ledger(key) == [("GET /v1/products", 1), ("GET /v1/products (refund)", -1)]


def test_search_failure_refunds_full_charge(api, monkeypatch):
    client, key = api

    async def search(query, marketplaces, limit):
        raise RuntimeError("search backend down")

    monkeypatch.setattr(main, "search_products", search)

    response = client.post("/v1/products/search", json={"query": "kettle", "marketplaces": ["amazon", "yahoo"], "limit": 3},
                           headers={"X-API-Key": key})

    assert response.status_code == 502
    assert balance(key) == 100
    assert ledger(key) == [("POST /v1/products/search", 6), ("POST /v1/products/search (refund)", -6)]


def test_research_ingest_partial_failure_refunds_failed_urls(api, monkeypatch):
    client, key = api

    async def comments(url, limit):
        if "broken" in url:
            raise RuntimeError("blocked")
        return {"url": url, "source": "example", "market": "JP", "locale": "ja-JP", "comments": ["高すぎる", "壊れやすい"]}

    monkeypatch.setattr(main, "fetch_public_comments", comments)

    response = client.post("/v1/research/ingest",
                           json={"urls": ["https://a.example.com/r", "https://b.example.com/broken"]},
                           headers={"X-API-Key": key})

    assert response.status_code == 200
    body = response.json()
    assert [r.get("ok") for r in body["results"]][1] is False
    assert body["credits"]["credits_used"] == 1
    assert_consistent(response, key, 1)


@pytest.mark.parametrize("starting_balance", [0, 1])
def test_insufficient_balance_is_402_without_any_ledger_write(api, monkeypatch, starting_balance):
    client, key = api
    calls = []

    async def fetch(url):
        calls.append(url)
        return product(url), False

    monkeypatch.setattr(main, "fetch_product_cached", fetch)
    set_balance(key, starting_balance)

    response = client.post("/v1/products/compare", json={"urls": ["https://a.example.com/1", "https://b.example.com/2"]},
                           headers={"X-API-Key": key})

    assert response.status_code == 402
    assert response.json() == {"detail": "Insufficient API credits"}
    assert calls == []
    assert balance(key) == starting_balance
    assert ledger(key) == []


def test_invalid_and_revoked_keys_are_401_without_charge(api, monkeypatch, pg_store):
    client, key = api
    monkeypatch.setattr(main, "fetch_product_cached", lambda url: (_ for _ in ()).throw(AssertionError("no fetch")))

    response = client.get("/v1/products", params={"url": "https://shop.example.com/x"}, headers={"X-API-Key": "ecp_live_unknown"})
    assert response.status_code == 401

    pg_store.revoke_api_key(key)
    response = client.get("/v1/products", params={"url": "https://shop.example.com/x"}, headers={"X-API-Key": key})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or revoked API key"}
    assert ledger(key) == []
    assert balance(key) == 100


def test_concurrent_requests_cannot_spend_the_last_credit_twice(api, monkeypatch):
    client, key = api

    async def slow_fetch(url):
        time.sleep(0.2)
        return product(url), False

    monkeypatch.setattr(main, "fetch_product_cached", slow_fetch)
    set_balance(key, 1)
    statuses = []
    barrier = threading.Barrier(4)

    def call():
        barrier.wait()
        with TestClient(main.app) as c:
            statuses.append(c.get("/v1/products", params={"url": "https://shop.example.com/x"},
                                  headers={"X-API-Key": key}).status_code)

    threads = [threading.Thread(target=call) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(statuses) == [200, 402, 402, 402]
    assert balance(key) == 0
    assert ledger(key) == [("GET /v1/products", 1)]


def test_failed_refund_is_logged(api, monkeypatch, caplog):
    client, key = api

    async def fetch(url):
        raise RuntimeError("upstream down")

    def broken_refund(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "fetch_product_cached", fetch)
    monkeypatch.setattr(main, "refund_credit", broken_refund)

    with caplog.at_level("ERROR"):
        response = client.get("/v1/products", params={"url": "https://shop.example.com/x"}, headers={"X-API-Key": key})

    assert response.status_code == 502
    assert balance(key) == 99
    assert any("credit refund failed" in r.getMessage() for r in caplog.records)
    assert all(key not in r.getMessage() for r in caplog.records)


def test_search_where_every_marketplace_failed_is_refunded(api, monkeypatch):
    from app.services import product_search

    client, key = api

    async def down(*args, **kwargs):
        raise RuntimeError("marketplace down")

    async def nothing(*args, **kwargs):
        return []

    for name in ["_search_marketplace", "_search_amazon_official", "_search_yahoo_official", "_search_rakuten_official"]:
        monkeypatch.setattr(product_search, name, down)
    monkeypatch.setattr(product_search, "_search_bing_marketplace", nothing)

    response = client.post("/v1/products/search", json={"query": "kettle", "marketplaces": ["amazon", "yahoo"], "limit": 2},
                           headers={"X-API-Key": key})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert {e["marketplace"] for e in body["marketplace_errors"]} == {"amazon", "yahoo"}
    assert body["credits"]["credits_used"] == 0
    assert_consistent(response, key, 0)


def test_search_with_one_marketplace_up_keeps_the_charge(api, monkeypatch):
    from app.services import product_search

    client, key = api

    async def down(*args, **kwargs):
        raise RuntimeError("marketplace down")

    async def links(marketplace, query, limit):
        return ["https://shopping.yahoo.co.jp/item/1"]

    async def fetch(url):
        return product(url), False

    monkeypatch.setattr(product_search, "_search_marketplace", lambda m, q, l: down() if m == "amazon" else links(m, q, l))
    monkeypatch.setattr(product_search, "fetch_product_cached", fetch)
    for name in ["AMAZON_CLIENT_ID", "YAHOO_SHOPPING_APP_ID", "RAKUTEN_APPLICATION_ID"]:
        monkeypatch.delenv(name, raising=False)

    response = client.post("/v1/products/search", json={"query": "kettle", "marketplaces": ["amazon", "yahoo"], "limit": 2},
                           headers={"X-API-Key": key})

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert_consistent(response, key, 4)
