import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from app.services import google_auth
from app.services.url_safety import _blocked_ip


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.1.2.3", "172.16.0.1", "172.31.255.255", "192.168.1.1",
    "169.254.169.254", "100.64.0.1", "0.0.0.0", "224.0.0.1",
    "::1", "::", "fe80::1", "fe80::1%eth0", "fc00::1", "fd12:3456::1",
    "::ffff:127.0.0.1", "::ffff:169.254.169.254",
    "64:ff9b::7f00:1", "64:ff9b::a9fe:a9fe", "64:ff9b:1::a00:1",
    "2002:7f00:1::1", "2002:a9fe:a9fe::1",
    "2001:0:4136:e378:8000:63bf:80ff:fffe",
])
def test_private_and_transition_addresses_are_blocked(address):
    assert _blocked_ip(address) is True


@pytest.mark.parametrize("address", ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed(address):
    assert _blocked_ip(address) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://localhost/", "http://127.0.0.1/", "http://[::1]/", "http://10.0.0.1/",
    "http://172.16.0.1/", "http://192.168.0.1/", "http://169.254.169.254/latest/meta-data/",
    "http://[fe80::1]/", "http://[::ffff:127.0.0.1]/", "file:///etc/passwd", "gopher://example.com/",
    "ftp://example.com/", "http://example.com:22/", "http:///nohost",
])
async def test_unsafe_urls_are_rejected(url):
    from app.services.url_safety import validate_public_url
    with pytest.raises(ValueError):
        await validate_public_url(url)


def test_session_cookies_are_secure_when_base_url_is_https(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://api.example.com")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return FakeResponse()

    monkeypatch.setattr(google_auth.httpx, "AsyncClient", FakeClient)
    client = TestClient(main.app, base_url="https://api.example.com")
    client.cookies.set("ecp_oauth_verifier", "v" * 64, domain="api.example.com", path="/auth")
    response = client.get("/auth/callback", params={"code": "c"}, follow_redirects=False)
    assert response.status_code == 302
    cookies = [v for k, v in response.headers.multi_items() if k == "set-cookie"]
    session = [c for c in cookies if c.startswith(("ecp_access_token=", "ecp_refresh_token="))]
    assert len(session) == 2
    for cookie in session:
        lowered = cookie.lower()
        assert "secure" in lowered and "httponly" in lowered and "samesite=lax" in lowered


def test_security_headers_and_request_id(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://api.example.com")
    client = TestClient(main.app)
    response = client.get("/", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "max-age=" in response.headers["Strict-Transport-Security"]
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")

    generated = client.get("/", headers={"X-Request-ID": "bad id\r\nx"}).headers["X-Request-ID"]
    assert generated != "bad id\r\nx" and len(generated) == 32

    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "Content-Security-Policy" not in docs.headers


def test_database_outage_returns_503_without_details(monkeypatch):
    def broken(api_key):
        raise psycopg.OperationalError("connection to server at 10.0.0.5 failed: password authentication failed for user neondb_owner")

    monkeypatch.setattr(main, "validate_api_key", broken)
    response = TestClient(main.app).get("/v1/account", headers={"X-API-Key": "k" * 20})
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is temporarily unavailable"}
    assert "neondb_owner" not in response.text
    assert response.headers["Retry-After"] == "5"


def test_admin_routes_are_hidden_from_openapi():
    from api.index import app
    paths = app.openapi()["paths"]
    assert not any(path.startswith("/v1/admin") for path in paths)
    assert "/v1/research/batch" in paths
