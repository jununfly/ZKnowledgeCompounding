"""ZKC · 任务队列单测：MemoryStorage 注入，覆盖生成规则与完成闭环。"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from zkc.repository import get_storage
from zkc.repository.models import AttentionObservation
from zkc.task_queue import complete_task, generate_due_tasks, task_queue_view

UTC = timezone.utc


def _at(d: date, h: int = 9) -> datetime:
    return datetime(d.year, d.month, d.day, h, 0, 0, tzinfo=UTC)


def _friday() -> datetime:
    d = date(2026, 11, 2)
    while d.weekday() != 4:  # 找到最近的周五
        d += timedelta(days=1)
    return _at(d)


class TaskQueueRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = get_storage("memory")

    def _kinds(self, now: datetime) -> set[str]:
        return {s.kind for s in generate_due_tasks(self.store, now)}

    def test_daily_periodic_always_present(self) -> None:
        now = _at(date(2026, 11, 2))  # 周一
        kinds = self._kinds(now)
        self.assertIn("daily_review", kinds)
        self.assertIn("daily_close", kinds)
        self.assertIn("commit_push", kinds)
        # 非周五不应有每周快照
        self.assertNotIn("weekly_snapshot", kinds)
        self.assertNotIn("orphan_spike", kinds)

    def test_friday_weekly_snapshot(self) -> None:
        kinds = self._kinds(_friday())
        self.assertIn("weekly_snapshot", kinds)

    def test_orphan_spike_window(self) -> None:
        inside = _at(date(2026, 11, 5))
        self.assertIn("orphan_spike", self._kinds(inside))
        outside = _at(date(2026, 11, 10))
        self.assertNotIn("orphan_spike", self._kinds(outside))

    def test_labeled_judgment_threshold(self) -> None:
        # 低于阈值：无判定任务
        self.store.attention.record_observation(
            AttentionObservation(day=date(2026, 11, 1), labeled_completed=5))
        self.assertNotIn("labeled_judgment", self._kinds(_at(date(2026, 11, 2))))
        # 达到阈值（≥20）：出现判定任务
        self.store.attention.record_observation(
            AttentionObservation(day=date(2026, 11, 2), labeled_completed=20))
        self.assertIn("labeled_judgment", self._kinds(_at(date(2026, 11, 3))))

    def test_view_counts_and_idempotent_done(self) -> None:
        now = _at(date(2026, 11, 2))
        view = task_queue_view(self.store, now)
        # 每日基线：daily_review + daily_close + commit_push = 3 开放
        self.assertEqual(view["open_count"], 3)
        # 完成 daily_review
        daily = next(it for it in view["items"] if it["kind"] == "daily_review")
        done = complete_task(self.store, daily["id"], now)
        self.assertEqual(done["status"], "done")
        # 再次取视图（内部 ensure_today 重算）：done 不被覆盖，开放数减 1
        view2 = task_queue_view(self.store, now)
        self.assertEqual(view2["open_count"], 2)
        self.assertEqual(view2["done_count"], 1)
        reopen = next(it for it in view2["items"] if it["kind"] == "daily_review")
        self.assertEqual(reopen["status"], "done")


if __name__ == "__main__":
    unittest.main()
