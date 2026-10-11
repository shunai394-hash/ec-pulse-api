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
| 3 | Navigation and information architecture | Source-reviewed; automated checks added | Main sections have named anchors, skip navigation, active section state, and a mobile menu. New regression test checks duplicate IDs and local fragments. |
| 4 | Responsive and touch behavior | Source-reviewed; runtime not verified | Responsive breakpoints and touch-sized controls exist in CSS. Mobile screenshots, keyboard/touch interaction and overflow still need real-device/browser checks. |
| 5 | Accessibility and motion | Source-reviewed; automated checks added | Focus styles, tab semantics, a visible demo pause control, and reduced-motion handling are present. New test checks account input labels. Screen-reader and keyboard testing remain NOT RUN. |
| 6 | Demo honesty and product comprehension | Improved | The demo is labelled sample data. Added two FAQ entries clarifying that source coverage is not guaranteed and that data must be checked before purchasing. |
| 7 | Pricing and conversion | Blocked / needs owner data | Free-plan value is explicit, but Pro/Business prices and credit quotas are deferred to Stripe. This weakens buyer confidence and cannot be corrected safely without verifying the actual Stripe prices and quotas. |
| 8 | Data sourcing, rights and trust | Improved; compliance review pending | Added user-facing source-availability and permitted-use caveats. Backend includes source-aware public-HTML selectors; official API permissions, source terms, retention, and commercial-use rights need a source-by-source review. |
| 9 | Security, privacy and legal readiness | Partial / launch blocker | Inline CSP hashes, security headers, and account security flows are present in source. Legal pages still contain `［要入力］` placeholders; operator details and final legal review are required before paid public launch. No live security test was run. |
| 10 | Performance, SEO and production health | Partial / NOT VERIFIED | Canonical/description/Open Graph title metadata, robots/sitemap endpoints and CI exist. Live HTTP smoke tests, Core Web Vitals, asset/render performance, social preview image, current production-domain correctness and runtime DB health remain unverified. |

## Changes in this review branch

- Added explicit FAQ guidance that marketplace/review access varies by API entitlement, contract, public availability, terms and access restrictions; it does not promise universal coverage or bypass source rules.
- Added a reminder to verify current source data before purchase.
- Added regression tests for Japanese HTML/primary actions, sample-data labelling, unique IDs and fragments, account input labels, and hash-restricted inline CSP.

## Release gates — do not mark PASS without evidence

- [ ] CI `pytest -q` passes on the pull request.
- [ ] Browser smoke: `/`, `/account`, `/docs`, `/redoc`, all legal pages, `/pricing`, `/health`, `/sitemap.xml`.
- [ ] Check HTML and JSON root behavior with real browser and API-client Accept headers on the canonical production alias.
- [ ] Test desktop, tablet and narrow mobile; keyboard-only navigation; reduced motion; screen reader labels.
- [ ] Measure Core Web Vitals and verify no console errors or CSP violations.
- [ ] Confirm actual Stripe plan amounts and monthly credit quotas are visible before checkout.
- [ ] Resolve all legal placeholders with real operator details and counsel review.
- [ ] Complete source-by-source data permission, retention and commercial-use review.
- [ ] Obtain independent reviewer feedback, fix it, and repeat the review.
- [ ] Only after release gates pass: full regression/security tests, then decide on native app work.

## Status

Round count for this source-level patrol: **10/10 review passes performed**.  
Award-level readiness: **NOT VERIFIED**. The branch is a review candidate, not a production release. The outstanding gates above are real blockers, not assumed passes.
