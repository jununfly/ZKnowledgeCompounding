"""人工定轨 UI 回归（P2.3 消费端上 /review，2026-11-02 补齐真空档）。

背景：classify 队列此前只有领域函数（list_pending_classify/resolve_classify），
没有任何 web 出口——zj 在 /review 找不到「待定轨笔记」。
本文件验证：视图序列化 + HTTP 两端点 + 定轨闭环（node 落轨 + 条目 resolved）。
"""
from __future__ import annotations

import unittest
from uuid import UUID

from zkc.ingest import list_pending_classify
from zkc.repository import get_storage
from zkc.web.app import create_app
from zkc.web.review import classify_queue_view

from tests.test_web_capture import FakeClient

from zkc.routing import DecisionRouter


def _seed_vague_capture(store):
    """复现真实链路：捕获一条必然弃权的笔记 → classify 行入队。"""
    app = create_app(
        store=store,
        decision_router=DecisionRouter(FakeClient({"track": "vague", "confidence": 0.1})),
        lexical_router=None,
    )
    return app


class ClassifyViewTest(unittest.TestCase):
    def test_view_lists_pending_with_node_title(self):
        store = get_storage("memory")
        _seed_vague_capture(store)
        # 走真实捕获链路太绕，直接用弃权捕获等价物：ingest 已在 capture 测试覆盖，
        # 这里经由 create_app 的 /capture 端点落一条。
        from fastapi.testclient import TestClient

        app = _seed_vague_capture(store)
        c = TestClient(app)
        r = c.post("/capture", data={"note": "没想清楚的事\n一些补充上下文"})
        self.assertEqual(r.status_code, 200)

        v = classify_queue_view(store)
        self.assertEqual(v["count"], 1)
        self.assertEqual(v["items"][0]["title"], "没想清楚的事")
        self.assertEqual(v["items"][0]["preview"], "一些补充上下文")


class ClassifyHTTPTest(unittest.TestCase):
    def test_resolve_endpoint_closes_loop(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("httpx/TestClient 未安装")

        store = get_storage("memory")
        app = _seed_vague_capture(store)
        c = TestClient(app, raise_server_exceptions=False)
        c.post("/capture", data={"note": "待定轨笔记"})

        # 列表端点
        v = c.get("/review/api/classify").json()
        self.assertEqual(v["count"], 1)
        item_id = v["items"][0]["id"]

        # 非法 track 拒绝
        r_bad = c.post("/review/api/classify/resolve",
                       data={"item_id": item_id, "track": "vague"})
        self.assertEqual(r_bad.status_code, 500)  # 异常守卫返回 JSON 500

        # 合法定轨 → node 落轨 + 条目 resolved
        r = c.post("/review/api/classify/resolve",
                   data={"item_id": item_id, "track": "dynamic"})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j["ok"])
        node = store.nodes.get(UUID(j["node_id"]))
        self.assertEqual(node.track, "dynamic")
        self.assertEqual(list_pending_classify(store=store), [])

        # 列表清空
        self.assertEqual(c.get("/review/api/classify").json()["count"], 0)


if __name__ == "__main__":
    unittest.main()
