"""HMAC request signing through the real FastAPI dependency and a real
PostgreSQL-backed API key (no stubs on the authentication path)."""
import hashlib
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app import main
from app.services.request_signature import MAX_CLOCK_SKEW_SECONDS, sign_request
from tests.conftest import pg_query

NOW = 1_760_000_000


@pytest.fixture
def api(pg_store, monkeypatch):
    monkeypatch.setenv("EC_PULSE_REQUIRE_REQUEST_SIGNATURE", "true")
    monkeypatch.setattr("app.services.request_signature.time.time", lambda: NOW)
    key = pg_store.provision_customer_api_key(f"user-{uuid.uuid4()}")["api_key"]
    return TestClient(main.app), key


def signed(key, method, target, body=b"", ts=NOW, signing_key=None):
    return {
        "X-API-Key": key,
        "X-EC-Timestamp": str(ts),
        "X-EC-Signature": sign_request(signing_key or key, str(ts), method, target, body),
    }


def charged(key):
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return pg_query("SELECT count(*) FROM api_usage WHERE api_key_hash = %s", (key_hash,))[0][0]


def test_get_with_query_is_bound_to_exact_raw_query(api):
    client, key = api
    target = "/v1/research/runs?limit=5&url=https%3A%2F%2Fa.example.com%2Fx"
    assert client.get(target, headers=signed(key, "GET", target)).status_code == 200

    for tampered in [
        "/v1/research/runs?limit=6&url=https%3A%2F%2Fa.example.com%2Fx",
        "/v1/research/runs?url=https%3A%2F%2Fa.example.com%2Fx&limit=5",
        "/v1/research/runs?limit=5&url=https://a.example.com/x",
        "/v1/research/runs?limit=5",
    ]:
        response = client.get(tampered, headers=signed(key, "GET", target))
        assert response.status_code == 401, tampered
        assert response.json() == {"detail": "Invalid request signature"}


def test_path_only_signature_does_not_cover_a_query(api):
    client, key = api
    response = client.get("/v1/research/runs?limit=5", headers=signed(key, "GET", "/v1/research/runs"))
    assert response.status_code == 401


def test_percent_encoded_path_is_signed_as_sent(api):
    client, key = api
    target = "/v1/research/runs/run%2D1/opportunity"
    response = client.get(target, headers=signed(key, "GET", target))
    # Authenticated (the run does not exist), so the raw path matched.
    assert response.status_code == 404


def test_post_binds_method_body_and_query(api):
    client, key = api
    body = json.dumps({"comments": ["too expensive"]}).encode()
    target = "/v1/consumer-insights/analyze"
    headers = {**signed(key, "POST", target, body), "Content-Type": "application/json"}

    assert client.post(target, content=body, headers=headers).status_code == 200
    assert charged(key) == 1

    tampered = json.dumps({"comments": ["too cheap"]}).encode()
    assert client.post(target, content=tampered, headers=headers).status_code == 401
    assert client.post(target + "?source=x", content=body, headers=headers).status_code == 401
    get_headers = signed(key, "GET", target, body)
    assert client.post(target, content=body, headers={**get_headers, "Content-Type": "application/json"}).status_code == 401
    # Rejected requests are never charged.
    assert charged(key) == 1


def test_empty_body_post_signature(api):
    client, key = api
    response = client.post("/v1/billing/portal", headers=signed(key, "POST", "/v1/billing/portal", b""))
    # Signature accepted; the account simply has no Stripe customer.
    assert response.status_code in {400, 503}
    assert response.json()["detail"] != "Invalid request signature"


@pytest.mark.parametrize(
    ("offset", "status"),
    [(-MAX_CLOCK_SKEW_SECONDS, 200), (MAX_CLOCK_SKEW_SECONDS, 200),
     (-MAX_CLOCK_SKEW_SECONDS - 1, 401), (MAX_CLOCK_SKEW_SECONDS + 1, 401)],
)
def test_clock_skew_boundary_past_and_future(api, offset, status):
    client, key = api
    response = client.get("/v1/research/runs", headers=signed(key, "GET", "/v1/research/runs", ts=NOW + offset))
    assert response.status_code == status


@pytest.mark.parametrize("timestamp", [" 1760000000", "+1760000000", "1_760_000_000", "١٧٦٠٠٠٠٠٠٠", "1760000000.0", ""])
def test_non_canonical_timestamps_are_rejected(api, timestamp):
    client, key = api
    headers = [
        (b"X-API-Key", key.encode()),
        (b"X-EC-Timestamp", timestamp.encode()),
        (b"X-EC-Signature", sign_request(key, timestamp or "0", "GET", "/v1/research/runs", b"").encode()),
    ]
    response = client.get("/v1/research/runs", headers=headers)
    assert response.status_code == 401


@pytest.mark.parametrize("signature", [b"sha256=\xe9\xe9", b"garbage", b"sha256=", b"sha256=" + b"0" * 64])
def test_malformed_signatures_are_401_not_500(api, signature):
    client, key = api
    headers = [(b"X-API-Key", key.encode()), (b"X-EC-Timestamp", str(NOW).encode()), (b"X-EC-Signature", signature)]
    response = client.get("/v1/research/runs", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid request signature"}


def test_missing_headers_and_wrong_key(api, pg_store):
    client, key = api
    assert client.get("/v1/research/runs", headers={"X-API-Key": key}).json() == {
        "detail": "Missing request signature headers"}

    other = pg_store.provision_customer_api_key(f"user-{uuid.uuid4()}")["api_key"]
    response = client.get("/v1/research/runs", headers=signed(key, "GET", "/v1/research/runs", signing_key=other))
    assert response.status_code == 401
    assert client.get("/v1/research/runs", headers=signed("ecp_live_unknown", "GET", "/v1/research/runs")).status_code == 401


def test_repeated_query_parameters_are_bound_in_order(api):
    client, key = api
    target = "/v1/research/runs?limit=5&limit=6"
    assert client.get(target, headers=signed(key, "GET", target)).status_code == 200
    for tampered in ["/v1/research/runs?limit=6&limit=5", "/v1/research/runs?limit=5", "/v1/research/runs?limit=5&limit=6&limit=7"]:
        assert client.get(tampered, headers=signed(key, "GET", target)).status_code == 401, tampered


def test_same_timestamp_does_not_let_one_signature_cover_another_request(api):
    client, key = api
    first = signed(key, "GET", "/v1/research/runs?limit=1")
    second = signed(key, "GET", "/v1/research/runs?limit=2")
    assert first["X-EC-Timestamp"] == second["X-EC-Timestamp"]
    assert first["X-EC-Signature"] != second["X-EC-Signature"]
    assert client.get("/v1/research/runs?limit=2", headers=first).status_code == 401
