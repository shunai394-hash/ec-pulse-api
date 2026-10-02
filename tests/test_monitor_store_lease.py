from app.services import monitor_store


class Cursor:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class Conn:
    def __init__(self, lease_row):
        self.lease_row = lease_row
        self.sql = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.sql.append(normalized)
        if normalized.startswith("INSERT INTO monitor_run_leases"):
            return Cursor(self.lease_row)
        return Cursor()

    def commit(self):
        self.committed = True


def test_monitor_run_lease_skips_active_existing_lease(monkeypatch):
    conn = Conn(None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_args, **_kwargs: conn)

    lease_token = "new-token"
    row = conn.execute(
        """
        INSERT INTO monitor_run_leases (monitor_id, lease_token, locked_until)
        VALUES (%s, %s, CURRENT_TIMESTAMP + INTERVAL '10 minutes')
        ON CONFLICT (monitor_id) DO UPDATE
        SET lease_token = EXCLUDED.lease_token,
            locked_until = EXCLUDED.locked_until
        WHERE monitor_run_leases.locked_until <= CURRENT_TIMESTAMP
        RETURNING lease_token
        """,
        ("monitor-1", lease_token),
    ).fetchone()

    assert row is None
    assert conn.committed is False
    sql = conn.sql[0]
    assert "ON CONFLICT (monitor_id) DO UPDATE" in sql
    assert "WHERE monitor_run_leases.locked_until <= CURRENT_TIMESTAMP" in sql
    assert "RETURNING lease_token" in sql


def test_monitor_run_lease_claims_when_existing_lease_is_expired(monkeypatch):
    conn = Conn(("new-token",))
    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    monkeypatch.setattr(monitor_store.psycopg, "connect", lambda *_args, **_kwargs: conn)

    row = conn.execute(
        """
        INSERT INTO monitor_run_leases (monitor_id, lease_token, locked_until)
        VALUES (%s, %s, CURRENT_TIMESTAMP + INTERVAL '10 minutes')
        ON CONFLICT (monitor_id) DO UPDATE
        SET lease_token = EXCLUDED.lease_token,
            locked_until = EXCLUDED.locked_until
        WHERE monitor_run_leases.locked_until <= CURRENT_TIMESTAMP
        RETURNING lease_token
        """,
        ("monitor-1", "new-token"),
    ).fetchone()

    assert row == ("new-token",)
    assert conn.committed is False
    assert "locked_until <= CURRENT_TIMESTAMP" in conn.sql[0]
