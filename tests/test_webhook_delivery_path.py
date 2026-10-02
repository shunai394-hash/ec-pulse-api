import asyncio
from contextlib import asynccontextmanager

from app.services import monitor_store


class Cursor:
    def __init__(self, row=None, rowcount=1):
        self.row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self.row


class Conn:
    def __init__(self, claim_row, lease_owned=True, update_rowcount=1):
        self.claim_row = claim_row
        self.lease_owned = lease_owned
        self.update_rowcount = update_rowcount
        self.sql = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.sql.append((normalized, params))
        if normalized.startswith("SELECT d.event_id"):
            return Cursor(self.claim_row)
        if normalized.startswith("SELECT 1") and "webhook_deliveries" in normalized:
            return Cursor((1,) if self.lease_owned else None)
        if normalized.startswith("UPDATE webhook_deliveries") and "status='delivered'" in normalized:
            return Cursor(rowcount=self.update_rowcount)
        return Cursor()

    def commit(self):
        self.commits += 1


class Response:
    def raise_for_status(self):
        return None


class StreamContext:
    async def __aenter__(self):
        return Response()

    async def __aexit__(self, *args):
        return False


class Client:
    def __init__(self, calls):
        self.calls = calls

    def stream(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return StreamContext()


@asynccontextmanager
async def fake_client(*args, **kwargs):
    yield Client(fake_client.calls)


fake_client.calls = []


def test_webhook_delivery_posts_only_after_real_lease_check(monkeypatch):
    conn = Conn(
        ("evt-1", "monitor-1", '{"event":"price_changed"}', "https://example.com/hook", 0),
        lease_owned=True,
        update_rowcount=1,
    )
    fake_client.calls.clear()

    async def fake_validate(url):
        return None

    async def fake_read_response_bytes(response, limit):
        return b"{}"

    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_a, **_k: conn)
    monkeypatch.setattr(monitor_store, "_init", lambda _conn: None)
    monkeypatch.setattr(monitor_store, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(monitor_store, "safe_async_client", fake_client)
    monkeypatch.setattr(monitor_store, "validate_public_url", fake_validate)
    monkeypatch.setattr(monitor_store, "read_response_bytes", fake_read_response_bytes)

    result = asyncio.run(monitor_store._deliver_pending_webhooks())

    assert result == 1
    assert len(fake_client.calls) == 1
    method, url, kwargs = fake_client.calls[0]
    assert method == "POST"
    assert url == "https://example.com/hook"
    assert kwargs["headers"]["X-EC-Pulse-Event-ID"] == "evt-1"
    assert any("FOR UPDATE" in sql and "lease_token = %s" in sql for sql, _ in conn.sql)
    assert any("status='delivered'" in sql and "WHERE event_id=%s AND lease_token=%s" in sql for sql, _ in conn.sql)


def test_webhook_delivery_does_not_post_when_lease_is_lost(monkeypatch):
    conn = Conn(
        ("evt-1", "monitor-1", '{"event":"price_changed"}', "https://example.com/hook", 0),
        lease_owned=False,
    )
    fake_client.calls.clear()

    async def fake_validate(url):
        return None

    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_a, **_k: conn)
    monkeypatch.setattr(monitor_store, "_init", lambda _conn: None)
    monkeypatch.setattr(monitor_store, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(monitor_store, "safe_async_client", fake_client)
    monkeypatch.setattr(monitor_store, "validate_public_url", fake_validate)

    result = asyncio.run(monitor_store._deliver_pending_webhooks())

    assert result == 0
    assert fake_client.calls == []
    assert not any("status='delivered'" in sql for sql, _ in conn.sql)


def test_webhook_delivery_does_not_count_stale_completion(monkeypatch):
    conn = Conn(
        ("evt-1", "monitor-1", '{"event":"price_changed"}', "https://example.com/hook", 0),
        lease_owned=True,
        update_rowcount=0,
    )
    fake_client.calls.clear()

    async def fake_validate(url):
        return None

    async def fake_read_response_bytes(response, limit):
        return b"{}"

    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_a, **_k: conn)
    monkeypatch.setattr(monitor_store, "_init", lambda _conn: None)
    monkeypatch.setattr(monitor_store, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(monitor_store, "safe_async_client", fake_client)
    monkeypatch.setattr(monitor_store, "validate_public_url", fake_validate)
    monkeypatch.setattr(monitor_store, "read_response_bytes", fake_read_response_bytes)

    result = asyncio.run(monitor_store._deliver_pending_webhooks())

    assert result == 0
    assert len(fake_client.calls) == 1
