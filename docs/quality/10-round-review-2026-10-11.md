# EC Pulse API — 10-round quality patrol

Date: 2026-10-11  
Scope: repository source review on `main`, focusing on `app/pages.py`, `app/main.py`, `app/services/product_search.py`, `app/services/research_ingest.py`, legal drafts, Vercel deployment metadata, and CI configuration.

This is a source-level self-review, not a claim that the site has won or would win an award. A real browser run, live production smoke test, and independent human review are still required.

## Review standard

The review uses the Webby website criteria (content, navigation, visual design, functionality, interactivity, innovation, overall experience) and a design/UX/creative/content lens inspired by Awwwards and FWA. No award outcome is guaranteed.

## Ten passes

| Pass | Focus | Result | Findings / action |
|---:|---|---|---|
| 1 | Product positioning | Reviewed | The API-first positioning is clear: market signal → pain point → candidate → price → decision. Keep EC Pulse API as the single product identity. |
| 2 | Visual system and craft | Source-reviewed | Custom typography, restrained palette, console demo, consistent cards and spacing exist. Actual visual rendering and viewport-by-viewport polish are not verified in a browser. |
| 3 | Navigation and information architecture | Source-reviewed; automated checks added | Main sections have named anchors, skip navigation, active section state, and a mobile menu. New regression test checks duplicate IDs and local fragments; the landing page now surfaces research history comparison and CSV export. |
| 4 | Responsive and touch behavior | Source-reviewed; runtime not verified | Responsive breakpoints and touch-sized controls exist in CSS. Mobile screenshots, keyboard/touch interaction and overflow still need real-device/browser checks. |
| 5 | Accessibility and motion | Source-reviewed; automated checks added | Focus styles, tab semantics, a visible demo pause control, and reduced-motion handling are present. New test checks account input labels. Screen-reader and keyboard testing remain NOT RUN. |
| 6 | Demo honesty and product comprehension | Improved | The demo is labelled sample data. Added source coverage/freshness caveats and clarified the initial Pro persona as a testable hypothesis, not validated market research. |
| 7 | Pricing and conversion | Code improved; production configuration still unverified | `/v1/pricing` now returns public metadata from active recurring Stripe prices, and the landing page displays real price/quota values when configured. Paid CTAs remain disabled unless price, quota, and the legal launch gate are all ready. Actual target-production values remain unverified. |
| 8 | Data sourcing, rights and trust | Improved; compliance review pending | Added user-facing source-availability and permitted-use caveats. Backend includes source-aware public-HTML selectors; official API permissions, source terms, retention, and commercial-use rights need a source-by-source review. |
| 9 | Security, privacy and legal readiness | Partial / launch blocker | Inline CSP hashes, security headers, and account security flows are present in source. Legal pages still contain `［要入力］` placeholders; operator details and final legal review are required before paid public launch. No live security test was run. |
| 10 | Performance, SEO and production health | Partial / NOT VERIFIED | Canonical/description/Open Graph title metadata, robots/sitemap endpoints and CI exist. Live HTTP smoke tests, Core Web Vitals, asset/render performance, social preview image, Vercel metadata identifies `ec-pulse-api-one.vercel.app` on the older `shunai394-9704s-projects/ec-pulse-api` project (deployment `dpl_5Ak3NzAtvwpjESR95W67gKFhuUXY`, commit `9458508`), which conflicts with the intended migration to `naito3087`; reconcile the canonical domain before calling migration complete. Runtime DB health remains unverified. |

## Changes in this review branch

- Added explicit FAQ guidance that marketplace/review access varies by API entitlement, contract, public availability, terms and access restrictions; it does not promise universal coverage or bypass source rules.
- Added a reminder to verify current source data before purchase.
- Added regression tests for Japanese HTML/primary actions, sample-data labelling, unique IDs and fragments, account input labels, and hash-restricted inline CSP.
- Added live Stripe recurring-price metadata and fail-closed paid-plan CTAs; no price is invented when Stripe configuration is missing or unavailable.
- Added authenticated CSV export for research history/trends, with UTF-8 BOM for spreadsheet compatibility and formula-injection neutralization for source-controlled text.
- Surfaced `GET /v1/research/runs` and `GET /v1/research/runs/export.csv` in the landing page and README.

## Release gates — do not mark PASS without evidence

- [x] CI `pytest -q` passed on code-bearing commit `2bf3a0e61544842c70e4c718e96640c4a9c55075`: `tests` workflow **398 passed**, `EC Pulse Python tests` **301 passed, 97 skipped**, each with 1 warning. The subsequent README change is documentation-only.
- [ ] Browser smoke: `/`, `/account`, `/docs`, `/redoc`, all legal pages, `/pricing`, `/health`, `/sitemap.xml`.
- [ ] Check HTML and JSON root behavior with real browser and API-client Accept headers on the canonical production alias.
- [ ] Resolve Vercel ownership/routing: PR status checks currently report successful deployments for both `ec-pulse-api` and `ec-pulse` under the older `shunai394-9704s-projects` scope, while the intended migration target was `naito3087`.
- [ ] Test desktop, tablet and narrow mobile; keyboard-only navigation; reduced motion; screen reader labels.
- [ ] Measure Core Web Vitals and verify no console errors or CSP violations.
- [ ] Confirm actual Stripe plan amounts and monthly credit quotas are visible in the intended production project before enabling checkout.
- [ ] Resolve all legal placeholders with real operator details and counsel review.
- [ ] Complete source-by-source data permission, retention and commercial-use review.
- [ ] Obtain independent reviewer feedback, fix it, and repeat the review.
- [ ] Only after release gates pass: full regression/security tests, then decide on native app work.

