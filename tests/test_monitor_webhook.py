import inspect

import pytest

from app.services import monitor_store


def test_webhook_outbox_is_durable_and_deduplicated():
    assert "CREATE TABLE IF NOT EXISTS webhook_deliveries" in monitor_store.SCHEMA
    assert "event_id TEXT PRIMARY KEY" in monitor_store.SCHEMA
    assert "status TEXT NOT NULL DEFAULT 'pending'" in monitor_store.SCHEMA


def test_monitor_state_and_webhook_outbox_commit_together():
    source = inspect.getsource(monitor_store.run_due_monitors)
    enqueue = source.index("await _enqueue_webhook")
    commit = source.index("conn.commit()", enqueue)
    assert enqueue < commit



def test_monitor_results_require_active_lease_before_persisting():
    source = inspect.getsource(monitor_store.run_due_monitors)
    assert "AND lease_token = %s" in source
    assert "AND locked_until > CURRENT_TIMESTAMP" in source
    assert "RETURNING lease_token" in source
    lease_check = source.index("lease_owned =")
    history_insert = source.index("INSERT INTO price_history")
    assert lease_check < history_insert


def test_monitor_results_renew_lease_before_persisting():
    source = inspect.getsource(monitor_store.run_due_monitors)
    assert "UPDATE monitor_run_leases" in source
    assert "SET locked_until = CURRENT_TIMESTAMP + INTERVAL '10 minutes'" in source
    assert "RETURNING lease_token" in source
    assert "AND lease_token = %s" in source
    assert "AND locked_until > CURRENT_TIMESTAMP" in source
    lease_renewal = source.index("UPDATE monitor_run_leases")
    history_insert = source.index("INSERT INTO price_history")
    assert lease_renewal < history_insert
