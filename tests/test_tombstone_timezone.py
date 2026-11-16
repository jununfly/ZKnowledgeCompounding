"""S3 时区回归（独立 TDD 切片，2026-11-16）。

背景：mark_tombstone/restore_node 的生产默认路径 `at = at or datetime.now()`
用 naive 本地时区；而 sweep/daily 用 aware UTC。本机 UTC+8 → 墓碑时刻被存成
「真 UTC +8h」，list_tombstones_before 的 `deleted_at <= now` 恒扫不到。

现有 test_tombstone_human/sweep 全部显式传 at=self.now（aware UTC），
从不走生产默认分支，故全绿也漏报。本文件专锁「不传 at」的生产路径。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from zkc.repository import get_storage
from zkc.repository.models import Node
from zkc.sweep import sweep_tombstones
from zkc.tombstone import mark_tombstone, restore_node


class TombstoneTimezoneTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")

    def _node(self):
        return self.store.nodes.save(
            Node(track="dynamic", title="tz-victim", decay_score=0.9)
        ).id

    def test_mark_default_time_is_aware_utc(self):
        """生产默认路径（不传 at）产出的墓碑时刻必须是 aware UTC，不得 naive 本地。"""
        nid = self._node()
        res = mark_tombstone(self.store, nid, operator="zj")  # 不传 at = 生产路径
        self.assertTrue(res["applied"])
        stored = self.store.nodes.get(nid).deleted_at
        self.assertIsNotNone(
            stored.tzinfo,
            "墓碑时刻必须 aware：生产默认不得用 naive datetime.now()（本机 UTC+8 会未来化 8h）",
        )
        self.assertEqual(stored.utcoffset(), timedelta(0), "墓碑时刻时区必须是 UTC")

    def test_restore_default_time_is_aware_utc(self):
        """restore 的生产默认时刻同样是 aware UTC（对称守门）。"""
        nid = self._node()
        mark_tombstone(self.store, nid, operator="zj", at=datetime.now(timezone.utc))
        res = restore_node(self.store, nid, operator="zj")  # 不传 at = 生产路径
        self.assertTrue(res["applied"])
        self.assertIsNotNone(res["restored_at"].tzinfo, "恢复时刻必须 aware UTC")
        self.assertEqual(res["restored_at"].utcoffset(), timedelta(0))

    def test_sweep_sees_freshly_marked_tombstone_via_default_path(self):
        """生产场景闭环：此刻经默认路径 mark 的墓碑，此刻 sweep 必须扫得到。
        bug 下墓碑被未来化 8h，deleted_at <= now 恒 false → scanned=0（或 naive/aware
        比较直接 TypeError），两种都是失败。"""
        nid = self._node()
        mark_tombstone(self.store, nid, operator="zj")  # 不传 at = 生产路径
        res = sweep_tombstones(
            self.store, now=datetime.now(timezone.utc), operator="zj", dry_run=True)
        self.assertGreaterEqual(
            res["scanned"], 1,
            "刚经生产路径标记的墓碑必须出现在扫描中，不得被时区未来化后永远扫不到",
        )


if __name__ == "__main__":
    unittest.main()
