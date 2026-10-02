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
