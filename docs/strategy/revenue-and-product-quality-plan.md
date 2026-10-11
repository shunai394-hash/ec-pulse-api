# EC Pulse API — revenue and product-quality operating plan

Date: 2026-10-12  
Status: strategic working document; hypotheses must be validated with real customers and production data.

## North-star outcome

Help ecommerce operators make better product, sourcing, pricing, and monitoring decisions with less manual research. EC Pulse must show where each signal came from, how fresh it is, and what it does **not** prove. It must not imply that estimated demand guarantees sales or profit.

## Revenue target: ¥160 million annual revenue

The target equals about ¥13.33 million per month on a simple annualized basis. These are arithmetic scenarios, not forecasts or current plan prices:

| Illustrative average monthly revenue per paying account | Approximate active paying accounts to annualize to ¥160M |
|---:|---:|
| ¥3,000 | 4,445 |
| ¥10,000 | 1,334 |
| ¥30,000 | 445 |
| ¥50,000 | 267 |

Formula: annualized revenue = active paying accounts × average monthly revenue per account × 12. Actual recognized revenue depends on churn, discounts, taxes, refunds, usage-based revenue, and timing. Track gross margin, net revenue retention, acquisition cost, and support cost as well as account count.

## Competitive landscape: evidence-based comparison

Official product pages reviewed on 2026-10-12:

- [Nint EC Lite](https://ec-lite.nint.jp/) emphasizes product-level tracking across Amazon, Rakuten, and Yahoo! Shopping, estimated sales, price/rank trends, a 10-product free trial, and CSV export on paid plans.
- [Nint ECommerce](https://www.nint.jp/ec/) positions broader category, shop, product and market-share analysis, an AI assistant grounded in its estimated data, downloads, and customer support.
- [Jungle Scout](https://www.junglescout.com/pricing/) combines Amazon seller product/keyword research with sales estimates and a larger brand-intelligence offering for enterprise customers.
- [Helium 10](https://www.helium10.com/tools/product-research/) emphasizes product and keyword discovery, browser extension workflows, profit/loss and inventory functions on relevant plans, and rules-based advertising automation.

These are vendor-described features, not an independent accuracy or user-satisfaction study. Re-check pricing and scope before publishing competitor claims externally.

## EC Pulse weaknesses to close

1. **Data reliability is not yet a defensible moat.** Show source, observation time, API-vs-estimate provenance, missing fields, coverage, and stale-data warnings. Benchmark against seller-provided ground truth before claiming accuracy.
2. **Source permissions are a release gate.** Official API credentials and contractual permissions should be the default. Unofficial HTML scraping remains off unless every source's terms and rights have been reviewed and explicitly approved.
3. **Workflow completeness needs proof.** Connect discover → validate evidence → estimate unit economics → compare shortlist → monitor changes → alert → actionable report. Every step needs an observable success state and recovery path.
4. **Profit calculations need user-specific costs.** Include selling fees, shipping, taxes where applicable, fulfillment, returns, advertising, landed cost, and target margin. Distinguish user inputs from retrieved facts and estimates.
5. **Trust and onboarding must beat complexity.** Help a new user reach a useful result without learning API terminology first. Keep API power for advanced users; provide guided setup, clearly marked demo data, copyable recipes, and actionable errors.
6. **Retention must be earned.** Saved research runs, change summaries, scheduled reports, price alerts, and integrations should deliver a recurring reason to return.
7. **Customer proof is missing.** Do not fabricate testimonials, customer counts, conversion lifts, coverage, or ROI. Recruit design partners and publish measured case studies only with permission.

## Product roadmap by release gates

### P0 — trust and safe operation
- Confirm production project, canonical domain, routing, environment variables, database, Stripe price IDs and webhook delivery.
- Keep scraping disabled by default; verify official API integrations and source-specific rights.
- Add source provenance, timestamps, partial-result semantics, and freshness metadata.
- Keep billing fail-closed when price or credit configuration is missing.
- Establish deterministic CI, security scans, database-backed tests, and live smoke tests that report NOT RUN distinctly.

### P1 — first successful customer outcome
- Guided onboarding: choose marketplace/category → run a sample search → compare three candidates → enter cost assumptions → save a monitor.
- Add a transparent unit-economics worksheet and downloadable report with formulas and assumptions.
- Improve empty, loading, partial-data, rate-limit, and recovery states.
- Instrument funnel events without collecting unnecessary personal data.

### P2 — repeatable automation
- Saved research runs and diff summaries.
- Scheduled discovery and monitoring with deduplication, retry/backoff, per-account quotas, pause/resume, and alert delivery history.
- Webhook signing, replay protection, failure retry policy, dead-letter visibility, and endpoint ownership checks.
- CSV/Sheets exports and integration recipes; require explicit confirmation before purchases or other consequential actions.

### P3 — defensible intelligence
- Build accuracy benchmarks against opt-in customer ground truth.
- Segment signals by category, geography, marketplace, sample size and freshness.
- Add confidence and coverage metrics only when calibrated; no arbitrary AI confidence scores.
- Offer customer-specific alert thresholds, cost assumptions, and reports.

### P4 — scale and international readiness
- Load tests, queue-based processing, tenant isolation reviews, rate-limit fairness, observability, incident response, backup/restore drills, and support playbooks.
- Validate demand in each new marketplace and locale before claiming coverage.
- Consider mobile apps only after web/API activation and retention show a repeatable need.

## Continuous quality loop

For each iteration:
1. Observe a real user task and where it stalls.
2. Record evidence, severity, affected segment, and expected business impact.
3. Fix the highest-impact issue without weakening security, data permissions, or billing correctness.
4. Add regression tests and update docs.
5. Run unit/integration/security checks and relevant browser viewport checks.
6. Re-review as a first-time customer, keyboard user, mobile user, API integrator, and operator.
7. Compare against the previous version and select the next bottleneck.

Do not declare award-level readiness from source review alone. Track independent design review, accessibility, performance, content, functionality, innovation, and real-user outcomes.

## Operating dashboard

Track weekly activation, time to first useful result (median/p90), data coverage by source and endpoint, saved/exported/compared/monitored result rate, week-1/month-1 retention, free-to-paid conversion, ARPA, churn, refunds, net revenue retention, gross margin, acquisition payback, p95 latency, stale-data rate, webhook delivery, incidents, and trust/privacy issues.

Set numerical baselines after the first instrumented cohort; do not invent targets without data.
