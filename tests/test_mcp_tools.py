"""暴露面五 tool 的接线验收（含黑名单拒绝、攻击面枚举表）。

ADR-0004：白名单五 tool、黑名单四类危险写绝不暴露、handler 只调既有
repository/command API、零网络面。私人 claim 默认脱敏在此层落地，
完整注入验收链路在注入防护切片。
"""
from __future__ import annotations

import ast
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from zkc.mcp.exposure import attack_surface_table
from zkc.mcp.wiring import build_zkc_server
from zkc.repository import get_storage
from zkc.repository.models import Claim, Node
from zkc.routing import ChatClient, DecisionRouter
from zkc.transport.contract import BLACKLIST, TOOL_NAMES, contract_snapshot


class FakeClient(ChatClient):
    """离线替身：health 恒 False，不触网。"""

    def chat_json(self, system, user):
        return None

    def health(self):
        return False


def _fixture():
    store = get_storage("memory")
    audits = []
    server = build_zkc_server(
        store_provider=lambda: store,
        routing_provider=lambda: (DecisionRouter(FakeClient()), None, False),
        audit_sink=audits.append,
    )
    return store, audits, server


def _call(server, name, arguments, *, request_id=1):
    res = server.handle_message({
        "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert "result" in res, res
    result = res["result"]
    text = result["content"][0]["text"]
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        payload = {"_raw": text}
    return result["isError"], payload, text


def _frame(server, method, params=None, *, request_id=1):
    return server.handle_message({
        "jsonrpc": "2.0", "id": request_id, "method": method,
        "params": params or {},
    })


class ExposureSurfaceTest(unittest.TestCase):
    def test_tools_list_matches_contract_exactly(self):
        _, _, server = _fixture()
        tools = _frame(server, "tools/list")["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], list(TOOL_NAMES))
        snapshot = {t["name"]: t["inputSchema"] for t in contract_snapshot()["tools"]}
        for tool in tools:
            self.assertEqual(tool["inputSchema"], snapshot[tool["name"]])

    def test_blacklisted_writes_are_refused_and_audited(self):
        _, audits, server = _fixture()
        for name in sorted(BLACKLIST):
            with self.subTest(name=name):
                is_err, _, text = _call(server, name, {})
                self.assertTrue(is_err)
                self.assertIn("拒绝", text)
        denied = [a for a in audits if a["event"] == "tool_denied"]
        self.assertEqual(len(denied), len(BLACKLIST))
        self.assertTrue(all(a["reason"].startswith("命中 ADR-0004") for a in denied))

    def test_unregistered_non_blacklisted_tool_refused(self):
        _, audits, server = _fixture()
        is_err, _, text = _call(server, "zkc_admin_override", {})
        self.assertTrue(is_err)
        self.assertIn("白名单", text)
        self.assertEqual(audits[-1]["event"], "tool_denied")

    def test_resources_list_exposes_attention_resource(self):
        _, _, server = _fixture()
        resources = _frame(server, "resources/list")["result"]["resources"]
        self.assertEqual([r["uri"] for r in resources], ["zkc://scheduler/due"])
        self.assertIn("注意力", resources[0]["description"])

    def test_attack_surface_table_is_machine_readable_and_consistent(self):
        table = attack_surface_table()
        self.assertEqual([e["name"] for e in table["entry"]], list(TOOL_NAMES))
        self.assertEqual(table["egress"], contract_snapshot()["egress"])
        self.assertEqual(table["egress"], [])
        self.assertIn("stdio", table["trustBoundary"])
        self.assertEqual(set(table["blacklist"]), set(BLACKLIST))
        self.assertEqual(len(table["injectionGate"]), 3)
        json.dumps(table, ensure_ascii=False)

    def test_mcp_layer_has_no_raw_sql_or_driver_import(self):
        base = Path(__file__).resolve().parents[1] / "src" / "zkc" / "mcp"
        for path in base.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(alias.name.startswith("psycopg"), path.name)
                elif isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith("psycopg"), path.name)
            source = path.read_text(encoding="utf-8")
            for forbidden in ("SELECT ", "CREATE TABLE", "INSERT INTO", "UPDATE node"):
                self.assertNotIn(forbidden, source, (path.name, forbidden))

    def test_server_construction_is_lazy_about_storage(self):
        import zkc.repository as repository

        original = repository.get_storage

        def forbidden(*_a, **_kw):
            raise AssertionError("构造阶段不得连库（handler 首次调用才取 store）")

        repository.get_storage = forbidden
        try:
            server = build_zkc_server(audit_sink=lambda _e: None)
            self.assertEqual(_frame(server, "initialize")["result"]["serverInfo"]["name"], "zkc")
            self.assertEqual(len(_frame(server, "tools/list")["result"]["tools"]), 5)
        finally:
            repository.get_storage = original


class CaptureToolTest(unittest.TestCase):
    def test_capture_goes_through_routing_gate_and_enqueues_human_review(self):
        store, _, server = _fixture()
        is_err, payload, _ = _call(server, "zkc_capture", {
            "documents": [{"title": "明天要开会讨论需求", "content": "准备材料"}],
        })
        self.assertFalse(is_err, payload)
        self.assertEqual(payload["captured"], 1)
        self.assertEqual(payload["profile"], "capture")
        nodes = store.nodes.list_by_track("unrouted")
        self.assertEqual(len(nodes), 1)
        pending = [it for it in store.review_queue.list_open() if it.action == "classify"]
        self.assertEqual(len(pending), 1, "分流闸弃权必须入人审队列")

    def test_capture_never_writes_interval_or_claims(self):
        store, _, server = _fixture()
        _call(server, "zkc_capture", {"documents": [{"title": "一条事实", "content": "正文"}]})
        node = store.nodes.list_by_track("unrouted")[0]
        self.assertIsNone(node.review_interval)
        self.assertEqual(node.interval_source, "auto")
        self.assertEqual(store.claims.list_all(), [])

    def test_capture_rejects_more_than_1000_documents(self):
        _, _, server = _fixture()
        is_err, _, text = _call(server, "zkc_capture", {
            "documents": [{"title": f"n{i}"} for i in range(1001)],
        })
        self.assertTrue(is_err)
        self.assertIn("1000", text)


class QueryToolTest(unittest.TestCase):
    def _seed(self, store, *, private="SECRET-私人手机号-13800000000"):
        node = store.nodes.save(Node(
            title="可检索的公开标题", content=private, track="static",
        ))
        claim = store.claims.save(Claim(
            statement="敏感私人 claim 内容", evidence_refs=[node.id],
        ))
        return node, claim, private

    def test_query_returns_evidence_refs_and_strips_private_content(self):
        store, _, server = _fixture()
        node, _claim, private = self._seed(store)
        is_err, payload, text = _call(server, "zkc_query", {"query": "可检索"})
        self.assertFalse(is_err, payload)
        self.assertEqual(len(payload["items"]), 1)
        item = payload["items"][0]
        self.assertEqual(item["node_id"], str(node.id))
        self.assertEqual(item["evidence_refs"], [str(node.id)])
        self.assertNotIn("content", item)
        self.assertNotIn(private, text)
        self.assertNotIn("敏感私人 claim", text)

    def test_query_private_claims_scope_denied_by_default(self):
        store, audits, server = _fixture()
        self._seed(store)
        is_err, payload, text = _call(server, "zkc_query", {
            "query": "可检索", "scope": "private_claims",
        })
        self.assertFalse(is_err)
        self.assertTrue(payload["denied"])
        self.assertEqual(payload["items"], [])
        self.assertNotIn("SECRET-私人手机号", text)
        self.assertTrue(any(a["event"] == "private_scope_denied" for a in audits))


class ReviewQueueToolTest(unittest.TestCase):
    def test_list_returns_open_items_with_action_filter(self):
        store, _, server = _fixture()
        node = store.nodes.save(Node(title="n"))
        store.review_queue.enqueue(node.id, "classify", None)
        store.review_queue.enqueue(node.id, "distill", None)
        is_err, payload, _ = _call(server, "zkc_review_queue_list", {})
        self.assertFalse(is_err)
        self.assertEqual(len(payload["items"]), 2)
        is_err, filtered, _ = _call(server, "zkc_review_queue_list", {"action": "classify"})
        self.assertFalse(is_err)
        self.assertEqual([i["action"] for i in filtered["items"]], ["classify"])

    def test_resolve_only_marks_resolved_and_records_hitl_attribution(self):
        store, audits, server = _fixture()
        node = store.nodes.save(Node(title="n", track="dynamic", decay_score=0.7))
        item = store.review_queue.enqueue(node.id, "distill", None)
        is_err, payload, _ = _call(server, "zkc_review_queue_resolve", {
            "item_id": str(item.id), "attribution": "zj 人工复核 2026-11-05",
        })
        self.assertFalse(is_err, payload)
        self.assertTrue(payload["resolved"])
        self.assertNotIn(item.id, [i.id for i in store.review_queue.list_open()])
        self.assertTrue(any(a["event"] == "hitl_attribution" for a in audits))
        stored = store.nodes.get(node.id)
        self.assertIsNone(stored.review_interval, "resolve 绝不能顺手写 interval")

    def test_resolve_unknown_item_is_error_result(self):
        _, _, server = _fixture()
        is_err, _, text = _call(server, "zkc_review_queue_resolve", {
            "item_id": str(uuid4()), "attribution": "x",
        })
        self.assertTrue(is_err)
        self.assertIn("不存在", text)


class SchedulerDueToolTest(unittest.TestCase):
    def _seed_due(self, store):
        return store.nodes.save(Node(
            title="到期的注意力条目", track="dynamic", decay_score=0.8,
            review_interval=timedelta(days=3),
            last_reviewed_at=datetime.now(timezone.utc) - timedelta(days=10),
        ))

    def test_due_tool_returns_attention_semantics(self):
        store, _, server = _fixture()
        node = self._seed_due(store)
        is_err, payload, _ = _call(server, "zkc_scheduler_due", {})
        self.assertFalse(is_err, payload)
        self.assertEqual(len(payload["items"]), 1)
        item = payload["items"][0]
        self.assertEqual(item["node_id"], str(node.id))
        self.assertIn("decay_score", item)
        self.assertIn("review_interval_days", item)

    def test_due_resource_read_returns_same_attention_list(self):
        store, _, server = _fixture()
        node = self._seed_due(store)
        res = _frame(server, "resources/read", {"uri": "zkc://scheduler/due"})["result"]
        payload = json.loads(res["contents"][0]["text"])
        self.assertEqual(payload["items"][0]["node_id"], str(node.id))


if __name__ == "__main__":
    unittest.main()
