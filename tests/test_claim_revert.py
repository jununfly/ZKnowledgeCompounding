"""zkc/distill.revert_claim 单测（残余 2 hook：级联 recompute_baseline_on_capture_loss）。

覆盖：删 claim 后对其每条 evidence 节点级联重算 → 基线 28d→未捕获基线（有连接 14d /
孤儿 7d）且 D7 审计 reason 含 capture-loss；节点仍被别的 claim 捕获 → no-op。
PG 集成行为见 tests/test_claim_revert_pg.py。
"""
from __future__ import annotations

import unittest
from datetime import timedelta
from uuid import uuid4

from zkc import distill as D
from zkc import scheduling as S
from zkc.repository import get_storage
from zkc.repository.models import Claim, ModelingArtifact, Node


def _days(store, node_id) -> float:
    iv = store.nodes.get(node_id).baseline_interval
    return iv.total_seconds() / 86400.0


class ClaimRevertTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")
        self.now = None
        self.n = self.store.nodes.save(
            Node(title="提炼过的记录", content="b", track="dynamic", decay_score=0.0))
        self.src = self.store.nodes.save(
            Node(title="源", content="b", track="dynamic", decay_score=0.0))
        self.store.edges.link(self.src.id, self.n.id, "derived_from")

    def _claim(self, evidence) -> Claim:
        return self.store.claims.save(Claim(
            statement="结论已被提炼", level="insight", evidence_refs=list(evidence)))

    # ------------------------------------------------------------------
    def test_revert_recaptures_baseline_and_audits(self):
        c = self._claim([self.n.id])
        S.assign_baselines(self.store)
        # 已捕获 → 28d
        self.assertEqual(_days(self.store, self.n.id), S._t("BASELINE_CAPTURED_DAYS"))

        res = D.revert_claim(self.store, c.id, produced_by=None)
        # claim 已删
        self.assertIsNone(self.store.claims.get(c.id))
        # 级联重算：有连接 → 14d（非孤儿 7d）
        self.assertTrue(res["recomputed"])
        self.assertTrue(any(r["node_id"] == self.n.id for r in res["recomputed"]))
        self.assertEqual(_days(self.store, self.n.id), S._t("BASELINE_CONNECTED_DAYS"))
        # D7 审计 reason 含 capture-loss
        audit = [a for a in self.store.nodes._audit_log
                 if a["node_id"] == self.n.id and "capture-loss" in a["reason"]]
        self.assertTrue(audit, "capture-loss 审计缺失")
        # 返回的 recomputed 项 reason 也含 capture-loss
        rec = next(r for r in res["recomputed"] if r["node_id"] == self.n.id)
        self.assertIn("capture-loss", rec["reason"])

    def test_revert_no_op_when_still_captured_by_other(self):
        # 两条 claim 都捕获同一节点 → 删一条，仍被另一条捕获 → 不重算
        c1 = self._claim([self.n.id])
        c2 = self._claim([self.n.id])
        S.assign_baselines(self.store)
        self.assertEqual(_days(self.store, self.n.id), S._t("BASELINE_CAPTURED_DAYS"))
        before = _days(self.store, self.n.id)

        res = D.revert_claim(self.store, c1.id)
        self.assertIsNone(self.store.claims.get(c1.id))
        self.assertIsNotNone(self.store.claims.get(c2.id))
        # 仍被 c2 捕获 → 该 evidence 节点的 recompute 内部 no-op（applied=False, tier=captured）
        self.assertEqual(len(res["recomputed"]), 1)
        rec = res["recomputed"][0]
        self.assertEqual(rec["node_id"], self.n.id)
        self.assertFalse(rec["applied"])
        self.assertEqual(rec["tier"], "captured")
        self.assertEqual(_days(self.store, self.n.id), before)
        self.assertEqual(_days(self.store, self.n.id), S._t("BASELINE_CAPTURED_DAYS"))

    def test_revert_orphan_falls_to_orphan_days(self):
        # 无连接、无上下文的捕获节点 → 撤销后应为孤儿 7d
        orphan = self.store.nodes.save(
            Node(title="孤立记录", content="b", track="dynamic", decay_score=0.0))
        c = self._claim([orphan.id])
        S.assign_baselines(self.store)
        self.assertEqual(_days(self.store, orphan.id), S._t("BASELINE_CAPTURED_DAYS"))

        D.revert_claim(self.store, c.id)
        self.assertEqual(_days(self.store, orphan.id), S._t("BASELINE_ORPHAN_DAYS"))


