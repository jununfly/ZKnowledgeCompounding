"""zkc/expiry 纯函数单测（spike-08 路由提升进生产，无 DB 依赖）。

覆盖到期分流决策表（captured→archive / conn|context 未捕获→distill（压力≥0.8→abstain）
/ orphan→abstain）、apply_archive、enqueue_review、route_and_apply（含去重）、
process_expired_dynamic_nodes（refresh_decay 后路由全部到期节点）。

PG 集成行为见 tests/test_expiry_pg.py。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from zkc import distill as D
from zkc import expiry as E
from zkc import scheduling as S
from zkc.repository import get_storage
from zkc.repository.models import Claim, Node


def _make_node(store, title="t", content=None,
               last_reviewed=None, interval_days=7) -> Node:
    n = store.nodes.save(Node(track="dynamic", title=title, content=content,
                              decay_score=0.0))
    store.nodes.set_baseline_interval(n.id, timedelta(days=interval_days), "auto", "seed")
    lr = last_reviewed if last_reviewed is not None else datetime(2020, 1, 1, tzinfo=timezone.utc)
    store.nodes.mark_reviewed(n.id, lr)
    return n


class ExpiryRouteTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # 让 refresh_decay 计算出的 decay 必然 ≥ ROT
        self.old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        # 让 refresh_decay 计算出的 decay < ROT
        self.recent = self.now - timedelta(days=1)

    def _expired(self, **kw) -> Node:
        n = _make_node(self.store, last_reviewed=self.old, **kw)
        # 直接钉死 decay，使 route_expired 的判定与 refresh 解耦（direct 测试）
        self.store.nodes.update_decay(n.id, 0.95)
        return n

    # ------------------------------------------------------------ 决策表
    def test_captured_archives(self):
        n = self._expired()
        self.store.claims.save(Claim(statement="s", evidence_refs=[n.id]))
        r = E.route_expired(self.store, n.id)
        self.assertTrue(r["routable"])
        self.assertEqual(r["action"], "archive")
        self.assertTrue(r["signals"]["captured"])

    def test_connected_distills(self):
        n = self._expired()
        src = _make_node(self.store, title="src")
        self.store.edges.link(src.id, n.id, "derived_from")
        r = E.route_expired(self.store, n.id)
        self.assertEqual(r["action"], "distill")
        self.assertFalse(r["signals"]["captured"])
        self.assertGreaterEqual(r["signals"]["conn_count"], 1)

    def test_self_loop_context_distills(self):
        # 仅 self_loop 上下文、无连接、未捕获 → 仍应 distill（属于「有上下文」）
        n = self._expired()
        ctx = self.store.contexts.save(
            __import__("zkc.repository.models", fromlist=["Context"]).Context(
                scope="self_loop", title="proj"))
        self.store.contexts.add_member(ctx.id, n.id, produced_by=uuid4())
        r = E.route_expired(self.store, n.id)
        self.assertEqual(r["action"], "distill")

    def test_connected_high_pressure_abstains(self):
        n = self._expired()
        src = _make_node(self.store, title="src")
        self.store.edges.link(src.id, n.id, "derived_from")
        r = E.route_expired(self.store, n.id, attention_pressure=0.9)
        self.assertEqual(r["action"], "abstain")

    def test_orphan_abstains(self):
        n = self._expired()
        r = E.route_expired(self.store, n.id)
        self.assertEqual(r["action"], "abstain")

    # ------------------------------------------------------------ 不可路由
    def test_not_expired_not_routable(self):
        n = _make_node(self.store, last_reviewed=self.recent)  # decay ≈ 0.14
        r = E.route_expired(self.store, n.id)
        self.assertFalse(r["routable"])
        self.assertIsNone(r["action"])

    def test_static_not_routable(self):
        n = self.store.nodes.save(Node(title="s", track="static", decay_score=0.0))
        r = E.route_expired(self.store, n.id)
        self.assertFalse(r["routable"])

    def test_already_archived_not_routable(self):
        n = self._expired()
        self.store.nodes.archive(n.id, self.now)
        r = E.route_expired(self.store, n.id)
        self.assertFalse(r["routable"])

    # ------------------------------------------------------------ 应用侧
    def test_apply_archive_sets_archived_at(self):
        n = self._expired()
        E.apply_archive(self.store, n.id, self.now)
        self.assertIsNotNone(self.store.nodes.get(n.id).archived_at)

    def test_enqueue_review_persists(self):
        n = self._expired()
        E.enqueue_review(self.store, n.id, "distill", "reason")
        items = self.store.review_queue.list_open()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].action, "distill")
        self.assertEqual(items[0].node_id, n.id)

    def test_route_and_apply_captured_archives_and_skips_queue(self):
        n = self._expired()
        self.store.claims.save(Claim(statement="s", evidence_refs=[n.id]))
        r = E.route_and_apply(self.store, n.id)
        self.assertEqual(r["action"], "archive")
        self.assertIsNotNone(self.store.nodes.get(n.id).archived_at)
        self.assertEqual(self.store.review_queue.list_open(), [])

    def test_route_and_apply_connected_enqueues_distill(self):
        n = self._expired()
        src = _make_node(self.store, title="src")
        self.store.edges.link(src.id, n.id, "derived_from")
        r = E.route_and_apply(self.store, n.id)
        self.assertEqual(r["action"], "distill")
        items = self.store.review_queue.list_open()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].action, "distill")

    def test_route_and_apply_dedup_no_double_enqueue(self):
        n = self._expired()
        src = _make_node(self.store, title="src")
        self.store.edges.link(src.id, n.id, "derived_from")
        E.route_and_apply(self.store, n.id)
        E.route_and_apply(self.store, n.id)  # 第二次：同 action 已 open → 跳过
        self.assertEqual(len(self.store.review_queue.list_open()), 1)

    # ------------------------------------------------------------ 批量
    def test_process_expired_routes_all(self):
        # 到期：captured / connected / orphan
        cap = _make_node(self.store, title="cap", last_reviewed=self.old)
        self.store.claims.save(Claim(statement="s", evidence_refs=[cap.id]))
        conn = _make_node(self.store, title="conn", last_reviewed=self.old)
        # src 用 static：不进 load_schedulable，但其出边仍给 conn 一个连接计数
        src = self.store.nodes.save(Node(track="static", title="src", decay_score=0.0))
        self.store.nodes.set_baseline_interval(src.id, timedelta(days=7), "auto", "seed")
        self.store.edges.link(src.id, conn.id, "derived_from")
        orph = _make_node(self.store, title="orph", last_reviewed=self.old)
        # 未到期：不应被路由
        fresh = _make_node(self.store, title="fresh", last_reviewed=self.recent)

        res = E.process_expired_dynamic_nodes(self.store, now=self.now)
        self.assertEqual(res["processed"], 3)
        self.assertEqual(res["archived"], 1)
        self.assertEqual(res["distilled"], 1)
        self.assertEqual(res["abstained"], 1)
        self.assertIsNotNone(self.store.nodes.get(cap.id).archived_at)
        # 未到期节点保持未归档
        self.assertIsNone(self.store.nodes.get(fresh.id).archived_at)
        # 未到期节点不被钉 decay（refresh 后衰减低，仍 < ROT）
        self.assertLess(self.store.nodes.get(fresh.id).decay_score, S._t("ROT_THRESHOLD"))


# ============================================================ 真蒸馏接线（残余 B）

class ApplyDistillTest(unittest.TestCase):
    """apply_distill：distill 决策不再只入队——可注入 distiller 真跑蒸馏并落 claim。"""

    def setUp(self):
        self.store = get_storage("memory")
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.old = datetime(2020, 1, 1, tzinfo=timezone.utc)

    def _expired_connected(self) -> Node:
        n = _make_node(self.store, title="conn", content="材料正文",
                       last_reviewed=self.old)
        # src 用 static：不进 load_schedulable，但其出边仍给 conn 一个连接计数
        src = self.store.nodes.save(Node(track="static", title="src", decay_score=0.0))
        self.store.nodes.set_baseline_interval(src.id, timedelta(days=7), "auto", "seed")
        self.store.edges.link(src.id, n.id, "derived_from")
        self.store.nodes.update_decay(n.id, 0.95)
        return n

    @staticmethod
    def _distiller_ok():
        """可注入 distiller：(store, node_id) -> DistillationResult。走真实 distill_node。"""
        def _d(store, nid):
            node = store.nodes.get(nid)
            return D.distill_node(nid, [(nid, node.title or "t")],
                                  lambda prompt: f"蒸馏结论 [[{nid}]]")
        return _d

    def test_apply_distill_saves_claim_and_resets_decay(self):
        n = self._expired_connected()
        res = E.apply_distill(self.store, n.id, self._distiller_ok(), now=self.now)
        self.assertTrue(res["applied"])
        claims = self.store.claims.list_by_evidence(n.id)
        self.assertEqual(len(claims), 1)
        self.assertIn(n.id, claims[0].evidence_refs)
        self.assertEqual(res["claim_ids"], [claims[0].id])
        # mark_reviewed 复位衰减钟 → 节点重新进入 captured 28d 观察期（单程票 pacing）
        node = self.store.nodes.get(n.id)
        self.assertEqual(node.decay_score, 0.0)
        self.assertEqual(node.last_reviewed_at, self.now)

    def test_apply_distill_failure_falls_back_to_human_queue(self):
        n = self._expired_connected()

        def bad(store, nid):
            return D.DistillationResult(claims=[])  # 空产物 → validate 抛 DistillationError

        res = E.apply_distill(self.store, n.id, bad, now=self.now)
        self.assertFalse(res["applied"])
        self.assertEqual(self.store.claims.list_by_evidence(n.id), [])
        items = self.store.review_queue.list_open()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].action, "distill")

    def test_apply_distill_raises_also_fall_back(self):
        n = self._expired_connected()

        def boom(store, nid):
            raise RuntimeError("llm offline")

        res = E.apply_distill(self.store, n.id, boom, now=self.now)
        self.assertFalse(res["applied"])
        self.assertEqual(len(self.store.review_queue.list_open()), 1)

    # ---------------------------------------------- 蒸馏结构化接线：score 表落库（Langfuse 替代）

    def test_apply_distill_success_records_score(self):
        n = self._expired_connected()
        res = E.apply_distill(self.store, n.id, self._distiller_ok(),
                              now=self.now, model="m-test")
        self.assertTrue(res["applied"])
        rows = self.store.scores.list_recent()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r.operation, "distill")
        self.assertEqual(r.node_id, n.id)
        self.assertEqual(r.model, "m-test")
        self.assertTrue(r.parse_ok)
        self.assertEqual(r.attempts, 1)
        self.assertEqual(r.n_claims, 1)
        self.assertEqual(r.n_citations, 1)
        self.assertIsNone(r.error)
        self.assertIsNotNone(r.id)
        self.assertIsNotNone(r.created_at)
        self.assertGreaterEqual(r.latency_ms, 0.0)

    def test_apply_distill_failure_records_score_with_error(self):
        n = self._expired_connected()

        def bad(store, nid):
            return D.DistillationResult(claims=[])

        E.apply_distill(self.store, n.id, bad, now=self.now, model="m-test")
        rows = self.store.scores.list_recent()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertFalse(r.parse_ok)
        self.assertIn("distillation", (r.error or ""))
        self.assertIsNone(r.n_claims)  # 失败路径拿不到产物计数（诚实语义：未知非 0）

    def test_score_human_verdict_roundtrip(self):
        # rubric 人工打分入口：good/bad 可回填，非法值拒绝
        n = self._expired_connected()
        E.apply_distill(self.store, n.id, self._distiller_ok(), now=self.now)
        row = self.store.scores.list_recent()[0]
        self.assertIsNone(row.human_verdict)
        self.store.scores.set_human_verdict(row.id, "good")
        self.assertEqual(self.store.scores.list_recent()[0].human_verdict, "good")
        self.store.scores.set_human_verdict(row.id, "bad")
        self.assertEqual(self.store.scores.list_recent()[0].human_verdict, "bad")
        with self.assertRaises(ValueError):
            self.store.scores.set_human_verdict(row.id, "meh")

    def test_score_list_recent_orders_and_limits(self):
        n = self._expired_connected()
        E.apply_distill(self.store, n.id, self._distiller_ok(), now=self.now)
        E.apply_distill(self.store, n.id, self._distiller_ok(), now=self.now)
        rows = self.store.scores.list_recent(limit=1)
        self.assertEqual(len(rows), 1)  # 最近一条

    def test_route_and_apply_with_distiller_runs_distill_not_enqueue(self):
        n = self._expired_connected()
        r = E.route_and_apply(self.store, n.id, distiller=self._distiller_ok())
        self.assertEqual(r["action"], "distill")
        self.assertEqual(len(self.store.claims.list_by_evidence(n.id)), 1)
        self.assertEqual(self.store.review_queue.list_open(), [])

    def test_route_and_apply_distiller_resolves_prior_open_item(self):
        # 先前（无 distiller 的轮次）已入队 → 有 distiller 后蒸馏成功应 resolve 该项
        n = self._expired_connected()
        E.route_and_apply(self.store, n.id)  # 入队
        self.assertEqual(len(self.store.review_queue.list_open()), 1)
        r = E.route_and_apply(self.store, n.id, distiller=self._distiller_ok())
        self.assertTrue(r["applied"])
        self.assertEqual(self.store.review_queue.list_open(), [])

    def test_process_expired_with_distiller_counts(self):
        n = self._expired_connected()
        res = E.process_expired_dynamic_nodes(
            self.store, distiller=self._distiller_ok(), now=self.now)
        self.assertEqual(res["distilled"], 1)
        self.assertEqual(len(self.store.claims.list_by_evidence(n.id)), 1)


if __name__ == "__main__":
    unittest.main()
