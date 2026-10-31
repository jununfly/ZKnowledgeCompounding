"""ZKC · P4.2 每日复审队列 UI 测试。

纯函数层用内存 fake 验证闭环语义；HTTP 层用 FastAPI TestClient 验证路由装配。
两条路径都围绕同一组事实：复审标注驱动 L3（锚 A）+ 今日观测累加驱动 budget（锚 B）。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from zkc import scheduling as S
from zkc.decay import refresh_decay
from zkc.repository import get_storage
from zkc.repository.models import AttentionObservation, Node
from zkc.web.review import (
    OUTCOME_VERDICT,
    decide_review,
    record_daily_observation,
    review_queue_view,
)

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(days=10)


def _seed_due(store, n: int = 2) -> list:
    """造 n 条动态条目，赋基线并把 last_reviewed_at 推到 10 天前 → 衰减饱和、入队待复审。"""
    ids = []
    for i in range(n):
        node = store.nodes.save(
            Node(title=f"D{i}", content="随手记的灵感碎片", track="dynamic"))
        ids.append(node.id)
    S.assign_baselines(store)                      # 赋 L1 基线（orphan 7d）+ 种 last_reviewed_at
    for nid in ids:
        store.nodes.mark_reviewed(nid, PAST)       # 推入过去 → 衰减积累、到期
    refresh_decay(store.nodes, NOW)
    return ids


class ReviewPureTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")
        self.ids = _seed_due(self.store, 2)

    # ---- 队列可见性 ----
    def test_queue_view_lists_due_items(self):
        view = review_queue_view(self.store, NOW)
        self.assertEqual(view["due_count"], 2)
        self.assertEqual(len(view["items"]), 2)
        self.assertIn(str(self.ids[0]), [it["id"] for it in view["items"]])

    def test_graceful_when_empty(self):
        empty = get_storage("memory")
        view = review_queue_view(empty, NOW)
        self.assertEqual(view["due_count"], 0)
        self.assertEqual(view["items"], [])

    # ---- 锚 A：复审标注驱动 L3 ----
    def test_decide_still_valid_resets_clock_and_labels(self):
        before = self.store.nodes.get(self.ids[0])
        res = decide_review(self.store, self.ids[0], "still_valid", NOW)
        after = self.store.nodes.get(self.ids[0])
        # 标注计数累加：completed=1, labeled=1
        obs = self.store.attention.get(NOW.date())
        self.assertEqual(obs.completed, 1)
        self.assertEqual(obs.labeled_completed, 1)
        # 衰减时钟复位
        self.assertEqual(after.decay_score, 0.0)
        self.assertEqual(after.last_reviewed_at, NOW)
        # still_valid → on_time → 节奏不变（applied 可能为 False，但 reason 表明 on_time）
        self.assertEqual(res["verdict"], "on_time")
        self.assertIsNotNone(res["reason"])

    def test_decide_changed_shrinks_interval(self):
        old_days = self.store.nodes.get(self.ids[0]).review_interval.total_seconds() / 86400.0
        self.assertAlmostEqual(old_days, 7.0, delta=0.01)
        res = decide_review(self.store, self.ids[0], "changed", NOW)
        new_days = res["new_interval_days"]
        # too_late → AIMD_DOWN(0.7) → 缩短
        self.assertTrue(res["applied"])
        self.assertLess(new_days, old_days)
        self.assertAlmostEqual(new_days, old_days * 0.7, delta=0.01)

    def test_decide_browse_counts_unlabeled(self):
        # browse：completed++ 但 labeled 不增（闸门因此可能关闭）
        res = decide_review(self.store, self.ids[0], "browse", NOW)
        obs = self.store.attention.get(NOW.date())
        self.assertEqual(obs.completed, 1)
        self.assertEqual(obs.labeled_completed, 0)      # 未标注
        self.assertIsNone(res["verdict"])
        self.assertIsNone(res["new_interval_days"])      # 不触发 L3

    def test_observation_accumulates_across_reviews(self):
        decide_review(self.store, self.ids[0], "still_valid", NOW)
        decide_review(self.store, self.ids[1], "changed", NOW)
        obs = self.store.attention.get(NOW.date())
        self.assertEqual(obs.completed, 2)
        self.assertEqual(obs.labeled_completed, 2)

    # ---- 锚 B：每日收口保留已累加计数 ----
    def test_record_daily_observation_preserves_counts(self):
        decide_review(self.store, self.ids[0], "still_valid", NOW)
        decide_review(self.store, self.ids[1], "stale", NOW)
        row = record_daily_observation(self.store, pushed=5, queue_remaining=3, now=NOW)
        self.assertEqual(row["pushed"], 5)
        self.assertEqual(row["queue_remaining"], 3)
        self.assertEqual(row["completed"], 2)            # 前两次复审累加保留
        self.assertEqual(row["labeled_completed"], 2)

    def test_unknown_outcome_rejected(self):
        with self.assertRaises(ValueError):
            decide_review(self.store, self.ids[0], "bogus", NOW)

    def test_outcome_verdict_mapping(self):
        self.assertEqual(OUTCOME_VERDICT["still_valid"], "on_time")
        self.assertEqual(OUTCOME_VERDICT["changed"], "too_late")
        self.assertEqual(OUTCOME_VERDICT["stale"], "too_late")


class ReviewHttpTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from zkc.web.app import create_app

        self.store = get_storage("memory")
        self.ids = _seed_due(self.store, 2)
        # 注入内存 store + 占位路由（避免 Ollama）；P4.2 不命中 /capture
        self.app = create_app(
            store=self.store, decision_router=object(), lexical_router=object())
        self.client = TestClient(self.app)

    def test_review_page_renders(self):
        r = self.client.get("/review")
        self.assertEqual(r.status_code, 200)
        self.assertIn("每日复审队列", r.text)
        self.assertIn("/review/api/queue", r.text)

    def test_queue_api_returns_due(self):
        r = self.client.get("/review/api/queue")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["due_count"], 2)
        self.assertIn("gate", body)
        self.assertIn("budget", body)

    def test_decide_api_runs_l3(self):
        r = self.client.post(
            "/review/api/decide",
            data={"node_id": str(self.ids[0]), "outcome": "changed"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome"], "changed")
        self.assertEqual(body["verdict"], "too_late")
        self.assertTrue(body["applied"])

    def test_observe_api_records_close(self):
        r = self.client.post(
            "/review/api/observe",
            data={"pushed": "5", "queue_remaining": "3"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["pushed"], 5)
        self.assertEqual(body["queue_remaining"], 3)

    def test_decide_then_queue_shrinks(self):
        # 处理一条后，队列应减少（该条 last_reviewed_at 复位 → 不再到期）
        r0 = self.client.get("/review/api/queue").json()
        self.assertEqual(r0["due_count"], 2)
        self.client.post(
            "/review/api/decide",
            data={"node_id": str(self.ids[0]), "outcome": "still_valid"},
        )
        r1 = self.client.get("/review/api/queue").json()
        self.assertEqual(r1["due_count"], 1)


if __name__ == "__main__":
    unittest.main()
