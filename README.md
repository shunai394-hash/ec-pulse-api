# EC Pulse API

EC product data API and price monitoring infrastructure for Japanese e-commerce.

## Product

EC Pulse turns Japanese marketplace product pages and search results into normalized API data, then adds price history, monitoring, webhooks, and opportunity signals.

## Base URL and website

- API base URL / website: `https://ec-pulse-api-one.vercel.app` (the Vercel production domain; preview deployment URLs are not stable and must not be used in integrations)
- `/` — product site (browsers); API clients that do not send `Accept: text/html` get the JSON root document
- `/account` — Google login, API key issue/rotation, credits, 30-day usage, Stripe checkout and billing portal
- `/docs` (Swagger UI), `/redoc` — API reference
- `/legal/terms`, `/legal/privacy`, `/legal/billing`, `/legal/commercial-transactions`, `/legal/acceptable-use`
- `/health` — returns 200 only when the database is reachable (503 otherwise)

## Quick start

```bash
curl -X POST https://ec-pulse-api-one.vercel.app/v1/products \
  -H "X-API-Key: $EC_PULSE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://shop.example.jp/item/123"}'
```

### Credit cost

| Endpoint | Credits |
|---|---|
| `GET/POST /v1/products` | 1 |
| `POST /v1/products/search` | `limit` × number of marketplaces |
| `POST /v1/products/compare` | number of URLs |
| `POST /v1/research/ingest`, `POST /v1/research/batch` | number of URLs |
| `POST /v1/consumer-insights/analyze` | 1 per 50 comments |
| `POST /v1/monitors` | 1 |
| `GET /v1/monitors/{id}/history` | 1 |
| `GET /v1/monitors/{id}/opportunity` | 2 |
| `GET /v1/monitors`, `GET /v1/account`, `GET /v1/pricing` | 0 |

### Errors

| Status | Meaning |
|---|---|
| 401 | Missing, invalid or revoked API key |
| 402 | Insufficient credits (nothing is charged) |
| 400 / 422 | Invalid input, or a private/local network URL |
| 429 | Rate limit exceeded; retry after `Retry-After` seconds |
| 502 | Upstream page/marketplace failure (charged credits are refunded) |
| 503 | Database or a required integration is unavailable |

## Current API model

- REST + API key authentication
- Credit-based usage
- Per-customer usage ledger
- Per-customer monitor isolation
- Per-plan rate limits
- Response headers for remaining credits and rate limits
- Product cache to reduce duplicate upstream fetches

### Plans

| Plan | Credits | Rate limit |
|---|---:|---:|
| Free | 100 | 30 req/min |
| Pro | `EC_PULSE_PRO_MONTHLY_CREDITS` | 300 req/min |
| Business | `EC_PULSE_BUSINESS_MONTHLY_CREDITS` | 3000 req/min |

When Stripe reports a paid invoice (`invoice.paid` / `invoice.payment_succeeded`, or `checkout.session.completed` for the first invoice) for an active Pro/Business subscription, the account balance is topped up to that plan's monthly credit quota. The balance is never reduced by a grant, and each Stripe invoice is granted at most once (`credit_grants` table). If the quota variable is not set, no credits are granted.

Credits charged for work that fails upstream (product fetch/search failure, failed URLs in compare/research) are refunded and recorded in the usage ledger as `<endpoint> (refund)`.

Plan limits, Stripe checkout, subscription synchronization, credit accounting, usage tracking, Google login, and self-service customer API-key provisioning are implemented. A customer can authenticate, issue a free API key, use the API, and start a Pro/Business Stripe checkout without administrator intervention.

## Core endpoints

