"""S6 · 月扫 sweep 幂等红→绿。

语义（Q5 / 方案 §5）：月度门闩（同月重复 no-op）+ TTL 7d 边界 +
--dry-run 零写入 + sweep 不做墓碑标记/恢复（只处理已满 TTL 的既有墓碑）。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from zkc.repository import get_storage
from zkc.repository.models import Node
from zkc.tombstone import mark_tombstone
from zkc.sweep import sweep_tombstones


class SweepTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")
        self.now = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)

    def _tomb(self, title, days_ago):
        n = self.store.nodes.save(Node(track="dynamic", title=title, decay_score=1.0))
        mark_tombstone(self.store, n.id, operator="zj",
                       at=self.now - timedelta(days=days_ago))
        return n

    def test_ttl_boundary_7d(self):
        young = self._tomb("young", 6)   # 未满 7d
        old = self._tomb("old", 8)       # 满 7d
        res = sweep_tombstones(self.store, now=self.now, operator="zj")
        self.assertEqual(res["scanned"], 2)
        self.assertEqual(res["purged"], 1)
        self.assertIsNone(self.store.nodes.get(old.id))
        self.assertIsNotNone(self.store.nodes.get(young.id), "未满 7d 不得真删")

    def test_monthly_gate_noop_on_repeat(self):
        self._tomb("old", 8)
        first = sweep_tombstones(self.store, now=self.now, operator="zj")
        self.assertEqual(first["purged"], 1)
        # 同月再扫：门闩命中，no-op
        again = sweep_tombstones(self.store, now=self.now + timedelta(days=1), operator="zj")
        self.assertTrue(again["noop_month_gate"])
        self.assertEqual(again["purged"], 0)

    def test_cross_month_triggers(self):
        self._tomb("old-dec", 40)
        sweep_tombstones(self.store, now=datetime(2026, 12, 1, tzinfo=timezone.utc), operator="zj")
        # 次月新增墓碑，跨月应触发
        jan = self._tomb("old-jan", 8)
        res = sweep_tombstones(self.store, now=datetime(2027, 1, 10, tzinfo=timezone.utc),
                               operator="zj")
        self.assertFalse(res["noop_month_gate"])
        self.assertIsNone(self.store.nodes.get(jan.id))

    def test_dry_run_zero_writes(self):
        old = self._tomb("old", 8)
        res = sweep_tombstones(self.store, now=self.now, operator="zj", dry_run=True)
        self.assertTrue(res["dry_run"])
        self.assertGreaterEqual(res["eligible"], 1)
        self.assertEqual(res["purged"], 0)
        self.assertIsNotNone(self.store.nodes.get(old.id), "dry-run 不得删节点")
        self.assertEqual(self.store.tasks.list_open(self.now), [])

    def test_sweep_never_marks_or_restores(self):
        n = self.store.nodes.save(Node(track="dynamic", title="active", decay_score=1.0))
        sweep_tombstones(self.store, now=self.now, operator="zj")
        self.assertIsNone(self.store.nodes.get(n.id).deleted_at, "sweep 不得自动标记墓碑")


if __name__ == "__main__":
    unittest.main()
