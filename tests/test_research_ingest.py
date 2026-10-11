import pytest

from app.services.research_ingest import _assert_allowed_source, detect_source, fetch_public_comments


def test_detect_source_requires_real_domain_boundary():
    assert detect_source("www.amazon.co.jp") == "amazon"
    assert detect_source("evil-amazon.co.jp.example") == "generic"
    assert detect_source("shopping.yahoo.co.jp") == "yahoo"
    assert detect_source("evilshopping.yahoo.co.jp.example") == "generic"


@pytest.mark.asyncio
async def test_research_comment_limit_is_bounded():
    with pytest.raises(ValueError, match="max_comments"):
        await fetch_public_comments("https://example.com", 501)



def test_research_ingest_rejects_non_allowlisted_domains():
    with pytest.raises(ValueError, match="allow-listed"):
        _assert_allowed_source("https://example.com/product")


def test_research_ingest_accepts_allowlisted_source_domain():
    _assert_allowed_source("https://www.amazon.co.jp/dp/B012345678")


@pytest.mark.asyncio
async def test_public_html_research_ingest_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("EC_PULSE_ENABLE_UNOFFICIAL_HTML_SCRAPING", raising=False)
    with pytest.raises(RuntimeError, match="disabled"):
        await fetch_public_comments("https://www.amazon.co.jp/dp/B012345678", 10)
