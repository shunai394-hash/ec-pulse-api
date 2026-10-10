from datetime import datetime, timezone, timedelta

from app.services.billing import _apply_subscription


class FakeCursor:
    def __init__(self, rows):
        self.rows = iter(rows)

    def fetchone(self):
        return next(self.rows)


class FakeConn:
    def __init__(self, state=(None, None, None, None, None)):
        self.updates = 0
        self.last_params = None
        self.state = state
        self.state_sql = None

    def execute(self, sql, params=()):
        if "SELECT api_key_hash" in sql:
            return FakeCursor([("account-hash",)])
        if "SELECT stripe_subscription_id, subscription_status" in sql:
            self.state_sql = sql
            return FakeCursor([self.state])
        self.updates += 1
        self.last_params = params
        return FakeCursor([])


def _subscription(status="active", event_id="evt_123"):
    return {
        "id": "sub_123",
        "customer": "cus_123",
        "status": status,
        "items": {"data": [{"price": {"id": "price_pro"}}]},
        "_ec_pulse_event_id": event_id,
    }


def test_active_subscription_applies_plan(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn()
    assert _apply_subscription(conn, _subscription("active"), 100) is True
    assert conn.updates == 1
    assert conn.last_params[-3] == "evt_123"


def test_past_due_subscription_keeps_plan_during_retry(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn()
    assert _apply_subscription(conn, _subscription("past_due"), 100) is True
    assert conn.updates == 1
    assert conn.last_params[0] == "pro"


def test_canceled_subscription_clears_cancel_at_period_end(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn()
    assert _apply_subscription(conn, _subscription("canceled"), 100) is True
    assert conn.updates == 1
    assert conn.last_params[5] is False


def test_canceled_subscription_downgrades_to_free(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn()
    assert _apply_subscription(conn, _subscription("canceled"), 100) is True
    assert conn.updates == 1
    assert conn.last_params[0] == "free"


def test_event_id_does_not_act_as_fake_ordering(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn()
    subscription = _subscription("active")
    subscription["_ec_pulse_event_id"] = "evt_001"
    assert _apply_subscription(conn, subscription, 200) is True
    subscription["_ec_pulse_event_id"] = "evt_999"
    assert _apply_subscription(conn, subscription, 100) is True
    assert conn.updates == 2


def test_older_event_created_is_ignored(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn(("sub_123", "active", 200, "evt_002", 150))
    assert _apply_subscription(conn, _subscription("active"), 100) is False
    assert conn.updates == 0


def test_same_timestamp_does_not_compare_ids(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn(("sub_123", "active", 100, "evt_002", 50))
    assert _apply_subscription(conn, _subscription("active", "evt_001"), 100) is True
    assert conn.updates == 1


def test_subscription_state_row_is_locked_during_update(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn()
    assert _apply_subscription(conn, _subscription("active"), 100) is True
    assert "FOR UPDATE" in conn.state_sql


def test_subscription_state_row_is_locked_during_cancellation(monkeypatch):
    import app.services.billing as billing

    class Cursor:
        def fetchone(self):
            return ("cus_123", "sub_123", "active", None, False)

    class Conn:
        def __init__(self):
            self.sql = None
        def execute(self, sql, params=()):
            if "FOR UPDATE" in sql:
                self.select_sql = sql
            self.sql = sql
            return Cursor()
        def rollback(self):
            pass
        def commit(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    class FakeSubscription:
        @staticmethod
        def modify(subscription_id, **kwargs):
            assert subscription_id == "sub_123"
            assert kwargs["cancel_at_period_end"] is True
            assert kwargs["idempotency_key"]
            return {"id": "sub_123", "status": "active", "cancel_at_period_end": True}

    class FakeStripe:
        Subscription = FakeSubscription

    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: Conn())
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr("app.services.monitor_store._account_hash", lambda key: "account-hash")

    result = billing.cancel_subscription("secret")
    assert result["cancel_at_period_end"] is True


def test_canceled_subscription_cannot_be_canceled_again(monkeypatch):
    import app.services.billing as billing

    class Cursor:
        def fetchone(self):
            return ("cus_123", "sub_123", "canceled", None, False)

    class Conn:
        def execute(self, sql, params=()):
            return Cursor()
        def commit(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: Conn())
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(billing, "_account_hash", lambda key: "account-hash")
    try:
        billing.cancel_subscription("secret")
    except ValueError as exc:
        assert "No active Stripe subscription" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_checkout_rejects_existing_active_subscription(monkeypatch):
    import app.services.billing as billing

    class Cursor:
        def fetchone(self):
            return ("account-hash", "cus_123", "sub_123", "active", None, None, None)

    class Conn:
        def execute(self, sql, params=()):
            assert "FOR UPDATE" in sql
            return Cursor()
        def commit(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: Conn())
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr("app.services.monitor_store._account_hash", lambda key: "account-hash")

    try:
        billing.create_checkout("secret", "pro")
    except ValueError as exc:
        assert "active Stripe subscription" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_checkout_sets_pending_before_stripe_call(monkeypatch):
    import app.services.billing as billing

    class Cursor:
        def fetchone(self):
            return ("account-hash", None, None, None, None, None, None)

    class Conn:
        def __init__(self):
            self.committed = False
            self.closed = False
            self.sql = None
        def execute(self, sql, params=()):
            self.sql = sql
            return Cursor()
        def commit(self):
            self.committed = True
        def rollback(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.closed = True

    conn = Conn()
    class Checkout:
        @staticmethod
        def create(**kwargs):
            assert conn.committed is True
            return type("Session", (), {"id": "cs_test", "url": "https://checkout.example/session"})()

    class FakeStripe:
        checkout = type("CheckoutContainer", (), {"Session": Checkout})

    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: conn)
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr("app.services.monitor_store._account_hash", lambda key: "account-hash")

    result = billing.create_checkout("secret", "pro")
    assert result == "https://checkout.example/session"
    assert conn.committed is True
    assert "checkout_pending_key" in conn.sql


def test_checkout_uses_owning_account_hash_in_metadata(monkeypatch):
    import app.services.billing as billing

    class Cursor:
        def fetchone(self):
            return ("account-hash", None, None, None, None, None, None)

    class Conn:
        def execute(self, sql, params=()):
            return Cursor()
        def commit(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    class Checkout:
        @staticmethod
        def create(**kwargs):
            assert kwargs["metadata"]["api_key_hash"] == "account-hash"
            assert kwargs["metadata"]["checkout_pending_key"]

            return type("Session", (), {"id": "cs_test", "url": "https://checkout.example/session"})()

    class FakeStripe:
        checkout = type("CheckoutContainer", (), {"Session": Checkout})

    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: Conn())
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr(billing, "_account_hash", lambda key: "key-hash")

    assert billing.create_checkout("shared-key", "pro") == "https://checkout.example/session"


def test_checkout_rejects_existing_pending_checkout(monkeypatch):
    import app.services.billing as billing
    from datetime import datetime, timezone, timedelta

    class Cursor:
        def fetchone(self):
            return ("account-hash", "cus_123", None, None, "pending-key", datetime.now(timezone.utc) + timedelta(minutes=5), "cs_old")

    class Conn:
        def execute(self, sql, params=()):
            return Cursor()
        def commit(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: Conn())
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(billing, "_account_hash", lambda key: "account-hash")
    try:
        billing.create_checkout("secret", "pro")
    except ValueError as exc:
        assert "checkout is already in progress" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_stale_checkout_completion_cannot_clear_new_pending_checkout(monkeypatch):
    import app.services.billing as billing

    class Event:
        def to_dict(self):
            return {
                "id": "evt_checkout_old",
                "type": "checkout.session.completed",
                "created": 200,
                "data": {"object": {
                    "customer": "cus_old",
                    "subscription": "sub_old",
                    "metadata": {"api_key_hash": "account-hash", "checkout_pending_key": "old-key"},
                }},
            }

    class Webhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            return Event()

    FakeStripe = type("FakeStripe", (), {"Webhook": Webhook})

    class Cursor:
        def __init__(self, row): self.row = row
        def fetchone(self): return self.row

    class Conn:
        def __init__(self): self.updates = 0
        def execute(self, sql, params=()):
            if "INSERT INTO billing_events" in sql:
                return Cursor(("evt_checkout_old",))
            if "SELECT checkout_pending_key" in sql:
                return Cursor(("new-key", datetime.now(timezone.utc) + timedelta(minutes=5), "cus_new"))
            self.updates += 1
            return Cursor(None)
        def commit(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

    conn = Conn()
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: conn)
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")

    result = billing.process_webhook(b"payload", "sig")
    assert result["handled"] is False
    assert conn.updates == 0



def test_stale_checkout_completion_cannot_claim_account_while_new_checkout_is_pending(monkeypatch):
    import app.services.billing as billing
    from datetime import datetime, timezone, timedelta

    class Event:
        def to_dict(self):
            return {
                "id": "evt_checkout_stale_first_customer",
                "type": "checkout.session.completed",
                "created": 200,
                "data": {"object": {
                    "customer": "cus_old",
                    "subscription": "sub_old",
                    "metadata": {"api_key_hash": "account-hash", "checkout_pending_key": "old-key"},
                }},
            }

    class Webhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            return Event()

    FakeStripe = type("FakeStripe", (), {"Webhook": Webhook})

    class Cursor:
        def __init__(self, row): self.row = row
        def fetchone(self): return self.row

    class Conn:
        def __init__(self):
            self.updates = []
        def execute(self, sql, params=()):
            if "INSERT INTO billing_events" in sql:
                return Cursor(("evt_checkout_stale_first_customer",))
            if "SELECT checkout_pending_key" in sql:
                return Cursor(("new-key", datetime.now(timezone.utc) + timedelta(minutes=5), None))
            self.updates.append((sql, params))
            return Cursor(None)
        def commit(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

    conn = Conn()
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: conn)
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")

    result = billing.process_webhook(b"payload", "sig")
    assert result["handled"] is False
    assert conn.updates == []

def test_expired_checkout_completion_still_links_customer_and_subscription(monkeypatch):
    import app.services.billing as billing

    class Event:
        def to_dict(self):
            return {
                "id": "evt_checkout_expired",
                "type": "checkout.session.completed",
                "created": 400,
                "data": {"object": {
                    "customer": "cus_old",
                    "subscription": "sub_old",
                    "metadata": {"api_key_hash": "account-hash", "checkout_pending_key": "expired-key"},
                }},
            }

    class Webhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            return Event()

    class Subscription:
        @staticmethod
        def retrieve(subscription_id):
            return type("SubscriptionObject", (), {
                "to_dict": lambda self: {
                    "id": subscription_id,
                    "customer": "cus_old",
                    "created": 390,
                    "status": "active",
                    "items": {"data": [{"price": {"id": "price_pro"}}]},
                }
            })()

    FakeStripe = type("FakeStripe", (), {"Webhook": Webhook, "Subscription": Subscription})

    class Cursor:
        def __init__(self, row): self.row = row
        def fetchone(self): return self.row

    class Conn:
        def __init__(self): self.updates = []
        def execute(self, sql, params=()):
            if "INSERT INTO billing_events" in sql:
                return Cursor(("evt_checkout_expired",))
            if "SELECT checkout_pending_key" in sql:
                return Cursor(("newer-key", datetime.now(timezone.utc) - timedelta(minutes=1), None))
            if "SELECT api_key_hash" in sql:
                return Cursor(("account-hash",))
            if "SELECT stripe_subscription_id, subscription_status" in sql:
                return Cursor((None, None, None, None, None))
            self.updates.append((sql, params))
            return Cursor(None)
        def commit(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

    conn = Conn()
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: conn)
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")

    result = billing.process_webhook(b"payload", "sig")
    assert result["handled"] is True
    assert any("stripe_customer_id=%s, updated_at=%s WHERE api_key_hash=%s AND (stripe_customer_id IS NULL OR stripe_customer_id=%s)" in sql for sql, _ in conn.updates)
    assert not any("checkout_pending_key=NULL" in sql for sql, _ in conn.updates)


def test_invoice_payment_failed_reconciles_latest_subscription(monkeypatch):
    import app.services.billing as billing
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")

    class Event:
        def to_dict(self):
            return {
                "id": "evt_invoice_failed",
                "type": "invoice.payment_failed",
                "created": 600,
                "data": {"object": {"subscription": "sub_123"}},
            }

    class Webhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            return Event()

    class Subscription:
        @staticmethod
        def retrieve(subscription_id):
            assert subscription_id == "sub_123"
            return type("SubscriptionObject", (), {
                "to_dict": lambda self: {
                    "id": "sub_123",
                    "customer": "cus_123",
                    "created": 500,
                    "status": "past_due",
                    "items": {"data": [{"price": {"id": "price_pro"}}]},
                }
            })()

    class Cursor:
        def __init__(self, row): self.row = row
        def fetchone(self): return self.row

    class Conn:
        def __init__(self): self.updates = 0
        def execute(self, sql, params=()):
            if "INSERT INTO billing_events" in sql:
                return Cursor(("evt_invoice_failed",))
            if "SELECT api_key_hash" in sql:
                return Cursor(("account-hash",))
            if "SELECT stripe_subscription_id, subscription_status" in sql:
                return Cursor(("sub_123", "active", 500, "evt_old", 500))
            self.updates += 1
            return Cursor(None)
        def commit(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

    FakeStripe = type("FakeStripe", (), {"Webhook": Webhook, "Subscription": Subscription})
    conn = Conn()
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: conn)
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")

    result = billing.process_webhook(b"payload", "sig")
    assert result["handled"] is True
    assert conn.updates == 1


def test_invoice_paid_reconciles_latest_subscription(monkeypatch):
    import app.services.billing as billing
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")

    class Event:
        def to_dict(self):
            return {
                "id": "evt_invoice_paid",
                "type": "invoice.paid",
                "created": 700,
                "data": {"object": {"subscription": "sub_123"}},
            }

    class Webhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            return Event()

    class Subscription:
        @staticmethod
        def retrieve(subscription_id):
            return type("SubscriptionObject", (), {
                "to_dict": lambda self: {
                    "id": subscription_id,
                    "customer": "cus_123",
                    "created": 500,
                    "status": "active",
                    "items": {"data": [{"price": {"id": "price_pro"}}]},
                }
            })()

    class Cursor:
        def __init__(self, row): self.row = row
        def fetchone(self): return self.row

    class Conn:
        def __init__(self): self.updates = 0
        def execute(self, sql, params=()):
            if "INSERT INTO billing_events" in sql:
                return Cursor(("evt_invoice_paid",))
            if "SELECT api_key_hash" in sql:
                return Cursor(("account-hash",))
            if "SELECT stripe_subscription_id, subscription_status" in sql:
                return Cursor(("sub_123", "past_due", 600, "evt_failed", 500))
            self.updates += 1
            return Cursor(None)
        def commit(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

    FakeStripe = type("FakeStripe", (), {"Webhook": Webhook, "Subscription": Subscription})
    conn = Conn()
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: conn)
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")

    result = billing.process_webhook(b"payload", "sig")
    assert result["handled"] is True
    assert conn.updates == 1


def test_stale_terminal_event_from_old_subscription_cannot_replace_new_active_subscription(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn(("sub_new", "active", 300, "evt_new", 300))
    old_subscription = _subscription("canceled", "evt_old")
    old_subscription["id"] = "sub_old"
    assert _apply_subscription(conn, old_subscription, 301) is False
    assert conn.updates == 0


def test_equal_timestamp_old_subscription_cannot_replace_new_active_subscription(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn(("sub_new", "active", 300, "evt_new", 300))
    old_subscription = _subscription("canceled", "evt_old")
    old_subscription["id"] = "sub_old"
    assert _apply_subscription(conn, old_subscription, 300) is False
    assert conn.updates == 0



def test_older_subscription_cannot_replace_newer_active_subscription_even_with_later_event_timestamp(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn(("sub_new", "active", 300, "evt_new", 500))
    old_subscription = _subscription("active", "evt_old")
    old_subscription["id"] = "sub_old"
    old_subscription["created"] = 400
    assert _apply_subscription(conn, old_subscription, 400) is False
    assert conn.updates == 0


def test_new_subscription_can_replace_terminal_previous_subscription_even_if_its_event_is_older(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn(("sub_old", "canceled", 500, "evt_old_terminal", 200))
    new_subscription = _subscription("active", "evt_new")
    new_subscription["id"] = "sub_new"
    new_subscription["created"] = 300
    assert _apply_subscription(conn, new_subscription, 300) is True
    assert conn.updates == 1


def test_new_subscription_can_replace_terminal_previous_subscription(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn(("sub_old", "canceled", 300, "evt_old", 200))
    new_subscription = _subscription("active", "evt_new")
    new_subscription["id"] = "sub_new"
    assert _apply_subscription(conn, new_subscription, 300) is True
    assert conn.updates == 1


def test_expired_checkout_is_expired_in_stripe_before_new_checkout(monkeypatch):
    import app.services.billing as billing
    from datetime import datetime, timezone, timedelta

    class Cursor:
        def fetchone(self):
            return ("account-hash", None, None, None, "old-key",
                    datetime.now(timezone.utc) - timedelta(minutes=1), "cs_old")

    class Conn:
        def __init__(self):
            self.sql = []
        def execute(self, sql, params=()):
            self.sql.append((sql, params))
            return Cursor()
        def commit(self): pass
        def rollback(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

    conn = Conn()

    class Session:
        def __init__(self, status="open"):
            self.status = status
            self.id = "cs_new"
            self.url = "https://checkout.example/new"
        def get(self, key, default=None):
            return getattr(self, key, default)

    class Sessions:
        @staticmethod
        def retrieve(session_id):
            assert session_id == "cs_old"
            return Session("open")
        @staticmethod
        def expire(session_id):
            assert session_id == "cs_old"
            return Session("expired")
        @staticmethod
        def create(**kwargs):
            return Session("open")

    class FakeStripe:
        checkout = type("CheckoutContainer", (), {"Session": Sessions})

    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: conn)
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr("app.services.monitor_store._account_hash", lambda key: "account-hash")

    assert billing.create_checkout("secret", "pro") == "https://checkout.example/new"
    assert any("checkout_session_id" in sql for sql, _ in conn.sql)


def test_expired_pending_completed_checkout_waits_for_webhook(monkeypatch):
    import app.services.billing as billing
    from datetime import datetime, timezone, timedelta

    class Cursor:
        def fetchone(self):
            return ("account-hash", None, None, None, "old-key",
                    datetime.now(timezone.utc) - timedelta(minutes=1), "cs_old")

    class Conn:
        def execute(self, sql, params=()):
            return Cursor()
        def commit(self): pass
        def rollback(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

    class Session:
        status = "complete"
        def get(self, key, default=None): return getattr(self, key, default)

    class Sessions:
        @staticmethod
        def retrieve(session_id):
            return Session()

    class FakeStripe:
        checkout = type("CheckoutContainer", (), {"Session": Sessions})

    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: Conn())
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr("app.services.monitor_store._account_hash", lambda key: "account-hash")

    try:
        billing.create_checkout("secret", "pro")
    except RuntimeError as exc:
        assert "waiting for webhook" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_checkout_reuses_linked_stripe_customer(monkeypatch):
    import app.services.billing as billing

    class Cursor:
        def fetchone(self):
            return ("account-hash", "cus_existing", None, None, None, None, None)

    class Conn:
        def execute(self, sql, params=()):
            return Cursor()
        def commit(self):
            pass
        def rollback(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    class Session:
        id = "cs_customer"
        url = "https://checkout.example/customer"

    class Checkout:
        @staticmethod
        def create(**kwargs):
            assert kwargs["customer"] == "cus_existing"
            assert kwargs["line_items"][0]["price"] == "price_pro"
            assert kwargs["mode"] == "subscription"
            return Session()

    FakeStripe = type("FakeStripe", (), {
        "checkout": type("CheckoutContainer", (), {"Session": Checkout})
    })

    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")
    monkeypatch.setattr(billing.psycopg, "connect", lambda *args, **kwargs: Conn())
    monkeypatch.setattr(billing, "_init_billing", lambda conn: None)
    monkeypatch.setattr(billing, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(billing, "_stripe", lambda: FakeStripe())
    monkeypatch.setattr("app.services.monitor_store._account_hash", lambda key: "account-hash")

    assert billing.create_checkout("customer-key", "pro") == "https://checkout.example/customer"


def test_unknown_active_stripe_price_does_not_downgrade_to_free(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("EC_PULSE_PRO_MONTHLY_CREDITS", "1000")
    conn = FakeConn()
    subscription = _subscription("active")
    subscription["items"]["data"][0]["price"]["id"] = "price_unconfigured"
    try:
        _apply_subscription(conn, subscription, 100)
    except RuntimeError as exc:
        assert "unrecognized price" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
    assert conn.updates == 0
