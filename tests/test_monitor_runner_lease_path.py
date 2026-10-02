"""run_due_monitors against a real PostgreSQL database.

The production runner, its lease SQL and its writes run unmodified. Only the
product fetch (network) and the webhook receiver are replaced.
"""
import asyncio
import threading

import httpx
import psycopg
import pytest

from tests.conftest import pg_exec, pg_query

PRODUCT = "https://shop.example.com/item/1"
HOOK = "https://hooks.example.com/ec-pulse"


@pytest.fixture
def store(pg_store, public_dns, monkeypatch):
    posts = []

    async def receiver(request):
        posts.append(request)
        return httpx.Response(204)

    monkeypatch.setattr(
        pg_store, "safe_async_client",
        lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(receiver), **kw),
    )
    pg_store.webhook_posts = posts
    return pg_store


class Fetcher:
    def __init__(self, price=1000.0, before_return=None, error=None):
        self.calls = 0
        self.price = price
        self.before_return = before_return
        self.error = error
        self.lock = threading.Lock()

    async def __call__(self, url):
        with self.lock:
            self.calls += 1
        if self.before_return:
            self.before_return()
        if self.error:
            raise self.error
        return {
            "pricing": {"price": self.price, "currency": "JPY"},
            "source": {"url": url, "site": "shop.example.com"},
            "captured_at": "2026-10-02T00:00:00+00:00",
        }


def use_fetcher(monkeypatch, fetcher):
    monkeypatch.setattr("app.services.product_parser.fetch_product", fetcher)


def make_monitor(store, webhook_url=HOOK, interval=60):
    return store.create_monitor("ecp_live_runner_test", PRODUCT, interval, webhook_url)["id"]


def monitor_state(monitor_id):
    return pg_query("SELECT last_price, last_checked_at FROM monitors WHERE id = %s", (monitor_id,))[0]


def history(monitor_id):
    return pg_query("SELECT price FROM price_history WHERE monitor_id = %s ORDER BY id", (monitor_id,))


def run(store):
    return asyncio.run(store.run_due_monitors())


def test_first_run_records_price_and_releases_lease(store, monkeypatch):
    fetcher = Fetcher(price=1980.0)
    use_fetcher(monkeypatch, fetcher)
    monitor_id = make_monitor(store)

    assert run(store) == {"checked": 1, "changed": 0, "failed": 0, "webhooks_delivered": 0}

    assert fetcher.calls == 1
    assert history(monitor_id) == [(1980.0,)]
    assert monitor_state(monitor_id)[0] == 1980.0
    assert pg_query("SELECT count(*) FROM monitor_run_leases")[0][0] == 0
    # Not due again inside the interval.
    assert run(store)["checked"] == 0
    assert fetcher.calls == 1


def test_price_change_enqueues_and_delivers_one_event(store, monkeypatch):
    monitor_id = make_monitor(store)
    use_fetcher(monkeypatch, Fetcher(price=1000.0))
    run(store)
    pg_exec("UPDATE monitors SET last_checked_at = last_checked_at - INTERVAL '61 minutes'")

    use_fetcher(monkeypatch, Fetcher(price=900.0))
    result = run(store)

    assert result == {"checked": 1, "changed": 1, "failed": 0, "webhooks_delivered": 1}
    assert history(monitor_id) == [(1000.0,), (900.0,)]
    rows = pg_query("SELECT status, payload::jsonb->>'direction' FROM webhook_deliveries WHERE monitor_id = %s", (monitor_id,))
    assert rows == [("delivered", "down")]
    assert len(store.webhook_posts) == 1


def test_active_lease_of_another_worker_skips_fetch(store, monkeypatch):
    fetcher = Fetcher()
    use_fetcher(monkeypatch, fetcher)
    monitor_id = make_monitor(store)
    pg_exec("INSERT INTO monitor_run_leases VALUES (%s, 'other-worker', CURRENT_TIMESTAMP + INTERVAL '5 minutes')", (monitor_id,))

    assert run(store)["checked"] == 0
    assert fetcher.calls == 0
    assert history(monitor_id) == []
    # The other worker's lease is left alone.
    assert pg_query("SELECT lease_token FROM monitor_run_leases")[0][0] == "other-worker"


