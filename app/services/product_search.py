import asyncio
import json
import os
import re
from urllib.parse import quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.product_cache import fetch_product_cached
from app.services.url_safety import MAX_REDIRECTS, next_redirect, read_response_bytes, safe_async_client, validate_public_url


SEARCH_URLS = {
    "amazon": "https://www.amazon.co.jp/s?k={query}",
    "rakuten": "https://search.rakuten.co.jp/search/mall/{query}/",
    "yahoo": "https://shopping.yahoo.co.jp/search?p={query}",
}


YAHOO_API_URL = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
AMAZON_API_URL = "https://creatorsapi.amazon/catalog/v1/searchItems"
AMAZON_TOKEN_URLS = {"3.1": "https://api.amazon.com/auth/o2/token", "3.2": "https://api.amazon.co.uk/auth/o2/token", "3.3": "https://api.amazon.co.jp/auth/o2/token"}
_YAHOO_REQUEST_LOCK = asyncio.Lock()
_YAHOO_MIN_INTERVAL_SECONDS = 1.05
_yahoo_last_request_at = 0.0
_AMAZON_TOKEN_LOCK = asyncio.Lock()
_amazon_access_token: str | None = None
_amazon_token_expires_at = 0.0
MAX_SEARCH_RESPONSE_BYTES = 2 * 1024 * 1024


async def _amazon_token() -> str:
    global _amazon_access_token, _amazon_token_expires_at
    client_id = os.getenv("AMAZON_CLIENT_ID")
    client_secret = os.getenv("AMAZON_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Amazon Creators API credentials are not configured")
    now = asyncio.get_running_loop().time()
    if _amazon_access_token and now < _amazon_token_expires_at - 60:
        return _amazon_access_token
    async with _AMAZON_TOKEN_LOCK:
        now = asyncio.get_running_loop().time()
        if _amazon_access_token and now < _amazon_token_expires_at - 60:
            return _amazon_access_token
        credential_version = os.getenv("AMAZON_CREDENTIAL_VERSION", "3.3")
        token_url = AMAZON_TOKEN_URLS.get(credential_version)
        if not token_url:
            raise RuntimeError("AMAZON_CREDENTIAL_VERSION must be 3.1, 3.2, or 3.3")
        async with safe_async_client(timeout=15.0) as client:
            async with client.stream(
                "POST",
                token_url,
                headers={"Content-Type": "application/json"},
                json={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "creatorsapi::default",
                },
            ) as response:
                response.raise_for_status()
                body = await read_response_bytes(response, MAX_SEARCH_RESPONSE_BYTES)
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Invalid Amazon Creators API token response")
    token = payload.get("access_token")
    expires_in = payload.get("expires_in", 3600)
    if not token:
        raise ValueError("Invalid Amazon Creators API token response")
    _amazon_access_token = token
    _amazon_token_expires_at = asyncio.get_running_loop().time() + float(expires_in)
    return token

def _amazon_item(item: dict) -> dict:
    info = item.get("itemInfo") if isinstance(item.get("itemInfo"), dict) else {}
    title = info.get("title") if isinstance(info.get("title"), dict) else {}
    byline = info.get("byLineInfo") if isinstance(info.get("byLineInfo"), dict) else {}
    brand = byline.get("brand") if isinstance(byline.get("brand"), dict) else {}
    offers = item.get("offersV2") if isinstance(item.get("offersV2"), dict) else {}
    listings = offers.get("listings") if isinstance(offers.get("listings"), list) else []
    listing = listings[0] if listings and isinstance(listings[0], dict) else {}
    price = listing.get("price") if isinstance(listing.get("price"), dict) else {}
    money = price.get("money") if isinstance(price.get("money"), dict) else {}
    availability = listing.get("availability") if isinstance(listing.get("availability"), dict) else {}
    images = item.get("images") if isinstance(item.get("images"), dict) else {}
    primary = images.get("primary") if isinstance(images.get("primary"), dict) else {}
    image = primary.get("medium") if isinstance(primary.get("medium"), dict) else primary.get("small")
    return {
        "url": item.get("detailPageURL"),
        "cache_hit": False,
        "product": {
            "product": {
                "title": title.get("displayValue"),
                "brand": brand.get("displayValue"),
                "model": None,
                "sku": item.get("asin"),
                "gtin": None,
                "product_id": item.get("asin"),
            },
            "pricing": {
                "price": money.get("amount"),
                "list_price": None,
                "currency": money.get("currency") or "JPY",
            },
            "availability": {"status": availability.get("type")},
            "rating": {"score": None, "count": 0},
            "seller": {"name": (listing.get("merchantInfo") or {}).get("name") if isinstance(listing.get("merchantInfo"), dict) else None},
            "source": {
                "site": "amazon.co.jp",
                "marketplace": "amazon",
                "product_id": item.get("asin"),
                "url": item.get("detailPageURL"),
                "image": image.get("url") if isinstance(image, dict) else None,
            },
        },
    }


