"""Status codes and error bodies across the real app and a real database.

Every error must be JSON ``{"detail": ...}`` and must never echo database
DSNs, API keys, provider secrets or stack traces.
"""
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from app.services import rate_limit

SECRETS = ["SuperSecretDbPassword", "sk_live_never_echo", "whsec_never_echo", "GOCSPX-never-echo"]


@pytest.fixture
def api(pg_store, public_dns, monkeypatch):
    monkeypatch.delenv("EC_PULSE_REQUIRE_REQUEST_SIGNATURE", raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_never_echo")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_never_echo")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "GOCSPX-never-echo")
    key = pg_store.provision_customer_api_key(f"user-{uuid.uuid4()}")["api_key"]
    return TestClient(main.app, raise_server_exceptions=False), key


def assert_clean(response, key=None):
    assert response.headers["content-type"].startswith("application/json")
    assert set(response.json()) == {"detail"}
    for secret in SECRETS + ([key] if key else []):
        assert secret not in response.text
    assert "Traceback" not in response.text and "postgresql://" not in response.text


def test_status_codes_for_common_failures(api, monkeypatch):
    client, key = api
    h = {"X-API-Key": key}

    r = client.get("/v1/products", params={"url": "http://127.0.0.1/admin"}, headers=h)
    assert r.status_code == 400; assert_clean(r, key)

    r = client.get("/v1/monitors")
    assert r.status_code == 401; assert_clean(r)

    r = client.get(f"/v1/monitors/{uuid.uuid4()}/history", headers=h)
    assert r.status_code == 404; assert_clean(r, key)

    r = client.post("/v1/products/compare", json={"urls": ["not a url"]}, headers=h)
    assert r.status_code == 422; assert "detail" in r.json()

    r = client.post("/api/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "t=1,v1=bad"})
    assert r.status_code == 400; assert_clean(r)

    pg_store_balance = "UPDATE api_accounts SET credits_balance = 0"
    with psycopg.connect(main.os.environ["DATABASE_URL"]) as conn:
        conn.execute(pg_store_balance + " WHERE api_key_hash = %s", (main._key_hash(key),))
        conn.commit()
    r = client.post("/v1/consumer-insights/analyze", json={"comments": ["x"]}, headers=h)
    assert r.status_code == 402; assert_clean(r, key)


def test_rate_limit_is_429_with_retry_after(api, monkeypatch):
    client, key = api
    monkeypatch.setitem(rate_limit._LIMITS, "free", 0)
    r = client.get("/v1/monitors", headers={"X-API-Key": key})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1
    assert r.headers["X-RateLimit-Remaining"] == "0"
    assert_clean(r, key)


def test_upstream_failure_is_502_without_upstream_details(api, monkeypatch):
    client, key = api

    async def boom(url):
        raise RuntimeError("upstream said: password=SuperSecretDbPassword")

    monkeypatch.setattr(main, "fetch_product_cached", boom)
    r = client.get("/v1/products", params={"url": "https://shop.example.com/x"}, headers={"X-API-Key": key})
    assert r.status_code == 502
    assert_clean(r, key)


def test_database_outage_is_503_without_dsn(api, monkeypatch):
    client, key = api
    monkeypatch.setenv("DATABASE_URL", "postgresql://admin:SuperSecretDbPassword@127.0.0.1:1/prod?connect_timeout=1")
    for path in ["/v1/monitors", "/health"]:
        r = client.get(path, headers={"X-API-Key": key})
        assert r.status_code == 503
        assert "SuperSecretDbPassword" not in r.text and key not in r.text


def test_unexpected_exception_is_json_500_and_logged(api, monkeypatch, caplog):
    client, key = api

    def broken(*args, **kwargs):
        raise psycopg.errors.UndefinedTable('relation "monitors" does not exist; dsn=postgresql://admin:SuperSecretDbPassword@db')

    monkeypatch.setattr(main, "list_monitors", broken)
    with caplog.at_level("ERROR"):
        r = client.get("/v1/monitors", headers={"X-API-Key": key})

    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error"}
    assert_clean(r, key)
    assert any(rec.levelname == "ERROR" for rec in caplog.records)
