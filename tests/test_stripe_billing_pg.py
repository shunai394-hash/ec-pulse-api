"""Stripe webhook processing against a real PostgreSQL database.

Events are signed and verified by the real stripe SDK and processed by the
production ``process_webhook``; only ``stripe.Subscription.retrieve`` (a
network call) is replaced.
"""
import hashlib
import hmac
import json
import threading
import time
import uuid

import psycopg
import pytest
import stripe

import app.services.billing as billing
from tests.conftest import TEST_DB, pg_exec, pg_query

SECRET = "whsec_pg_integration"


@pytest.fixture
def account(pg_store, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_unused")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("STRIPE_PRICE_BUSINESS", "price_business")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "5000")
    monkeypatch.setenv("EC_PULSE_BUSINESS_MONTHLY_CREDITS", "20000")
    key = pg_store.provision_customer_api_key(f"user-{uuid.uuid4()}")["api_key"]
    account_hash = hashlib.sha256(key.encode()).hexdigest()
    customer = f"cus_{uuid.uuid4().hex[:12]}"
    sub_id = f"sub_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(TEST_DB) as conn:
        billing._init_billing(conn)
    pg_exec("UPDATE api_accounts SET stripe_customer_id = %s WHERE api_key_hash = %s", (customer, account_hash))
    state = {"status": "active", "price": "price_pro", "fail": False}

    def retrieve(_id):
        if state["fail"]:
            raise stripe.APIConnectionError("network down")
        return stripe.StripeObject.construct_from({
            "id": sub_id, "customer": customer, "status": state["status"], "created": 10,
            "items": {"data": [{"price": {"id": state["price"]}, "current_period_start": 1, "current_period_end": 2}]},
        }, "sk_test_unused")

    monkeypatch.setattr(stripe.Subscription, "retrieve", staticmethod(retrieve))
    return {"key": key, "hash": account_hash, "customer": customer, "sub": sub_id, "state": state, "store": pg_store}


def send(event_id, event_type, obj, created=20):
    payload = json.dumps({"id": event_id, "object": "event", "type": event_type, "created": created,
                          "data": {"object": obj}}).encode()
    ts = str(int(time.time()))
    sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return billing.process_webhook(payload, f"t={ts},v1={sig}")


def invoice(account, invoice_id):
    return {"id": invoice_id, "object": "invoice",
            "parent": {"subscription_details": {"subscription": account["sub"]}}}


def acct(account):
    return pg_query("SELECT plan, credits_balance, subscription_status FROM api_accounts WHERE api_key_hash = %s",
                    (account["hash"],))[0]


def evt():
    return f"evt_{uuid.uuid4().hex[:16]}"


def test_concurrent_events_for_same_invoice_grant_credits_once(account):
    invoice_id = f"in_{uuid.uuid4().hex[:12]}"
    results, errors = [], []
    barrier = threading.Barrier(4)

    def worker(event_type):
        barrier.wait()
        try:
            results.append(send(evt(), event_type, invoice(account, invoice_id)))
        except Exception as exc:  # pragma: no cover - surfaced by the assertion below
            errors.append(exc)

    types = ["invoice.paid", "invoice.payment_succeeded", "invoice.paid", "invoice.payment_succeeded"]
    threads = [threading.Thread(target=worker, args=(t,)) for t in types]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    granted = [r["credit_grant"]["granted"] for r in results]
    assert granted.count(True) == 1
    assert pg_query("SELECT count(*) FROM credit_grants WHERE invoice_id = %s", (invoice_id,))[0][0] == 1
    assert acct(account) == ("pro", 5000, "active")


def test_concurrent_redelivery_of_same_event_is_processed_once(account):
    event_id = evt()
    invoice_id = f"in_{uuid.uuid4().hex[:12]}"
    results = []
    barrier = threading.Barrier(3)

    def worker():
        barrier.wait()
        results.append(send(event_id, "invoice.paid", invoice(account, invoice_id)))

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(r["duplicate"] for r in results) == [False, True, True]
    assert pg_query("SELECT count(*) FROM billing_events WHERE event_id = %s", (event_id,))[0][0] == 1


def test_stripe_failure_rolls_back_so_the_retry_is_processed(account):
    event_id = evt()
    invoice_id = f"in_{uuid.uuid4().hex[:12]}"
    account["state"]["fail"] = True
    with pytest.raises(RuntimeError, match="Unable to retrieve Stripe subscription"):
        send(event_id, "invoice.paid", invoice(account, invoice_id))
    assert pg_query("SELECT count(*) FROM billing_events WHERE event_id = %s", (event_id,))[0][0] == 0
    assert acct(account)[1] == 100

    account["state"]["fail"] = False
    result = send(event_id, "invoice.paid", invoice(account, invoice_id))
    assert result["duplicate"] is False and result["credit_grant"]["granted"] is True
    assert acct(account)[1] == 5000


def test_db_failure_after_grant_rolls_back_event_and_grant_together(account, monkeypatch):
    event_id = evt()
    invoice_id = f"in_{uuid.uuid4().hex[:12]}"
    real_grant = billing._grant_plan_credits

    def grant_then_crash(*args, **kwargs):
        real_grant(*args, **kwargs)
        raise psycopg.errors.SerializationFailure("simulated")

    monkeypatch.setattr(billing, "_grant_plan_credits", grant_then_crash)
    with pytest.raises(psycopg.errors.SerializationFailure):
        send(event_id, "invoice.paid", invoice(account, invoice_id))
    assert pg_query("SELECT count(*) FROM credit_grants WHERE invoice_id = %s", (invoice_id,))[0][0] == 0
    assert pg_query("SELECT count(*) FROM billing_events WHERE event_id = %s", (event_id,))[0][0] == 0
    assert acct(account) == ("free", 100, None)

    monkeypatch.setattr(billing, "_grant_plan_credits", real_grant)
    assert send(event_id, "invoice.paid", invoice(account, invoice_id))["credit_grant"]["granted"] is True
    assert acct(account) == ("pro", 5000, "active")


def test_failed_invoice_never_grants_and_marks_past_due(account):
    account["state"]["status"] = "past_due"
    result = send(evt(), "invoice.payment_failed", invoice(account, f"in_{uuid.uuid4().hex[:12]}"))
    assert "credit_grant" not in result
    assert acct(account) == ("pro", 100, "past_due")


def test_upgrade_downgrade_and_cancellation(account):
    sub = {"id": account["sub"], "object": "subscription"}
    send(evt(), "customer.subscription.created", sub, created=20)
    assert acct(account)[0] == "pro"

    account["state"]["price"] = "price_business"
    send(evt(), "customer.subscription.updated", sub, created=30)
    send(evt(), "invoice.paid", invoice(account, f"in_{uuid.uuid4().hex[:12]}"), created=31)
    assert acct(account) == ("business", 20000, "active")

    # Downgrade: plan follows Stripe, but a top-up never reduces the balance.
    account["state"]["price"] = "price_pro"
    send(evt(), "customer.subscription.updated", sub, created=40)
    send(evt(), "invoice.paid", invoice(account, f"in_{uuid.uuid4().hex[:12]}"), created=41)
    assert acct(account) == ("pro", 20000, "active")

    account["state"]["status"] = "canceled"
    send(evt(), "customer.subscription.deleted", sub, created=50)
    assert acct(account)[0] == "free" and acct(account)[2] == "canceled"


def test_stale_event_does_not_overwrite_newer_state(account):
    sub = {"id": account["sub"], "object": "subscription"}
    send(evt(), "customer.subscription.updated", sub, created=100)
    account["state"]["status"] = "canceled"
    result = send(evt(), "customer.subscription.updated", sub, created=99)
    assert result["handled"] is False
    assert acct(account)[2] == "active"


def test_expired_checkout_clears_its_pending_checkout(account):
    pending = str(uuid.uuid4())
    pg_exec("""UPDATE api_accounts SET checkout_pending_key = %s,
               checkout_pending_until = CURRENT_TIMESTAMP + INTERVAL '10 minutes',
               checkout_session_id = 'cs_old' WHERE api_key_hash = %s""", (pending, account["hash"]))

    other = send(evt(), "checkout.session.expired",
                 {"id": "cs_other", "metadata": {"api_key_hash": account["hash"], "checkout_pending_key": "someone-else"}})
    assert other["handled"] is False
    assert pg_query("SELECT checkout_pending_key FROM api_accounts WHERE api_key_hash = %s", (account["hash"],))[0][0] == pending

    result = send(evt(), "checkout.session.expired",
                  {"id": "cs_old", "metadata": {"api_key_hash": account["hash"], "checkout_pending_key": pending}})
    assert result["handled"] is True
    row = pg_query("""SELECT checkout_pending_key, checkout_pending_until, checkout_session_id
                      FROM api_accounts WHERE api_key_hash = %s""", (account["hash"],))[0]
    assert row == (None, None, None)


def test_schema_setup_does_not_take_table_locks_on_every_call(account):
    """A request holding a row lock on api_accounts (e.g. cancel_subscription
    while it waits on Stripe) must not block billing calls on DDL locks."""
    holder = psycopg.connect(TEST_DB)
    try:
        holder.execute("SELECT 1 FROM api_accounts WHERE api_key_hash = %s FOR UPDATE", (account["hash"],))
        with psycopg.connect(TEST_DB) as conn:
            conn.execute("SET lock_timeout = '1s'")
            billing._init_billing(conn)
    finally:
        holder.rollback()
        holder.close()


def test_concurrent_first_calls_run_schema_setup_once_and_failure_is_retried(account, monkeypatch):
    real_create = billing._create_billing_schema
    calls = []

    def counting_create(conn):
        calls.append(1)
        real_create(conn)

    monkeypatch.setattr(billing, "_BILLING_SCHEMA_READY", False)
    monkeypatch.setattr(billing, "_create_billing_schema", counting_create)
    errors = []
    barrier = threading.Barrier(4)

    def first_request():
        barrier.wait()
        try:
            with psycopg.connect(TEST_DB) as conn:
                billing._init_billing(conn)
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=first_request) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and len(calls) == 1

    # A failed setup (e.g. DB outage) must not mark the schema ready.
    def failing_create(conn):
        raise psycopg.OperationalError("connection lost")

    monkeypatch.setattr(billing, "_BILLING_SCHEMA_READY", False)
    monkeypatch.setattr(billing, "_create_billing_schema", failing_create)
    with pytest.raises(psycopg.OperationalError), psycopg.connect(TEST_DB) as conn:
        billing._init_billing(conn)
    assert billing._BILLING_SCHEMA_READY is False

    monkeypatch.setattr(billing, "_create_billing_schema", counting_create)
    with psycopg.connect(TEST_DB) as conn:
        billing._init_billing(conn)
    assert billing._BILLING_SCHEMA_READY is True and len(calls) == 2