async def _search_amazon_official(query: str, limit: int) -> list[dict]:
    global _amazon_access_token, _amazon_token_expires_at
    partner_tag = os.getenv("AMAZON_PARTNER_TAG")
    if not partner_tag:
        raise RuntimeError("AMAZON_PARTNER_TAG is not configured")
    token = await _amazon_token()
    payload = {
        "keywords": query,
        "itemCount": min(limit, 10),
        "marketplace": "www.amazon.co.jp",
        "partnerTag": partner_tag,
        "searchIndex": "All",
        "sortBy": "Price:LowToHigh",
        "resources": [
            "images.primary.medium",
            "itemInfo.title",
            "itemInfo.byLineInfo",
            "offersV2.listings.price",
            "offersV2.listings.availability",
            "offersV2.listings.merchantInfo",
        ],
    }

    async def request(current_token: str) -> tuple[int, dict]:
        async with safe_async_client(timeout=15.0) as client:
            async with client.stream(
                "POST",
                AMAZON_API_URL,
                headers={
                    "Authorization": f"Bearer {current_token}",
                    "Content-Type": "application/json",
                    "x-marketplace": "www.amazon.co.jp",
                },
                json=payload,
            ) as response:
                status = response.status_code
                response.raise_for_status()
                body = await read_response_bytes(response, MAX_SEARCH_RESPONSE_BYTES)
        data = json.loads(body.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid Amazon Creators API response")
        return status, data

    try:
        status, data = await request(token)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 401:
            raise
        _amazon_access_token = None
        _amazon_token_expires_at = 0.0
        token = await _amazon_token()
        status, data = await request(token)

    result = data.get("searchResult") if isinstance(data.get("searchResult"), dict) else {}
    items = result.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Invalid Amazon Creators API response")
    return [_amazon_item(item) for item in items[:limit] if isinstance(item, dict)]

def _yahoo_item(item: dict) -> dict:
    review = item.get("review") if isinstance(item.get("review"), dict) else {}
    seller = item.get("seller") if isinstance(item.get("seller"), dict) else {}
    image = item.get("image") if isinstance(item.get("image"), dict) else {}
    price = item.get("price")
    return {
        "url": item.get("url"),
        "cache_hit": False,
        "product": {
            "product": {"title": item.get("name"), "brand": (item.get("brand") or {}).get("name") if isinstance(item.get("brand"), dict) else item.get("brand"), "model": None, "sku": item.get("code"), "gtin": item.get("janCode"), "product_id": item.get("code") or item.get("janCode")},
            "pricing": {"price": float(price) if isinstance(price, (int, float)) else None, "list_price": None, "currency": "JPY"},
            "availability": {"status": "InStock" if item.get("inStock") else "OutOfStock"},
            "rating": {"score": review.get("rate"), "count": review.get("count", 0)},
            "seller": {"name": seller.get("name")},
            "source": {"site": "shopping.yahoo.co.jp", "marketplace": "yahoo", "product_id": item.get("code") or item.get("janCode"), "url": item.get("url"), "image": image.get("medium")},
        },
    }


RAKUTEN_API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"


def _rakuten_item(item: dict) -> dict:
    return {
        "url": item.get("itemUrl"),
        "cache_hit": False,
        "product": {
            "product": {"title": item.get("itemName"), "brand": None, "model": None, "sku": item.get("itemCode"), "gtin": None, "product_id": item.get("itemCode")},
            "pricing": {"price": float(item.get("itemPrice")) if isinstance(item.get("itemPrice"), (int, float)) else None, "list_price": None, "currency": "JPY"},
            "availability": {"status": "InStock"},
            "rating": {"score": item.get("reviewAverage"), "count": item.get("reviewCount", 0)},
            "seller": {"name": item.get("shopName")},
            "source": {"site": "rakuten.co.jp", "marketplace": "rakuten", "product_id": item.get("itemCode"), "url": item.get("itemUrl"), "image": None},
        },
    }


async def _search_rakuten_official(query: str, limit: int) -> list[dict]:
    app_id = os.getenv("RAKUTEN_APPLICATION_ID")
    access_key = os.getenv("RAKUTEN_ACCESS_KEY")
    if not app_id or not access_key:
        raise RuntimeError("Rakuten API credentials are not configured")
    async with safe_async_client(timeout=15.0) as client:
        async with client.stream(
            "GET",
            RAKUTEN_API_URL,
            params={"applicationId": app_id, "format": "json", "formatVersion": 2, "keyword": query, "hits": min(limit, 30), "sort": "+itemPrice"},
            headers={"Accept": "application/json", "User-Agent": "EC-Pulse/0.12", "accessKey": access_key},
        ) as response:
            response.raise_for_status()
            body = await read_response_bytes(response, MAX_SEARCH_RESPONSE_BYTES)
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid Rakuten API response")
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Invalid Rakuten API response")
    return [_rakuten_item(item) for item in items[:limit] if isinstance(item, dict)]

async def _search_yahoo_official(query: str, limit: int) -> list[dict]:
    app_id = os.getenv("YAHOO_SHOPPING_APP_ID")
    if not app_id:
        raise RuntimeError("YAHOO_SHOPPING_APP_ID is not configured")
    global _yahoo_last_request_at
    async with _YAHOO_REQUEST_LOCK:
        now = asyncio.get_running_loop().time()
        wait = _YAHOO_MIN_INTERVAL_SECONDS - (now - _yahoo_last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        async with safe_async_client(timeout=15.0) as client:
            async def request():
                async with client.stream(
                    "GET",
                    YAHOO_API_URL,
                    params={"appid": app_id, "query": query, "results": min(limit, 50), "sort": "+price"},
                    headers={"Accept": "application/json", "User-Agent": "EC-Pulse/0.12"},
                ) as response:
                    _yahoo_last_request_at = asyncio.get_running_loop().time()
                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        try:
                            delay = min(float(retry_after), 5.0) if retry_after else 1.1
                        except ValueError:
                            delay = 1.1
                        return response.status_code, None, delay
                    response.raise_for_status()
                    body = await read_response_bytes(response, MAX_SEARCH_RESPONSE_BYTES)
                    return response.status_code, json.loads(body.decode("utf-8")), 0.0

            status, payload, delay = await request()
            if status == 429:
                await asyncio.sleep(delay)
                status, payload, _ = await request()
                if status == 429:
                    raise RuntimeError("Yahoo Shopping API rate limit")
    if not isinstance(payload, dict):
        raise ValueError("Invalid Yahoo Shopping API response")
    hits = payload.get("hits", [])
    if not isinstance(hits, list):
        raise ValueError("Invalid Yahoo Shopping API response")
    return [_yahoo_item(item) for item in hits[:limit] if isinstance(item, dict)]

def _links(html: str, marketplace: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if marketplace == "amazon":
            match = re.search(r"(https?://www\.amazon\.co\.jp)?/[^\s\"']*/dp/([A-Z0-9]{10})", href, re.I)
            if match:
                url = f"https://www.amazon.co.jp/dp/{match.group(2).upper()}"
            else:
                continue
        elif marketplace == "rakuten":
            parsed = urlparse(href)
            if parsed.scheme not in {"http", "https"} or parsed.hostname != "item.rakuten.co.jp":
                continue
            url = href.split("?")[0]
        else:
            parsed = urlparse(href)
            if parsed.scheme not in {"http", "https"} or parsed.hostname != "shopping.yahoo.co.jp":
                continue
            url = href.split("?")[0]

        if url not in seen:
            seen.add(url)
            found.append(url)
        if len(found) >= 10:
            break
    return found


async def _search_marketplace(marketplace: str, query: str, limit: int) -> list[str]:
    url = SEARCH_URLS[marketplace].format(query=quote_plus(query))
    current_url = await validate_public_url(url)
    async with safe_async_client(
        follow_redirects=False,
        timeout=15.0,
        headers={"User-Agent": "EC-Pulse/0.1 (+https://ec-pulse-api.vercel.app)"},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            async with client.stream("GET", current_url) as response:
                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Redirect response did not include a location")
                    current_url = await validate_public_url(next_redirect(current_url, location))
                    continue
                response.raise_for_status()
                body = await read_response_bytes(response, MAX_SEARCH_RESPONSE_BYTES)
                break
        else:
            raise ValueError("Too many redirects")
    return _links(body.decode("utf-8"), marketplace)[:limit]



async def _search_bing_marketplace(query: str, limit: int) -> list[dict]:
    """Last-resort public discovery when marketplace APIs/search HTML yield no links."""
    search_url = "https://www.bing.com/search?q=" + quote_plus(
        query + " (site:shopping.yahoo.co.jp OR site:item.rakuten.co.jp OR site:amazon.co.jp)"
    ) + "&setlang=ja-JP&cc=JP"
    try:
        async with safe_async_client(
            follow_redirects=True,
            timeout=12.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; EC-Pulse/0.12)"},
        ) as client:
            async with client.stream("GET", search_url) as response:
                response.raise_for_status()
                html = await read_response_bytes(response, MAX_SEARCH_RESPONSE_BYTES)
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")
    found: list[dict] = []
    seen: set[str] = set()

    # Bing changes its result-item markup periodically. Do not depend on
    # li.b_algo being present; scan all result links and keep only marketplace
    # product hosts. This makes the public fallback resilient to markup drift.
    anchors = soup.select("li.b_algo h2 a[href]")
    if not anchors:
        anchors = soup.select("h2 a[href]")
    if not anchors:
        anchors = soup.find_all("a", href=True)

    for anchor in anchors:
        href = str(anchor.get("href") or "")
        title = " ".join(anchor.stripped_strings)
        if not href.startswith(("http://", "https://")) or not title:
            continue
        try:
            host = (urlparse(href).hostname or "").lower()
        except Exception:
            continue
        if host == "shopping.yahoo.co.jp" or host.endswith(".shopping.yahoo.co.jp"):
            marketplace = "yahoo"
        elif host == "item.rakuten.co.jp" or host.endswith(".item.rakuten.co.jp"):
            marketplace = "rakuten"
        elif host == "amazon.co.jp" or host.endswith(".amazon.co.jp"):
            marketplace = "amazon"
        else:
            continue
        clean_url = href.split("?")[0]
        if clean_url in seen:
            continue
        seen.add(clean_url)
        found.append({"url": clean_url, "title": title, "marketplace": marketplace})
        if len(found) >= limit:
            break
    return found


async def search_products(query: str, marketplaces: list[str], limit: int) -> dict:
    results_by_marketplace = await asyncio.gather(
        *(_search_amazon_official(query, limit) if marketplace == "amazon" and os.getenv("AMAZON_CLIENT_ID") and os.getenv("AMAZON_CLIENT_SECRET") and os.getenv("AMAZON_PARTNER_TAG") else _search_yahoo_official(query, limit) if marketplace == "yahoo" and os.getenv("YAHOO_SHOPPING_APP_ID") else _search_rakuten_official(query, limit) if marketplace == "rakuten" and os.getenv("RAKUTEN_APPLICATION_ID") and os.getenv("RAKUTEN_ACCESS_KEY") else _search_marketplace(marketplace, query, limit) for marketplace in marketplaces),
        return_exceptions=True,
    )

    candidates = []
    for marketplace, result in zip(marketplaces, results_by_marketplace):
        if isinstance(result, Exception):
            candidates.append({
                "marketplace": marketplace,
                "ok": False,
                "error": type(result).__name__,
                "results": [],
            })
            continue

        if marketplace == "amazon" and os.getenv("AMAZON_CLIENT_ID") and os.getenv("AMAZON_CLIENT_SECRET") and os.getenv("AMAZON_PARTNER_TAG"):
            candidates.append({"marketplace": marketplace, "ok": True, "results": result})
            continue
        if marketplace == "yahoo" and os.getenv("YAHOO_SHOPPING_APP_ID"):
            candidates.append({"marketplace": marketplace, "ok": True, "results": result})
            continue
        if marketplace == "rakuten" and os.getenv("RAKUTEN_APPLICATION_ID") and os.getenv("RAKUTEN_ACCESS_KEY"):
            candidates.append({"marketplace": marketplace, "ok": True, "results": result})
            continue

        product_results = await asyncio.gather(
            *(fetch_product_cached(url) for url in result),
            return_exceptions=True,
        )
        items = []
        for url, product_result in zip(result, product_results):
            if isinstance(product_result, Exception):
                continue
            payload, cache_hit = product_result
            items.append({
                "url": url,
                "cache_hit": cache_hit,
                "product": payload,
            })
        candidates.append({
            "marketplace": marketplace,
            "ok": True,
            "results": items,
        })

    flat = [
        item
        for group in candidates
        for item in group["results"]
    ]

    # Do not return an empty catalog just because one or more marketplace
    # credentials/scrapers failed. Use public search as a last-resort
    # discovery path, then normalize the discovered product pages.
    if not flat:
        discovered = await _search_bing_marketplace(query, max(limit * len(marketplaces), limit))
        if discovered:
            normalized = await asyncio.gather(
                *(fetch_product_cached(item["url"]) for item in discovered),
                return_exceptions=True,
            )
            for item, product_result in zip(discovered, normalized):
                if not isinstance(product_result, Exception):
                    payload, cache_hit = product_result
                    flat.append({
                        "url": item["url"],
                        "cache_hit": cache_hit,
                        "product": payload,
                    })
                    continue

                # Discovery is still a usable catalog candidate even when the
                # destination page blocks our detailed product parser.
                flat.append({
                    "url": item["url"],
                    "cache_hit": False,
                    "product": {
                        "product": {
                            "title": item.get("title") or "商品候補",
                            "brand": None,
                            "model": None,
                            "sku": None,
                            "gtin": None,
                            "product_id": None,
                        },
                        "pricing": {
                            "price": None,
                            "list_price": None,
                            "currency": "JPY",
                        },
                        "availability": {"status": "Unknown"},
                        "rating": {"score": None, "count": 0},
                        "seller": {"name": None},
                        "source": {
                            "site": item.get("marketplace") or "marketplace",
                            "marketplace": item.get("marketplace"),
                            "product_id": None,
                            "url": item["url"],
                            "image": None,
                        },
                    },
                })
    priced = [
        item for item in flat
        if item["product"].get("pricing", {}).get("price") is not None
    ]
    priced.sort(key=lambda item: item["product"]["pricing"]["price"])

    return {
        "query": query,
        "marketplaces": marketplaces,
        "count": len(flat),
        "results": flat,
        "price_ranking": [
            {
                "rank": i,
                "url": item["url"],
                "title": item["product"].get("product", {}).get("title"),
                "price": item["product"].get("pricing", {}).get("price"),
                "currency": item["product"].get("pricing", {}).get("currency"),
                "marketplace": item["product"].get("source", {}).get("marketplace"),
                "product_id": item["product"].get("source", {}).get("product_id"),
            }
            for i, item in enumerate(priced, 1)
        ],
    }