def test_expired_lease_is_taken_over(store, monkeypatch):
    fetcher = Fetcher()
    use_fetcher(monkeypatch, fetcher)
    monitor_id = make_monitor(store)
    pg_exec("INSERT INTO monitor_run_leases VALUES (%s, 'crashed-worker', CURRENT_TIMESTAMP - INTERVAL '1 second')", (monitor_id,))

    assert run(store)["checked"] == 1
    assert fetcher.calls == 1
    assert len(history(monitor_id)) == 1


@pytest.mark.parametrize("takeover", ["steal", "expire_and_steal"])
def test_worker_that_lost_lease_during_fetch_writes_nothing(store, monkeypatch, takeover):
    monitor_id = make_monitor(store)
    use_fetcher(monkeypatch, Fetcher(price=1000.0))
    run(store)
    pg_exec("UPDATE monitors SET last_checked_at = last_checked_at - INTERVAL '61 minutes'")
    before = monitor_state(monitor_id)

    def lose_lease():
        if takeover == "steal":
            pg_exec("UPDATE monitor_run_leases SET lease_token = 'other-worker'")
        else:
            pg_exec("UPDATE monitor_run_leases SET locked_until = CURRENT_TIMESTAMP - INTERVAL '1 second'")
            pg_exec("UPDATE monitor_run_leases SET lease_token = 'other-worker', "
                    "locked_until = CURRENT_TIMESTAMP + INTERVAL '10 minutes'")

    use_fetcher(monkeypatch, Fetcher(price=500.0, before_return=lose_lease))
    result = run(store)

    assert result["checked"] == 0 and result["changed"] == 0
    assert history(monitor_id) == [(1000.0,)]
    assert monitor_state(monitor_id) == before
    assert pg_query("SELECT count(*) FROM webhook_deliveries")[0][0] == 0
    assert pg_query("SELECT lease_token FROM monitor_run_leases")[0][0] == "other-worker"


def test_stale_due_list_does_not_double_process_after_other_worker_finished(store, monkeypatch):
    """Worker B reads the due list, then worker A runs the monitor to completion
    and releases its lease before B tries to take it."""
    monitor_id = make_monitor(store)
    use_fetcher(monkeypatch, Fetcher(price=1000.0))
    run(store)
    pg_exec("UPDATE monitors SET last_checked_at = last_checked_at - INTERVAL '61 minutes'")

    fetcher = Fetcher(price=900.0)
    use_fetcher(monkeypatch, fetcher)
    real_connect = psycopg.connect
    worker_b = threading.current_thread()
    b_connects = []
    a_result = {}

    def connect(*args, **kwargs):
        if threading.current_thread() is worker_b:
            b_connects.append(1)
            if len(b_connects) == 2:  # B has its due list; next is its lease INSERT.
                t = threading.Thread(target=lambda: a_result.update(run(store)))
                t.start()
                t.join()
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(store.psycopg, "connect", connect)
    b_result = run(store)

    assert a_result["checked"] == 1 and a_result["changed"] == 1
    assert b_result["checked"] == 0 and b_result["changed"] == 0
    assert fetcher.calls == 1
    assert history(monitor_id) == [(1000.0,), (900.0,)]
    assert pg_query("SELECT count(*) FROM webhook_deliveries")[0][0] == 1


@pytest.fixture
def update_audit():
    """Count real UPDATEs on monitors with a temporary trigger."""
    pg_exec("CREATE TABLE IF NOT EXISTS test_monitor_update_audit (monitor_id TEXT)")
    pg_exec("TRUNCATE test_monitor_update_audit")
    pg_exec("""CREATE OR REPLACE FUNCTION test_audit_monitor_update() RETURNS trigger AS $$
               BEGIN INSERT INTO test_monitor_update_audit VALUES (NEW.id); RETURN NEW; END $$ LANGUAGE plpgsql""")
    pg_exec("CREATE TRIGGER test_audit_monitor_update AFTER UPDATE ON monitors "
            "FOR EACH ROW EXECUTE FUNCTION test_audit_monitor_update()")
    try:
        yield lambda: dict(pg_query("SELECT monitor_id, count(*) FROM test_monitor_update_audit GROUP BY 1"))
    finally:
        pg_exec("DROP TRIGGER IF EXISTS test_audit_monitor_update ON monitors")
        pg_exec("DROP TABLE IF EXISTS test_monitor_update_audit")


