---
name: ec-monitor
description: Inspect EC Pulse price monitors and opportunity signals
argument-hint: "[monitor ID or inspection request]"
allowed-tools:
  - mcp__plugin_ec-pulse_ec-pulse__ec_monitor_list
  - mcp__plugin_ec-pulse_ec-pulse__ec_monitor_history
  - mcp__plugin_ec-pulse_ec-pulse__ec_monitor_opportunity
  - mcp__plugin_ec-pulse_ec-pulse__ec_monitor_create
---

Inspect the authenticated EC Pulse price monitors.

- Use monitor list for discovery.
- If a monitor is named, retrieve its history and opportunity signal.
- Never create a monitor unless the user explicitly requests creation.
- Before creation, confirm the requested product URL, interval, and webhook destination.
- Never expose the customer's API key or other secrets.


When creating a monitor, offer an optional target price if the customer wants a buy-price alert. Explain that target_price uses the listed product currency and sends a target_price_reached webhook only when an observed price crosses from above the threshold to at or below it. Do not imply the threshold accounts for shipping, taxes, marketplace fees, or profit.
