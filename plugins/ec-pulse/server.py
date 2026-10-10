#!/usr/bin/env python3
"""Local stdio MCP adapter for EC Pulse.

Secrets are read from environment variables and are never printed by this process.
The adapter performs one upstream request per tool call and never retries automatically.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://ec-pulse-api.vercel.app"
TIMEOUT_SECONDS = 20
MAX_RESPONSE_BYTES = 5 * 1024 * 1024

def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None, *, read_only: bool = True, destructive: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": properties, "required": required or []},
        "annotations": {"readOnlyHint": read_only, "destructiveHint": destructive, "title": name},
    }

TOOLS = [
    _tool("ec_product_search", "Search EC Pulse product data across Amazon, Rakuten, and Yahoo Japan.", {
        "query": {"type": "string", "minLength": 1, "maxLength": 200},
        "marketplaces": {"type": "array", "items": {"type": "string", "enum": ["amazon", "rakuten", "yahoo"]}, "minItems": 1, "maxItems": 3},
        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
    }, ["query"]),
    _tool("ec_product_get", "Retrieve normalized product data for one public product URL through EC Pulse.", {
        "url": {"type": "string", "format": "uri", "minLength": 1}
    }, ["url"]),
    _tool("ec_product_compare", "Compare normalized product data and observed prices for 2 to 20 public product URLs.", {
        "urls": {"type": "array", "items": {"type": "string", "format": "uri"}, "minItems": 2, "maxItems": 20}
    }, ["urls"]),
    _tool("ec_research_ingest", "Collect publicly accessible comments from supported URLs and return EC Pulse research analysis.", {
        "urls": {"type": "array", "items": {"type": "string", "format": "uri"}, "minItems": 1, "maxItems": 20},
        "max_comments_per_url": {"type": "integer", "minimum": 1, "maximum": 500}
    }, ["urls"]),
    _tool("ec_consumer_insights", "Analyze supplied customer comments with EC Pulse's rule-based pain-point and term extraction.", {
        "comments": {"type": "array", "items": {"type": "string", "maxLength": 2000}, "minItems": 1, "maxItems": 5000},
        "source": {"type": "string", "maxLength": 50}
    }, ["comments"]),
    _tool("ec_monitor_create", "Create a price monitor. This changes persistent account state and requires explicit user intent.", {
        "url": {"type": "string", "format": "uri"},
        "interval_minutes": {"type": "integer", "minimum": 5, "maximum": 10080},
        "webhook_url": {"type": "string", "format": "uri"},
        "target_price": {"type": "number", "exclusiveMinimum": 0, "description": "Optional alert threshold in listed currency"}
    }, ["url", "webhook_url"], read_only=False, destructive=False),
    _tool("ec_monitor_list", "List price monitors owned by the authenticated EC Pulse account.", {}),
    _tool("ec_monitor_history", "Read price history for one monitor owned by the authenticated EC Pulse account.", {
        "monitor_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "limit": {"type": "integer", "minimum": 1, "maximum": 1000}
    }, ["monitor_id"]),
    _tool("ec_monitor_opportunity", "Analyze price movement for one owned monitor and return the EC Pulse opportunity signal.", {
        "monitor_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "limit": {"type": "integer", "minimum": 2, "maximum": 1000}
    }, ["monitor_id"]),
    _tool("ec_account", "Return the authenticated account plan, remaining credits, and usage summary. The raw API key is never returned.", {}),
]

TOOL_MAP = {t["name"]: t for t in TOOLS}

def _api_key() -> str:
    value = os.getenv("EC_PULSE_API_KEY", "").strip()
    if not value:
        raise RuntimeError("EC_PULSE_API_KEY is not configured")
    return value

def _base_url() -> str:
    # An unset variable can reach the process as an empty string via .mcp.json.
    value = (os.getenv("EC_PULSE_API_BASE_URL") or "").strip().rstrip("/") or DEFAULT_BASE_URL
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("EC_PULSE_API_BASE_URL must be a valid http(s) URL")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Non-local EC_PULSE_API_BASE_URL must use HTTPS")
    return value

def _validate_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("URL must be a non-empty string")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed")
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise ValueError("URL host is required")
    if host in {"localhost", "localhost.localdomain", "ip6-localhost"}:
        raise ValueError("Local/private destinations are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast or address.is_reserved):
        raise ValueError("Local/private destinations are not allowed")
    return value

def _validate_args(name: str, args: Any) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise ValueError("Tool arguments must be a JSON object")
    allowed = set(TOOL_MAP[name]["inputSchema"]["properties"])
    unknown = set(args) - allowed
    if unknown:
        raise ValueError("Unknown argument(s): " + ", ".join(sorted(unknown)))
    if name == "ec_product_search":
        q = args.get("query")
        if not isinstance(q, str) or not 1 <= len(q.strip()) <= 200:
            raise ValueError("query must contain 1-200 characters")
        markets = args.get("marketplaces", ["amazon", "rakuten", "yahoo"])
        if not isinstance(markets, list) or not 1 <= len(markets) <= 3 or len(set(markets)) != len(markets) or any(x not in {"amazon", "rakuten", "yahoo"} for x in markets):
            raise ValueError("marketplaces must contain 1-3 unique values from amazon, rakuten, yahoo")
        limit = args.get("limit", 5)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise ValueError("limit must be between 1 and 10")
    elif name == "ec_product_get":
        _validate_url(args.get("url"))
    elif name in {"ec_product_compare", "ec_research_ingest"}:
        urls = args.get("urls")
        minimum = 2 if name == "ec_product_compare" else 1
        if not isinstance(urls, list) or not minimum <= len(urls) <= 20:
            raise ValueError(f"urls must contain {minimum}-20 items")
        for item in urls:
            _validate_url(item)
        if name == "ec_research_ingest":
            value = args.get("max_comments_per_url", 500)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 500:
                raise ValueError("max_comments_per_url must be between 1 and 500")
    elif name == "ec_consumer_insights":
        comments = args.get("comments")
        if not isinstance(comments, list) or not 1 <= len(comments) <= 5000 or any(not isinstance(x, str) or len(x) > 2000 for x in comments):
            raise ValueError("comments must contain 1-5000 strings, each at most 2000 characters")
        source = args.get("source")
        if source is not None and (not isinstance(source, str) or len(source) > 50):
            raise ValueError("source must be at most 50 characters")
    elif name == "ec_monitor_create":
        _validate_url(args.get("url"))
        _validate_url(args.get("webhook_url"))
        interval = args.get("interval_minutes", 60)
        if isinstance(interval, bool) or not isinstance(interval, int) or not 5 <= interval <= 10080:
            raise ValueError("interval_minutes must be between 5 and 10080")
        target = args.get("target_price")
        if target is not None and (isinstance(target, bool) or not isinstance(target, (int, float)) or target <= 0):
            raise ValueError("target_price must be a positive number")
    elif name in {"ec_monitor_history", "ec_monitor_opportunity"}:
        monitor_id = args.get("monitor_id")
        if not isinstance(monitor_id, str) or not 1 <= len(monitor_id) <= 200:
            raise ValueError("monitor_id must be 1-200 characters")
        if "limit" in args:
            limit = args["limit"]
            minimum = 2 if name == "ec_monitor_opportunity" else 1
            if isinstance(limit, bool) or not isinstance(limit, int) or not minimum <= limit <= 1000:
                raise ValueError(f"limit must be between {minimum} and 1000")
    return args

def _sign(key: str, timestamp: str, method: str, path: str, body: bytes) -> str:
    digest = hashlib.sha256(body).hexdigest()
    payload = f"{timestamp}.{method.upper()}.{path}.{digest}".encode()
    return "sha256=" + hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()

def _api_request(method: str, path: str, *, body: dict[str, Any] | None = None, query: dict[str, Any] | None = None) -> Any:
    key = _api_key()
    url = _base_url() + path
    if query:
        url += "?" + urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode() if body is not None else b""
    headers = {"Accept": "application/json", "User-Agent": "EC-Pulse-Claude-Plugin/0.1.0", "X-API-Key": key}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if os.getenv("EC_PULSE_REQUIRE_REQUEST_SIGNATURE", "").lower() in {"1", "true", "yes"}:
        timestamp = str(int(time.time()))
        headers["X-EC-Timestamp"] = timestamp
        headers["X-EC-Signature"] = _sign(key, timestamp, method, path, payload)
    req = Request(url, data=payload if method != "GET" else None, headers=headers, method=method)
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RuntimeError("EC Pulse response exceeded the plugin response limit")
        return json.loads(raw.decode("utf-8")) if raw else {}
    except HTTPError as exc:
        if exc.code == 401:
            raise RuntimeError("EC Pulse authentication failed (401)") from exc
        if exc.code == 402:
            raise RuntimeError("EC Pulse credits are insufficient (402)") from exc
        if exc.code == 403:
            raise RuntimeError("EC Pulse authorization failed (403)") from exc
        if exc.code == 404:
            raise RuntimeError("EC Pulse resource was not found (404)") from exc
        if exc.code == 429:
            raise RuntimeError("EC Pulse rate limit exceeded (429)") from exc
        if 400 <= exc.code < 500:
            raise RuntimeError(f"EC Pulse request was rejected ({exc.code})") from exc
        raise RuntimeError(f"EC Pulse upstream service error ({exc.code})") from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise RuntimeError("EC Pulse request timed out") from exc
        raise RuntimeError(f"EC Pulse connection failed ({type(exc.reason).__name__})") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("EC Pulse returned invalid JSON") from exc

def _call_tool(name: str, args: Any) -> Any:
    args = _validate_args(name, args)
    if name == "ec_product_search":
        return _api_request("POST", "/v1/products/search", body={"query": args["query"].strip(), "marketplaces": args.get("marketplaces", ["amazon", "rakuten", "yahoo"]), "limit": args.get("limit", 5)})
    if name == "ec_product_get":
        return _api_request("GET", "/v1/products", query={"url": args["url"]})
    if name == "ec_product_compare":
        return _api_request("POST", "/v1/products/compare", body={"urls": args["urls"]})
    if name == "ec_research_ingest":
        return _api_request("POST", "/v1/research/ingest", body={"urls": args["urls"], "max_comments_per_url": args.get("max_comments_per_url", 500)})
    if name == "ec_consumer_insights":
        return _api_request("POST", "/v1/consumer-insights/analyze", body={"comments": args["comments"], "source": args.get("source")})
    if name == "ec_monitor_create":
        return _api_request("POST", "/v1/monitors", body={"url": args["url"], "interval_minutes": args.get("interval_minutes", 60), "webhook_url": args["webhook_url"], **({"target_price": args["target_price"]} if "target_price" in args else {})})
    if name == "ec_monitor_list":
        return _api_request("GET", "/v1/monitors")
    if name == "ec_monitor_history":
        return _api_request("GET", f"/v1/monitors/{quote(args['monitor_id'], safe='')}/history", query={"limit": args.get("limit", 100)})
    if name == "ec_monitor_opportunity":
        return _api_request("GET", f"/v1/monitors/{quote(args['monitor_id'], safe='')}/opportunity", query={"limit": args.get("limit", 100)})
    if name == "ec_account":
        return _api_request("GET", "/v1/account")
    raise ValueError("Unknown tool")

def _tool_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}

def _handle(message: Any) -> dict[str, Any] | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    method = message.get("method")
    request_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "ec-pulse", "version": "0.1.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params")
        if not isinstance(params, dict):
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "params must be an object"}}
        name = params.get("name")
        if name not in TOOL_MAP:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Unknown tool"}}
        try:
            value = _call_tool(name, params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, separators=(",", ":"))}], "isError": False}}
        except (ValueError, RuntimeError) as exc:
            return {"jsonrpc": "2.0", "id": request_id, "result": _tool_error(str(exc))}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": request_id, "result": _tool_error(f"Unexpected plugin error: {type(exc).__name__}")}
    if method is None:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32600, "message": "Invalid Request"}}
    if request_id is None:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}

def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = _handle(message)
        except json.JSONDecodeError:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        except Exception:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": "Internal plugin error"}}
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
