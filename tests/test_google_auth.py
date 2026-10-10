from fastapi.testclient import TestClient
from app.main import app


def test_google_login_requires_configuration(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    response = TestClient(app).get("/auth/google", follow_redirects=False)
    assert response.status_code == 503


def test_google_login_redirect(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("APP_BASE_URL", "https://ec-pulse-api.vercel.app")
    response = TestClient(app).get("/auth/google", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("https://example.supabase.co/auth/v1/authorize?")
    assert "provider=google" in response.headers["location"]
    assert "ecp_oauth_verifier=" in response.headers["set-cookie"]


def test_current_user_requires_session(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    response = TestClient(app).get("/auth/me")
    assert response.status_code == 401


def test_browser_callback_failure_returns_to_account_page():
    client = TestClient(app)
    response = client.get("/auth/callback", headers={"Accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/account?login=failed"


def test_api_callback_failure_keeps_json_error():
    client = TestClient(app)
    response = client.get("/auth/callback", headers={"Accept": "application/json"})
    assert response.status_code == 400
    assert response.json() == {"detail": "Missing OAuth code"}


def test_successful_callback_lands_on_account_page(monkeypatch):
    import httpx
    from app.services import google_auth

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *exc): return False
        async def post(self, *args, **kwargs):
            return httpx.Response(200, json={"access_token": "a" * 20, "refresh_token": "r" * 20, "expires_in": 3600})

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setattr(google_auth.httpx, "AsyncClient", FakeClient)
    client = TestClient(app)
    client.cookies.set("ecp_oauth_verifier", "v" * 64, path="/auth")
    response = client.get("/auth/callback?code=abc", headers={"Accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/account"


def test_browser_callback_survives_auth_provider_outage(monkeypatch):
    import httpx
    from app.services import google_auth

    class DownClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *exc): return False
        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("supabase unreachable")

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setattr(google_auth.httpx, "AsyncClient", DownClient)
    client = TestClient(app)
    client.cookies.set("ecp_oauth_verifier", "v" * 64, path="/auth")
    response = client.get("/auth/callback?code=abc", headers={"Accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/account?login=failed"


def test_google_login_strips_environment_newlines(monkeypatch):
    from urllib.parse import parse_qs, urlparse

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co\\n")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test\\n")
    monkeypatch.setenv("APP_BASE_URL", "https://ec-pulse-api-one.vercel.app\\n")
    response = TestClient(app).get("/auth/google", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    assert urlparse(location).hostname == "example.supabase.co"
    redirect_to = parse_qs(urlparse(location).query)["redirect_to"][0]
    assert redirect_to == "https://ec-pulse-api-one.vercel.app/auth/callback"
    assert "\\n" not in location
