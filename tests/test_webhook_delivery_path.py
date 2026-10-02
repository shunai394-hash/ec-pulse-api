"""Webhook delivery against a real PostgreSQL database.

The production ``_deliver_pending_webhooks`` runs unmodified: claims, lease
checks and state transitions hit real tables. Only the network is replaced,
by an httpx ``MockTransport`` so responses still flow through httpx streaming,
``raise_for_status`` and ``read_response_bytes``.
"""
import asyncio
import json
import threading
import time
from collections import Counter

import httpx
import psycopg
import pytest

from tests.conftest import TEST_DB, pg_exec, pg_query

HOOK = "https://hooks.example.com/ec-pulse"


@pytest.fixture
def store(pg_store, public_dns):
    return pg_store


class Receiver:
    def __init__(self, respond=None):
        self.posts = []
        self.lock = threading.Lock()
        self.respond = respond or (lambda request: httpx.Response(204))

    async def handler(self, request: httpx.Request):
        with self.lock:
            self.posts.append(request)
        result = self.respond(request)
        if asyncio.iscoroutine(result):
            result = await result
        return result


def use_receiver(monkeypatch, store, receiver):
    def client(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(receiver.handler), **kwargs)

    monkeypatch.setattr(store, "safe_async_client", client)


def make_monitor(store, webhook_url=HOOK):
    return store.create_monitor("ecp_live_webhook_test", "https://shop.example.com/p/1", 60, webhook_url)["id"]


def enqueue(store, monitor_id, event_id):
    from datetime import datetime, timezone

    with psycopg.connect(TEST_DB) as conn:
        asyncio.run(store._enqueue_webhook(
            conn, monitor_id, event_id, {"event": "price_changed", "event_id": event_id},
            datetime.now(timezone.utc),
        ))
        conn.commit()


def delivery(event_id):
    rows = pg_query(
        """SELECT status, attempts, lease_token, locked_until, last_error, delivered_at,
                  EXTRACT(EPOCH FROM next_attempt_at - CURRENT_TIMESTAMP)
           FROM webhook_deliveries WHERE event_id = %s""",
        (event_id,),
    )
    status, attempts, token, locked, error, delivered_at, due_in = rows[0]
    return {"status": status, "attempts": attempts, "lease_token": token, "locked_until": locked,
            "last_error": error, "delivered_at": delivered_at, "due_in": float(due_in)}


def deliver(store):
    return asyncio.run(store._deliver_pending_webhooks())


def test_success_marks_delivered_and_posts_event_once(store, monkeypatch):
    receiver = Receiver()
    use_receiver(monkeypatch, store, receiver)
    enqueue(store, make_monitor(store), "evt-ok")

    assert deliver(store) == 1

    assert len(receiver.posts) == 1
    request = receiver.posts[0]
    assert request.method == "POST" and str(request.url) == HOOK
    assert request.headers["X-EC-Pulse-Event-ID"] == "evt-ok"
    assert json.loads(request.content) == {"event": "price_changed", "event_id": "evt-ok"}
    row = delivery("evt-ok")
    assert row["status"] == "delivered" and row["attempts"] == 0
    assert row["delivered_at"] is not None and row["lease_token"] is None and row["locked_until"] is None
    # A second run finds nothing to deliver: no duplicate POST.
    assert deliver(store) == 0
    assert len(receiver.posts) == 1


@pytest.mark.parametrize(
    ("respond", "expected_error"),
    [
        (lambda r: httpx.Response(500), "http_500"),
        (lambda r: httpx.Response(503), "http_503"),
        (lambda r: httpx.Response(400), "http_400"),
        (lambda r: httpx.Response(404), "http_404"),
        # Redirects are never followed: a 3xx is a failed delivery.
        (lambda r: httpx.Response(302, headers={"Location": "http://169.254.169.254/"}), "http_302"),
    ],
)
def test_http_error_schedules_retry_with_backoff(store, monkeypatch, respond, expected_error):
    receiver = Receiver(respond)
    use_receiver(monkeypatch, store, receiver)
    enqueue(store, make_monitor(store), "evt-http")

    assert deliver(store) == 0

    assert len(receiver.posts) == 1  # the redirect target is never requested
    row = delivery("evt-http")
    assert row["status"] == "pending" and row["attempts"] == 1
    assert row["last_error"] == expected_error
    assert row["lease_token"] is None and row["locked_until"] is None
    assert 50 <= row["due_in"] <= 61  # first retry after ~60s


