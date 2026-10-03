"""MCP stdio smoke test for plugins/ec-pulse/server.py against a live API.

Speaks newline-delimited JSON-RPC to the plugin server exactly as Claude Code
does. ec_account is called against the live API when EC_PULSE_SMOKE_API_KEY
is set (0 credits).
"""
import json
import os
import subprocess
import sys

BASE = os.getenv("EC_PULSE_BASE_URL", "https://ec-pulse-api.vercel.app").rstrip("/")
KEY = os.getenv("EC_PULSE_SMOKE_API_KEY", "").strip()
SERVER = os.path.join(os.path.dirname(__file__), "..", "plugins", "ec-pulse", "server.py")
EXPECTED_TOOLS = {
    "ec_product_search", "ec_product_get", "ec_product_compare", "ec_research_ingest", "ec_consumer_insights",
    "ec_monitor_create", "ec_monitor_list", "ec_monitor_history", "ec_monitor_opportunity", "ec_account",
}

messages = [
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized"}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/list"}',
    '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"ec_account","arguments":{}}}',
    '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"no_such_tool","arguments":{}}}',
    '{"jsonrpc":"2.0","id":5,"method":"no/such/method"}',
    '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":"not-an-object"}',
    '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"ec_product_get","arguments":{"url":"http://127.0.0.1/"}}}',
    '{not json',
    '["not","an","object"]',
]

env = {**os.environ, "EC_PULSE_API_BASE_URL": BASE, "EC_PULSE_API_KEY": KEY}
proc = subprocess.run([sys.executable, SERVER], input="\n".join(messages) + "\n", capture_output=True,
                      text=True, env=env, timeout=120)
responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
by_id = {r.get("id"): r for r in responses if r.get("id") is not None}
null_id = [r for r in responses if r.get("id") is None]
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)


init = by_id.get(1, {}).get("result", {})
check("initialize returns protocolVersion and tools capability",
      bool(init.get("protocolVersion")) and "tools" in init.get("capabilities", {}), json.dumps(init)[:120])
check("notifications/initialized gets no response", len(responses) == len(messages) - 1,
      f"{len(responses)} responses to {len(messages)} messages")
tools = {t["name"] for t in by_id.get(2, {}).get("result", {}).get("tools", [])}
check("tools/list exposes the 10 EC Pulse tools", tools == EXPECTED_TOOLS, f"missing={sorted(EXPECTED_TOOLS - tools)} extra={sorted(tools - EXPECTED_TOOLS)}")
account = by_id.get(3, {}).get("result", {})
text = (account.get("content") or [{}])[0].get("text", "")
if KEY:
    check("tools/call ec_account succeeds against the live API", account.get("isError") is False and "credits_balance" in text,
          text[:100] if account.get("isError") else "credits_balance present")
else:
    check("tools/call ec_account without key fails cleanly (isError)", account.get("isError") is True, text[:100])
check("unknown tool is -32602", by_id.get(4, {}).get("error", {}).get("code") == -32602)
check("unknown method is -32601", by_id.get(5, {}).get("error", {}).get("code") == -32601)
check("non-object params is -32602", by_id.get(6, {}).get("error", {}).get("code") == -32602)
ssrf = by_id.get(7, {}).get("result", {})
check("ec_product_get with loopback URL is rejected as a tool error", ssrf.get("isError") is True,
      ((ssrf.get("content") or [{}])[0].get("text", ""))[:100])
codes = sorted(r.get("error", {}).get("code") for r in null_id)
check("malformed JSON is -32700 and non-object request is -32600", codes == [-32700, -32600], f"codes={codes}")
check("server wrote nothing to stderr", not proc.stderr.strip(), proc.stderr[:200])
check("API key never appears in output", not KEY or KEY not in proc.stdout + proc.stderr)
sys.exit(0 if all(results) else 1)
