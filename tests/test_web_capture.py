"""ZKC · 快捕获 web 层测试（P2.1）。

主张：捕获逻辑（标题/正文拆分 + 分流落库 + 弃权入 classify 队列）在无 Ollama/无 PG 下可验证；
HTTP 层用 FastAPI TestClient（需 httpx）做 GET 页面 + POST /capture。
"""
from __future__ import annotations

import unittest
from uuid import UUID

from zkc import routing
from zkc.routing import DecisionRouter, LexicalRouter
from zkc.ingest import list_pending_classify, CLASSIFY_ACTION
from zkc.repository import get_storage
from zkc.web.app import create_app, capture_note


class FakeClient(routing.ChatClient):
    """测试用 LLM 客户端：返回预设 JSON，或 None（模拟不可达/解析失败）。"""

    def __init__(self, response):
        self.response = response

    def chat_json(self, system, user):
        return self.response


# 受控拟合集：static / dynamic 各自词汇基本不交叠
SENTENCES = [
    ("合同金额是 100 万", "static"),
    ("上线日期定在 2026", "static"),
    ("服务器地址为 10.0.0.1", "static"),
    ("明天要开会讨论需求", "dynamic"),
    ("今天记得回复邮件", "dynamic"),
    ("下午去处理线上故障", "dynamic"),
]


def _fitted_lexical(gate: float = 0.4) -> LexicalRouter:
    r = LexicalRouter(gate=gate)
    r.fit(SENTENCES)
    return r


class CaptureNoteTest(unittest.TestCase):
    def test_dynamic_note_commits_dynamic_track(self):
        store = get_storage("memory")
        dr = DecisionRouter(FakeClient({"track": "dynamic", "confidence": 0.9}))
        res = capture_note(
            "明天要开会讨论需求\n准备材料", store=store,
            decision_router=dr, lexical_router=_fitted_lexical(),
        )
        self.assertEqual(res["track"], "dynamic")
        self.assertFalse(res["vague"])
        self.assertEqual(store.review_queue.list_open(), [])

    def test_first_line_is_title_rest_is_content(self):
        store = get_storage("memory")
        dr = DecisionRouter(FakeClient({"track": "dynamic", "confidence": 0.9}))
        res = capture_note(
            "标题行\n正文行", store=store,
            decision_router=dr, lexical_router=_fitted_lexical(),
        )
        node = store.nodes.get(UUID(res["node_id"]))
        self.assertEqual(node.title, "标题行")
        self.assertEqual(node.content, "正文行")

    def test_vague_note_enqueues_classify(self):
        store = get_storage("memory")
        dr = DecisionRouter(FakeClient({"track": "vague", "confidence": 0.1}))
        res = capture_note(
            "没想清楚的事", store=store,
            decision_router=dr, lexical_router=_fitted_lexical(),
        )
        self.assertTrue(res["vague"])
        self.assertEqual(res["track"], routing.VAGUE)
        items = list_pending_classify(store=store)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].action, CLASSIFY_ACTION)

    def test_empty_note_rejected(self):
        store = get_storage("memory")
        dr = DecisionRouter(FakeClient({"track": "dynamic", "confidence": 0.9}))
        with self.assertRaises(ValueError):
            capture_note("   ", store=store, decision_router=dr)

    def test_offline_lexical_only_commits(self):
        store = get_storage("memory")
        dr = DecisionRouter(FakeClient(None))
        res = capture_note(
            "明天要开会讨论需求", store=store,
            decision_router=dr, lexical_router=_fitted_lexical(), llm_available=False,
        )
        self.assertEqual(res["track"], "dynamic")
        self.assertEqual(res["source"], "lexical-only")

    def test_offline_undecided_abstains(self):
        store = get_storage("memory")
        dr = DecisionRouter(FakeClient(None))
        res = capture_note(
            "嗯随便吧", store=store,
            decision_router=dr, lexical_router=_fitted_lexical(), llm_available=False,
        )
        self.assertTrue(res["vague"])
        self.assertEqual(res["source"], "abstain-offline")


class CaptureHTTPTest(unittest.TestCase):
    def _app(self):
        store = get_storage("memory")
        dr = DecisionRouter(FakeClient({"track": "dynamic", "confidence": 0.9}))
        return create_app(store=store, decision_router=dr, lexical_router=_fitted_lexical())

    def test_get_page_has_textarea(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("httpx/TestClient 未安装")
        c = TestClient(self._app())
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("快捕获", r.text)
        self.assertIn("textarea", r.text)

    def test_post_capture_returns_json(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("httpx/TestClient 未安装")
        c = TestClient(self._app())
        r = c.post("/capture", data={"note": "明天要开会讨论需求\n准备材料"})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["track"], "dynamic")
        self.assertFalse(j["vague"])


if __name__ == "__main__":
    unittest.main()
