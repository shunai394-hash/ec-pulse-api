"""Stripe webhook tests that use the real stripe SDK for signing/verification.

Earlier tests stubbed ``construct_event`` with objects exposing
``to_dict_recursive()``, which the pinned stripe SDK no longer provides; a real
signed event therefore crashed the webhook with AttributeError (HTTP 500).
"""
import hashlib
import hmac
import json
import time

import pytest
import stripe
from fastapi.testclient import TestClient

import app.services.billing as billing
from app import main

SECRET = "whsec_unit_test_only"


def _signed(event: dict, secret: str = SECRET) -> tuple[bytes, str]:
    payload = json.dumps(event).encode()
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return payload, f"t={ts},v1={sig}"


class _Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Conn:
    """Minimal in-memory stand-in for the billing tables."""

    def __init__(self, balance=3):
        self.events = set()
        self.grants = set()
        self.balance = balance
        self.plan = "free"
        self.committed = 0

    def execute(self, sql, params=()):
        if "INSERT INTO billing_events" in sql:
            if params[0] in self.events:
                return _Cursor(None)
            self.events.add(params[0])
            return _Cursor((params[0],))
        if "SELECT api_key_hash FROM api_accounts WHERE stripe_customer_id" in sql:
            return _Cursor(("acct-hash",) if params[0] == "cus_1" else None)
        if "SELECT stripe_subscription_id, subscription_status" in sql:
            return _Cursor((None, None, None, None, None))
        if "SELECT credits_balance FROM api_accounts" in sql:
            return _Cursor((self.balance,))
        if "INSERT INTO credit_grants" in sql:
            if params[0] in self.grants:
                return _Cursor(None)
            self.grants.add(params[0])
            return _Cursor((params[0],))
        if sql.startswith("UPDATE api_accounts SET credits_balance"):
            self.balance = params[0]
        elif "UPDATE api_accounts SET plan" in sql:
            self.plan = params[0]
        return _Cursor(None)

    def commit(self):
        self.committed += 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _subscription_object(sub_id="sub_1"):
    # Shape of a subscription on API versions >= 2025-03-31: billing period on items.
    return stripe.StripeObject.construct_from({
        "id": sub_id,
        "object": "subscription",
        "customer": "cus_1",
        "status": "active",
        "created": 100,
        "cancel_at_period_end": False,
        "latest_invoice": "in_1",
        "items": {"object": "list", "data": [{
            "id": "si_1",
            "object": "subscription_item",
            "price": {"id": "price_pro", "object": "price"},
            "current_period_start": 1_700_000_000,
            "current_period_end": 1_702_592_000,
        }]},
    }, "sk_test_unused")


@pytest.fixture
def conn(monkeypatch):
    c = _Conn()
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_unused")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "5000")
    monkeypatch.setattr(billing.psycopg, "connect", lambda *a, **k: c)
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(stripe.Subscription, "retrieve", staticmethod(lambda sub_id: _subscription_object(sub_id)))
    return c


def _invoice_event(event_id="evt_inv_1", event_type="invoice.paid", invoice_id="in_1"):
    # API versions >= 2025-03-31 expose the subscription under parent.subscription_details.
    return {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "created": 200,
        "data": {"object": {
            "id": invoice_id,
            "object": "invoice",
            "parent": {"type": "subscription_details", "subscription_details": {"subscription": "sub_1"}},
        }},
    }


def test_real_signed_event_is_processed_not_500(conn):
    payload, sig = _signed(_invoice_event())
    client = TestClient(main.app)
    response = client.post("/api/stripe/webhook", content=payload, headers={"Stripe-Signature": sig})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["handled"] is True
    assert conn.plan == "pro"


def test_both_webhook_paths_accept_real_signed_events(conn):
    client = TestClient(main.app)
    for index, path in enumerate(["/api/stripe/webhook", "/api/webhooks/stripe"]):
        payload, sig = _signed(_invoice_event(event_id=f"evt_path_{index}", invoice_id=f"in_path_{index}"))
        response = client.post(path, content=payload, headers={"Stripe-Signature": sig})
        assert response.status_code == 200, (path, response.text)


def test_invalid_signature_returns_400_not_500(conn):
    payload, _ = _signed(_invoice_event())
    _, bad_sig = _signed(_invoice_event(), secret="whsec_wrong")
    client = TestClient(main.app)
    response = client.post("/api/stripe/webhook", content=payload, headers={"Stripe-Signature": bad_sig})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Stripe webhook signature"
    assert conn.events == set()


def test_malformed_payload_returns_400(conn):
    client = TestClient(main.app)
    response = client.post("/api/stripe/webhook", content=b"not json", headers={"Stripe-Signature": "t=1,v1=00"})
    assert response.status_code == 400


def test_duplicate_event_is_not_processed_twice(conn):
    payload, sig = _signed(_invoice_event())
    first = billing.process_webhook(payload, sig)
    second = billing.process_webhook(payload, sig)
    assert first["duplicate"] is False
    assert second == {"ok": True, "duplicate": True, "event_id": "evt_inv_1"}


def test_paid_invoice_grants_plan_credits_once_per_invoice(conn):
    paid, paid_sig = _signed(_invoice_event("evt_a", "invoice.paid", "in_1"))
    succeeded, succeeded_sig = _signed(_invoice_event("evt_b", "invoice.payment_succeeded", "in_1"))
    first = billing.process_webhook(paid, paid_sig)
    second = billing.process_webhook(succeeded, succeeded_sig)
    assert first["credit_grant"]["granted"] is True
    assert conn.balance == 5000
    assert second["credit_grant"] == {"granted": False, "reason": "already_granted"}
    assert conn.balance == 5000


def test_credit_grant_never_reduces_a_larger_balance(conn):
    conn.balance = 9000
    payload, sig = _signed(_invoice_event())
    result = billing.process_webhook(payload, sig)
    assert result["credit_grant"]["granted"] is True
    assert conn.balance == 9000


def test_failed_invoice_does_not_grant_credits(conn):
    payload, sig = _signed(_invoice_event("evt_f", "invoice.payment_failed", "in_f"))
    result = billing.process_webhook(payload, sig)
    assert "credit_grant" not in result
    assert conn.balance == 3


def test_unconfigured_quota_does_not_grant(conn, monkeypatch):
    monkeypatch.delenv("EC_PULSE_PRO_MONTHLY_CREDITS")
    payload, sig = _signed(_invoice_event())
    result = billing.process_webhook(payload, sig)
    assert result["credit_grant"]["reason"] == "quota_not_configured"
    assert conn.balance == 3


def test_legacy_invoice_subscription_field_is_still_supported():
    assert billing._invoice_subscription_id({"subscription": "sub_legacy"}) == "sub_legacy"
    assert billing._invoice_subscription_id({"parent": {"subscription_details": {"subscription": "sub_new"}}}) == "sub_new"
    assert billing._invoice_subscription_id({}) is None


def test_subscription_period_falls_back_to_items():
    start, end = billing._subscription_period(billing._as_dict(_subscription_object()))
    assert (start, end) == (1_700_000_000, 1_702_592_000)
    assert billing._subscription_period({"current_period_start": 1, "current_period_end": 2}) == (1, 2)
