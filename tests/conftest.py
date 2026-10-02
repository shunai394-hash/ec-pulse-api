"""Shared fixtures for tests that run against a real PostgreSQL database.

Tests using ``pg_store`` are skipped unless EC_PULSE_TEST_DATABASE_URL points at
a disposable database (CI provides one). Never point it at production: the
fixture truncates the monitor/webhook tables.
"""
import os

import psycopg
import pytest

TEST_DB = os.getenv("EC_PULSE_TEST_DATABASE_URL")


@pytest.fixture
def pg_store(monkeypatch):
    if not TEST_DB:
        pytest.skip("EC_PULSE_TEST_DATABASE_URL is not set")
    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    monkeypatch.delenv("EC_PULSE_API_KEY", raising=False)
    import app.services.monitor_store as monitor_store

    monkeypatch.setattr(monitor_store, "_SCHEMA_READY", False)
    with psycopg.connect(TEST_DB) as conn:
        monitor_store._init(conn)
        # The runner and the delivery worker process every due row in the
        # database, so rows left by other tests would leak into assertions.
        conn.execute("TRUNCATE monitors, price_history, monitor_run_leases, webhook_deliveries")
        conn.commit()
    return monitor_store


def pg_query(sql: str, params=()):
    with psycopg.connect(TEST_DB) as conn:
        return conn.execute(sql, params).fetchall()


def pg_exec(sql: str, params=()):
    with psycopg.connect(TEST_DB) as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount
