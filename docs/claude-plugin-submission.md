# Claude Code Plugin Marketplace Submission

## Package

- Plugin: `ec-pulse`
- Repository: https://github.com/shunai394-hash/ec-pulse-api
- Plugin path: `plugins/ec-pulse/`
- Production API: https://ec-pulse-api.vercel.app
- Claude Code support: local stdio MCP + commands + skills
- MCP server: `.mcp.json` -> `server.py`

## Current implementation

- 10 MCP tools
- 3 Claude Code commands
- 3 Agent Skills
- MCP JSON-RPC protocol handling
- Input validation
- Safe upstream error mapping
- API-key environment configuration
- Optional HMAC request signing
- Local/private literal URL rejection
- No automatic retry loop
- Unit tests and GitHub Actions workflow

## Public documentation

- API repository: https://github.com/shunai394-hash/ec-pulse-api
- Privacy policy draft: https://github.com/shunai394-hash/ec-pulse-api/blob/main/docs/legal/privacy-policy.md
- Terms draft: https://github.com/shunai394-hash/ec-pulse-api/blob/main/docs/legal/terms-of-service.md
- Billing/cancellation draft: https://github.com/shunai394-hash/ec-pulse-api/blob/main/docs/legal/billing-and-cancellation.md
- Acceptable use: https://github.com/shunai394-hash/ec-pulse-api/blob/main/docs/legal/acceptable-use.md
- Commercial transactions draft: https://github.com/shunai394-hash/ec-pulse-api/blob/main/docs/legal/commercial-transactions.md

## Marketplace form data to confirm

Do not submit until the following are truthful and complete:

- Operator/business legal name
- Support email or support URL
- Privacy-policy URL containing final operator/contact information
- Terms URL containing final operator information
- Billing/refund/cancellation policy with final refund rules
- Commercial-transactions disclosure with final business information, where applicable
- Final homepage/product landing page
- Category selected in the submission portal
- Test account or sample data requested by the reviewer
- Confirmation that the operator controls the published API endpoint and documentation
- Final pricing/credit description

## Current blockers

The legal documents still contain `［要入力］` placeholders and therefore must not be represented as final legal policies.

Production smoke testing is NOT PASS. No production `EC_PULSE_API_KEY` is available to the test runner, so authenticated production smoke testing remains NOT RUN. Direct production HTTP verification is also NOT VERIFIED from this audit environment because external DNS resolution is unavailable.

Deployment/commit-SHA verification must be recorded per audit; do not reuse a SHA from an earlier audit.

The repository has no LICENSE file and `plugin.json` declares no `license`; decide the license before submission.

## Evaluation status

- Product discovery: NOT RUN against current production
- Market research: NOT RUN against current production
- Consumer insight: NOT RUN against current production
- Price monitoring: NOT RUN against current production
- Credit shortage: NOT RUN
- Invalid/private URL: NOT RUN against production; local literal-private validation is covered by unit tests
- API authentication failure: NOT RUN against production
- MCP protocol: automated test suite is present; latest audited plugin CI result is PASS on a previously audited plugin commit. Production MCP smoke remains NOT RUN

Never mark a case PASS without an actual recorded run.