def test_connection_error_and_timeout_are_retried(store, monkeypatch):
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    use_receiver(monkeypatch, store, Receiver(refuse))
    enqueue(store, make_monitor(store), "evt-conn")
    assert deliver(store) == 0
    assert delivery("evt-conn")["last_error"] == "ConnectError"

    async def slow(request):
        await asyncio.sleep(5)
        return httpx.Response(204)

    pg_exec("TRUNCATE webhook_deliveries")
    monkeypatch.setattr(store, "WEBHOOK_POST_DEADLINE_SECONDS", 0.2)
    use_receiver(monkeypatch, store, Receiver(slow))
    enqueue(store, make_monitor(store), "evt-slow")
    started = time.monotonic()
    assert deliver(store) == 0
    assert time.monotonic() - started < 3
    row = delivery("evt-slow")
    assert row["status"] == "pending" and row["attempts"] == 1
    assert row["last_error"] == "TimeoutError"


def test_oversized_response_body_is_a_failed_delivery(store, monkeypatch):
    big = b"x" * (store.MAX_WEBHOOK_RESPONSE_BYTES + 1)
    use_receiver(monkeypatch, store, Receiver(lambda r: httpx.Response(200, content=big)))
    enqueue(store, make_monitor(store), "evt-big")

    assert deliver(store) == 0
    row = delivery("evt-big")
    assert row["status"] == "pending" and row["attempts"] == 1
    assert row["last_error"] == "ValueError: HTTP response is too large"


def test_private_webhook_url_is_never_posted(store, monkeypatch):
    receiver = Receiver()
    use_receiver(monkeypatch, store, receiver)
    enqueue(store, make_monitor(store, "http://127.0.0.1/hook"), "evt-private")

    assert deliver(store) == 0
    assert receiver.posts == []
    row = delivery("evt-private")
    assert row["attempts"] == 1
    assert row["last_error"] == "ValueError: Private or local network URLs are not allowed"


def test_error_log_never_stores_webhook_url_secrets(store, monkeypatch):
    use_receiver(monkeypatch, store, Receiver(lambda r: httpx.Response(500)))
    enqueue(store, make_monitor(store, HOOK + "?token=receiver-secret"), "evt-secret")

    deliver(store)
    assert "receiver-secret" not in delivery("evt-secret")["last_error"]


def test_failure_then_backoff_then_success(store, monkeypatch):
    responses = iter([httpx.Response(500), httpx.Response(200, json={"ok": True})])
    receiver = Receiver(lambda r: next(responses))
    use_receiver(monkeypatch, store, receiver)
    enqueue(store, make_monitor(store), "evt-retry")

    assert deliver(store) == 0
    assert delivery("evt-retry")["attempts"] == 1
    # Still inside the backoff window: no new POST.
    assert deliver(store) == 0
    assert len(receiver.posts) == 1

    pg_exec("UPDATE webhook_deliveries SET next_attempt_at = CURRENT_TIMESTAMP - INTERVAL '1 second'")
    assert deliver(store) == 1
    assert len(receiver.posts) == 2
    row = delivery("evt-retry")
    assert row["status"] == "delivered" and row["attempts"] == 1 and row["last_error"] is None


def test_backoff_grows_exponentially_and_is_capped(store):
    assert [store._webhook_retry_delay_seconds(n) for n in range(1, 9)] == [
        60, 120, 240, 480, 960, 1920, 3600, 3600,
    ]


def test_attempts_are_capped_and_event_becomes_failed(store, monkeypatch):
    receiver = Receiver(lambda r: httpx.Response(500))
    use_receiver(monkeypatch, store, receiver)
    enqueue(store, make_monitor(store), "evt-dead")
    pg_exec("UPDATE webhook_deliveries SET attempts = %s", (store.MAX_WEBHOOK_ATTEMPTS - 1,))

    deliver(store)
    row = delivery("evt-dead")
    assert row["status"] == "failed" and row["attempts"] == store.MAX_WEBHOOK_ATTEMPTS

    pg_exec("UPDATE webhook_deliveries SET next_attempt_at = CURRENT_TIMESTAMP - INTERVAL '1 hour'")
    deliver(store)
    assert len(receiver.posts) == 1