# ============================================================ 残余 A：artifact 撤销 hook

class ArtifactRevertTest(unittest.TestCase):
    """ArtifactRepository + revert_artifact：建模产物捕获/撤销与 claim 完全同语义。"""

    def setUp(self):
        self.store = get_storage("memory")
        self.n = self.store.nodes.save(
            Node(title="被结合的记录", content="b", track="dynamic", decay_score=0.0))
        self.src = self.store.nodes.save(
            Node(title="源", content="b", track="dynamic", decay_score=0.0))
        self.store.edges.link(self.src.id, self.n.id, "derived_from")

    def _artifact(self, evidence) -> ModelingArtifact:
        return self.store.artifacts.save(ModelingArtifact(
            title="方法论产物", kind="methodology", body={"steps": ["a"]},
            evidence_refs=list(evidence)))

    def test_artifact_captures_node(self):
        a = self._artifact([self.n.id])
        rows = {r.id: r for r in self.store.load_schedulable()}
        self.assertTrue(rows[self.n.id].captured,
                        "artifact evidence 应使 memory load_schedulable.captured=True（与 PG 对齐）")
        S.assign_baselines(self.store)
        self.assertEqual(_days(self.store, self.n.id), S._t("BASELINE_CAPTURED_DAYS"))
        self.assertIsNotNone(self.store.artifacts.get(a.id))
        # memory load_metric_inputs 的 artifact_evidence 补齐（此前 fake 返回空）
        mi = self.store.load_metric_inputs()
        self.assertIn([self.n.id], [list(x) for x in mi.artifact_evidence])

    def test_revert_artifact_cascades_recompute_and_audits(self):
        a = self._artifact([self.n.id])
        S.assign_baselines(self.store)
        self.assertEqual(_days(self.store, self.n.id), S._t("BASELINE_CAPTURED_DAYS"))

        res = D.revert_artifact(self.store, a.id)
        self.assertIsNone(self.store.artifacts.get(a.id))
        self.assertTrue(any(r["node_id"] == self.n.id for r in res["recomputed"]))
        self.assertEqual(_days(self.store, self.n.id), S._t("BASELINE_CONNECTED_DAYS"))
        audit = [x for x in self.store.nodes._audit_log
                 if x["node_id"] == self.n.id and "capture-loss" in x["reason"]]
        self.assertTrue(audit, "capture-loss 审计缺失")

    def test_revert_artifact_no_op_when_still_captured_by_claim(self):
        self._artifact([self.n.id])
        c = self.store.claims.save(Claim(statement="s", evidence_refs=[self.n.id]))
        S.assign_baselines(self.store)
        before = _days(self.store, self.n.id)

        res = D.revert_artifact(self.store, next(iter(
            self.store.artifacts.list_by_evidence(self.n.id))).id)
        self.assertIsNotNone(self.store.claims.get(c.id))
        rec = res["recomputed"][0]
        self.assertEqual(rec["node_id"], self.n.id)
        self.assertFalse(rec["applied"])
        self.assertEqual(rec["tier"], "captured")
        self.assertEqual(_days(self.store, self.n.id), before)

    def test_revert_artifact_missing_is_noop(self):
        res = D.revert_artifact(self.store, uuid4())
        self.assertFalse(res["deleted"])
        self.assertEqual(res["recomputed"], [])


if __name__ == "__main__":
    unittest.main()
