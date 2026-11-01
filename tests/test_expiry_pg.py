"""zkc/expiry 真实 PG 集成实测（spike-08 路由提升进生产）。

需 docker + psycopg；ZKC_RUN_PG_TESTS=0 跳过。验证 route_and_apply 在真实 PG 上
归档 persisted（archived_at 落库）、distill 入队 persisted（review_queue 行），
以及 process_expired_dynamic_nodes 批量路由计数正确。
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from zkc import distill as D
from zkc import expiry as E
from zkc.repository import get_storage
from zkc.repository.models import Claim, Node
from zkc import migrate


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgExpiryTest(unittest.TestCase):
    TEST_DB = "zkc_expiry_test"

    @classmethod
    def setUpClass(cls):
        import psycopg

        cls._orig_dsn = os.environ.get("ZKC_PG_DSN")
        base_dsn = cls._orig_dsn or "postgresql://postgres:zkc@localhost:55433/zkc_dev"
        cls._pg = psycopg.connect(base_dsn.replace("/zkc_dev", "/postgres"), autocommit=True)
        cls._pg.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        cls._pg.execute(f'CREATE DATABASE "{cls.TEST_DB}"')
        cls._pg.close()
        cls._test_dsn = base_dsn.replace("/zkc_dev", f"/{cls.TEST_DB}")
        migrate.apply_all(cls.TEST_DB)
        os.environ["ZKC_PG_DSN"] = cls._test_dsn

    @classmethod
    def tearDownClass(cls):
        import psycopg

        c = psycopg.connect(cls._test_dsn.replace(f"/{cls.TEST_DB}", "/postgres"), autocommit=True)
        c.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        c.close()
        if cls._orig_dsn is None:
            os.environ.pop("ZKC_PG_DSN", None)
        else:
            os.environ["ZKC_PG_DSN"] = cls._orig_dsn

    def setUp(self):
        self.store = get_storage("pg")
        self.store.clear_all()
        self.now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    def _node(self, title, last_reviewed=None) -> Node:
        n = self.store.nodes.save(Node(track="dynamic", title=title, decay_score=0.0))
        self.store.nodes.set_baseline_interval(n.id, timedelta(days=7), "auto", "seed")
        self.store.nodes.mark_reviewed(
            n.id, last_reviewed or datetime(2020, 1, 1, tzinfo=timezone.utc))
        return n

    def test_route_and_apply_captured_archives(self):
        n = self._node("cap")
        self.store.claims.save(Claim(statement="s", evidence_refs=[n.id]))
        self.store.nodes.update_decay(n.id, 0.95)
        r = E.route_and_apply(self.store, n.id)
        self.assertEqual(r["action"], "archive")
        cur = self.store._conn.cursor()
        cur.execute("SELECT archived_at FROM public.node WHERE id=%s", (str(n.id),))
        self.assertIsNotNone(cur.fetchone()[0])

    def test_route_and_apply_connected_enqueues(self):
        n = self._node("conn")
        src = self._node("src")
        self.store.edges.link(src.id, n.id, "derived_from")
        self.store.nodes.update_decay(n.id, 0.95)
        r = E.route_and_apply(self.store, n.id)
        self.assertEqual(r["action"], "distill")
        cur = self.store._conn.cursor()
        cur.execute(
            "SELECT count(*) FROM public.review_queue WHERE node_id=%s AND action='distill'",
            (str(n.id),))
        self.assertEqual(cur.fetchone()[0], 1)

    def test_process_expired_routes_three(self):
        cap = self._node("cap", datetime(2020, 1, 1, tzinfo=timezone.utc))
        self.store.claims.save(Claim(statement="s", evidence_refs=[cap.id]))
        conn = self._node("conn", datetime(2020, 1, 1, tzinfo=timezone.utc))
        src = self.store.nodes.save(Node(track="static", title="src", decay_score=0.0))
        self.store.nodes.set_baseline_interval(src.id, timedelta(days=7), "auto", "seed")
        self.store.edges.link(src.id, conn.id, "derived_from")
        orph = self._node("orph", datetime(2020, 1, 1, tzinfo=timezone.utc))
        fresh = self._node("fresh", self.now - timedelta(days=1))  # 未到期

        res = E.process_expired_dynamic_nodes(self.store, now=self.now)
        self.assertEqual(res["processed"], 3)
        self.assertEqual(res["archived"], 1)
        self.assertEqual(res["distilled"], 1)
        self.assertEqual(res["abstained"], 1)
        cur = self.store._conn.cursor()
        cur.execute("SELECT archived_at FROM public.node WHERE id=%s", (str(cap.id),))
        self.assertIsNotNone(cur.fetchone()[0])


# ============================================================ 真蒸馏接线（残余 B，PG）

class PgApplyDistillTest(PgExpiryTest):
    """apply_distill 在真实 PG 上：claim 落库 + mark_reviewed 复位 + 失败回落入队。"""

    def _expired_connected(self) -> Node:
        n = self._node("conn")
        src = self._node("src")
        self.store.edges.link(src.id, n.id, "derived_from")
        self.store.nodes.update_decay(n.id, 0.95)
        return n

    @staticmethod
    def _distiller_ok():
        def _d(store, nid):
            node = store.nodes.get(nid)
            return D.distill_node(nid, [(nid, node.title or "t")],
                                  lambda prompt: f"蒸馏结论 [[{nid}]]")
        return _d

    def test_apply_distill_saves_claim_and_resets_decay(self):
        n = self._expired_connected()
        res = E.apply_distill(self.store, n.id, self._distiller_ok(), now=self.now)
        self.assertTrue(res["applied"])
        cur = self.store._conn.cursor()
        cur.execute(
            "SELECT count(*) FROM public.meta_claim WHERE %s::uuid = ANY(evidence_refs)",
            (str(n.id),))
        self.assertEqual(cur.fetchone()[0], 1)
        node = self.store.nodes.get(n.id)
        self.assertEqual(node.decay_score, 0.0)
        self.assertEqual(node.last_reviewed_at, self.now)

    def test_apply_distill_failure_falls_back_to_queue(self):
        n = self._expired_connected()

        def bad(store, nid):
            return D.DistillationResult(claims=[])

        res = E.apply_distill(self.store, n.id, bad, now=self.now)
        self.assertFalse(res["applied"])
        cur = self.store._conn.cursor()
        cur.execute(
            "SELECT count(*) FROM public.review_queue WHERE node_id=%s AND action='distill'",
            (str(n.id),))
        self.assertEqual(cur.fetchone()[0], 1)

    def test_route_and_apply_with_distiller_resolves_prior_item(self):
        n = self._expired_connected()
        E.route_and_apply(self.store, n.id)  # 旧轮次入队
        r = E.route_and_apply(self.store, n.id, distiller=self._distiller_ok())
        self.assertTrue(r["applied"])
        cur = self.store._conn.cursor()
        cur.execute(
            "SELECT count(*) FROM public.review_queue "
            "WHERE node_id=%s AND action='distill' AND NOT resolved",
            (str(n.id),))
        self.assertEqual(cur.fetchone()[0], 0)


# ============================================================ 1-5-6：score 表（PG）

class PgScoreTest(PgExpiryTest):
    """llm_call_score 真实 PG：apply_distill 落库 + rubric 回填（Langfuse 替代）。"""

    def test_apply_distill_success_records_score(self):
        n = self._node("conn")
        src = self._node("src")
        self.store.edges.link(src.id, n.id, "derived_from")
        self.store.nodes.update_decay(n.id, 0.95)

        def ok(store, nid):
            return D.distill_node(nid, [(nid, "材料")],
                                  lambda p: '{"claims": [{"text": "c", '
                                            '"topic": "t", '
                                            '"citations": ["%s"]}]}' % nid)

        res = E.apply_distill(self.store, n.id, ok, now=self.now, model="m-test")
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

    def test_apply_distill_failure_records_score(self):
        n = self._node("conn")
        src = self._node("src")
        self.store.edges.link(src.id, n.id, "derived_from")
        self.store.nodes.update_decay(n.id, 0.95)

        def bad(store, nid):
            return D.DistillationResult(claims=[])

        res = E.apply_distill(self.store, n.id, bad, now=self.now)
        self.assertFalse(res["applied"])
        r = self.store.scores.list_recent()[0]
        self.assertFalse(r.parse_ok)
        self.assertTrue(r.error)

    def test_score_human_verdict_roundtrip(self):
        from zkc.repository.models import LLMCallScore

        self.store.scores.record(LLMCallScore(operation="distill", parse_ok=True))
        row = self.store.scores.list_recent()[0]
        self.assertIsNone(row.human_verdict)
        self.store.scores.set_human_verdict(row.id, "good")
        self.assertEqual(self.store.scores.list_recent()[0].human_verdict, "good")
        with self.assertRaises(ValueError):
            self.store.scores.set_human_verdict(row.id, "meh")

    def test_human_verdict_check_constraint(self):
        # DB CHECK 白名单是最后一道闸：repository 层漏检也进不了库
        from zkc.repository.models import LLMCallScore

        self.store.scores.record(LLMCallScore(operation="distill", parse_ok=True))
        row = self.store.scores.list_recent()[0]
        cur = self.store._conn.cursor()
        with self.assertRaises(Exception):
            cur.execute(
                "UPDATE public.llm_call_score SET human_verdict='meh' WHERE id=%s",
                (str(row.id),))
        self.store._conn.rollback()


if __name__ == "__main__":
    unittest.main()
