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


def _landing() -> str:
    return client.get("/", headers={"Accept": "text/html"}).text


def test_landing_demo_tabs_point_at_existing_panels():
    page = _landing()
    tabs = re.findall(r'role="tab" id="(t\d)" aria-controls="(p\d)"', page)
    assert [t for t, _ in tabs] == ["t1", "t2", "t3", "t4", "t5"]
    for tab, panel in tabs:
        assert f'role="tabpanel" id="{panel}" aria-labelledby="{tab}"' in page


def test_landing_labels_sample_data_and_avoids_unbacked_claims():
    page = _landing()
    # The demo and decision card use illustrative numbers; they must say so.
    assert "サンプル" in page
    assert "保証するものではありません" in page
    # The API has no demand/competition score; the page must not invent one.
    for claim in ("必ず儲かる", "絶対に売れる", "利益保証", "Opportunity Score"):
        assert claim not in page
    assert not re.search(r"\d+\s*/\s*100\b", page)  # no "86/100"-style scores


def test_landing_buy_ceiling_example_matches_formula():
    # 仕入れ上限 = 販売価格 × (1 − 手数料率 − 目標粗利率) − 送料・梱包 − その他コスト
    price, fee, margin, shipping, other = 4980, 0.10, 0.30, 500, 0
    ceiling = int(price * (1 - fee - margin) - shipping - other)
    assert ceiling == 2488
    page = _landing()
    assert "¥2,488" in page
    assert 'value="4980"' in page and 'value="10"' in page and 'value="500"' in page and 'value="30"' in page


def test_landing_has_skip_link_and_no_external_resources():
    page = _landing()
    assert '<a class="skip" href="#main">' in page and 'id="main"' in page
    assert "http://" not in page.replace("http://localhost", "")
    assert "<link rel=\"stylesheet\"" not in page and "<script src" not in page