def test_no_post_when_lease_is_lost_before_post(store, monkeypatch):
    receiver = Receiver()
    use_receiver(monkeypatch, store, receiver)
    enqueue(store, make_monitor(store), "evt-stolen")
    real_validate = store.validate_public_url

    async def validate_then_lose_lease(url):
        # Another worker takes the lease after this worker claimed the row.
        pg_exec("UPDATE webhook_deliveries SET lease_token = 'other-worker', "
                "locked_until = CURRENT_TIMESTAMP + INTERVAL '1 minute'")
        return await real_validate(url)

    monkeypatch.setattr(store, "validate_public_url", validate_then_lose_lease)

    assert deliver(store) == 0
    assert receiver.posts == []
    row = delivery("evt-stolen")
    assert row["status"] == "pending" and row["attempts"] == 0
    assert row["lease_token"] == "other-worker"


def test_acknowledged_post_is_recorded_even_if_lease_was_lost_during_post(store, monkeypatch):
    def lose_lease_then_ack(request):
        pg_exec("UPDATE webhook_deliveries SET lease_token = 'other-worker'")
        return httpx.Response(200)

    receiver = Receiver(lose_lease_then_ack)
    use_receiver(monkeypatch, store, receiver)
    enqueue(store, make_monitor(store), "evt-ack")

    assert deliver(store) == 1
    row = delivery("evt-ack")
    assert row["status"] == "delivered" and row["lease_token"] is None
    # The worker that now holds the stale lease cannot claim or re-POST it.
    pg_exec("UPDATE webhook_deliveries SET locked_until = CURRENT_TIMESTAMP - INTERVAL '1 second'")
    assert deliver(store) == 0
    assert len(receiver.posts) == 1


def test_failure_after_lease_takeover_does_not_touch_new_owner(store, monkeypatch):
    def lose_lease_then_fail(request):
        pg_exec("UPDATE webhook_deliveries SET lease_token = 'other-worker', "
                "locked_until = CURRENT_TIMESTAMP + INTERVAL '1 minute'")
        return httpx.Response(500)

    use_receiver(monkeypatch, store, Receiver(lose_lease_then_fail))
    enqueue(store, make_monitor(store), "evt-takeover")

    assert deliver(store) == 0
    row = delivery("evt-takeover")
    assert row["attempts"] == 0 and row["lease_token"] == "other-worker" and row["last_error"] is None


def test_active_lease_blocks_claim_but_expired_lease_is_reclaimed(store, monkeypatch):
    receiver = Receiver()
    use_receiver(monkeypatch, store, receiver)
    enqueue(store, make_monitor(store), "evt-lease")
    pg_exec("UPDATE webhook_deliveries SET lease_token = 'crashed-worker', "
            "locked_until = CURRENT_TIMESTAMP + INTERVAL '1 minute'")

    assert deliver(store) == 0
    assert receiver.posts == []

    pg_exec("UPDATE webhook_deliveries SET locked_until = CURRENT_TIMESTAMP - INTERVAL '1 second'")
    assert deliver(store) == 1
    assert len(receiver.posts) == 1
    assert delivery("evt-lease")["status"] == "delivered"


def test_one_run_is_bounded(store, monkeypatch):
    receiver = Receiver()
    use_receiver(monkeypatch, store, receiver)
    monkeypatch.setattr(store, "MAX_WEBHOOK_DELIVERIES_PER_RUN", 3)
    monitor_id = make_monitor(store)
    for i in range(5):
        enqueue(store, monitor_id, f"evt-bound-{i}")

    assert deliver(store) == 3
    assert deliver(store) == 2


def test_enqueue_is_idempotent_per_event_id(store, monkeypatch):
    receiver = Receiver()
    use_receiver(monkeypatch, store, receiver)
    monitor_id = make_monitor(store)
    enqueue(store, monitor_id, "evt-dup")
    enqueue(store, monitor_id, "evt-dup")

    assert deliver(store) == 1
    assert len(receiver.posts) == 1


def test_concurrent_workers_never_post_the_same_event_twice(store, monkeypatch):
    async def slow_ack(request):
        await asyncio.sleep(0.05)
        return httpx.Response(204)

    receiver = Receiver(slow_ack)
    use_receiver(monkeypatch, store, receiver)
    monitor_id = make_monitor(store)
    events = [f"evt-race-{i}" for i in range(12)]
    for event_id in events:
        enqueue(store, monitor_id, event_id)

    totals = []
    barrier = threading.Barrier(3)

    def worker():
        barrier.wait()
        totals.append(deliver(store))

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    posted = Counter(request.headers["X-EC-Pulse-Event-ID"] for request in receiver.posts)
    assert set(posted) == set(events)
    assert max(posted.values()) == 1
    assert sum(totals) == len(events)
    assert {delivery(e)["status"] for e in events} == {"delivered"}
