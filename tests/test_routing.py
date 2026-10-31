"""ZKC · 双轨分流引擎单元测试（P2.2）。

主张：双信号弃权 / 离线兜底 / 人工兜底 全部在无 Ollama、无网络的条件下可验证。
LLM 信号用 FakeClient 注入；词法信号用受控拟合集。
"""
from __future__ import annotations

import tempfile
import unittest

from zkc import routing
from zkc.routing import (
    DecisionRouter,
    LexicalRouter,
    OllamaClient,
    RoutingResult,
    load_lexical_corpus,
    route_text,
)
from zkc.ingest import (
    ingest_with_routing,
    list_pending_classify,
    resolve_classify,
    CLASSIFY_ACTION,
)
from zkc.repository import get_storage


class FakeClient(routing.ChatClient):
    """测试用 LLM 客户端：返回预设 JSON，或 None（模拟不可达/解析失败）。"""

    def __init__(self, response):
        self.response = response

    def chat_json(self, system, user):
        return self.response


class UnhealthyClient(FakeClient):
    """health()=False：模拟 Ollama 进程挂掉，验证自动离线降级。"""

    def health(self):
        return False


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


# ----------------------------------------------------------------- P2.3 联调（1-3-3）
class HealthAndAutoOfflineTest(unittest.TestCase):
    """残留#1：Ollama 探活 + route_text 自动离线降级（沙箱无 Ollama 也可验证）。"""

    def test_ollama_health_false_on_closed_port(self):
        # 连接必然被拒的端口 → health 必为 False，与机器上是否装 Ollama 无关
        client = OllamaClient(url="http://localhost:59999")
        self.assertFalse(client.health())

    def test_route_text_auto_degrades_when_client_unhealthy(self):
        # 调用方以为 LLM 在线，但 health()=False → 自动走离线兜底（词法单信号）
        dr = DecisionRouter(UnhealthyClient({"track": "dynamic", "confidence": 0.9}))
        res = route_text(EX_STATIC, dr, _fitted_lexical(), llm_available=True)
        self.assertEqual(res.track, "static")
        self.assertEqual(res.source, "lexical-only")
        self.assertEqual(res.aborted, "llm-unavailable-lexical-fallback")

    def test_route_text_auto_offline_undecided_abstains(self):
        dr = DecisionRouter(UnhealthyClient({"track": "dynamic", "confidence": 0.9}))
        res = route_text("嗯随便", dr, _fitted_lexical(), llm_available=True)
        self.assertEqual(res.track, routing.VAGUE)
        self.assertEqual(res.source, "abstain-offline")


class ResolveClassifyTest(unittest.TestCase):
    """残留#2/#3：classify 消费 + 词法语料回灌。"""

    def _vague_ingest(self, store, title, content):
        dr = DecisionRouter(FakeClient({"track": "vague", "confidence": 0.1}))
        node, _ = ingest_with_routing(
            title=title, content=content,
            decision_router=dr, lexical_router=_fitted_lexical(), store=store,
        )
        return node

    def test_list_pending_classify_filters_action_and_resolved(self):
        store = get_storage("memory")
        self._vague_ingest(store, "含糊1", "x")
        self._vague_ingest(store, "含糊2", "y")
        # 非 classify 的 open 条目不应混入
        other = store.review_queue.enqueue(store.nodes.list_by_track("unrouted")[0].id,
                                           "distill", reason="其他动作")
        items = list_pending_classify(store=store)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(it.action == CLASSIFY_ACTION for it in items))
        # resolve 一个后只剩 1
        store.review_queue.resolve(other.id)
        items[0] and store.review_queue.resolve(items[0].id)
        self.assertEqual(len(list_pending_classify(store=store)), 1)

    def test_resolve_sets_track_and_marks_resolved(self):
        store = get_storage("memory")
        node = self._vague_ingest(store, "待定", "内容")
        item = list_pending_classify(store=store)[0]
        saved = resolve_classify(item.id, "dynamic", store=store)
        self.assertEqual(saved.track, "dynamic")
        self.assertIsNone(saved.routing_confidence)  # 人工路径无 LLM 置信
        self.assertEqual(list_pending_classify(store=store), [])
        # OCC 版本链：unrouted(v1) → dynamic(v2)，历史快照保留
        hist = store.nodes.history(saved.id)
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0].track, routing.VAGUE)
        self.assertEqual(saved.version_seq, 2)

    def test_resolve_rejects_invalid_track(self):
        store = get_storage("memory")
        node = self._vague_ingest(store, "待定", "内容")
        item = list_pending_classify(store=store)[0]
        with self.assertRaises(ValueError):
            resolve_classify(item.id, "vague", store=store)  # vague 不是轨道
        with self.assertRaises(ValueError):
            resolve_classify(item.id, "乱写", store=store)
        # 条目仍未消费
        self.assertEqual(len(list_pending_classify(store=store)), 1)

    def test_resolve_unknown_or_resolved_item_rejected(self):
        store = get_storage("memory")
        node = self._vague_ingest(store, "待定", "内容")
        item = list_pending_classify(store=store)[0]
        resolve_classify(item.id, "static", store=store)
        with self.assertRaises(ValueError):
            resolve_classify(item.id, "dynamic", store=store)  # 已 resolved 不可再定轨

    def test_resolve_feeds_corpus_and_refits(self):
        store = get_storage("memory")
        router = LexicalRouter()  # 冷启动未 fit
        self.assertFalse(router.fitted)
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/corpus.json"
            node = self._vague_ingest(store, "待定", "内容")
            item = list_pending_classify(store=store)[0]
            resolve_classify(item.id, "dynamic", store=store,
                             lexical_router=router, lexical_corpus_path=path)
            # 语料落盘 + 内容正确
            corpus = load_lexical_corpus(path)
            self.assertEqual(corpus, [("待定 内容", "dynamic")])
            # 样本不足 3/类 → 仍无法自动提交（安全欠覆盖保持）
            self.assertFalse(router.fitted)

    def test_end_to_end_vague_to_learned_router(self):
        """端到端闭环：vague→classify→人工定轨×6→LexicalRouter 自动 fit 并能预测。

        gate=0.25：实测发现（记录进 roadmap）——字级 unigram TF-IDF + 小语料下，
        类质心余弦对语料原文也只有 ~0.33，tuning 的 0.5 恒弃权；gate 校准属
        真实语料阶段的 tuning 任务（PLACEHOLDER 语义一致），本测试只验证学习闭环。
        """
        store = get_storage("memory")
        router = LexicalRouter(gate=0.25)
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/corpus.json"
            samples = [
                ("事项1", "续租合同租金 6800", "static"),
                ("事项2", "服务器地址 10.0.0.1", "static"),
                ("事项3", "上线日期定在 2026", "static"),
                ("事项4", "明天要开会讨论需求", "dynamic"),
                ("事项5", "今天记得回复邮件", "dynamic"),
                ("事项6", "下午去处理线上故障", "dynamic"),
            ]
            for title, content, track in samples:
                self._vague_ingest(store, title, content)
                item = list_pending_classify(store=store)[0]
                resolve_classify(item.id, track, store=store,
                                 lexical_router=router, lexical_corpus_path=path)
            self.assertEqual(load_lexical_corpus(path), [
                ("事项1 续租合同租金 6800", "static"),
                ("事项2 服务器地址 10.0.0.1", "static"),
                ("事项3 上线日期定在 2026", "static"),
                ("事项4 明天要开会讨论需求", "dynamic"),
                ("事项5 今天记得回复邮件", "dynamic"),
                ("事项6 下午去处理线上故障", "dynamic"),
            ])
            self.assertTrue(router.fitted)  # ≥3/类 → 自动化解锁
            track, conf = router.predict("续租合同金额确认")
            self.assertEqual(track, "static")
            self.assertGreaterEqual(conf, 0.0)
            # 队列清空：闭环无残留
            self.assertEqual(list_pending_classify(store=store), [])


