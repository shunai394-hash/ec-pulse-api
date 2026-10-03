"""Real-browser smoke test (Chromium via Playwright) against a live deployment.

Checks each page at 390 / 820 / 1366 px for CSP violations, console and page
errors, failed or mixed-content requests, and horizontal overflow, and checks
that in-page navigation targets exist. Screenshots go to SCREENSHOT_DIR.
"""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

BASE = os.getenv("EC_PULSE_BASE_URL", "https://ec-pulse-api.vercel.app").rstrip("/")
OUT = os.getenv("SCREENSHOT_DIR", "browser-smoke")
PAGES = ["/", "/account", "/docs", "/legal/terms", "/legal/commercial-transactions"]
VIEWPORTS = {"mobile": (390, 844), "tablet": (820, 1180), "desktop": (1366, 900)}
# Same-page anchors and site links every visitor relies on.
LANDING_LINKS = ["#features", "#pricing", "#quickstart", "#security", "/docs", "/account",
                 "/legal/terms", "/legal/privacy", "/legal/billing", "/legal/commercial-transactions"]

CSP_LISTENER = """
window.__csp = [];
document.addEventListener('securitypolicyviolation', e => window.__csp.push(
  e.violatedDirective + ' blocked ' + (e.blockedURI || 'inline')));
"""


async def check_page(browser, viewport_name, size, path):
    context = await browser.new_context(viewport={"width": size[0], "height": size[1]})
    await context.add_init_script(CSP_LISTENER)
    page = await context.new_page()
    console_errors, page_errors, failed, mixed = [], [], [], []
    page.on("console", lambda m: console_errors.append(m.text[:200]) if m.type == "error" else None)
    page.on("pageerror", lambda e: page_errors.append(str(e)[:200]))
    page.on("requestfailed", lambda r: failed.append(f"{r.url[:120]} {r.failure}"))
    if BASE.startswith("https://"):
        page.on("request", lambda r: mixed.append(r.url[:120]) if r.url.startswith("http://") else None)
    response = await page.goto(BASE + path, wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(1000)
    metrics = await page.evaluate(
        "({sw: document.documentElement.scrollWidth, iw: window.innerWidth,"
        " bg: getComputedStyle(document.body).backgroundColor, csp: window.__csp,"
        " title: document.title, swagger: !!document.querySelector('.swagger-ui .info')})"
    )
    os.makedirs(OUT, exist_ok=True)
    await page.screenshot(path=f"{OUT}/{viewport_name}{path.replace('/', '_') or '_root'}.png", full_page=True)
    missing_links = []
    if path == "/":
        for href in LANDING_LINKS:
            if href.startswith("#"):
                if not await page.locator(href).count():
                    missing_links.append(href)
            elif not await page.locator(f'a[href="{href}"]').count():
                missing_links.append(href)
    # The account page's own fetches answer 401 for anonymous visitors; that is expected.
    console_errors = [e for e in console_errors if not (path == "/account" and "401" in e)]
    result = {
        "page": path, "viewport": viewport_name, "status": response.status if response else None,
        "title": metrics["title"], "horizontal_overflow": metrics["sw"] > metrics["iw"],
        "styled": metrics["bg"] not in ("rgba(0, 0, 0, 0)", "transparent") or path == "/docs",
        "swagger_rendered": metrics["swagger"] if path == "/docs" else None,
        "csp_violations": metrics["csp"], "console_errors": console_errors, "page_errors": page_errors,
        "failed_requests": failed, "mixed_content": mixed, "missing_links": missing_links,
    }
    result["ok"] = (
        result["status"] == 200 and not result["horizontal_overflow"] and result["styled"]
        and not result["csp_violations"] and not console_errors and not page_errors
        and not failed and not mixed and not missing_links
        and (path != "/docs" or result["swagger_rendered"])
    )
    await context.close()
    return result


async def check_account_cta(browser):
    """Anonymous visitors on /account must get a working Google login button."""
    context = await browser.new_context(viewport={"width": 390, "height": 844})
    page = await context.new_page()
    await page.goto(BASE + "/account", wait_until="networkidle")
    await page.wait_for_timeout(1000)
    visible = await page.locator("#signed-out").is_visible()
    status_text = (await page.locator("#status").text_content() or "").strip()
    target = None
    if visible:
        try:
            async with page.expect_request(lambda r: "/auth/v1/authorize" in r.url, timeout=20000) as req:
                await page.click('a[href="/auth/google"]')
            target = (await req.value).url.split("?")[0]
        except Exception as exc:  # report, don't crash: the page checks above still count
            target = f"error: {type(exc).__name__}"
    await context.close()
    return {"check": "account login CTA", "ok": bool(visible and target and ".supabase.co/" in target),
            "signed_out_panel_visible": visible, "status_text": status_text, "login_navigates_to": target}


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        results = []
        for name, size in VIEWPORTS.items():
            for path in PAGES:
                result = await check_page(browser, name, size, path)
                results.append(result)
                print(("PASS " if result["ok"] else "FAIL ") + json.dumps(result, ensure_ascii=False), flush=True)
        cta = await check_account_cta(browser)
        results.append(cta)
        print(("PASS " if cta["ok"] else "FAIL ") + json.dumps(cta, ensure_ascii=False), flush=True)
        await browser.close()
    with open(f"{OUT}/results.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    failed = [r for r in results if not r["ok"]]
    print(json.dumps({"target": BASE, "checked": len(results), "failed": len(failed)}))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
