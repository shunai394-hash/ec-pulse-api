import hashlib
import hmac
import re
import time


SIGNATURE_HEADER = "X-EC-Signature"
TIMESTAMP_HEADER = "X-EC-Timestamp"
MAX_CLOCK_SKEW_SECONDS = 300
_TIMESTAMP_RE = re.compile(r"[0-9]{1,12}")


def signature_payload(timestamp: str, method: str, path: str, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    return f"{timestamp}.{method.upper()}.{path}.{body_hash}".encode("utf-8")


def sign_request(api_key: str, timestamp: str, method: str, path: str, body: bytes) -> str:
    if not api_key:
        raise ValueError("api_key is required")
    return "sha256=" + hmac.new(
        api_key.encode("utf-8"),
        signature_payload(timestamp, method, path, body),
        hashlib.sha256,
    ).hexdigest()


def verify_request_signature(
    api_key: str,
    timestamp: str | None,
    signature: str | None,
    method: str,
    path: str,
    body: bytes,
    now: int | None = None,
) -> None:
    if not timestamp or not signature:
        raise ValueError("Missing request signature headers")
    # Only plain ASCII digits: int() would also accept " 1", "+1", "1_0" and
    # non-ASCII digits, giving one timestamp many signable spellings.
    if not _TIMESTAMP_RE.fullmatch(timestamp):
        raise ValueError("Invalid request signature timestamp")
    ts = int(timestamp)

    current = int(time.time()) if now is None else now
    if abs(current - ts) > MAX_CLOCK_SKEW_SECONDS:
        raise ValueError("Request signature timestamp is expired")

    expected = sign_request(api_key, timestamp, method, path, body)
    # compare_digest raises TypeError for non-ASCII str input (an HTTP 500);
    # compare bytes instead.
    if not hmac.compare_digest(signature.encode("utf-8", "surrogateescape"), expected.encode()):
        raise ValueError("Invalid request signature")
