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


def test_concurrent_workers_fetch_each_monitor_once(store, monkeypatch):
    import time

    fetcher = Fetcher(before_return=lambda: time.sleep(0.1))
    use_fetcher(monkeypatch, fetcher)
    monitors = [make_monitor(store) for _ in range(4)]
    results = []
    barrier = threading.Barrier(3)

    def worker():
        barrier.wait()
        results.append(run(store))

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert fetcher.calls == len(monitors)
    assert sum(r["checked"] for r in results) == len(monitors)
    assert sum(r["failed"] for r in results) == 0
    assert all(len(history(m)) == 1 for m in monitors)


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
