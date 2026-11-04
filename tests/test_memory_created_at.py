"""Risk B TDD · 内存后端 save 必须设 created_at（对齐 PG 的 created_at 默认 now()）。

背景：PG 实现的 node 在 INSERT 时由 DB 默认 created_at=now()；内存实现此前不设置，
导致 count_nodes_created_since 对内存后端恒返 0，与 PG 行为不一致 —— 每日真值收口
的 pushed（今日创建节点数）在内存路径下失真。

Seam：MemoryNodeRepository.save（公开）+ count_nodes_created_since（公开）。
不测内部字段，只测「save 后 created_at 存在 / 计数正确 / 更新不重置」。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from zkc.repository import get_storage
from zkc.repository.models import Node


class MemoryCreatedAtTest(unittest.TestCase):
    def test_save_sets_created_at_when_absent(self) -> None:
        """新节点未给 created_at，save 后应被补齐（非空），且能被今日计数捕获。"""
        store = get_storage("memory")
        n = Node(track="dynamic", title="t1", decay_score=0.0)
        self.assertIsNone(n.created_at, "前置：构造时未设 created_at")
        saved = store.nodes.save(n)
        self.assertIsNotNone(saved.created_at, "save 必须补齐 created_at")

        start_of_today = datetime(
            saved.created_at.year, saved.created_at.month, saved.created_at.day,
            tzinfo=saved.created_at.tzinfo,
        )
        self.assertEqual(
            store.nodes.count_nodes_created_since(start_of_today), 1,
            "今日创建的节点应被 count_nodes_created_since 计入",
        )

    def test_save_preserves_existing_created_at_on_update(self) -> None:
        """再次 save（更新）不得重置已存在的 created_at。"""
        store = get_storage("memory")
        original = datetime(2020, 1, 1, tzinfo=timezone.utc)
        n = Node(track="static", title="t2", created_at=original)
        first = store.nodes.save(n)
        self.assertEqual(first.created_at, original)

        first.title = "t2-renamed"
        second = store.nodes.save(first)
        self.assertEqual(
            second.created_at, original,
            "更新保存不得改写既有 created_at（与 PG 列默认只在 INSERT 生效一致）",
        )

    def test_count_excludes_nodes_before_since(self) -> None:
        """created_at 早于 since 的节点不计入（验证过滤语义，而非恒返 0）。"""
        store = get_storage("memory")
        now = datetime.now(timezone.utc)
        old = Node(track="dynamic", title="old", created_at=now - timedelta(days=5))
        store.nodes.save(old)
        # 今日零点之后的窗口，不应包含 5 天前的节点
        start_of_today = datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
        self.assertEqual(store.nodes.count_nodes_created_since(start_of_today), 0)


if __name__ == "__main__":
    unittest.main()
