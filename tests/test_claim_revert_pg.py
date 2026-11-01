"""zkc/distill.revert_claim 真实 PG 集成实测（残余 2 hook）。

需 docker + psycopg；ZKC_RUN_PG_TESTS=0 跳过。验证删 claim 后在真实 PG 上对其 evidence
节点级联 recompute_baseline_on_capture_loss：基线 28d→有连接 14d，且 interval_adjustment
审计 reason 含 capture-loss；仍被别的 claim 捕获则不重算。
"""
from __future__ import annotations

import os
import unittest
from datetime import timedelta

from zkc import distill as D
from zkc import scheduling as S
from zkc.repository import get_storage
from zkc.repository.models import Claim, ModelingArtifact, Node
from zkc import migrate


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgClaimRevertTest(unittest.TestCase):
    TEST_DB = "zkc_claim_revert_test"

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
        self._seed()

    def _seed(self):
        self.s1 = self.store.nodes.save(Node(title="S1", track="static", decay_score=0.0))
        self.d5 = self.store.nodes.save(Node(title="D5", track="dynamic", decay_score=0.0))
        self.c1 = self.store.claims.save(Claim(
            statement="D5 结论已被提炼", level="insight", evidence_refs=[self.d5.id]))
        self.store.edges.link(self.s1.id, self.d5.id, "derived_from")

    def _days(self, node_id) -> float:
        iv = self.store.nodes.get(node_id).baseline_interval
        return iv.total_seconds() / 86400.0

    def test_revert_recaptures_and_audits(self):
        S.assign_baselines(self.store)
        self.assertEqual(self._days(self.d5.id), S._t("BASELINE_CAPTURED_DAYS"))
        res = D.revert_claim(self.store, self.c1.id, produced_by=None)
        self.assertIsNone(self.store.claims.get(self.c1.id))
        self.assertTrue(res["recomputed"])
        self.assertEqual(self._days(self.d5.id), S._t("BASELINE_CONNECTED_DAYS"))
        cur = self.store._conn.cursor()
        cur.execute(
            "SELECT reason FROM public.interval_adjustment "
            "WHERE node_id=%s AND reason LIKE %s",
            (str(self.d5.id), "%capture-loss%"))
        self.assertTrue(cur.fetchall(), "capture-loss 审计缺失")

    def test_revert_no_op_when_still_captured(self):
        S.assign_baselines(self.store)
        self.assertEqual(self._days(self.d5.id), S._t("BASELINE_CAPTURED_DAYS"))
        c2 = self.store.claims.save(Claim(
            statement="另一条也捕获 D5", level="insight", evidence_refs=[self.d5.id]))
        before = self._days(self.d5.id)
        res = D.revert_claim(self.store, self.c1.id)
        self.assertIsNotNone(self.store.claims.get(c2.id))
        # 仍被 c2 捕获 → 该 evidence 节点的 recompute 内部 no-op（applied=False, tier=captured）
        self.assertEqual(len(res["recomputed"]), 1)
        rec = res["recomputed"][0]
        self.assertFalse(rec["applied"])
        self.assertEqual(rec["tier"], "captured")
        self.assertEqual(self._days(self.d5.id), before)
        self.assertEqual(self._days(self.d5.id), S._t("BASELINE_CAPTURED_DAYS"))


# ============================================================ 残余 A：artifact 撤销 hook（PG）

class PgArtifactRevertTest(PgClaimRevertTest):
    """modeling_artifact 走真实 PG（0001 基线已有表）：save/captured/revert 级联。"""

    def _artifact(self, evidence) -> ModelingArtifact:
        return self.store.artifacts.save(ModelingArtifact(
            title="方法论产物", kind="methodology", body={"steps": ["a"]},
            evidence_refs=list(evidence)))

    def test_artifact_captures_and_revert_cascades(self):
        a = self._artifact([self.d5.id])
        # 种子 claim c1 也捕获 d5 —— 本测试只验 artifact 捕获路径，先删掉种子 claim
        self.store.claims.delete(self.c1.id)
        S.assign_baselines(self.store)
        self.assertEqual(self._days(self.d5.id), S._t("BASELINE_CAPTURED_DAYS"))
        rows = {r.id: r for r in self.store.load_schedulable()}
        self.assertTrue(rows[self.d5.id].captured)

        res = D.revert_artifact(self.store, a.id)
        self.assertIsNone(self.store.artifacts.get(a.id))
        self.assertEqual(self._days(self.d5.id), S._t("BASELINE_CONNECTED_DAYS"))
        cur = self.store._conn.cursor()
        cur.execute(
            "SELECT reason FROM public.interval_adjustment "
            "WHERE node_id=%s AND reason LIKE %s",
            (str(self.d5.id), "%capture-loss%"))
        self.assertTrue(cur.fetchall(), "capture-loss 审计缺失")

    def test_revert_artifact_no_op_when_still_captured_by_claim(self):
        a = self._artifact([self.d5.id])
        c2 = self.store.claims.save(Claim(
            statement="claim 也捕获 D5", level="insight", evidence_refs=[self.d5.id]))
        S.assign_baselines(self.store)
        before = self._days(self.d5.id)

        res = D.revert_artifact(self.store, a.id)
        self.assertIsNotNone(self.store.claims.get(c2.id))
        rec = res["recomputed"][0]
        self.assertFalse(rec["applied"])
        self.assertEqual(rec["tier"], "captured")
        self.assertEqual(self._days(self.d5.id), before)
        self.assertEqual(self._days(self.d5.id), S._t("BASELINE_CAPTURED_DAYS"))


if __name__ == "__main__":
    unittest.main()
