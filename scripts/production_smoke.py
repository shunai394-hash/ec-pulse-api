"""HTTP smoke test against a live EC Pulse API deployment.

Usage:
    EC_PULSE_BASE_URL=https://ec-pulse-api.vercel.app \
    EC_PULSE_SMOKE_API_KEY=... \
    EXPECTED_COMMIT=ddb1dfd \
    python scripts/production_smoke.py

Only the standard library is used. Secrets are never printed. Without
EC_PULSE_SMOKE_API_KEY the authenticated checks are reported as "skipped".
Credit-consuming calls: one successful product fetch (1 credit) and one
Stripe Checkout session; every other check is free or is refunded.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.getenv("EC_PULSE_BASE_URL", "https://ec-pulse-api.vercel.app").rstrip("/")
KEY = os.getenv("EC_PULSE_SMOKE_API_KEY", "").strip()
EXPECTED_COMMIT = os.getenv("EXPECTED_COMMIT", "").strip()[:7]
UA = "EC-Pulse-Production-Smoke/1.0"

results: list[dict] = []


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def request(method, path, *, headers=None, body=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    hdrs = {"User-Agent": UA, **(headers or {})}
    if body is not None:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=hdrs)
    try:
        resp = _opener.open(req, timeout=45)
        status, resp_headers, payload = resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as exc:
        status, resp_headers, payload = exc.code, exc.headers, exc.read()
    text = payload.decode("utf-8", "replace")
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    return status, resp_headers, text, parsed


def check(name, ok, detail="", skipped=False):
    state = "skipped" if skipped else ("pass" if ok else "fail")
    results.append({"check": name, "result": state, "detail": detail})
    print(f"[{state.upper():7}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def detail_of(parsed, text):
    if isinstance(parsed, dict) and "detail" in parsed:
        d = parsed["detail"]
        return d if isinstance(d, str) else json.dumps(d, ensure_ascii=False)[:160]
    return text[:120].replace("\n", " ")


def public_checks():
    status, headers, text, parsed = request("GET", "/", headers={"Accept": "application/json"})
    check("GET / (JSON) is 200", status == 200, f"status={status}")
    commit = (parsed or {}).get("commit")
    env = (parsed or {}).get("environment")
    check("root reports Vercel environment=production", env == "production", f"environment={env}")
    if EXPECTED_COMMIT:
        check("deployed commit matches release", commit == EXPECTED_COMMIT, f"deployed={commit} expected={EXPECTED_COMMIT}")
    else:
        check("deployed commit", bool(commit), f"deployed={commit}")

    status, headers, text, _ = request("GET", "/", headers={"Accept": "text/html"})
    csp = headers.get("Content-Security-Policy", "")
    check("GET / (browser) serves the product landing page", status == 200 and 'id="pricing"' in text and 'id="calc"' in text, f"status={status}")
    check("landing CSP whitelists inline style by hash, no unsafe-inline",
          "style-src 'sha256-" in csp and "unsafe-inline" not in csp, csp[:90])

    for path, want in [
        ("/account", 200), ("/docs", 200), ("/redoc", 200), ("/openapi.json", 200), ("/v1/pricing", 200),
        ("/legal/terms", 200), ("/legal/privacy", 200), ("/legal/billing", 200),
        ("/legal/terms-of-service", 200), ("/legal/privacy-policy", 200),
        ("/legal/billing-and-cancellation", 200), ("/legal/commercial-transactions", 200),
        ("/legal/acceptable-use", 200), ("/robots.txt", 200), ("/favicon.ico", 200), ("/favicon.svg", 200),
        ("/legal/does-not-exist", 404),
    ]:
        status, headers, text, _ = request("GET", path, headers={"Accept": "text/html"})
        check(f"GET {path} is {want}", status == want, f"status={status} type={headers.get('Content-Type', '')}")

    status, _, text, parsed = request("GET", "/health")
    check("GET /health is 200 with database ok", status == 200 and (parsed or {}).get("database") == "ok",
          f"status={status} body={text[:120]}")

    status, headers, _, parsed = request("GET", "/auth/google")
    location = headers.get("Location", "")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    redirect_to = (query.get("redirect_to") or [""])[0]
    host = urllib.parse.urlparse(location).hostname or ""
    check("GET /auth/google redirects to Supabase Google OAuth",
          status == 302 and host.endswith(".supabase.co") and query.get("provider") == ["google"],
          f"status={status} host={host or '-'} detail={detail_of(parsed, '') if status != 302 else ''}")
    check("OAuth callback is the production URL", redirect_to == BASE + "/auth/callback", f"redirect_to={redirect_to or '-'}")
    cookie = headers.get("Set-Cookie", "")
    check("OAuth verifier cookie is HttpOnly, Secure, SameSite=Lax",
          "httponly" in cookie.lower() and "secure" in cookie.lower() and "samesite=lax" in cookie.lower(),
          "cookie flags only; value not shown")

    status, _, text, parsed = request("GET", "/auth/me")
    check("GET /auth/me without session is 401", status == 401, f"status={status} {detail_of(parsed, text)}")
    status, _, text, parsed = request("GET", "/auth/callback")
    check("GET /auth/callback without code is 400", status == 400, f"status={status}")

    status, _, text, parsed = request("POST", "/api/stripe/webhook", raw=b"{}")
    check("Stripe webhook without signature is 400", status == 400, f"status={status} {detail_of(parsed, text)}")
    status, _, text, parsed = request("POST", "/api/stripe/webhook", raw=b'{"id":"evt_smoke"}',
                                      headers={"Stripe-Signature": "t=1,v1=00"})
    check("Stripe webhook secret configured (bad signature is 400, not 503)", status == 400,
          f"status={status} {detail_of(parsed, text)}")

    for path in ("/api/cron/check-monitors", "/api/cron/patrol"):
        status, _, _, _ = request("GET", path)
        check(f"GET {path} without CRON_SECRET is 401", status == 401, f"status={status}")
        status, _, _, _ = request("GET", path, headers={"Authorization": "Bearer wrong-secret"})
        check(f"GET {path} with wrong CRON_SECRET is 401", status == 401, f"status={status}")

    body = {"url": "https://example.com/"}
    status, _, text, parsed = request("POST", "/v1/products", body=body)
    check("POST /v1/products without API key is 401", status == 401, f"status={status} {detail_of(parsed, text)}")
    status, _, text, parsed = request("POST", "/v1/products", body=body, headers={"X-API-Key": "ecp_live_invalid_smoke_key"})
    check("POST /v1/products with invalid API key is 401", status == 401, f"status={status} {detail_of(parsed, text)}")
    status, _, text, parsed = request("GET", "/v1/monitors")
    check("GET /v1/monitors without API key is 401", status == 401, f"status={status}")


def balance():
    status, _, _, parsed = request("GET", "/v1/account", headers={"X-API-Key": KEY})
    if status != 200 or not isinstance(parsed, dict):
        return None
    for key in ("credits_balance", "credits_remaining"):
        if key in parsed:
            return parsed[key]
    return (parsed.get("account") or {}).get("credits_balance")


def authenticated_checks():
    names = [
        "GET /v1/account", "422 validation", "SSRF rejects private targets", "redirect to private IP refunded",
        "POST /v1/products success", "GET /v1/monitors", "POST /v1/monitors validation", "Stripe checkout",
        "429 rate limit",
    ]
    if not KEY:
        for name in names:
            check(name, False, "EC_PULSE_SMOKE_API_KEY not provided", skipped=True)
        return
    auth = {"X-API-Key": KEY}

    status, _, text, parsed = request("GET", "/v1/account", headers=auth)
    start = balance()
    check("GET /v1/account is 200", status == 200, f"status={status} credits={start}")

    status, _, _, _ = request("POST", "/v1/products", body={"url": "not-a-url"}, headers=auth)
    check("POST /v1/products invalid URL is 422", status == 422, f"status={status}")

    ssrf_targets = [
        "http://127.0.0.1/", "http://localhost/", "http://[::1]/", "http://10.0.0.1/", "http://192.168.1.1/",
        "http://172.16.0.1/", "http://169.254.169.254/latest/meta-data/", "http://2130706433/",
        "http://localtest.me/", "http://metadata.google.internal/", "https://ec-pulse-api.vercel.app:8443/",
    ]
    for target in ssrf_targets:
        status, _, text, parsed = request("POST", "/v1/products", body={"url": target}, headers=auth)
        check(f"SSRF rejected: {target}", status == 400, f"status={status} {detail_of(parsed, text)}")
    after_ssrf = balance()
    check("SSRF rejections consume no credits", start is not None and after_ssrf == start, f"before={start} after={after_ssrf}")

    redirect = "https://httpbin.org/redirect-to?url=" + urllib.parse.quote("http://127.0.0.1/", safe="")
    status, _, text, parsed = request("POST", "/v1/products", body={"url": redirect}, headers=auth)
    check("public URL redirecting to 127.0.0.1 is refused", status in (400, 502), f"status={status} {detail_of(parsed, text)}")
    after_redirect = balance()
    check("refused redirect leaves credits unchanged (refund)", after_redirect == after_ssrf,
          f"before={after_ssrf} after={after_redirect}")

    status, headers, text, parsed = request("POST", "/v1/products", body={"url": "https://example.com/"}, headers=auth)
    used = headers.get("X-EC-Credits-Used")
    check("POST /v1/products succeeds on a public page", status in (200, 502),
          f"status={status} credits_used={used} {'' if status == 200 else detail_of(parsed, text)}")
    after_fetch = balance()
    expected = (after_redirect - 1) if status == 200 and after_redirect is not None else after_redirect
    check("credit ledger matches outcome (1 on success, 0 on upstream failure)", after_fetch == expected,
          f"before={after_redirect} after={after_fetch}")

    status, _, text, parsed = request("GET", "/v1/monitors", headers=auth)
    check("GET /v1/monitors is 200", status == 200, f"status={status}")
    status, _, text, parsed = request("POST", "/v1/monitors", headers=auth,
                                      body={"url": "https://example.com/", "webhook_url": "http://192.168.0.10/hook"})
    check("POST /v1/monitors private webhook is 400", status == 400, f"status={status} {detail_of(parsed, text)}")
    status, _, _, _ = request("POST", "/v1/monitors", headers=auth,
                              body={"url": "https://example.com/", "webhook_url": "https://example.com/h", "interval_minutes": 1})
    check("POST /v1/monitors interval below 5 minutes is 422", status == 422, f"status={status}")

    status, _, text, parsed = request("POST", "/v1/billing/checkout?plan=pro", headers=auth)
    url = (parsed or {}).get("url", "") if isinstance(parsed, dict) else ""
    check("Stripe Checkout session can be created for Pro",
          status == 200 and urllib.parse.urlparse(url).hostname == "checkout.stripe.com",
          f"status={status} host={urllib.parse.urlparse(url).hostname if url else '-'} {'' if status == 200 else detail_of(parsed, text)}")

    statuses = []
    for _ in range(40):
        status, headers, _, _ = request("GET", "/v1/monitors", headers=auth)
        statuses.append(status)
        if status == 429:
            check("rate limit returns 429 with Retry-After", bool(headers.get("Retry-After")),
                  f"after {len(statuses)} requests, Retry-After={headers.get('Retry-After')}")
            break
    else:
        check("rate limit returns 429", False, f"no 429 in {len(statuses)} requests (plan limit may be higher)")
    time.sleep(1)


def main():
    print(f"Target: {BASE}")
    public_checks()
    authenticated_checks()
    failed = [r for r in results if r["result"] == "fail"]
    summary = {
        "target": BASE,
        "passed": sum(r["result"] == "pass" for r in results),
        "failed": len(failed),
        "skipped": sum(r["result"] == "skipped" for r in results),
        "results": results,
    }
    with open(os.getenv("SMOKE_REPORT", "production-smoke.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