def test_two_free_running_workers_process_each_due_monitor_once(store, monkeypatch, update_audit):
    """Two real runners start together on the same due monitors. The first
    fetch is slow, so the other worker processes (and releases) the remaining
    monitors before the slow worker reaches them with its stale due list."""
    import time

    monitors = [make_monitor(store) for _ in range(6)]
    use_fetcher(monkeypatch, Fetcher(price=1000.0))
    run(store)
    pg_exec("UPDATE monitors SET last_checked_at = last_checked_at - INTERVAL '61 minutes'")
    pg_exec("TRUNCATE test_monitor_update_audit")

    fetch_counts = {}
    lock = threading.Lock()
    first = threading.Event()

    async def fetch(url):
        with lock:
            fetch_counts[threading.current_thread().name] = fetch_counts.get(threading.current_thread().name, 0) + 1
            slow = not first.is_set()
            first.set()
        if slow:
            time.sleep(0.5)
        return {"pricing": {"price": 900.0, "currency": "JPY"},
                "source": {"url": url, "site": "shop.example.com"},
                "captured_at": "2026-10-02T00:00:00+00:00"}

    use_fetcher(monkeypatch, fetch)
    results = {}
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        results[threading.current_thread().name] = run(store)

    threads = [threading.Thread(target=worker, name=name) for name in ("worker-a", "worker-b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Both workers really ran concurrently and each did part of the work.
    assert all(r["checked"] > 0 for r in results.values()), results
    assert sum(fetch_counts.values()) == len(monitors)
    assert sum(r["checked"] for r in results.values()) == len(monitors)
    assert sum(r["changed"] for r in results.values()) == len(monitors)
    assert all(len(history(m)) == 2 for m in monitors)  # initial run + exactly one more
    assert update_audit() == {m: 1 for m in monitors}
    assert pg_query("SELECT count(*) FROM webhook_deliveries")[0][0] == len(monitors)
    assert len(store.webhook_posts) == len(monitors)


def test_fetch_exception_counts_failure_and_leaves_state_untouched(store, monkeypatch):
    use_fetcher(monkeypatch, Fetcher(error=httpx.ConnectTimeout("timed out")))
    monitor_id = make_monitor(store)

    assert run(store) == {"checked": 0, "changed": 0, "failed": 1, "webhooks_delivered": 0}
    assert history(monitor_id) == []
    assert monitor_state(monitor_id) == (None, None)
    assert pg_query("SELECT count(*) FROM monitor_run_leases")[0][0] == 0


def test_private_webhook_url_fails_before_fetch(store, monkeypatch):
    fetcher = Fetcher()
    use_fetcher(monkeypatch, fetcher)
    monitor_id = make_monitor(store, webhook_url="http://169.254.169.254/latest")

    assert run(store)["failed"] == 1
    assert fetcher.calls == 0
    assert history(monitor_id) == []


def test_write_transaction_rolls_back_as_a_unit(store, monkeypatch):
    monitor_id = make_monitor(store)
    use_fetcher(monkeypatch, Fetcher(price=1000.0))
    run(store)
    pg_exec("UPDATE monitors SET last_checked_at = last_checked_at - INTERVAL '61 minutes'")
    before = monitor_state(monitor_id)

    async def broken_enqueue(*args, **kwargs):
        raise psycopg.errors.SerializationFailure("simulated")

    monkeypatch.setattr(store, "_enqueue_webhook", broken_enqueue)
    use_fetcher(monkeypatch, Fetcher(price=900.0))

    assert run(store)["failed"] == 1
    assert history(monitor_id) == [(1000.0,)]
    assert monitor_state(monitor_id) == before


def test_interval_boundary(store, monkeypatch):
    fetcher = Fetcher()
    use_fetcher(monkeypatch, fetcher)
    monitor_id = make_monitor(store, interval=15)
    run(store)
    assert fetcher.calls == 1

    pg_exec("UPDATE monitors SET last_checked_at = CURRENT_TIMESTAMP - INTERVAL '14 minutes 55 seconds'")
    run(store)
    assert fetcher.calls == 1

    pg_exec("UPDATE monitors SET last_checked_at = CURRENT_TIMESTAMP - INTERVAL '15 minutes 1 second'")
    run(store)
    assert fetcher.calls == 2
    assert len(history(monitor_id)) == 2
