"""ZKC · ADR-0011/0012 verdict 语义 v2 · TDD 验收（Step 4 红绿）。

覆盖规格 §5 的全部断言分组：B(changed) / C(stale cover) / D(stale purge) /
E(still_valid+browse) / A3(外生锚 A 人工输入归零) / F1(四类 reason 互异) /
G1(历史 3 条 changed 不回填)，以及 CLI 契约 C5。

这些测试在 v1 代码下**应当失败（RED）**，落码后转绿（GREEN）。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from zkc import scheduling as S
from zkc.decay import refresh_decay
from zkc.repository import get_storage
from zkc.repository.models import AttentionObservation, Node
from zkc.web.review import REVIEW_REASON, decide_review

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(days=10)


def _seed_due(store, n: int = 2) -> list:
    """造 n 条动态条目，赋 L1 基线（orphan 7d）并把 last_reviewed_at 推到 10 天前 → 到期。"""
    ids = []
    for i in range(n):
        node = store.nodes.save(
            Node(title=f"D{i}", content="老内容", track="dynamic"))
        ids.append(node.id)
    S.assign_baselines(store)                      # 赋 L1 基线 + 种 last_reviewed_at
    for nid in ids:
        store.nodes.mark_reviewed(nid, PAST)       # 推入过去 → 衰减积累、到期
    refresh_decay(store.nodes, NOW)
    return ids


def _iv_days(node) -> float | None:
    return (node.review_interval.total_seconds() / 86400.0
            if node.review_interval is not None else None)


class VerdictV2PureTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")
        self.ids = _seed_due(self.store, 2)

    # ---- B. changed ----
    def test_changed_requires_content(self):
        # B1：缺内容载荷 → 拒收，节点状态不变、仍在 due 队列
        with self.assertRaises(ValueError):
            decide_review(self.store, self.ids[0], "changed", now=NOW)
        self.assertIsNotNone(self.store.nodes.get(self.ids[0]))
        due = [n.id for n in self.store.nodes.list_due_for_review(NOW)]
        self.assertIn(self.ids[0], due)

    def test_changed_writes_new_version_and_resets_baseline(self):
        # B2 + A1：写双时态新版本、interval 重置 L1 基线、不退出调度回路
        old = self.store.nodes.get(self.ids[0])
        old_days = _iv_days(old)
        baseline_days = old.baseline_interval.total_seconds() / 86400.0
        res = decide_review(self.store, self.ids[0], "changed",
                            content="新内容修正", now=NOW)
        new = self.store.nodes.get(self.ids[0])
        self.assertEqual(new.content, "新内容修正")
        hist = self.store.nodes.history(self.ids[0])
        self.assertGreater(len(hist), 1)            # 历史快照 +1
        # interval 重置 L1 基线（== baseline_interval），不再缩短
        self.assertAlmostEqual(res["new_interval_days"], baseline_days, delta=0.01)
        self.assertGreaterEqual(res["new_interval_days"], old_days)
        self.assertEqual(res["verdict"], "changed")
        self.assertEqual(res["reason"], REVIEW_REASON["changed"])
        # 不退出调度回路 = 未归档、仍在调度总体（区别于 stale+purge 的 archive 退出）
        changed = self.store.nodes.get(self.ids[0])
        self.assertIsNone(changed.archived_at)
        self.assertTrue(
            any(n.id == self.ids[0] for n in self.store.load_schedulable()))

    # ---- C. stale → cover ----
    def test_stale_cover_requires_branch_and_content(self):
        # C1：缺分支 / 缺内容 → 拒收
        with self.assertRaises(ValueError):
            decide_review(self.store, self.ids[0], "stale", now=NOW)
        with self.assertRaises(ValueError):
            decide_review(self.store, self.ids[0], "stale",
                          stale_branch="cover", now=NOW)
        with self.assertRaises(ValueError):
            decide_review(self.store, self.ids[0], "stale",
                          stale_branch="bogus", now=NOW)

    def test_stale_cover_writes_new_version(self):
        # C2/C3：写双时态新版本、重置 L1 基线（同构不继承收缩）、不退出
        res = decide_review(self.store, self.ids[0], "stale",
                            stale_branch="cover", content="覆盖后的内容", now=NOW)
        new = self.store.nodes.get(self.ids[0])
        self.assertEqual(new.content, "覆盖后的内容")
        self.assertEqual(res["verdict"], "stale_overwrite")
        self.assertEqual(res["reason"], REVIEW_REASON["stale_overwrite"])
        baseline_days = new.baseline_interval.total_seconds() / 86400.0
        self.assertAlmostEqual(res["new_interval_days"], baseline_days, delta=0.01)
        # 不退出调度回路 = 未归档、仍在调度总体（区别于 purge 的 archive 退出）
        self.assertIsNone(new.archived_at)
        self.assertTrue(
            any(n.id == self.ids[0] for n in self.store.load_schedulable()))

    # ---- D. stale → purge ----
    def test_stale_purge_requires_branch(self):
        # D1：缺分支 → 拒收，绝不默认 purge
        with self.assertRaises(ValueError):
            decide_review(self.store, self.ids[0], "stale", now=NOW)

    def test_stale_purge_archives_and_exits(self):
        # D2/D3：archive 软归档、退出 due 队列（−1）、reason 与 D2 区分
        before_due = len(self.store.nodes.list_due_for_review(NOW))
        res = decide_review(self.store, self.ids[0], "stale",
                            stale_branch="purge", now=NOW)
        new = self.store.nodes.get(self.ids[0])
        self.assertIsNotNone(new.archived_at)
        self.assertEqual(res["verdict"], "stale_purged")
        self.assertEqual(res["reason"], REVIEW_REASON["stale_purged"])
        after_due = [n.id for n in self.store.nodes.list_due_for_review(NOW)]
        self.assertNotIn(self.ids[0], after_due)
        self.assertEqual(len(after_due), before_due - 1)

    # ---- E. still_valid / browse ----
    def test_still_valid_resets_clock_no_aimd(self):
        # E1：时钟复位、interval 维持（不调 AIMD）
        before = self.store.nodes.get(self.ids[0])
        old_days = _iv_days(before)
        res = decide_review(self.store, self.ids[0], "still_valid", now=NOW)
        after = self.store.nodes.get(self.ids[0])
        self.assertEqual(after.decay_score, 0.0)
        self.assertEqual(after.last_reviewed_at, NOW)
        self.assertEqual(res["verdict"], "still_valid")
        self.assertEqual(res["reason"], REVIEW_REASON["still_valid"])
        self.assertAlmostEqual(_iv_days(after), old_days, delta=0.01)

    def test_browse_counts_unlabeled(self):
        # E2：completed++、labeled 不增、verdict=None
        res = decide_review(self.store, self.ids[0], "browse", now=NOW)
        obs = self.store.attention.get(NOW.date())
        self.assertEqual(obs.completed, 1)
        self.assertEqual(obs.labeled_completed, 0)
        self.assertIsNone(res["verdict"])
        self.assertEqual(res["reason"], REVIEW_REASON["browsed_without_label"])

    # ---- A3. 外生锚 A：verdict 不再触发 AIMD 乘因子 ----
    def test_aimd_loop_human_input_zeroed(self):
        with mock.patch.object(S, "adapt_interval") as m:
            decide_review(self.store, self.ids[0], "changed", content="x", now=NOW)
            decide_review(self.store, self.ids[1], "stale",
                          stale_branch="purge", now=NOW)
            decide_review(self.store, self.ids[0], "still_valid", now=NOW)
            decide_review(self.store, self.ids[1], "browse", now=NOW)
        self.assertEqual(m.call_count, 0,
                         "verdict 不应再触发 AIMD 乘因子（外生锚 A 人工输入归零）")

    # ---- F1. 四类 reason 互异（结构性）----
    def test_four_audit_reasons_distinct(self):
        vals = list(REVIEW_REASON.values())
        self.assertEqual(len(vals), len(set(vals)))
        for v in ("still_valid", "changed", "stale_overwrite",
                  "stale_purged", "browsed_without_label"):
            self.assertIn(v, REVIEW_REASON)
        # 与 D2（expiry archive reason）无关、不混同
        self.assertNotIn("archived", vals)

    # ---- G1. 历史 3 条 changed 不回填 ----
    def test_historical_changed_not_refilled(self):
        # 模拟旧语义已把某节点 interval 缩短到 4.9d（changed→too_late×0.7）
        self.store.nodes.set_interval(
            self.ids[0], timedelta(days=4.9), "auto", "legacy changed")
        legacy_days = 4.9
        # 对另一个节点做全新 v2 changed（不应 retroactive 改写历史节点）
        decide_review(self.store, self.ids[1], "changed", content="新", now=NOW)
        hist = self.store.nodes.get(self.ids[0])
        self.assertAlmostEqual(
            _iv_days(hist), legacy_days, delta=0.01)


class VerdictV2CliContractTest(unittest.TestCase):
    def test_verdicts_set_unchanged(self):
        # C5：VERDICTS 集合保持四档，无 too_early
        from zkc.cli import VERDICTS
        self.assertEqual(VERDICTS, ("still_valid", "changed", "stale", "browse"))


if __name__ == "__main__":
    unittest.main()
