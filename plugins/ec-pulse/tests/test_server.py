import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[1] / "server.py"
spec = importlib.util.spec_from_file_location("ec_pulse_server", SERVER)
server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(server)

class MCPProtocolTests(unittest.TestCase):
    def test_initialize(self):
        r=server._handle({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}})
        self.assertEqual(r["result"]["serverInfo"]["name"],"ec-pulse")
    def test_tools_list(self):
        r=server._handle({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
        self.assertEqual(len(r["result"]["tools"]),10)
        self.assertIn("ec_product_search",{x["name"] for x in r["result"]["tools"]})
    def test_unknown_method(self):
        r=server._handle({"jsonrpc":"2.0","id":3,"method":"nope","params":{}})
        self.assertEqual(r["error"]["code"],-32601)
    def test_unknown_tool(self):
        r=server._handle({"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"nope","arguments":{}}})
        self.assertEqual(r["error"]["code"],-32602)
    def test_invalid_request(self):
        r=server._handle({"jsonrpc":"1.0","id":5,"method":"initialize"})
        self.assertEqual(r["error"]["code"],-32600)
    def test_parse_error(self):
        with patch("sys.stdin",iter(["{broken\\n"])),patch("sys.stdout") as out:
            server.main()
            emitted=out.write.call_args.args[0]
        self.assertEqual(json.loads(emitted)["error"]["code"],-32700)

class ValidationTests(unittest.TestCase):
    def test_empty_query(self):
        with self.assertRaises(ValueError): server._validate_args("ec_product_search",{"query":""})
    def test_invalid_url(self):
        with self.assertRaises(ValueError): server._validate_url("not-a-url")
    def test_local_and_private_urls_rejected(self):
        for url in [
            "http://localhost:8080/x",
            "http://127.0.0.1:8080/x",
            "http://10.0.0.1/x",
            "http://172.16.0.1/x",
            "http://192.168.1.1/x",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/x",
            "http://[fc00::1]/x",
        ]:
            with self.assertRaises(ValueError, msg=url):
                server._validate_url(url)
    def test_compare_minimum(self):
        with self.assertRaises(ValueError): server._validate_args("ec_product_compare",{"urls":["https://example.com"]})
    def test_unknown_argument(self):
        with self.assertRaises(ValueError): server._validate_args("ec_account",{"api_key":"secret"})

    def test_monitor_target_price_must_be_positive(self):
        with self.assertRaises(ValueError): server._validate_args("ec_monitor_create", {"url":"https://example.com/p", "webhook_url":"https://hooks.example.com/x", "target_price":0})

    def test_monitor_target_price_rejects_boolean(self):
        with self.assertRaises(ValueError): server._validate_args("ec_monitor_create", {"url":"https://example.com/p", "webhook_url":"https://hooks.example.com/x", "target_price":True})

    def test_monitor_target_price_is_optional(self):
        args = server._validate_args("ec_monitor_create", {"url":"https://example.com/p", "webhook_url":"https://hooks.example.com/x"})
        self.assertNotIn("target_price", args)

class SecurityTests(unittest.TestCase):
    def test_key_missing(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(RuntimeError): server._api_key()
    def test_key_not_leaked(self):
        secret="TEST_SECRET_NOT_FOR_AUTH"
        with patch.dict(os.environ,{"EC_PULSE_API_KEY":secret},clear=True),patch.object(server,"_api_request",side_effect=RuntimeError("EC Pulse authentication failed (401)")):
            r=server._handle({"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"ec_account","arguments":{}}})
        self.assertNotIn(secret,r["result"]["content"][0]["text"])
    def test_no_retry(self):
        calls=[]
        def fail(*a,**k):
            calls.append(1)
            raise RuntimeError("EC Pulse rate limit exceeded (429)")
        with patch.object(server,"_api_request",side_effect=fail):
            server._handle({"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"ec_account","arguments":{}}})
        self.assertEqual(len(calls),1)
    def test_signature(self):
        self.assertEqual(len(server._sign("secret","1700000000","POST","/v1/products/search",b"{}")),71)


class BaseUrlTests(unittest.TestCase):
    def test_empty_base_url_falls_back_to_default(self):
        with patch.dict(os.environ, {"EC_PULSE_API_BASE_URL": ""}):
            self.assertEqual(server._base_url(), server.DEFAULT_BASE_URL)
    def test_unset_base_url_falls_back_to_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(server._base_url(), server.DEFAULT_BASE_URL)
    def test_remote_http_base_url_is_rejected(self):
        with patch.dict(os.environ, {"EC_PULSE_API_BASE_URL": "http://example.com"}):
            with self.assertRaises(RuntimeError): server._base_url()

class ManifestTests(unittest.TestCase):
    def test_mcp_env_defaults_are_declared(self):
        config = json.loads((SERVER.parent / ".mcp.json").read_text())
        env = config["mcpServers"]["ec-pulse"]["env"]
        self.assertEqual(env["EC_PULSE_API_BASE_URL"], "${EC_PULSE_API_BASE_URL:-https://ec-pulse-api-one.vercel.app}")
        self.assertEqual(env["EC_PULSE_API_KEY"], "${EC_PULSE_API_KEY}")
    def test_command_tool_references_exist(self):
        import re
        names = {t["name"] for t in server.TOOLS}
        for command in (SERVER.parent / "commands").glob("*.md"):
            for tool in re.findall(r"mcp__plugin_ec-pulse_ec-pulse__(\w+)", command.read_text()):
                self.assertIn(tool, names, f"{command.name} references unknown tool {tool}")
    def test_skill_tool_references_exist(self):
        import re
        names = {t["name"] for t in server.TOOLS}
        for skill in (SERVER.parent / "skills").glob("*/SKILL.md"):
            for tool in re.findall(r"`(ec_[a-z_]+)`", skill.read_text()):
                self.assertIn(tool, names, f"{skill} references unknown tool {tool}")

if __name__=="__main__":
    unittest.main()
