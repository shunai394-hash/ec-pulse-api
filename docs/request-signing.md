# App request signing

EC Pulse API supports HMAC-SHA256 request signing for app clients.

## Headers

```text
X-API-Key: ecp_live_...
X-EC-Timestamp: 1760000000
X-EC-Signature: sha256=<hex digest>
```

The signature covers the timestamp, HTTP method, exact request target (path plus raw query string when present), and SHA-256 hash of the exact request body:

```text
timestamp.METHOD.path.sha256(body)
```

The API key is the HMAC secret. The server accepts signatures only when the timestamp is within 5 minutes of server time.

Canonical form details:

- `path` is the request target exactly as sent on the wire: the raw path, still percent-encoded, followed by `?` and the raw query string when there is one (for example `/v1/research/runs?limit=5&url=https%3A%2F%2Fexample.com`). Parameter order and encoding are significant; do not re-encode or sort them.
- `timestamp` is Unix seconds as plain ASCII digits (no sign, spaces or decimals).
- A signed request can be replayed unchanged within the 5-minute window. Do not rely on the signature alone to make non-idempotent requests safe to expose.

## Python

```python
import hashlib
import hmac
import time

def sign_request(api_key, method, path, body=b""):
    timestamp = str(int(time.time()))
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{timestamp}.{method.upper()}.{path}.{body_hash}".encode()
    signature = hmac.new(api_key.encode(), message, hashlib.sha256).hexdigest()
    return {
        "X-API-Key": api_key,
        "X-EC-Timestamp": timestamp,
        "X-EC-Signature": f"sha256={signature}",
    }
```

## JavaScript

```javascript
async function signRequest(apiKey, method, path, body = "") {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const bytes = new TextEncoder().encode(body);
  const bodyHashBuffer = await crypto.subtle.digest("SHA-256", bytes);
  const bodyHash = [...new Uint8Array(bodyHashBuffer)]
    .map(b => b.toString(16).padStart(2, "0")).join("");
  const message = `${timestamp}.${method.toUpperCase()}.${path}.${bodyHash}`;

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(apiKey),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signatureBuffer = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(message),
  );
  const signature = [...new Uint8Array(signatureBuffer)]
    .map(b => b.toString(16).padStart(2, "0")).join("");

  return {
    "X-API-Key": apiKey,
    "X-EC-Timestamp": timestamp,
    "X-EC-Signature": `sha256=${signature}`,
  };
}
```

Keep the API key in secure app storage. Never ship a shared signing key in a browser bundle or expose it in client-side source.
