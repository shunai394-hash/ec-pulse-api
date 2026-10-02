import re
from urllib.parse import urlparse

from app.services.url_safety import MAX_REDIRECTS, next_redirect, read_response_bytes, safe_async_client, validate_public_url, is_redirect_response

import httpx
from bs4 import BeautifulSoup

SOURCE_CONFIG = {
    "amazon": {
        "domains": ("amazon.co.jp", "amazon.com"),
        "selectors": ['[data-hook="review-body"]', '[data-testid="review-body"]', '[itemprop="reviewBody"]'],
    },
    "rakuten": {
        "domains": ("review.rakuten.co.jp", "rakuten.co.jp"),
        "selectors": ['[class*="review"]', '[class*="comment"]'],
    },
    "yahoo": {
        "domains": ("shopping.yahoo.co.jp", "shopping.yahoo.com"),
        "selectors": ['[class*="review"]', '[class*="comment"]'],
    },
    "reddit": {
        "domains": ("reddit.com", "www.reddit.com"),
        "selectors": ['[data-testid="comment"]', 'div[data-comment-body]', 'blockquote'],
    },
    "youtube": {
        "domains": ("youtube.com", "www.youtube.com", "m.youtube.com"),
        "selectors": ['yt-attributed-string#content-text', '#content-text', 'ytd-comment-thread-renderer #content-text'],
    },
    "tiktok": {
        "domains": ("tiktok.com", "www.tiktok.com"),
        "selectors": ['[data-e2e="comment-text"]', '[class*="CommentItem"]', '[class*="comment"]'],
    },
}

MAX_RESPONSE_BYTES = 5 * 1024 * 1024

GENERIC_SELECTORS = [
    '[data-hook="review-body"]',
    '[data-testid="review-body"]',
    '[data-comment-body]',
    '.review-text',
    '.review-content',
    '.comment-content',
    '.comment-body',
    '[itemprop="reviewBody"]',
    'blockquote',
]

def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def detect_source(host: str) -> str:
    host = host.lower().split(":")[0]
    for source, config in SOURCE_CONFIG.items():
        if any(_host_matches(host, domain) for domain in config["domains"]):
            return source
    return "generic"

def detect_market(host: str, language_hint: str | None = None) -> str:
    host = host.lower()
    if host.endswith(".co.jp") or host == "co.jp" or language_hint == "ja":
        return "JP"
    if host == "amazon.com" or host.endswith(".amazon.com"):
        return "US"
    # Global social/community domains do not imply a US market by themselves.
    return "GLOBAL"

def detect_locale(market: str) -> str:
    return {"JP": "ja-JP", "US": "en-US"}.get(market, "en")

def _selectors_for(source: str) -> list[str]:
    return SOURCE_CONFIG.get(source, {}).get("selectors", []) + GENERIC_SELECTORS

def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()

async def fetch_public_comments(url: str, max_comments: int = 500) -> dict:
    if not isinstance(max_comments, int) or isinstance(max_comments, bool) or not 1 <= max_comments <= 500:
        raise ValueError("max_comments must be between 1 and 500")
    current_url = await validate_public_url(url)
    parsed = urlparse(current_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are supported")

    headers = {
        "User-Agent": "EC-Pulse-Research/0.12 (+public-page-analysis)",
        "Accept-Language": "ja,en;q=0.8",
    }

    async with safe_async_client(timeout=15, follow_redirects=False, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            async with client.stream("GET", current_url) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit() and int(content_length) > MAX_RESPONSE_BYTES:
                    raise ValueError("Research page response is too large")
                if is_redirect_response(response):
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Redirect response did not include a location")
                    current_url = await validate_public_url(next_redirect(current_url, location))
                    continue
                response.raise_for_status()
                body = await read_response_bytes(response, MAX_RESPONSE_BYTES)
            break
        else:
            raise ValueError("Too many redirects")

    final_parsed = urlparse(current_url)
    source = detect_source(final_parsed.netloc)
    market = detect_market(final_parsed.netloc)
    locale = detect_locale(market)
    soup = BeautifulSoup(body, "html.parser")
    candidates = []
    for selector in _selectors_for(source):
        for node in soup.select(selector):
            text = _clean_text(" ".join(node.stripped_strings))
            if 8 <= len(text) <= 2000:
                candidates.append(text)

    seen = set()
    comments = []
    for item in candidates:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        comments.append(item)
        if len(comments) >= max_comments:
            break

    title = soup.title.get_text(" ", strip=True) if soup.title else None
    return {
        "url": current_url,
        "source": final_parsed.netloc,
        "source_type": source,
        "market": market,
        "locale": locale,
        "title": title,
        "comments": comments,
        "comments_found": len(comments),
        "access": "public_html",
        "method": "source-aware public HTML selectors; official/public APIs should be preferred where available and source terms/robots/access rules must be respected",
    }
