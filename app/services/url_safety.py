import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

MAX_REDIRECTS = 5
MAX_URL_LENGTH = 2048
_ALLOWED_PORTS = {80, 443}


_NAT64_PREFIXES = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> list[ipaddress.IPv4Address]:
    """IPv4 addresses reachable through IPv6 transition mechanisms."""
    embedded = []
    if ip.ipv4_mapped:
        embedded.append(ip.ipv4_mapped)
    if ip.sixtofour:
        embedded.append(ip.sixtofour)
    if ip.teredo:
        embedded.extend(ip.teredo)
    if any(ip in prefix for prefix in _NAT64_PREFIXES):
        embedded.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    return embedded


def _blocked_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address):
        # Do not rely on the Python version's special-purpose registry for
        # transition prefixes: check the embedded IPv4 destination explicitly.
        if any(_blocked_ip(str(v4)) for v4 in _embedded_ipv4(ip)):
            return True
    # RFC 6598 shared address space is not considered private by Python's
    # ipaddress module, but it is not a safe destination for server-side fetches.
    shared = ipaddress.ip_network("100.64.0.0/10")
    return (
        ip in shared
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_public_addresses(host: str, port: int) -> set[str]:
    try:
        addresses = socket.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ValueError("Unable to resolve the URL host") from exc

    resolved = {item[4][0] for item in addresses if item[4]}
    if not resolved or any(_blocked_ip(address) for address in resolved):
        raise ValueError("Private or local network URLs are not allowed")
    return resolved


async def validate_public_url(url: str) -> str:
    if len(url) > MAX_URL_LENGTH:
        raise ValueError("URL is too long")
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("A valid public http(s) URL is required")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not allowed")
    if port not in (None, *_ALLOWED_PORTS):
        raise ValueError("Only ports 80 and 443 are allowed")

    await asyncio.to_thread(
        _resolve_public_addresses,
        parsed.hostname,
        port or (443 if parsed.scheme == "https" else 80),
    )
    return url


def next_redirect(base_url: str, location: str) -> str:
    return urljoin(base_url, location)


_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def is_redirect_response(response) -> bool:
    """True for redirect statuses, with or without a Location header.

    httpx 0.28 has no ``Response.is_permanent_redirect``; the previous
    ``is_redirect or is_permanent_redirect`` check raised AttributeError for
    every non-redirect response.
    """
    return response.status_code in _REDIRECT_STATUSES


def safe_async_transport():
    """
    Build an httpx transport that re-resolves the destination immediately
    before each new TCP connection and refuses private/local destinations.

    The HTTP Host header and TLS SNI remain the original hostname because
    httpcore performs TLS after the TCP connection is established.
    """
    import httpcore
    import httpx

    class _SafeNetworkBackend(httpcore.AsyncNetworkBackend):
        def __init__(self) -> None:
            from httpcore._backends.auto import AutoBackend
            self._backend = AutoBackend()

        async def connect_tcp(
            self,
            host: str,
            port: int,
            timeout: float | None = None,
            local_address: str | None = None,
            socket_options=None,
        ):
            resolved = await asyncio.to_thread(_resolve_public_addresses, host, port)
            target = next(iter(sorted(resolved)))
            return await self._backend.connect_tcp(
                target,
                port,
                timeout=timeout,
                local_address=local_address,
                socket_options=socket_options,
            )

        async def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options=None):
            raise ValueError("Unix socket connections are not allowed")

        async def sleep(self, seconds: float) -> None:
            await self._backend.sleep(seconds)

    transport = httpx.AsyncHTTPTransport(trust_env=False)
    transport._pool._network_backend = _SafeNetworkBackend()
    return transport


async def read_response_bytes(response, max_bytes: int) -> bytes:
    """Read an HTTP response with a hard application-level byte ceiling."""
    chunks = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("HTTP response is too large")
        chunks.append(chunk)
    return b"".join(chunks)


def safe_async_client(**kwargs):
    import httpx

    return httpx.AsyncClient(
        transport=safe_async_transport(),
        trust_env=False,
        **kwargs,
    )
