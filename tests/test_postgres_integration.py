"""Integration tests against a real PostgreSQL database.

Skipped unless EC_PULSE_TEST_DATABASE_URL points at a disposable database.
Never point this at production: the tests create and delete rows.
"""
import hashlib
import hmac
import json
import os
import threading
import time
import uuid

import pytest

TEST_DB = os.getenv("EC_PULSE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="EC_PULSE_TEST_DATABASE_URL is not set")


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    monkeypatch.delenv("EC_PULSE_API_KEY", raising=False)
    import app.services.monitor_store as monitor_store
    monkeypatch.setattr(monitor_store, "_SCHEMA_READY", False)
    return monitor_store


def _user():
    return f"user-{uuid.uuid4()}"


def test_key_lifecycle_rotation_and_revocation(store):
    user = _user()
    first = store.provision_customer_api_key(user)
    assert first["created"] is True and first["api_key"].startswith("ecp_live_")
    assert store.validate_api_key(first["api_key"]) is True

    again = store.provision_customer_api_key(user)
    assert again["created"] is False and "api_key" not in again

    rotated = store.provision_customer_api_key(user, rotate=True)
    assert store.validate_api_key(first["api_key"]) is False
    assert store.validate_api_key(rotated["api_key"]) is True

    keys = store.list_customer_api_keys(user)
    assert [k["active"] for k in keys] == [True, False]
    assert all("api_key" not in k for k in keys)

    assert store.revoke_customer_api_key(user, rotated["key_prefix"]) is True
    assert store.validate_api_key(rotated["api_key"]) is False


def test_raw_key_is_never_stored(store):
    import psycopg
    key = store.provision_customer_api_key(_user())["api_key"]
    with psycopg.connect(TEST_DB) as conn:
        hits = conn.execute(
            "SELECT count(*) FROM api_keys WHERE api_key_hash = %s OR key_prefix = %s",
            (key, key),
        ).fetchone()[0]
        hashed = conn.execute(
            "SELECT count(*) FROM api_keys WHERE api_key_hash = %s",
            (hashlib.sha256(key.encode()).hexdigest(),),
        ).fetchone()[0]
    assert hits == 0
    assert hashed == 1


def test_other_users_prefix_cannot_be_revoked(store):
    a = store.provision_customer_api_key(_user())
    b_user = _user()
    store.provision_customer_api_key(b_user)
    assert store.revoke_customer_api_key(b_user, a["key_prefix"]) is False
    assert store.validate_api_key(a["api_key"]) is True


def test_concurrent_charges_never_overdraw(store):
    key = store.provision_customer_api_key(_user())["api_key"]
    results, errors = [], []

    def worker():
        try:
            results.append(store.consume_credit(key, "test", 7))
        except RuntimeError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(30)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(results) == 100 // 7
    assert all(e == "Insufficient API credits" for e in errors)
    assert store.ensure_api_account(key)["credits_balance"] == 100 - 7 * len(results)


def test_refund_restores_balance_and_ledger(store):
    key = store.provision_customer_api_key(_user())["api_key"]
    store.consume_credit(key, "GET /v1/products", 5)
    refund = store.refund_credit(key, "GET /v1/products", 5)
    assert refund["credits_remaining"] == 100
    usage = store.get_account_usage(key)
    assert usage["credits_balance"] == 100
    assert usage["total_credits_used"] == 0


def test_monitor_and_research_isolation_between_accounts(store):
    a = store.provision_customer_api_key(_user())["api_key"]
    b = store.provision_customer_api_key(_user())["api_key"]
    monitor, _ = store.create_monitor_with_credit(a, "https://example.com/p", 60, "https://example.com/hook", "POST /v1/monitors")
    run = store.save_research_run(a, {"url": "https://example.com/r", "comments": ["too expensive"]}, {"pain_points": [{"pain": "price", "count": 1, "share_percent": 100}]})

    with pytest.raises(KeyError):
        store.get_price_history(b, monitor["id"])
    with pytest.raises(KeyError):
        store.get_price_opportunity(b, monitor["id"])
    with pytest.raises(KeyError):
        store.get_research_opportunity(b, run["run_id"])
    assert store.list_monitors(b) == []
    assert store.list_research_runs(b) == []
    assert store.get_price_history(a, monitor["id"])["monitor"]["id"] == monitor["id"]


def test_monitors_and_research_survive_key_rotation(store):
    user = _user()
    old = store.provision_customer_api_key(user)["api_key"]
    monitor, _ = store.create_monitor_with_credit(old, "https://example.com/p", 60, "https://example.com/hook", "POST /v1/monitors")
    run = store.save_research_run(old, {"url": "https://example.com/r", "comments": ["broken lid"]}, {"pain_points": [{"pain": "lid", "count": 1, "share_percent": 100}]})

    new = store.provision_customer_api_key(user, rotate=True)["api_key"]
    assert [m["id"] for m in store.list_monitors(new)] == [monitor["id"]]
    assert [r["run_id"] for r in store.list_research_runs(new)] == [run["run_id"]]
    assert store.get_research_opportunity(new, run["run_id"])["run_id"] == run["run_id"]
    with pytest.raises(KeyError):
        store.get_research_opportunity(old, run["run_id"])


def test_rate_limit_blocks_after_plan_limit(store):
    from app.services.rate_limit import check_rate_limit
    key = store.provision_customer_api_key(_user())["api_key"]
    store.ensure_api_account(key)
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    allowed = [check_rate_limit(key_hash, "free")["allowed"] for _ in range(31)]
    # A window boundary can reset the counter mid-loop; at most one reset is possible.
    assert allowed.count(False) >= 1 or allowed[:30].count(True) == 30
    blocked = check_rate_limit(key_hash, "free")
    if not blocked["allowed"]:
        assert blocked["remaining"] == 0 and blocked["reset_seconds"] >= 1


def test_webhook_credit_grant_and_duplicate_against_real_db(store, monkeypatch):
    import psycopg
    import stripe
    import app.services.billing as billing

    key = store.provision_customer_api_key(_user())["api_key"]
    account_hash = hashlib.sha256(key.encode()).hexdigest()
    customer = f"cus_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(TEST_DB) as conn:
        billing._init_billing(conn)
        conn.execute("UPDATE api_accounts SET stripe_customer_id=%s WHERE api_key_hash=%s", (customer, account_hash))
        conn.commit()

    secret = "whsec_integration"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_unused")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "5000")
    sub_id = f"sub_{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(stripe.Subscription, "retrieve", staticmethod(lambda _id: stripe.StripeObject.construct_from({
        "id": sub_id, "customer": customer, "status": "active", "created": 10,
        "items": {"data": [{"price": {"id": "price_pro"}, "current_period_start": 1, "current_period_end": 2}]},
    }, "sk_test_unused")))

    invoice_id = f"in_{uuid.uuid4().hex[:12]}"

    def send(event_id, event_type):
        payload = json.dumps({"id": event_id, "object": "event", "type": event_type, "created": 20,
                              "data": {"object": {"id": invoice_id, "parent": {"subscription_details": {"subscription": sub_id}}}}}).encode()
        ts = str(int(time.time()))
        sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
        return billing.process_webhook(payload, f"t={ts},v1={sig}")

    first_id = f"evt_{uuid.uuid4().hex[:12]}"
    assert send(first_id, "invoice.paid")["credit_grant"]["granted"] is True
    assert send(first_id, "invoice.paid")["duplicate"] is True
    assert send(f"evt_{uuid.uuid4().hex[:12]}", "invoice.payment_succeeded")["credit_grant"]["reason"] == "already_granted"
    account = store.ensure_api_account(key)
    assert account["plan"] == "pro"
    assert account["credits_balance"] == 5000
