"""SSRF defences exercised through the real httpx/httpcore client path.

``fetch_product`` and ``safe_async_client`` run unmodified, including DNS
re-resolution and the private-address check at TCP connect time. Two test
seams are used:

* ``_resolve_public_addresses`` is replaced by a scripted resolver, so
  hostnames resolve to chosen addresses without real DNS (still checked by
  the production ``_blocked_ip``).
* httpcore's base backend is redirected to a local test server *after* the
  production safety checks ran, so allowed requests have something to talk to.
"""
import asyncio
import ipaddress
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpcore._backends.auto as auto_backend
import pytest

from app.services import product_parser, url_safety

PAGE = """<html><head><script type="application/ld+json">{"@type":"Product","name":"Kettle",
"offers":{"@type":"Offer","price":"1980","priceCurrency":"JPY"}}</script></head></html>"""


class Server:
    def __init__(self):
        self.routes = {}
        self.request_lines = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                server.request_lines.append(self.requestline)
                status, headers, body = server.routes.get(self.path, (404, {}, b""))
                self.send_response(status)
                for k, v in headers.items():
                    if k != "Content-Length":
                        self.send_header(k, v)
                if headers.get("Content-Length") != "omit":
                    self.send_header("Content-Length", headers.get("Content-Length", str(len(body))))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def net(monkeypatch):
    server = Server()
    resolutions = {}
    calls = []

    def resolve(host, port):
        calls.append((host, port))
        try:
            ipaddress.ip_address(host.strip("[]"))
            answers = [host.strip("[]")]  # getaddrinfo returns an IP literal as-is
        except ValueError:
            answers = resolutions.get(host, ["93.184.216.34"])
        address = answers.pop(0) if len(answers) > 1 else answers[0]
        if url_safety._blocked_ip(address):
            raise ValueError("Private or local network URLs are not allowed")
        return {address}

    real_connect = auto_backend.AutoBackend.connect_tcp

    async def to_test_server(self, host, port, *args, **kwargs):
        return await real_connect(self, "127.0.0.1", server.port, *args, **kwargs)

    monkeypatch.setattr(url_safety, "_resolve_public_addresses", resolve)
    monkeypatch.setattr(auto_backend.AutoBackend, "connect_tcp", to_test_server)
    yield server, resolutions, calls
    server.close()


def fetch(url):
    return asyncio.run(product_parser.fetch_product(url))


def test_allowed_redirect_chain_is_followed_and_parsed(net):
    server, _, _ = net
    server.routes["/a"] = (301, {"Location": "/b"}, b"")
    server.routes["/b"] = (302, {"Location": "http://shop.example.com/c"}, b"")
    server.routes["/c"] = (200, {"Content-Type": "text/html"}, PAGE.encode())

    data = fetch("http://shop.example.com/a")

    assert data["pricing"] == {"price": 1980.0, "list_price": None, "currency": "JPY"}
    assert data["source"]["url"] == "http://shop.example.com/c"
    assert len(server.request_lines) == 3


@pytest.mark.parametrize("location", [
    "http://169.254.169.254/latest/meta-data/",
    "http://127.0.0.1/admin",
    "http://[::ffff:127.0.0.1]/admin",
    "http://[::1]/",
    "http://10.0.0.5/",
    "http://0.0.0.0/",
    "http://shop.example.com:8080/",
    "file:///etc/passwd",
    "http://user:pass@shop.example.com/",
])
def test_redirect_to_unsafe_destination_is_refused(net, location):
    server, _, _ = net
    server.routes["/start"] = (302, {"Location": location}, b"")

    with pytest.raises(ValueError):
        fetch("http://shop.example.com/start")
    assert len(server.request_lines) == 1


def test_redirect_to_host_that_resolves_private_is_refused(net):
    server, resolutions, _ = net
    resolutions["internal.example.com"] = ["10.1.2.3"]
    server.routes["/start"] = (302, {"Location": "http://internal.example.com/"}, b"")

    with pytest.raises(ValueError, match="Private or local"):
        fetch("http://shop.example.com/start")
    assert len(server.request_lines) == 1


def test_redirect_loop_stops_at_limit(net):
    server, _, _ = net
    server.routes["/loop"] = (302, {"Location": "/loop"}, b"")

    with pytest.raises(ValueError, match="Too many redirects"):
        fetch("http://shop.example.com/loop")
    assert len(server.request_lines) == url_safety.MAX_REDIRECTS + 1


def test_dns_rebinding_between_validation_and_connect_is_refused(net):
    server, resolutions, calls = net
    # First answer (validation) is public; the answer at connect time is not.
    resolutions["rebind.example.com"] = ["93.184.216.34", "127.0.0.1"]
    server.routes["/"] = (200, {}, PAGE.encode())

    with pytest.raises(ValueError, match="Private or local"):
        fetch("http://rebind.example.com/")
    assert [c[0] for c in calls] == ["rebind.example.com", "rebind.example.com"]
    assert server.request_lines == []


@pytest.mark.parametrize("var", ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "all_proxy"])
def test_proxy_environment_variables_are_ignored(net, monkeypatch, var):
    server, _, calls = net
    monkeypatch.setenv(var, "http://proxy.example.net:3128")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    server.routes["/p"] = (200, {}, PAGE.encode())

    fetch("http://shop.example.com/p")

    # Direct origin-form request to the shop, never an absolute-form proxy request.
    assert server.request_lines == ["GET /p HTTP/1.1"]
    assert all(host == "shop.example.com" for host, _ in calls)


def test_oversized_response_is_refused(net, monkeypatch):
    server, _, _ = net
    monkeypatch.setattr(product_parser, "MAX_RESPONSE_BYTES", 1000)
    server.routes["/declared"] = (200, {}, b"x" * 5000)
    with pytest.raises(ValueError, match="Product page response is too large"):
        fetch("http://shop.example.com/declared")

    # No Content-Length (body delimited by connection close): the streaming
    # byte ceiling still stops the read.
    server.routes["/streamed"] = (200, {"Content-Length": "omit"}, b"x" * 5000)
    with pytest.raises(ValueError, match="HTTP response is too large"):
        fetch("http://shop.example.com/streamed")


def test_research_ingest_and_marketplace_scrape_handle_plain_responses(net, monkeypatch):
    from app.services import product_search, research_ingest

    server, _, _ = net
    server.routes["/review"] = (302, {"Location": "/review2"}, b"")
    server.routes["/review2"] = (200, {"Content-Type": "text/html"},
                                 "<html><body><p>蓋がすぐ壊れる。値段の割に品質が悪いです。</p></body></html>".encode())
    item = asyncio.run(research_ingest.fetch_public_comments("http://reviews.example.com/review", 10))
    assert item["url"]

    # The test server speaks plain HTTP only.
    monkeypatch.setitem(product_search.SEARCH_URLS, "yahoo", "http://shopping.yahoo.co.jp/search?p={query}")
    server.routes["/search?p=kettle"] = (200, {"Content-Type": "text/html"}, b"<html></html>")
    links = asyncio.run(product_search._search_marketplace("yahoo", "kettle", 3))
    assert links == []


def test_validate_rejects_unsafe_urls_without_network(net):
    _, _, calls = net
    for url in ["ftp://shop.example.com/", "http://shop.example.com:22/", "http:///nohost",
                "http://user@shop.example.com/", "http://" + "a" * 2050 + ".com/"]:
        with pytest.raises(ValueError):
            asyncio.run(url_safety.validate_public_url(url))
    assert calls == []
