import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.services.url_safety import MAX_REDIRECTS, next_redirect, read_response_bytes, safe_async_client, validate_public_url, is_redirect_response

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "EC-Pulse/0.1 (+https://ec-pulse-api.vercel.app)"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024

MARKETPLACES = {
    "amazon.co.jp": "amazon",
    "www.amazon.co.jp": "amazon",
    "rakuten.co.jp": "rakuten",
    "item.rakuten.co.jp": "rakuten",
    "shopping.yahoo.co.jp": "yahoo",
    "lohaco.yahoo.co.jp": "yahoo",
}

def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None

def _jsonld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    items = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or tag.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            items.extend(x for x in data if isinstance(x, dict))
        elif isinstance(data, dict):
            items.append(data)
    return items

def _is_type(item: dict[str, Any], type_name: str) -> bool:
    value = item.get("@type")
    if isinstance(value, list):
        return type_name in value
    return value == type_name


def _find_product(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in items:
        if _is_type(item, "Product"):
            return item
        graph = item.get("@graph")
        if isinstance(graph, list):
            for node in graph:
                if isinstance(node, dict) and _is_type(node, "Product"):
                    return node
    return None


def _offers_dict(offers: Any) -> dict[str, Any]:
    if isinstance(offers, dict):
        return offers
    if isinstance(offers, list):
        for offer in offers:
            if isinstance(offer, dict) and offer.get("price") is not None:
                return offer
        return next((offer for offer in offers if isinstance(offer, dict)), {})
    return {}

def _number(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None

def _marketplace(host: str) -> str:
    host = host.lower().split(":")[0]
    return MARKETPLACES.get(host, "web")

def _product_id(marketplace: str, path: str) -> str | None:
    if marketplace == "amazon":
        match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", path, re.I)
        return match.group(1).upper() if match else None
    if marketplace == "rakuten":
        parts = [part for part in path.split("/") if part]
        return parts[-1] if parts else None
    if marketplace == "yahoo":
        parts = [part for part in path.split("/") if part]
        return parts[-1] if parts else None
    return None

async def fetch_product(url: str) -> dict[str, Any]:
    current_url = await validate_public_url(url)
    async with safe_async_client(
        follow_redirects=False,
        timeout=15.0,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            async with client.stream("GET", current_url) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit() and int(content_length) > MAX_RESPONSE_BYTES:
                    raise ValueError("Product page response is too large")
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

    soup = BeautifulSoup(body, "html.parser")
    product = _find_product(_jsonld(soup)) or {}
    offers = _offers_dict(product.get("offers"))
    final_url = str(response.url)
    final_parsed = urlparse(final_url)
    marketplace = _marketplace(final_parsed.netloc)
    product_id = (
        product.get("sku")
        or product.get("mpn")
        or product.get("gtin13")
        or _product_id(marketplace, final_parsed.path)
    )

    title = product.get("name") or _meta(soup, "og:title") or (
        soup.title.get_text(strip=True) if soup.title else None
    )
    image = product.get("image") or _meta(soup, "og:image")
    if isinstance(image, list):
        image = next((item for item in image if isinstance(item, str)), None)

    return {
        "product": {
            "title": title,
            "brand": (
                product.get("brand", {}).get("name")
                if isinstance(product.get("brand"), dict)
                else product.get("brand")
            ),
            "model": product.get("model"),
            "sku": product.get("sku"),
            "gtin": product.get("gtin13") or product.get("gtin"),
            "product_id": product_id,
        },
        "pricing": {
            "price": _number(offers.get("price") or product.get("price")),
            # Schema.org highPrice is a range ceiling, not necessarily an MSRP/list price.
            # Do not expose it as list_price because downstream profit calculations may trust it.
            "list_price": None,
            "currency": offers.get("priceCurrency"),
        },
        "availability": {
            "status": offers.get("availability"),
        },
        "rating": {
            "score": _number(
                product.get("aggregateRating", {}).get("ratingValue")
                if isinstance(product.get("aggregateRating"), dict)
                else None
            ),
            "count": int(
                _number(
                    product.get("aggregateRating", {}).get("reviewCount")
                    or product.get("aggregateRating", {}).get("ratingCount")
                )
                or 0
            ),
        },
        "seller": {
            "name": (
                offers.get("seller", {}).get("name")
                if isinstance(offers.get("seller"), dict)
                else offers.get("seller")
            ),
        },
        "source": {
            "site": final_parsed.netloc,
            "marketplace": marketplace,
            "product_id": product_id,
            "url": final_url,
            "image": image,
        },
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
