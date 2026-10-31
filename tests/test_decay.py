"""zkc/decay 纯函数测试（无 DB 依赖，P1.3）。

断言线性衰减模型 + 双轨语义（静态恒 0）+ 调度助手（surface / review_reset）行为正确。
阈值走 zkc.tuning，本文件不硬编码 0.6/0.9。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from zkc import tuning
from zkc.decay import (
    compute_decay_score,
    decay_linear,
    refresh_decay,
    review_reset,
    surface,
)
from zkc.repository.models import Node


class DecayModelTest(unittest.TestCase):
    def test_linear_boundary(self):
        # 0 时刻新鲜、到 interval 全腐、中点半腐
        self.assertAlmostEqual(decay_linear(0, 10), 0.0)
        self.assertAlmostEqual(decay_linear(5, 10), 0.5)
        self.assertAlmostEqual(decay_linear(10, 10), 1.0)
        # 超过 interval 被饱和在 1.0
        self.assertAlmostEqual(decay_linear(20, 10), 1.0)

    def test_linear_invalid_interval(self):
        # interval<=0 视为已腐（无法再衰减）
        self.assertEqual(decay_linear(0, 0), 1.0)

    def test_static_track_never_decays(self):
        now = datetime(2026, 6, 1)
        static = Node(
            id=__import__("uuid").uuid4(), track="static",
            review_interval=timedelta(days=1),
            last_reviewed_at=now - timedelta(days=100),
        )
        self.assertEqual(compute_decay_score(static, now), 0.0)

    def test_dynamic_decay_linear(self):
        now = datetime(2026, 6, 1)
        dyn = Node(
            id=__import__("uuid").uuid4(), track="dynamic",
            review_interval=timedelta(days=10),
            last_reviewed_at=now - timedelta(days=5),
        )
        # 5/10 = 0.5
        self.assertAlmostEqual(compute_decay_score(dyn, now), 0.5)

    def test_dynamic_no_interval_is_zero(self):
        now = datetime(2026, 6, 1)
        dyn = Node(
            id=__import__("uuid").uuid4(), track="dynamic",
            last_reviewed_at=now - timedelta(days=100),
        )
        self.assertEqual(compute_decay_score(dyn, now), 0.0)

    def test_surface_picks_above_threshold_and_orders(self):
        now = datetime(2026, 6, 1)
        items = [
            {"id": 1, "track": "dynamic", "review_interval": timedelta(days=10),
             "last_reviewed_at": now - timedelta(days=8)},   # 0.8
            {"id": 2, "track": "dynamic", "review_interval": timedelta(days=10),
             "last_reviewed_at": now - timedelta(days=2)},   # 0.2
            {"id": 3, "track": "static", "review_interval": timedelta(days=10),
             "last_reviewed_at": now - timedelta(days=9)},   # 恒 0
        ]
        picked = surface(items, now)  # 默认阈值 = SURFACE_THRESHOLD (0.6)
        ids = [i["id"] for i in picked]
        self.assertEqual(ids, [1])  # 仅 id=1 超过 0.6；静态恒 0 被排除

    def test_surface_budget_cap(self):
        now = datetime(2026, 6, 1)
        items = [
            {"id": i, "track": "dynamic", "review_interval": timedelta(days=10),
             "last_reviewed_at": now - timedelta(days=(i + 1) * 2)}
            for i in range(5)
        ]
        picked = surface(items, now, budget=2)
        self.assertEqual(len(picked), 2)

    def test_review_reset(self):
        now = datetime(2026, 6, 1)
        node = {"track": "dynamic", "decay_score": 0.9,
                "last_reviewed_at": now - timedelta(days=30)}
        reset = review_reset(node, now)
        self.assertEqual(reset["decay_score"], 0.0)
        self.assertEqual(reset["last_reviewed_at"], now)
        # 不就地改原对象
        self.assertEqual(node["decay_score"], 0.9)


class DecayRefreshContractTest(unittest.TestCase):
    """refresh_decay 对任意实现了 list_by_track + update_decay 的仓库都生效。"""

    def _fake_repo(self):
        class FakeRepo:
            def __init__(self):
                self.nodes = {}
                self.updates = []

            def list_by_track(self, track):
                return [n for n in self.nodes.values() if n.track == track]

            def update_decay(self, node_id, score):
                self.nodes[node_id].decay_score = score
                self.updates.append((node_id, score))

        repo = FakeRepo()
        now = datetime(2026, 6, 1)
        repo.nodes[1] = Node(id=1, track="dynamic",
                             review_interval=timedelta(days=10),
                             last_reviewed_at=now - timedelta(days=5))
        repo.nodes[2] = Node(id=2, track="static",
                             review_interval=timedelta(days=10),
                             last_reviewed_at=now - timedelta(days=5))
        return repo, now

    def test_refresh_writes_linear_score_and_skips_static(self):
        repo, now = self._fake_repo()
        n = refresh_decay(repo, now)
        self.assertEqual(n, 1)  # 仅 dynamic 被刷新
        self.assertAlmostEqual(repo.nodes[1].decay_score, 0.5)
        self.assertEqual(repo.nodes[2].decay_score, 0.0)


if __name__ == "__main__":
    unittest.main()
