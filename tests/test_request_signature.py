from app.services.request_signature import sign_request, verify_request_signature


def test_request_signature_round_trip():
    key = "ecp_live_test_secret"
    timestamp = "1760000000"
    body = b'{"url":"https://example.com/item"}'
    signature = sign_request(key, timestamp, "post", "/v1/products", body)

    verify_request_signature(
        key,
        timestamp,
        signature,
        "POST",
        "/v1/products",
        body,
        now=1760000000,
    )


def test_request_signature_rejects_body_tampering():
    key = "ecp_live_test_secret"
    timestamp = "1760000000"
    signature = sign_request(key, timestamp, "POST", "/v1/products", b"original")

    try:
        verify_request_signature(
            key,
            timestamp,
            signature,
            "POST",
            "/v1/products",
            b"tampered",
            now=1760000000,
        )
    except ValueError as exc:
        assert str(exc) == "Invalid request signature"
    else:
        raise AssertionError("tampered body must be rejected")


def test_request_signature_rejects_expired_timestamp():
    key = "ecp_live_test_secret"
    signature = sign_request(key, "1760000000", "GET", "/v1/account", b"")

    try:
        verify_request_signature(
            key,
            "1760000000",
            signature,
            "GET",
            "/v1/account",
            b"",
            now=1760000000 + 301,
        )
    except ValueError as exc:
        assert str(exc) == "Request signature timestamp is expired"
    else:
        raise AssertionError("expired signature must be rejected")


def test_request_signature_binds_query_string():
    key = "ecp_live_test_secret"
    timestamp = "1760000000"
    body = b""
    signed_target = "/v1/account?days=30"
    signature = sign_request(key, timestamp, "GET", signed_target, body)

    verify_request_signature(
        key, timestamp, signature, "GET", signed_target, body, now=1760000000
    )

    try:
        verify_request_signature(
            key, timestamp, signature, "GET", "/v1/account?days=365", body, now=1760000000
        )
    except ValueError as exc:
        assert str(exc) == "Invalid request signature"
    else:
        raise AssertionError("query-string tampering must be rejected")

def _patch_signature_dependency(monkeypatch):
    from app import main

    key = "ecp_live_test_secret"
    monkeypatch.setenv("EC_PULSE_REQUIRE_REQUEST_SIGNATURE", "true")
    monkeypatch.setattr(main, "validate_api_key", lambda value: value == key)
    monkeypatch.setattr(
        main,
        "ensure_api_account",
        lambda value: {"plan": "free", "credits_balance": 100},
    )
    monkeypatch.setattr(
        main,
        "check_rate_limit",
        lambda *args: {"allowed": True, "limit": 30, "remaining": 29, "reset_seconds": 60},
    )
    monkeypatch.setattr(main, "get_account_usage", lambda value: {"credits_balance": 100})
    monkeypatch.setattr("app.services.request_signature.time.time", lambda: 1760000000)
    return main, key


def test_fastapi_request_signature_binds_actual_query_string(monkeypatch):
    from fastapi.testclient import TestClient

    main, key = _patch_signature_dependency(monkeypatch)
    timestamp = "1760000000"
    signature = sign_request(key, timestamp, "GET", "/v1/account?days=30", b"")
    headers = {
        "X-API-Key": key,
        "X-EC-Timestamp": timestamp,
        "X-EC-Signature": signature,
    }
    client = TestClient(main.app)

    valid = client.get("/v1/account?days=30", headers=headers)
    assert valid.status_code == 200, valid.text

    tampered = client.get("/v1/account?days=365", headers=headers)
    assert tampered.status_code == 401
    assert tampered.json()["detail"] == "Invalid request signature"


def test_fastapi_request_signature_binds_query_encoding_and_order(monkeypatch):
    from fastapi.testclient import TestClient

    main, key = _patch_signature_dependency(monkeypatch)
    timestamp = "1760000000"
    signed_query = "days=30&scope=full%20text"
    signature = sign_request(
        key,
        timestamp,
        "GET",
        f"/v1/account?{signed_query}",
        b"",
    )
    headers = {
        "X-API-Key": key,
        "X-EC-Timestamp": timestamp,
        "X-EC-Signature": signature,
    }
    client = TestClient(main.app)

    valid = client.get(f"/v1/account?{signed_query}", headers=headers)
    assert valid.status_code == 200, valid.text

    reordered = client.get(
        "/v1/account?scope=full%20text&days=30",
        headers=headers,
    )
    assert reordered.status_code == 401

    reencoded = client.get(
        "/v1/account?days=30&scope=full+text",
        headers=headers,
    )
    assert reencoded.status_code == 401

def test_request_signature_rejects_missing_headers():
    key = "ecp_live_test_secret"

    for timestamp, signature in ((None, "sha256=test"), ("1760000000", None)):
        try:
            verify_request_signature(
                key,
                timestamp,
                signature,
                "GET",
                "/v1/account",
                b"",
                now=1760000000,
            )
        except ValueError as exc:
            assert str(exc) == "Missing request signature headers"
        else:
            raise AssertionError("missing signature headers must be rejected")


def test_request_signature_rejects_invalid_timestamp():
    key = "ecp_live_test_secret"

    try:
        verify_request_signature(
            key,
            "not-a-timestamp",
            "sha256=test",
            "GET",
            "/v1/account",
            b"",
            now=1760000000,
        )
    except ValueError as exc:
        assert str(exc) == "Invalid request signature timestamp"
    else:
        raise AssertionError("invalid timestamp must be rejected")


def test_request_signature_binds_http_method():
    key = "ecp_live_test_secret"
    timestamp = "1760000000"
    signature = sign_request(key, timestamp, "GET", "/v1/account", b"")

    try:
        verify_request_signature(
            key,
            timestamp,
            signature,
            "POST",
            "/v1/account",
            b"",
            now=1760000000,
        )
    except ValueError as exc:
        assert str(exc) == "Invalid request signature"
    else:
        raise AssertionError("method tampering must be rejected")


def test_request_signature_accepts_clock_skew_boundary():
    key = "ecp_live_test_secret"
    timestamp = "1760000000"
    signature = sign_request(key, timestamp, "GET", "/v1/account", b"")

    verify_request_signature(
        key,
        timestamp,
        signature,
        "GET",
        "/v1/account",
        b"",
        now=1760000000 + 300,
    )