- `GET /v1/products?url=...`
- `POST /v1/products`
- `POST /v1/products/search`
- `POST /v1/products/compare`
- `POST /v1/monitors` (optional `target_price` triggers a one-time threshold-crossing webhook)
- `GET /v1/monitors` (includes target price and latest observation)
- `GET /v1/monitors/{id}/history`
- `GET /v1/monitors/{id}/opportunity`
- `GET /v1/account`
- `POST /v1/research/ingest`
- `GET /v1/research/runs`
- `GET /v1/research/runs/{run_id}/opportunity`
- `POST /v1/consumer-insights/analyze`
- `POST /v1/billing/checkout`
- `POST /v1/billing/portal`
- `POST /v1/billing/cancel`
- `POST /v1/research/batch`
- `GET /v1/pricing`

## Customer (Google session cookie) endpoints

- `GET /auth/google`, `GET /auth/callback`, `GET /auth/me`, `POST /auth/logout`
- `POST /v1/customer/key` (issue or `{"rotate": true}`)
- `GET /v1/customer/keys`
- `POST /v1/customer/keys/revoke?key_prefix=...`
- `GET /v1/customer/account`
- `GET /v1/customer/usage?days=30`
- `GET /v1/customer/usage/alerts`

## Operator endpoints

- `POST /api/stripe/webhook` and `POST /api/webhooks/stripe` (Stripe-signed; same handler)
- `GET /api/cron/check-monitors`, `GET /api/cron/patrol`, `GET /api/cron/patrol/latest` (`Authorization: Bearer $CRON_SECRET`)
- `/v1/admin/keys` (admin key; hidden from `/docs`)

## Customer automation playbook

See the [customer automation playbook](docs/customer-automation-playbook.md) for practical discovery, comparison, research, monitoring, webhook, retry, and credit-usage workflows.

## Customer onboarding

1. Open `/account` (or `GET /auth/google`) and complete Google authentication. The account page covers steps 2–7 without writing any code.
2. Call `POST /v1/customer/key` to issue the first free API key.
3. Store the returned `api_key` securely; it is shown only when the key is created.
4. Send the key as `X-API-Key: <customer-key>` to metered endpoints.
5. Call `POST /v1/billing/checkout?plan=pro` or `POST /v1/billing/checkout?plan=business` to start Stripe Checkout.
6. Use `GET /v1/account` for API usage and `POST /v1/billing/portal` for Stripe billing management.
7. If the key is lost, call `POST /v1/customer/key` with `{"rotate":true}` to revoke the old active key and issue a new one for the same customer account.

## Authentication

API requests send:

`X-API-Key: <customer-key>`

Customer keys are stored as SHA-256 hashes. The bootstrap/admin key is supplied through `EC_PULSE_API_KEY`.

## Usage headers

Successful metered responses expose:

- `X-EC-Credits-Used`
- `X-EC-Credits-Remaining`
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

## Architecture

```text
Client
  |
  v
EC Pulse API
  |-- API key auth
  |-- plan/rate limit
  |-- credit ledger
  |-- product cache
  |-- product normalization
  |-- marketplace search
  |-- monitor ownership
  |-- research persistence
  |-- pain/trend detection
  |-- opportunity engine
  |-- price history
  |-- webhook events
  v
PostgreSQL
```

## Commercial launch checklist

1. Configure production Stripe secret, webhook secret, Pro/Business Price IDs, and `APP_BASE_URL`.
2. Configure Supabase Google OAuth and `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY`.
3. Configure the PostgreSQL `DATABASE_URL`.
4. Replace all legal-document placeholders before public sales.
5. Configure `CRON_SECRET` in the production scheduler so monitor checks run automatically.
6. Publish `/docs` as the API reference and provide customer onboarding instructions.

## Legal documents

Customer-facing policy drafts are maintained under `docs/legal/`:

- [Terms of Service](docs/legal/terms-of-service.md)
- [Privacy Policy](docs/legal/privacy-policy.md)
- [Billing / Refund / Cancellation Policy](docs/legal/billing-and-cancellation.md)
- [Specified Commercial Transactions Act disclosure](docs/legal/commercial-transactions.md)
- [Acceptable Use Policy](docs/legal/acceptable-use.md)

Before public launch, replace all `［要入力］` fields with the actual operator, contact, jurisdiction, retention, refund, and other business/legal details and review the final text for the applicable jurisdiction.