# ----------------------------------------------------------------- 词法门槛自动校准（解决 0.5 恒弃权）
class LexicalGateCalibrationTest(unittest.TestCase):
    """修复：硬编码 0.5 在小语料下恒弃权（类质心余弦仅 ~0.33）。

    默认构造 LexicalRouter() 拟合后应自动把 gate 校准到 seed(0.5) 以下，
    使词法信号不再恒弃权；显式传 gate 不受自动校准影响。
    """

    def test_default_gate_autocalibrates_below_seed(self):
        r = LexicalRouter()  # 默认 seed=0.5
        r.fit(SENTENCES)
        self.assertTrue(r.fitted)
        self.assertEqual(r.gate_source, "corpus-calibrated")
        self.assertLess(r.gate, 0.5)
        self.assertGreater(r.gate, 0.0)

    def test_in_corpus_query_commits_after_calibration(self):
        # 之前 gate=0.5 会因 best_sim~0.33 恒返回 None → 词法失效；
        # 校准后应能对类内样本给出判定（不再恒弃权）
        r = LexicalRouter().fit(SENTENCES)
        track, conf = r.predict(EX_STATIC)
        self.assertEqual(track, "static")
        self.assertGreaterEqual(conf, r.gate)

    def test_out_of_vocab_still_abstains(self):
        r = LexicalRouter().fit(SENTENCES)
        track, _ = r.predict("嗯随便吧")  # 无共享 token
        self.assertIsNone(track)

    def test_explicit_gate_not_overridden(self):
        r = LexicalRouter(gate=0.4)
        r.fit(SENTENCES)
        self.assertEqual(r.gate, 0.4)
        self.assertEqual(r.gate_source, "seed")

    def test_auto_off_respects_seed(self):
        r = LexicalRouter(auto_calibrate_gate=False)
        r.fit(SENTENCES)
        self.assertEqual(r.gate, r._seed_gate)
        self.assertEqual(r.gate_source, "seed")

    def test_dual_agree_reachable_with_default_router(self):
        # 生产路径 build_routers 用默认 LexicalRouter()：校准后应能 dual-agree
        # （此前 gate=0.5 恒 abstain-disagree，词法交叉验证形同失效）
        dr = DecisionRouter(FakeClient({"track": "static", "confidence": 0.9}))
        res = route_text(EX_STATIC, dr, LexicalRouter().fit(SENTENCES), llm_available=True)
        self.assertEqual(res.track, "static")
        self.assertEqual(res.source, "dual-agree")
        self.assertIsNone(res.aborted)

    def test_single_class_falls_back_to_seed(self):
        # 仅 dynamic 有 ≥3 样本 → 单类不可分 → 回退 seed，不强行降门槛
        r = LexicalRouter()
        r.fit([("明天开会", "dynamic"), ("今天回邮件", "dynamic"), ("处理故障", "dynamic")])
        self.assertTrue(r.fitted)
        self.assertEqual(r.gate, r._seed_gate)
        self.assertEqual(r.gate_source, "seed")


if __name__ == "__main__":
    unittest.main()
