import pytest

from app.services import monitor_store


class Cursor:
    def __init__(self, row=None, rowcount=1):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row


class Conn:
    def __init__(self, row):
        self.row = row
        self.statements = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.statements.append((normalized, params))
        if normalized.startswith("SELECT a.api_key_hash, a.credits_balance"):
            return Cursor(self.row)
        return Cursor()

    def commit(self):
        self.commits += 1


def _setup(monkeypatch, row):
    conn = Conn(row)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_args, **_kwargs: conn)
    monkeypatch.setattr(monitor_store, "_init", lambda _conn: None)
    return conn


def test_consume_credit_locks_account_and_records_usage(monkeypatch):
    conn = _setup(monkeypatch, ("account-hash", 5))

    result = monitor_store.consume_credit(
        "ecp_live_test-key",
        "GET /v1/products",
        credits=2,
    )

    assert result == {"credits_used": 2, "credits_remaining": 3}
    assert conn.commits == 1
    select_sql = conn.statements[0][0]
    assert "FOR UPDATE OF k, a" in select_sql
    updates = [sql for sql, _ in conn.statements if sql.startswith("UPDATE api_accounts SET credits_balance")]
    usage = [sql for sql, _ in conn.statements if sql.startswith("INSERT INTO api_usage")]
    assert len(updates) == 1
    assert len(usage) == 1


def test_consume_credit_rejects_insufficient_balance_without_writes(monkeypatch):
    conn = _setup(monkeypatch, ("account-hash", 1))

    with pytest.raises(RuntimeError, match="Insufficient API credits"):
        monitor_store.consume_credit(
            "ecp_live_test-key",
            "GET /v1/products",
            credits=2,
        )

    assert conn.commits == 0
    assert not any(sql.startswith("UPDATE api_accounts SET credits_balance") for sql, _ in conn.statements)
    assert not any(sql.startswith("INSERT INTO api_usage") for sql, _ in conn.statements)


def test_consume_credit_rejects_invalid_or_revoked_key_without_writes(monkeypatch):
    conn = _setup(monkeypatch, None)

    with pytest.raises(RuntimeError, match="Invalid or revoked API key"):
        monitor_store.consume_credit(
            "ecp_live_revoked-key",
            "GET /v1/products",
            credits=1,
        )

    assert conn.commits == 0
    assert not any(sql.startswith("UPDATE api_accounts SET credits_balance") for sql, _ in conn.statements)
    assert not any(sql.startswith("INSERT INTO api_usage") for sql, _ in conn.statements)


def test_consume_credit_rejects_zero_or_negative_charge_before_database_access(monkeypatch):
    called = False

    def fail_connect(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("database must not be touched")

    monkeypatch.setattr(monitor_store.psycopg, "connect", fail_connect)

    for credits in (0, -1):
        with pytest.raises(ValueError, match="credits must be positive"):
            monitor_store.consume_credit(
                "ecp_live_test-key",
                "GET /v1/products",
                credits=credits,
            )

    assert called is False
