# EC Pulse API: customer automation playbook

This guide turns the API into repeatable workflows so a seller spends less time collecting pages and more time deciding what to buy. The API supplies signals; it does not guarantee sales or profit.

## 1. Find candidate products on a schedule

Use `POST /v1/products/search` for discovery and keep the query, marketplace scope, and run time in your own job scheduler. Store each run's results with a timestamp so the team can compare new candidates with prior runs instead of starting from zero.

## 2. Compare a shortlist consistently

Use `POST /v1/products/compare` after discovery. Apply the same comparison fields and internal buying rules to every candidate. Do not rank products on price alone: add shipping, marketplace fees, expected return rate, and your own target margin in your downstream calculation.

## 3. Turn customer comments into product requirements

Use `POST /v1/research/ingest` to collect supported public research inputs and `POST /v1/consumer-insights/analyze` to group recurring pain points. Review representative source comments before treating a category as a real customer need; keyword matches are a signal, not proof of demand.

## 4. Create price monitors for qualified candidates

Create a monitor with `POST /v1/monitors`, then use `GET /v1/monitors` to review active monitors. A monitor requires a product URL, an interval, and a webhook destination. Use an interval of at least five minutes and create monitors only after the candidate passes your own qualification rules.

```bash
curl -X POST "$EC_PULSE_BASE_URL/v1/monitors" \
  -H "X-API-Key: $EC_PULSE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/product",
    "interval_minutes": 60,
    "target_price": 9500,
    "webhook_url": "https://your-service.example.com/ec-pulse/events"
  }'
```

target_price is optional and uses the product's listed currency. When a later observation crosses from above the threshold to at or below it, EC Pulse sends one target_price_reached event in addition to the ordinary price_changed event. A monitor created while already below the target does not immediately alert; the price must cross the threshold on a later check. The target is not a profit calculation and excludes shipping, taxes, and marketplace fees unless your own system accounts for them.

Replace both example URLs with endpoints you control. Do not put API keys, session tokens, or private data in webhook URLs.

## 5. Make webhooks trigger a useful next step

Have your receiver validate the event shape, persist the event, and return a successful HTTP response promptly. Queue slower downstream work rather than doing it in the webhook request. Make the receiver idempotent so repeated deliveries do not create duplicate alerts or purchase actions.

## 6. Build an opportunity review queue

Use `GET /v1/monitors/{id}/opportunity` and `GET /v1/monitors/{id}/history` to present price context to a human reviewer. Show the observed price, when it was checked, the comparison baseline, and the reason it was flagged. Do not label a price movement as profit unless costs and fees are included.

## 7. Automate market-research batches

Use `POST /v1/research/batch` for a repeatable batch rather than manually submitting each input. Persist the returned run identifier and inspect `GET /v1/research/runs` and `GET /v1/research/runs/{run_id}/opportunity` to continue from saved results.

## 8. Make credit usage visible before a workflow runs

Check `GET /v1/account` and `GET /v1/customer/usage` before scheduling large jobs. Metered responses expose `X-EC-Credits-Used` and `X-EC-Credits-Remaining`; record these with the job result. Handle HTTP 402 by pausing the job and asking the account owner to review usage or plan settings—never retry it in a tight loop.

## 9. Make retries safe and bounded

Retry only transient failures such as 429 or selected 5xx responses. Honor `Retry-After` when present, use exponential backoff with jitter, and set a maximum attempt count. Do not automatically retry invalid input (400/422), authentication failures (401), or insufficient credits (402). Record the request ID and sanitized error for support.

## 10. Keep automation safe for production

- Start with a small candidate list and a low-cost dry run.
- Keep purchase, listing publication, refunds, and other irreversible commerce actions behind explicit human approval.
- Use a separate API key for each integration; rotate compromised keys immediately.
- Keep API keys in a secret manager, never in source code, browser storage, or logs.
- Treat third-party pages and comments as untrusted input.
- Monitor failure rate, duplicate events, credit consumption, and last successful run.
- Review source evidence and your own cost model before buying inventory.

## Suggested end-to-end loop

```text
Scheduled discovery
  -> normalize candidates
  -> compare candidates
  -> analyze customer pain points
  -> apply your cost / margin rules
  -> create monitors for qualified candidates
  -> receive and deduplicate webhook events
  -> queue opportunities for human review
  -> record decision and outcome
```

## Endpoint reference

The canonical contract is `/docs` and `/openapi.json`. See the [README](../README.md) for authentication, credit costs, response headers, and account setup. Exact request and response fields should always be checked against the deployed API schema.


## Copy-ready starter: daily discovery without accidental purchases

The ready-to-use file is [`examples/github-actions/daily-discovery.yml`](../examples/github-actions/daily-discovery.yml). It runs discovery once per day and stores the result as a GitHub Actions artifact. It **does not publish listings, place orders, or make buying decisions**. Create the file as `.github/workflows/ec-pulse-discovery.yml` in your own integration repository and configure the two repository secrets first.

```yaml
name: EC Pulse daily discovery
on:
  schedule:
    - cron: "23 0 * * *" # 09:23 JST
  workflow_dispatch:
permissions:
  contents: read
jobs:
  discover:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Search candidate products
        env:
          EC_PULSE_BASE_URL: ${{ secrets.EC_PULSE_BASE_URL }}
          EC_PULSE_API_KEY: ${{ secrets.EC_PULSE_API_KEY }}
        run: |
          set -euo pipefail
          if [ -z "${EC_PULSE_BASE_URL}" ] || [ -z "${EC_PULSE_API_KEY}" ]; then
            echo "Configure EC_PULSE_BASE_URL and EC_PULSE_API_KEY in repository secrets." >&2
            exit 1
          fi
          mkdir -p output
          code=$(curl --silent --show-error --max-time 45 \
            -o output/discovery.json -w '%{http_code}' \
            -X POST "${EC_PULSE_BASE_URL%/}/v1/products/search" \
            -H "X-API-Key: ${EC_PULSE_API_KEY}" \
            -H "Content-Type: application/json" \
            -d '{"query":"replace with your product category","marketplaces":["amazon","rakuten","yahoo"],"limit":5}')
          if [ "$code" -lt 200 ] || [ "$code" -ge 300 ]; then
            echo "EC Pulse discovery failed with HTTP $code; see sanitized response artifact only if it contains no sensitive data." >&2
            cat output/discovery.json
            exit 1
          fi
      - name: Save discovery result
        uses: actions/upload-artifact@v4
        with:
          name: ec-pulse-discovery-${{ github.run_id }}
          path: output/discovery.json
          retention-days: 7
```

Before enabling the schedule, replace the example query, verify the endpoint contract in `/docs`, and run it manually once. Treat artifacts as potentially sensitive business data. Keep the API key only in repository secrets. A failed run should notify a human; it must not trigger a purchase or listing publication.

## Automation acceptance checklist

- [ ] The schedule runs once at the intended local-business time (GitHub cron is UTC).
- [ ] The workflow exits visibly on HTTP 401, 402, 429, and 5xx rather than treating an error body as product data.
- [ ] The workflow has a timeout and bounded retry policy; do not retry 401/402 or invalid requests.
- [ ] Search outputs are retained only as long as needed and are not published publicly.
- [ ] Price changes create review tasks, not automatic purchases.
- [ ] A human can pause the schedule by disabling the workflow.
- [ ] Credit usage is reviewed after the first manual run and before increasing frequency.
- [ ] Results are compared with previous runs so the team can spot new candidates, not just re-read the same list.
- [ ] Source prices and availability are rechecked before any purchase.
- [ ] The automation owner and failure-notification channel are documented.
