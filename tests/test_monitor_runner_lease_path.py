import asyncio

from app.services import monitor_store


class Cursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class Conn:
    def __init__(self, *, due_rows=None, lease_row=None, owned_row=None):
        self.due_rows = due_rows or []
        self.lease_row = lease_row
        self.owned_row = owned_row
        self.sql = []
        self.commits = 0
        self.deleted = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.sql.append((normalized, params))
        if normalized.startswith("SELECT id, url, interval_minutes, webhook_url"):
            return Cursor(rows=self.due_rows)
        if normalized.startswith("INSERT INTO monitor_run_leases"):
            return Cursor(row=self.lease_row)
        if normalized.startswith("UPDATE monitor_run_leases"):
            return Cursor(row=self.owned_row)
        if normalized.startswith("DELETE FROM monitor_run_leases"):
            self.deleted += 1
            return Cursor()
        return Cursor()

    def commit(self):
        self.commits += 1


def test_run_due_monitors_uses_real_lease_path_and_processes_one_monitor(monkeypatch):
    conn = Conn(
        due_rows=[("monitor-1", "https://example.com/product", 15, "https://example.com/hook", None, None)],
        lease_row=("lease-1",),
        owned_row=("lease-1",),
    )
    calls = {"fetch": 0, "validate": 0}

    async def fake_validate(url):
        calls["validate"] += 1

    async def fake_fetch(url):
        calls["fetch"] += 1
        return {
            "pricing": {"price": 123.0, "currency": "JPY"},
            "source": {"url": url, "site": "example.com"},
            "captured_at": "2026-10-03T00:00:00+00:00",
        }

    async def fake_deliver():
        return 0

    monkeypatch.setattr(monitor_store, "_init", lambda _conn: None)
    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_a, **_k: conn)
    monkeypatch.setattr(monitor_store, "validate_public_url", fake_validate)
    monkeypatch.setattr("app.services.product_parser.fetch_product", fake_fetch)
    monkeypatch.setattr(monitor_store, "_deliver_pending_webhooks", fake_deliver)

    result = asyncio.run(monitor_store.run_due_monitors())

    assert result == {"checked": 1, "changed": 0, "failed": 0, "webhooks_delivered": 0}
    assert calls == {"fetch": 1, "validate": 1}
    assert conn.commits >= 2
    assert conn.deleted == 1
    assert any("RETURNING lease_token" in sql for sql, _ in conn.sql)
    assert any("WHERE monitor_id = %s AND lease_token = %s" in sql for sql, _ in conn.sql)


def test_run_due_monitors_skips_product_fetch_when_active_lease_wins(monkeypatch):
    conn = Conn(
        due_rows=[("monitor-1", "https://example.com/product", 15, "https://example.com/hook", None, None)],
        lease_row=None,
    )
    calls = {"fetch": 0}

    async def fake_fetch(url):
        calls["fetch"] += 1
        raise AssertionError("product fetch must not run when the lease is not acquired")

    async def fake_deliver():
        return 0

    monkeypatch.setattr(monitor_store, "_init", lambda _conn: None)
    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_a, **_k: conn)
    monkeypatch.setattr(monitor_store, "validate_public_url", lambda _url: asyncio.sleep(0))
    monkeypatch.setattr("app.services.product_parser.fetch_product", fake_fetch)
    monkeypatch.setattr(monitor_store, "_deliver_pending_webhooks", fake_deliver)

    result = asyncio.run(monitor_store.run_due_monitors())

    assert result == {"checked": 0, "changed": 0, "failed": 0, "webhooks_delivered": 0}
    assert calls["fetch"] == 0
    assert conn.deleted == 1


def test_run_due_monitors_skips_write_when_lease_is_lost_after_fetch(monkeypatch):
    conn = Conn(
        due_rows=[("monitor-1", "https://example.com/product", 15, "https://example.com/hook", None, None)],
        lease_row=("lease-1",),
        owned_row=None,
    )
    calls = {"fetch": 0}

    async def fake_fetch(url):
        calls["fetch"] += 1
        return {
            "pricing": {"price": 123.0, "currency": "JPY"},
            "source": {"url": url},
            "captured_at": "2026-10-03T00:00:00+00:00",
        }

    async def fake_deliver():
        return 0

    monkeypatch.setattr(monitor_store, "_init", lambda _conn: None)
    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_a, **_k: conn)
    monkeypatch.setattr(monitor_store, "validate_public_url", lambda _url: asyncio.sleep(0))
    monkeypatch.setattr("app.services.product_parser.fetch_product", fake_fetch)
    monkeypatch.setattr(monitor_store, "_deliver_pending_webhooks", fake_deliver)

    result = asyncio.run(monitor_store.run_due_monitors())

    assert result == {"checked": 0, "changed": 0, "failed": 0, "webhooks_delivered": 0}
    assert calls["fetch"] == 1
    assert not any("INSERT INTO price_history" in sql for sql, _ in conn.sql)
    assert not any("UPDATE monitors SET last_price" in sql for sql, _ in conn.sql)
    assert conn.deleted == 1
