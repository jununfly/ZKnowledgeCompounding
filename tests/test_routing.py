"""ZKC · 双轨分流引擎单元测试（P2.2）。

主张：双信号弃权 / 离线兜底 / 人工兜底 全部在无 Ollama、无网络的条件下可验证。
LLM 信号用 FakeClient 注入；词法信号用受控拟合集。
"""
from __future__ import annotations

import unittest

from zkc import routing
from zkc.routing import (
    DecisionRouter,
    LexicalRouter,
    RoutingResult,
    route_text,
)
from zkc.ingest import ingest_with_routing, CLASSIFY_ACTION
from zkc.repository import get_storage


class FakeClient(routing.ChatClient):
    """测试用 LLM 客户端：返回预设 JSON，或 None（模拟不可达/解析失败）。"""

    def __init__(self, response):
        self.response = response

    def chat_json(self, system, user):
        return self.response


# 受控拟合集：static / dynamic 各自词汇基本不交叠
EX_STATIC = "合同金额是 100 万"
SENTENCES = [
    (EX_STATIC, "static"),
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


class LexicalRouterTest(unittest.TestCase):
    def test_fitted_and_exact_static(self):
        r = _fitted_lexical()
        self.assertTrue(r.fitted)
        track, conf = r.predict(EX_STATIC)
        self.assertEqual(track, "static")
        self.assertGreaterEqual(conf, 0.4)

    def test_exact_dynamic(self):
        r = _fitted_lexical()
        track, conf = r.predict("明天要开会讨论需求")
        self.assertEqual(track, "dynamic")
        self.assertGreaterEqual(conf, 0.4)

    def test_no_overlap_is_vague(self):
        r = _fitted_lexical()
        # 与任一质心都无共享 token → 低于门槛 → None（无法判定）
        track, conf = r.predict("嗯随便吧")
        self.assertIsNone(track)

    def test_cold_start_unfitted(self):
        r = LexicalRouter()
        self.assertFalse(r.fitted)
        self.assertEqual(r.predict("任何文本"), (None, 0.0))


class DecisionRouterTest(unittest.TestCase):
    def test_parses_structured_json(self):
        dr = DecisionRouter(FakeClient({"track": "dynamic", "confidence": 0.91, "reason": "x"}))
        track, conf = dr.predict("今晚完成评审")
        self.assertEqual(track, "dynamic")
        self.assertAlmostEqual(conf, 0.91)

    def test_parse_failure_returns_none(self):
        dr = DecisionRouter(FakeClient(None))
        track, conf = dr.predict("anything")
        self.assertIsNone(track)
        self.assertEqual(conf, 0.0)

    def test_vague_track_passthrough(self):
        dr = DecisionRouter(FakeClient({"track": "vague", "confidence": 0.2}))
        track, conf = dr.predict("含糊")
        self.assertEqual(track, "vague")


class RouteTextDualSignalTest(unittest.TestCase):
    def test_dual_agree_commits(self):
        dr = DecisionRouter(FakeClient({"track": "static", "confidence": 0.9}))
        res = route_text(EX_STATIC, dr, _fitted_lexical(), llm_available=True)
        self.assertEqual(res.track, "static")
        self.assertEqual(res.source, "dual-agree")
        self.assertIsNone(res.aborted)
        self.assertGreater(res.confidence, 0.0)

    def test_disagree_abstains(self):
        # LLM 判 static，但词法判 dynamic（强动态句）→ 双信号不一致 → 弃权
        dr = DecisionRouter(FakeClient({"track": "static", "confidence": 0.9}))
        res = route_text("明天要开会讨论需求计划", dr, _fitted_lexical(), llm_available=True)
        self.assertEqual(res.track, routing.VAGUE)
        self.assertEqual(res.source, "abstain-disagree")

    def test_llm_vague_abstains(self):
        dr = DecisionRouter(FakeClient({"track": "vague", "confidence": 0.1}))
        res = route_text("含糊不清", dr, _fitted_lexical(), llm_available=True)
        self.assertEqual(res.track, routing.VAGUE)
        self.assertEqual(res.source, "abstain-llm")

    def test_llm_low_confidence_abstains(self):
        dr = DecisionRouter(FakeClient({"track": "static", "confidence": 0.1}))
        res = route_text(EX_STATIC, dr, _fitted_lexical(), llm_available=True)
        self.assertEqual(res.track, routing.VAGUE)
        self.assertEqual(res.source, "abstain-llm")


class RouteTextOfflineTest(unittest.TestCase):
    def test_offline_lexical_only_commit(self):
        dr = DecisionRouter(FakeClient(None))  # 不会被调用
        res = route_text(EX_STATIC, dr, _fitted_lexical(), llm_available=False)
        self.assertEqual(res.track, "static")
        self.assertEqual(res.source, "lexical-only")

    def test_offline_lexical_undecided_abstain(self):
        dr = DecisionRouter(FakeClient(None))
        res = route_text("嗯随便", dr, _fitted_lexical(), llm_available=False)
        self.assertEqual(res.track, routing.VAGUE)
        self.assertEqual(res.source, "abstain-offline")

    def test_single_signal_fallback_when_lexical_absent(self):
        # 未要求双信号且无词法 → 单信号提交（降级，记录告警）
        dr = DecisionRouter(FakeClient({"track": "dynamic", "confidence": 0.8}))
        res = route_text("今晚完成评审", dr, None, llm_available=True,
                         require_dual_signal=False)
        self.assertEqual(res.track, "dynamic")
        self.assertEqual(res.source, "llm-only")
        self.assertEqual(res.aborted, "no-lexical-crosscheck")


class IngestWithRoutingTest(unittest.TestCase):
    def test_committed_track_persisted_no_classify(self):
        store = get_storage("memory")
        dr = DecisionRouter(FakeClient({"track": "static", "confidence": 0.9}))
        node, res = ingest_with_routing(
            title="合同", content="金额 100 万", text_for_routing=EX_STATIC,
            decision_router=dr, lexical_router=_fitted_lexical(), store=store,
        )
        self.assertEqual(node.track, "static")
        self.assertAlmostEqual(node.routing_confidence, 0.9)
        self.assertEqual(res.source, "dual-agree")
        self.assertEqual(store.review_queue.list_open(), [])

    def test_vague_enqueues_classify(self):
        store = get_storage("memory")
        dr = DecisionRouter(FakeClient({"track": "vague", "confidence": 0.1}))
        node, res = ingest_with_routing(
            title="含糊条目", content="没想清楚",
            decision_router=dr, lexical_router=_fitted_lexical(), store=store,
        )
        self.assertEqual(node.track, routing.VAGUE)
        self.assertIsNone(node.routing_confidence)
        open_items = store.review_queue.list_open()
        self.assertEqual(len(open_items), 1)
        self.assertEqual(open_items[0].action, CLASSIFY_ACTION)
        self.assertEqual(open_items[0].node_id, node.id)


if __name__ == "__main__":
    unittest.main()