## Status

Round count for this source-level patrol: **10/10 review passes performed**.  
Award-level readiness: **NOT VERIFIED**. The branch is a review candidate, not a production release. The outstanding gates above are real blockers, not assumed passes.


### CI notes

- `EC Pulse Python tests` and `tests` completed successfully on code-bearing commit `2bf3a0e61544842c70e4c718e96640c4a9c55075`.
- `EC Pulse Patrol AI` failed before running its review because the workflow has no `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, or configured workload identity. This is recorded as **NOT RUN / workflow auth missing**, not as a product-code test failure.

## Follow-up audit — 2026-10-11 (second session)

Evidence-backed results only. Anything not listed as verified was not verified.

### Reference URLs

| Purpose | URL | Status |
|---|---|---|
| Vercel dashboard (designated migration target) | https://vercel.com/naito3087/ec-pulse-api | Access denied (403) from this session; settings not verified |
| Previously observed deployment | https://ec-pulse-qo5r3c51i-naito3087.vercel.app/ | **Not confirmed as the production URL** |
| GitHub repository | https://github.com/shunai394-hash/ec-pulse-api | Verified |

### Verified

- PR #16 is still draft and unmerged; head was `f1ee7b2` before this session, base `main` at `9458508`.
- Local re-run on Python 3.13 (CI uses 3.12): **400 passed** with a disposable PostgreSQL 16; **303 passed, 97 skipped** without one. Counts include the two regression tests added below.
- Browser check against a local server (Chromium, 1440×900 and 390×844): `/` returns HTML to browsers and JSON to `Accept: */*` clients; no horizontal overflow; no console errors; with no Stripe configuration the Pro/Business cards show "価格未設定" and "現在、契約受付停止中" (fail-closed).
- `GET /v1/research/runs/export.csv` returns 401 without an API key; rows are scoped by `owner_key_hash`; rate limiting applies through `get_api_key`.

### Fixed

- `/v1/pricing` called Stripe `Price.retrieve` twice on every request, and the landing page requests it on every view. Anonymous traffic could consume the Stripe account rate limit shared with checkout, portal and webhooks. Prices are now cached for 10 minutes (failures for 60 seconds), keyed by Price ID.

### Not verified (blocked)

- Vercel: the connected Vercel account (`naito3087-3997`) gets `403 forbidden` on the `naito3087` scope and lists no projects. No project settings, domains, env vars, deployments or logs could be read. Migration completeness is **NOT VERIFIED**.
- Production HTTP: this session's network policy denies `*.vercel.app`, so no live request to any deployment URL was made. Which URL serves production is unconfirmed. The follow-up removes the unverified domain as a default: the app omits canonical metadata and sitemap entries until `PUBLIC_SITE_URL` is configured, while smoke tests and the MCP adapter require an explicit `EC_PULSE_API_BASE_URL`.
- Stripe: no access to the Stripe account; price IDs, webhook endpoint, event registration and the reported production webhook 500 are **NOT VERIFIED**.

### Source-access mitigation added to this review branch

- Added `EC_PULSE_ENABLE_UNOFFICIAL_HTML_SCRAPING`, defaulting to off. When off, marketplace search does not fall back to Amazon/Rakuten/Yahoo! search-page HTML or Bing HTML, and review ingestion does not fetch public-page HTML.
- When explicitly enabled, review ingestion accepts only the repository's configured source domains and re-checks the allow-list after every redirect.
- Official marketplace API integrations remain available when their credentials are configured. Direct product-URL lookup remains a separate feature and still requires source-by-source terms and permission review.
- This is a code-level guard, not a legal determination. The production environment was not changed; the flag must remain off until source permissions and data-retention rules are reviewed. CI for this change is pending.


## Product value and revenue operating plan — 2026-10-12

- Added `docs/strategy/revenue-and-product-quality-plan.md` with the ¥160M annual revenue target, illustrative account-count arithmetic, competitor comparison, prioritized product gaps, release gates, and a weekly quality dashboard.
- Measure activation, time-to-first-useful-result, data coverage, repeat usage, paid conversion, retention, support burden, and gross margin—not visual polish alone.
- Competitive research reviewed on 2026-10-12: [Nint EC Lite](https://ec-lite.nint.jp/), [Nint ECommerce](https://www.nint.jp/ec/), [Jungle Scout pricing](https://www.junglescout.com/pricing/), and [Helium 10 product research](https://www.helium10.com/tools/product-research/). Revalidate details before external investor materials.
