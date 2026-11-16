"""S4 · 真删引用闸门红→绿。

闸门扫三处引用：meta_claim.evidence_refs / modeling_artifact.evidence_refs /
citation.citing_node_id（真实表名，非 ADR 笔误 claim_evidence）。
任一命中 → 拒删（保留墓碑态）+ 写 task_queue 告警（kind=tombstone_purge_blocked）；
无引用 → 放行（真删本身在 S5，本切片只测闸门判定与告警）。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from zkc.repository import get_storage
from zkc.repository.models import Claim, ModelingArtifact, Node, TaskSpec
from zkc.purge_gate import check_purge_blockers, gate_and_report


class PurgeGateTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")
        self.now = datetime.now(timezone.utc)
        n = self.store.nodes.save(Node(track="dynamic", title="tomb", decay_score=1.0))
        self.nid = n.id
        self.store.nodes.tombstone(self.nid, self.now - timedelta(days=8))

    def test_no_reference_passes(self):
        blockers = check_purge_blockers(self.store, self.nid)
        self.assertEqual(blockers, [])

    def test_claim_evidence_reference_blocks(self):
        self.store.claims.save(Claim(statement="s", evidence_refs=[self.nid]))
        blockers = check_purge_blockers(self.store, self.nid)
        self.assertTrue(any(b["kind"] == "claim_evidence" for b in blockers))

    def test_artifact_evidence_reference_blocks(self):
        self.store.artifacts.save(ModelingArtifact(
            title="a", kind="methodology", body={}, evidence_refs=[self.nid]))
        blockers = check_purge_blockers(self.store, self.nid)
        self.assertTrue(any(b["kind"] == "artifact_evidence" for b in blockers))

    def test_gate_reports_and_enqueues_task_on_block(self):
        self.store.claims.save(Claim(statement="s", evidence_refs=[self.nid]))
        res = gate_and_report(self.store, self.nid, now=self.now)
        self.assertFalse(res["allowed"])
        self.assertTrue(res["blockers"])
        self.assertIn("claim_evidence", res["blockers"][0]["kind"])
        # 告警落 task_queue
        tasks = self.store.tasks.list_open(self.now)
        self.assertTrue(any(t.kind == "tombstone_purge_blocked" for t in tasks))

    def test_gate_allows_when_clean(self):
        res = gate_and_report(self.store, self.nid, now=self.now)
        self.assertTrue(res["allowed"])
        self.assertEqual(res["blockers"], [])
        self.assertEqual(self.store.tasks.list_open(self.now), [])

    def test_gate_does_not_delete_node(self):
        # 闸门只判定 + 告警，不做真删（真删 S5）
        self.store.claims.save(Claim(statement="s", evidence_refs=[self.nid]))
        gate_and_report(self.store, self.nid, now=self.now)
        self.assertIsNotNone(self.store.nodes.get(self.nid), "闸门不得删节点")


if __name__ == "__main__":
    unittest.main()
