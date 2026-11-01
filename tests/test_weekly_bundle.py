"""ZKC · P5.3 每周复盘 bundle 测试（切片E）。

rot_rate 纯函数口径 + weekly_review_bundle（MemoryStorage）+ /metrics/api 集成。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from zkc import metrics as M
from zkc.repository.memory import MemoryStorage
from zkc.repository.models import AttentionObservation, MetricInputs, Node
from zkc.web.metrics import register_metrics_routes, weekly_review_bundle


class RotRateTest(unittest.TestCase):
    def test_empty_safe(self):
        self.assertEqual(M.rot_rate(MetricInputs()), 0.0)

    def test_share_of_active_rotting(self):
        # 4 个活跃动态（2 腐化）+ 1 已归档动态（decay 高但不计）+ 1 静态（不计）
        inp = MetricInputs(nodes=[
            ("a", "dynamic", 0.95, False),
            ("b", "dynamic", 0.9, False),
            ("c", "dynamic", 0.5, False),
            ("d", "dynamic", 0.2, False),
            ("e", "dynamic", 1.0, True),   # 归档，不计
            ("f", "static", 1.0, False),   # 静态，不计
        ])
        self.assertAlmostEqual(M.rot_rate(inp), 0.5, delta=1e-9)

    def test_all_archived_returns_zero(self):
        inp = MetricInputs(nodes=[("a", "dynamic", 1.0, True)])
        self.assertEqual(M.rot_rate(inp), 0.0)


class WeeklyBundleTest(unittest.TestCase):
    def test_bundle_memory_store(self):
        st = MemoryStorage()
        today = datetime.utcnow()
        # 跨 3 天累计 completed=12 / labeled=8 → 越过 LABEL_MIN_SAMPLES=10，rate=0.667
        for offset, (comp, lab) in {0: (4, 3), 1: (4, 3), 2: (4, 2)}.items():
            st.attention.record_observation(AttentionObservation(
                day=today - timedelta(days=offset), pushed=comp,
                completed=comp, queue_remaining=0, labeled_completed=lab))
        st.nodes.save(Node(track="dynamic", title="烂了", decay_score=0.95))
        st.nodes.save(Node(track="dynamic", title="还好", decay_score=0.1))
        b = weekly_review_bundle(st)
        self.assertAlmostEqual(b["rot_rate"], 0.5, delta=1e-9)
        self.assertEqual(b["labeling"]["completed"], 12)
        self.assertEqual(b["labeling"]["labeled"], 8)
        self.assertAlmostEqual(b["labeling"]["rate"], 0.667, delta=1e-3)

    def test_bundle_insufficient_samples_gate_open(self):
        st = MemoryStorage()
        today = datetime.utcnow()
        st.attention.record_observation(AttentionObservation(
            day=today, pushed=1, completed=1, queue_remaining=0,
            labeled_completed=0))
        b = weekly_review_bundle(st)
        self.assertIsNone(b["labeling"]["rate"])  # 样本不足不判（D8 口径）
        self.assertEqual(b["labeling"]["gate"], "open")


class MetricsHttpBundleTest(unittest.TestCase):
    def test_metrics_api_contains_weekly_review(self):
        app = FastAPI()
        st = MemoryStorage()
        register_metrics_routes(app, st)
        client = TestClient(app)
        r = client.get("/metrics/api")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertIn("weekly_review", j)
        self.assertEqual(j["weekly_review"]["rot_rate"], 0.0)
        self.assertIn("labeling", j["weekly_review"])


if __name__ == "__main__":
    unittest.main()
