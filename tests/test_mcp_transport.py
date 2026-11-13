"""transport seam / MCP server 骨架的协议层单测（零领域语义）。

ADR-0004 要求：单边 server（stdio 默认，零网络面）、transport seam 为第四 seam、
handler 只调注入的 repository/command API、不直连 DDL，
对外契约 `zkc-mcp-contract v1` 独立版本化。

本文件只测 JSON-RPC 帧 / initialize / tools.list / tools.call 分发 / 错误码 /
stdio 循环 / 契约快照 / seam 纯净性，**不测任何 ZKC 业务行为**（留给 E3/E4/E5）。
"""
from __future__ import annotations

import ast
import io
import json
import unittest
from pathlib import Path

from zkc.transport.contract import (
    BLACKLIST,
    CONTRACT_VERSION,
    MCP_PROTOCOL_VERSION,
    TOOL_NAMES,
    contract_snapshot,
)
from zkc.transport.mcp_server import McpServer, ToolSpec
from zkc.transport.protocol import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    JsonRpcError,
    decode_message,
    encode_message,
    is_notification,
)
from zkc.transport.stdio import serve_stdio


def _echo_handler(arguments):
    return {"echo": arguments}


def _server_with_echo():
    return McpServer(tools=[
        ToolSpec(
            name="echo",
            description="协议层自测用 tool（无领域语义）",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=_echo_handler,
        )
    ])


