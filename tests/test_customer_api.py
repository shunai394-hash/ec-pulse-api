import pytest
from fastapi.testclient import TestClient

from app import main


def test_customer_key_requires_google_auth(monkeypatch):
    async def fake_current_user(request):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Not authenticated")

    monkeypatch.setattr(main, "current_user", fake_current_user)
    client = TestClient(main.app)

    response = client.post("/v1/customer/key", json={})

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_customer_key_provisions_for_authenticated_user(monkeypatch):
    async def fake_current_user(request):
        return {"id": "user-123"}

    def fake_provision(user_id, rotate=False):
        assert user_id == "user-123"
        assert rotate is False
        return {
            "created": True,
            "api_key": "ecp_live_test_key",
            "key_prefix": "ecp_live_test",
            "plan": "free",
            "credits_balance": 100,
        }

    monkeypatch.setattr(main, "current_user", fake_current_user)
    monkeypatch.setattr(main, "provision_customer_api_key", fake_provision)
    client = TestClient(main.app)

    response = client.post("/v1/customer/key", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["api_key"] == "ecp_live_test_key"
    assert body["plan"] == "free"


def test_customer_key_rotation_is_forwarded(monkeypatch):
    async def fake_current_user(request):
        return {"id": "user-456"}

    def fake_provision(user_id, rotate=False):
        assert user_id == "user-456"
        assert rotate is True
        return {"created": True, "api_key": "ecp_live_rotated"}

    monkeypatch.setattr(main, "current_user", fake_current_user)
    monkeypatch.setattr(main, "provision_customer_api_key", fake_provision)
    client = TestClient(main.app)

    response = client.post("/v1/customer/key", json={"rotate": True})

    assert response.status_code == 200
    assert response.json()["api_key"] == "ecp_live_rotated"


def test_billing_success_does_not_expose_checkout_session_id(monkeypatch):
    from datetime import datetime, timezone
    from fastapi.testclient import TestClient

    async def fake_current_user(request):
        return {"id": "user-789"}

    class Cursor:
        def fetchone(self):
            return (
                "pro", 500, "active", "cus_123", "sub_123",
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 2, 1, tzinfo=timezone.utc),
                False,
            )

    class Conn:
        def execute(self, sql, params=()):
            return Cursor()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    import app.services.monitor_store as monitor_store

    monkeypatch.setattr(main, "current_user", fake_current_user)
    monkeypatch.setattr(monitor_store, "_init", lambda conn: None)
    monkeypatch.setattr(monitor_store, "_db_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(main.psycopg, "connect", lambda *args, **kwargs: Conn())

    response = TestClient(main.app).get(
        "/billing/success?session_id=cs_sensitive",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    assert "checkout_session_id" not in body
    assert "cs_sensitive" not in response.text


@pytest.mark.parametrize("path,outcome", [
    ("/billing/success?session_id=cs_test", "success"),
    ("/billing/cancel", "cancel"),
    ("/billing", "portal"),
])
def test_stripe_return_urls_send_browsers_to_account_page(path, outcome):
    response = TestClient(main.app).get(path, headers={"Accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == f"/account?billing={outcome}"
    assert "cs_test" not in response.headers["location"]
