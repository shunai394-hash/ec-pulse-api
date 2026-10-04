import base64
import hashlib
import re

import pytest
from fastapi.testclient import TestClient

from app.main import _redact, app

client = TestClient(app)


def _inline_hashes(page: str, tag: str) -> set[str]:
    return {
        "'sha256-" + base64.b64encode(hashlib.sha256(block.encode()).digest()).decode() + "'"
        for block in re.findall(rf"<{tag}>(.*?)</{tag}>", page, re.S)
    }


def test_root_browser_gets_customer_landing_page():
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "EC Pulse API" in response.text
    for anchor in ('href="/docs"', 'href="/account"', 'id="pricing"', 'id="quickstart"', 'href="/legal/terms"'):
        assert anchor in response.text


def test_root_api_client_keeps_json_contract():
    response = client.get("/", headers={"Accept": "application/json"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "EC Pulse API"
    assert payload["docs"] == "/docs"
    assert payload["health"] == "/health"
    assert set(payload) >= {"commit", "environment"}


def test_root_reports_vercel_release(monkeypatch):
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "ddb1dfd026c12934e94418c748372e820104cac4")
    monkeypatch.setenv("VERCEL_ENV", "production")
    payload = client.get("/", headers={"Accept": "application/json"}).json()
    assert payload["commit"] == "ddb1dfd"
    assert payload["environment"] == "production"


@pytest.mark.parametrize("path", ["/", "/account", "/legal/terms"])
def test_html_pages_csp_allows_exactly_their_inline_blocks(path):
    # A blanket default-src 'none' once blocked the landing page's own stylesheet,
    # so browsers rendered it unstyled. The policy must whitelist each inline block.
    response = client.get(path, headers={"Accept": "text/html"})
    assert response.status_code == 200
    csp = response.headers["Content-Security-Policy"]
    assert "unsafe-inline" not in csp
    assert "frame-ancestors 'none'" in csp
    assert 'style="' not in response.text  # style attributes would need 'unsafe-hashes'
    for digest in _inline_hashes(response.text, "style") | _inline_hashes(response.text, "script"):
        assert digest in csp


def test_json_responses_keep_strict_csp():
    response = client.get("/", headers={"Accept": "application/json"})
    assert response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"


@pytest.mark.parametrize("slug", [
    "terms", "privacy", "billing", "commercial-transactions", "acceptable-use",
    "terms-of-service", "privacy-policy", "billing-and-cancellation",
])
def test_legal_documents_are_served(slug):
    response = client.get(f"/legal/{slug}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_unknown_legal_document_is_404():
    assert client.get("/legal/../../etc/passwd").status_code == 404
    assert client.get("/legal/unknown").status_code == 404


def test_favicon_and_robots():
    favicon = client.get("/favicon.ico")
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow: /v1/" in robots.text


def test_redact_strips_bearer_tokens_and_jwts():
    text = _redact("Authorization: Bearer abc.def-123 token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl")
    assert "abc.def-123" not in text
    assert "eyJhbGciOiJIUzI1NiJ9" not in text


def test_landing_exposes_accessible_decision_loop():
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    page = response.text
    assert 'class="skip-link" href="#main-content"' in page
    assert 'id="main-content"' in page
    assert 'role="tablist"' in page
    assert 'role="tab"' in page
    assert 'aria-selected="true"' in page
    assert 'aria-controls="radar-detail"' in page
    assert 'role="tabpanel"' in page
    assert 'ArrowRight' in page
    assert 'ArrowLeft' in page
    assert 'tabindex="-1"' in page
    assert 'href="/#engine"' in page
    assert 'href="/#profit-check"' in page
    assert "判断の出力イメージ" in page


def test_landing_keeps_csp_safe_dynamic_states():
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    page = response.text
    assert 'style="' not in page
    assert 'output.style' not in page
    assert '.max-buy.invalid' in page
    assert 'classList.toggle("invalid"' in page
    assert 'unsafe-inline' not in response.headers["Content-Security-Policy"]

def test_landing_has_unique_ids_and_interactive_engine():
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    page = response.text
    ids = re.findall(r'\bid="([^"]+)"', page)
    assert len(ids) == len(set(ids))
    assert 'id="engine"' in page
    assert 'id="flow"' in page
    assert 'role="tablist" aria-label="判断エンジンのステップ"' in page
    assert 'data-engine="3"' in page
    assert 'ArrowDown' in page and 'ArrowUp' in page
    assert 'id="profit-verdict"' in page
    assert 'position:sticky' in page
    assert 'backdrop-filter:blur(16px)' in page