class FrameLayerTest(unittest.TestCase):
    def test_decode_valid_message(self):
        msg = decode_message('{"jsonrpc":"2.0","id":1,"method":"ping"}')
        self.assertEqual(msg["method"], "ping")
        self.assertEqual(msg["id"], 1)

    def test_decode_rejects_broken_json_with_parse_error(self):
        with self.assertRaises(JsonRpcError) as ctx:
            decode_message("{not json")
        self.assertEqual(ctx.exception.code, PARSE_ERROR)

    def test_decode_rejects_non_object_and_bad_jsonrpc(self):
        for raw in ('[1,2]', '"hello"', '{"jsonrpc":"1.0","method":"ping"}',
                    '{"jsonrpc":"2.0"}'):
            with self.subTest(raw=raw):
                with self.assertRaises(JsonRpcError) as ctx:
                    decode_message(raw)
                self.assertEqual(ctx.exception.code, INVALID_REQUEST)

    def test_encode_is_single_line_and_roundtrips(self):
        payload = {"jsonrpc": "2.0", "id": 7, "result": {"text": "第一行\n第二行"}}
        line = encode_message(payload)
        self.assertNotIn("\n", line)
        self.assertEqual(json.loads(line), payload)

    def test_notification_has_no_id(self):
        self.assertTrue(is_notification({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertFalse(is_notification({"jsonrpc": "2.0", "id": 1, "method": "ping"}))


class DispatchTest(unittest.TestCase):
    def test_initialize_returns_protocol_capabilities_and_server_info(self):
        res = _server_with_echo().handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {}},
        })
        self.assertEqual(res["id"], 1)
        result = res["result"]
        self.assertEqual(result["protocolVersion"], MCP_PROTOCOL_VERSION)
        self.assertIn("tools", result["capabilities"])
        self.assertIn("resources", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "zkc")

    def test_initialize_exposes_independent_contract_version(self):
        res = _server_with_echo().handle_message({
            "jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {},
        })
        self.assertEqual(res["result"]["contractVersion"], CONTRACT_VERSION)

    def test_notification_produces_no_response(self):
        self.assertIsNone(_server_with_echo().handle_message({
            "jsonrpc": "2.0", "method": "notifications/initialized", "params": {},
        }))

    def test_ping_returns_empty_result(self):
        res = _server_with_echo().handle_message({"jsonrpc": "2.0", "id": 3, "method": "ping"})
        self.assertEqual(res["result"], {})

    def test_tools_list_returns_only_registered_schemas(self):
        res = _server_with_echo().handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
        tools = res["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], ["echo"])
        self.assertEqual(tools[0]["inputSchema"]["type"], "object")

    def test_tools_list_empty_without_registration(self):
        res = McpServer().handle_message({"jsonrpc": "2.0", "id": 5, "method": "tools/list"})
        self.assertEqual(res["result"]["tools"], [])

    def test_tools_call_dispatches_to_injected_handler(self):
        res = _server_with_echo().handle_message({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "hi"}},
        })
        self.assertFalse(res["result"]["isError"])
        content = res["result"]["content"][0]
        self.assertEqual(content["type"], "text")
        self.assertEqual(json.loads(content["text"]), {"echo": {"text": "hi"}})

    def test_tools_call_unknown_tool_is_error_result(self):
        res = _server_with_echo().handle_message({
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        })
        self.assertTrue(res["result"]["isError"])
        self.assertIn("nope", res["result"]["content"][0]["text"])

    def test_tools_call_missing_required_argument_is_error_result(self):
        res = _server_with_echo().handle_message({
            "jsonrpc": "2.0", "id": 8, "method": "tools/call",
            "params": {"name": "echo", "arguments": {}},
        })
        self.assertTrue(res["result"]["isError"])
        self.assertIn("text", res["result"]["content"][0]["text"])

    def test_tools_call_non_object_arguments_is_invalid_params(self):
        res = _server_with_echo().handle_message({
            "jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {"name": "echo", "arguments": [1, 2]},
        })
        self.assertEqual(res["error"]["code"], INVALID_PARAMS)

    def test_unknown_method_returns_method_not_found(self):
        res = _server_with_echo().handle_message({"jsonrpc": "2.0", "id": 10, "method": "no/such"})
        self.assertEqual(res["error"]["code"], METHOD_NOT_FOUND)

    def test_handler_exception_does_not_crash_server(self):
        def boom(_arguments):
            raise RuntimeError("injected handler failure")

        srv = McpServer(tools=[ToolSpec("boom", "x", {"type": "object"}, boom)])
        res = srv.handle_message({
            "jsonrpc": "2.0", "id": 11, "method": "tools/call",
            "params": {"name": "boom", "arguments": {}},
        })
        self.assertTrue(res["result"]["isError"])
        self.assertIn("RuntimeError", res["result"]["content"][0]["text"])
        # 同一 server 仍可继续服务
        self.assertEqual(
            srv.handle_message({"jsonrpc": "2.0", "id": 12, "method": "ping"})["result"], {}
        )

    def test_blacklisted_tool_registration_refused(self):
        for name in sorted(BLACKLIST)[:2]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    McpServer(tools=[ToolSpec(name, "x", {"type": "object"}, _echo_handler)])

    def test_duplicate_tool_registration_refused(self):
        with self.assertRaises(ValueError):
            McpServer(tools=[
                ToolSpec("echo", "a", {"type": "object"}, _echo_handler),
                ToolSpec("echo", "b", {"type": "object"}, _echo_handler),
            ])

    def test_server_never_obtains_storage_itself(self):
        import zkc.repository as repository

        original = repository.get_storage

        def forbidden(*_a, **_kw):
            raise AssertionError("transport 层不得自行获取 storage（handler 由调用方注入）")

        repository.get_storage = forbidden
        try:
            srv = _server_with_echo()
            for method, params in (("initialize", {}), ("tools/list", {}),
                                   ("tools/call", {"name": "echo", "arguments": {"text": "ok"}})):
                res = srv.handle_message({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
                self.assertNotIn("error", res)
        finally:
            repository.get_storage = original

    def test_transport_layer_imports_no_storage_or_driver(self):
        base = Path(__file__).resolve().parents[1] / "src" / "zkc" / "transport"
        for name in ("protocol.py", "contract.py", "mcp_server.py", "stdio.py"):
            tree = ast.parse((base / name).read_text(encoding="utf-8"), filename=name)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(alias.name.startswith("psycopg"), name)
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    self.assertFalse(mod.startswith("zkc.repository"), (name, mod))
                    self.assertFalse(mod.startswith("psycopg"), (name, mod))


class StdioLoopTest(unittest.TestCase):
    def test_serve_stdio_multiple_frames(self):
        lines = "\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "echo", "arguments": {"text": "ok"}}}),
        ]) + "\n"
        out = io.StringIO()
        serve_stdio(_server_with_echo(), stdin=io.StringIO(lines), stdout=out)
        frames = [json.loads(x) for x in out.getvalue().splitlines() if x.strip()]
        self.assertEqual([f["id"] for f in frames], [1, 2, 3])
        self.assertEqual(len(frames[1]["result"]["tools"]), 1)
        self.assertFalse(frames[2]["result"]["isError"])

    def test_serve_stdio_skips_blank_and_notifications_and_reports_bad_json(self):
        lines = "\n".join([
            "",
            "   ",
            "{broken",
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping", "params": {}}),
        ]) + "\n"
        out = io.StringIO()
        serve_stdio(_server_with_echo(), stdin=io.StringIO(lines), stdout=out)
        frames = [json.loads(x) for x in out.getvalue().splitlines() if x.strip()]
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0]["error"]["code"], PARSE_ERROR)
        self.assertEqual(frames[1]["id"], 9)

    def test_serve_stdio_output_is_one_line_per_frame(self):
        out = io.StringIO()
        serve_stdio(
            _server_with_echo(),
            stdin=io.StringIO(json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "echo", "arguments": {"text": "a\nb"}},
            }) + "\n"),
            stdout=out,
        )
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertIn("\\n", out.getvalue())

    def test_module_entrypoint_exits_zero_and_writes_frames_only_to_stdout(self):
        """回归：serve_stdio 的帧计数曾被当进程退出码 → 3 帧请求 exit 3。"""
        import subprocess
        import sys

        root = Path(__file__).resolve().parents[1]
        frames = "\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "distill/trigger", "arguments": {}}}),
        ]) + "\n"
        proc = subprocess.run(
            [sys.executable, "-m", "zkc.transport"],
            cwd=str(root), input=frames, text=True, capture_output=True, timeout=20,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 3)
        for line in lines:
            json.loads(line)
        self.assertTrue(json.loads(lines[2])["result"]["isError"])
        self.assertIn("no network listener", proc.stderr)


class ContractSnapshotTest(unittest.TestCase):
    def test_snapshot_is_independently_versioned_and_serializable(self):
        snap = contract_snapshot()
        self.assertEqual(snap["version"], CONTRACT_VERSION)
        self.assertEqual(snap["protocolVersion"], MCP_PROTOCOL_VERSION)
        json.dumps(snap, ensure_ascii=False)

    def test_snapshot_lists_exactly_five_allowlisted_tools(self):
        snap = contract_snapshot()
        names = [t["name"] for t in snap["tools"]]
        self.assertEqual(set(names), set(TOOL_NAMES))
        self.assertEqual(len(names), 5)
        for tool in snap["tools"]:
            self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_snapshot_declares_blacklist_and_trust_boundary(self):
        snap = contract_snapshot()
        self.assertEqual(set(snap["blacklist"]), set(BLACKLIST))
        self.assertEqual(snap["transport"], "stdio")
        self.assertIn("零网络", snap["trustBoundary"])
        self.assertEqual(snap["egress"], [])

    def test_snapshot_file_exists_beside_module(self):
        base = Path(__file__).resolve().parents[1] / "src" / "zkc" / "transport"
        path = base / "contract_v1.json"
        self.assertTrue(path.is_file())
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"], CONTRACT_VERSION)


if __name__ == "__main__":
    unittest.main()
