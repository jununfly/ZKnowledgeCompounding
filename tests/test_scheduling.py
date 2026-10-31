"""zkc/scheduling 纯函数单测（P4.1 / P4.4，无 DB 依赖）。

覆盖 L1 时间锚解析 / 基线阶梯、L2 优先级延后、L3 AIMD、标注率闸门、budget 删失估计。
全部走纯函数，可在无 docker 环境运行；PG 集成行为见 tests/test_scheduling_pg.py。

注：本文件对应 1-4-1（P4.1）标准 L1 顺序 = 时间锚 > 已捕获(28d) > self_loop(3d) >
connected(14d) > orphan(7d)。P4.5 的「self_loop 压过 已捕获」顺序变更属独立节点 1-4-5，
不在本次范围，故此处按 P4.1 口径断言。
"""
from __future__ import annotations

import unittest
from datetime import date, timedelta

from zkc.repository.models import AttentionObservation, SchedulableNode
from zkc import scheduling as S


def _row(**kw) -> SchedulableNode:
    base = dict(track="dynamic", title="t", content=None, captured=False,
                conn_count=0, self_loop_count=0, higher_dim_count=0,
                interval_days=None, baseline_days=None, source="auto", archived=False)
    base.update(kw)
    return SchedulableNode(**base)


def _obs(completed, labeled, q_remaining=0, day=None) -> AttentionObservation:
    return AttentionObservation(day=day or date(2026, 6, 1), pushed=completed,
                               completed=completed, queue_remaining=q_remaining,
                               labeled_completed=labeled)


class SchedulingPureTest(unittest.TestCase):
    # ------------------------------------------------------------ L1 时间锚
    def test_horizon_chinese_and_english(self):
        self.assertEqual(S.extract_horizon_days("下周三前提交评审材料"), 7.0)
        self.assertEqual(S.extract_horizon_days("3 天内跟进反馈"), 3.0)
        self.assertIsNone(S.extract_horizon_days("no anchor here"))
        self.assertEqual(S.extract_horizon_days("in 5 days"), 5.0)

    def test_horizon_takes_earliest(self):
        # 多个锚取最早：明天(1) vs 下周(7) -> 1
        self.assertEqual(S.extract_horizon_days("明天做，下周再复盘"), 1.0)

    def test_clamp_days_bounds(self):
        self.assertEqual(S.clamp_days(0.2), S._t("MIN_INTERVAL_DAYS"))
        self.assertEqual(S.clamp_days(999), S._t("MAX_INTERVAL_DAYS"))

    # ------------------------------------------------------------ L1 基线阶梯
    def test_baseline_static_none(self):
        r = S.baseline_for_signals("static", False, "x", "y", False, 0, 0, 0)
        self.assertIsNone(r["days"])

    def test_baseline_horizon_wins(self):
        r = S.baseline_for_signals("dynamic", False, "下周三前提交", "body", False, 3, 0, 0)
        self.assertEqual(r["tier"], "horizon")
        self.assertEqual(r["days"], 7.0)

    def test_baseline_captured_beats_selfloop(self):
        # P4.1 顺序：已捕获(28d) 压过 self_loop(3d)
        r = S.baseline_for_signals("dynamic", False, "项目 A 阻塞点", "b", True, 1, 0, 0)
        self.assertEqual(r["tier"], "captured")
        self.assertEqual(r["days"], S._t("BASELINE_CAPTURED_DAYS"))

    def test_baseline_selfloop(self):
        r = S.baseline_for_signals("dynamic", False, "t", "b", False, 1, 0, 0)
        self.assertEqual(r["tier"], "self_loop")
        self.assertEqual(r["days"], S._t("BASELINE_SELF_LOOP_DAYS"))

    def test_baseline_higher_dim_and_connected(self):
        self.assertEqual(
            S.baseline_for_signals("dynamic", False, "t", "b", False, 0, 1, 0)["days"],
            S._t("BASELINE_CONNECTED_DAYS"))
        self.assertEqual(
            S.baseline_for_signals("dynamic", False, "t", "b", False, 0, 0, 1)["days"],
            S._t("BASELINE_CONNECTED_DAYS"))

    def test_baseline_orphan(self):
        self.assertEqual(
            S.baseline_for_signals("dynamic", False, "灵感", "b", False, 0, 0, 0)["days"],
            S._t("BASELINE_ORPHAN_DAYS"))

    # ------------------------------------------------------------ L2 优先级
    def test_priority_ordering(self):
        self.assertEqual(S.priority_of(_row(title="下周截止", content="x")), 3)
        self.assertEqual(S.priority_of(_row(self_loop_count=1)), 2)
        self.assertEqual(S.priority_of(_row(conn_count=1)), 1)
        self.assertEqual(S.priority_of(_row()), 0)

    def test_fit_budget_noop_when_feasible(self):
        rows = [_row(interval_days=14), _row(interval_days=14)]
        r = S.fit_budget_rows(rows, budget_per_day=1.0)
        self.assertFalse(r["applied"])
        self.assertEqual(r["degraded"], [])

    def test_fit_budget_defers_lowest_priority_first(self):
        rows = [
            _row(id=1, interval_days=7, source="auto"),                 # orphan p0
            _row(id=2, interval_days=7, title="下周截止", source="auto"),  # horizon p3
        ]
        # 预算 0.4：原需求 0.476 > 0.4 需延后；延后孤儿(id1: 7→14)后需求 0.357 ≤ 0.4
        # 即停，高优先级(id2 horizon)不被延后。
        r = S.fit_budget_rows(rows, budget_per_day=0.4)
        self.assertTrue(r["applied"])
        degraded_ids = {d["id"] for d in r["degraded"]}
        self.assertIn("1", degraded_ids)
        self.assertNotIn("2", degraded_ids)  # 高优先级保留

    def test_fit_budget_preserves_human(self):
        rows = [_row(id=1, interval_days=7, source="human")]
        r = S.fit_budget_rows(rows, budget_per_day=0.0001)
        self.assertEqual(r["degraded"], [])

    def test_fit_budget_infeasible_reports_max(self):
        rows = [_row(id=1, interval_days=S._t("MAX_INTERVAL_DAYS"), source="auto")]
        r = S.fit_budget_rows(rows, budget_per_day=0.0001)
        self.assertTrue(r["infeasible"])
        self.assertIsNotNone(r["max_dynamic_items"])

    def test_fit_budget_warmup_passive(self):
        rows = [_row(interval_days=7)]
        r = S.fit_budget_rows(rows, budget_per_day=None)
        self.assertFalse(r["applied"])
        self.assertIn("warm-up", r["note"])

    # ------------------------------------------------------------ L3 AIMD
    def test_classify_review_boundaries(self):
        self.assertEqual(S.classify_review(0.1), "too_early")
        self.assertEqual(S.classify_review(0.5), "on_time")
        self.assertEqual(S.classify_review(0.95), "too_late")

    def test_adapt_math_factors(self):
        early = S.adapt_interval_math(10.0, "too_early")
        self.assertEqual(early["new_days"], 15.0)
        self.assertTrue(early["applied"])
        late = S.adapt_interval_math(10.0, "too_late")
        self.assertAlmostEqual(late["new_days"], 7.0)
        ontime = S.adapt_interval_math(10.0, "on_time")
        self.assertEqual(ontime["new_days"], 10.0)
        self.assertFalse(ontime["applied"])

    def test_adapt_math_human_exempt(self):
        r = S.adapt_interval_math(10.0, "too_late", human=True)
        self.assertFalse(r["applied"])
        self.assertEqual(r["new_days"], 10.0)

    # ------------------------------------------------------------ 标注率闸门 (P4.4)
    def test_label_rate_insufficient_samples_open(self):
        obs = [_obs(1, 0), _obs(1, 0), _obs(1, 0)]
        g = S.labeling_rate_from(obs)
        self.assertEqual(g["gate"], "open")
        self.assertIsNone(g["rate"])

    def test_label_rate_below_threshold_closed(self):
        obs = [_obs(12, 4)]  # 33% < 70%
        g = S.labeling_rate_from(obs)
        self.assertEqual(g["gate"], "closed")
        self.assertEqual(g["rate"], 0.333)

    def test_label_rate_at_threshold_open(self):
        g = S.labeling_rate_from([_obs(10, 7)])
        self.assertEqual(g["gate"], "open")
        self.assertEqual(g["rate"], 0.7)

    def test_label_rate_window_roll(self):
        obs = [
            _obs(10, 7, day=date(2026, 6, 10)),
            _obs(10, 0, day=date(2026, 1, 1)),
        ]
        g = S.labeling_rate_from(obs)
        self.assertEqual(g["completed"], 10)
        self.assertEqual(g["gate"], "open")

    # ------------------------------------------------------------ budget 删失估计 (切片 B)
    def test_estimate_budget_warmup_none(self):
        self.assertEqual(S.estimate_budget_from([])["confidence"], "none")

    def test_estimate_budget_lower_bound_when_no_saturated(self):
        obs = [_obs(5, 0, q_remaining=0, day=date(2026, 6, d)) for d in range(1, 8)]
        r = S.estimate_budget_from(obs)
        self.assertEqual(r["confidence"], "lower_bound")
        self.assertEqual(r["estimate"], 5.0)

    def test_estimate_budget_observed_at_saturated(self):
        obs = [_obs(8, 0, q_remaining=2, day=date(2026, 6, d)) for d in range(1, 5)]
        r = S.estimate_budget_from(obs)
        self.assertEqual(r["confidence"], "observed")
        self.assertEqual(r["estimate"], 8.0)

    def test_update_budget_guardrail_blocks_lowering(self):
        obs = [_obs(5, 0, q_remaining=0, day=date(2026, 6, d)) for d in range(1, 8)]
        r = S.update_budget_from(obs, current=10.0)
        self.assertEqual(r["new"], 10.0)
        self.assertFalse(r["applied"])

    def test_update_budget_bootstrap_from_none(self):
        obs = [_obs(8, 0, q_remaining=2, day=date(2026, 6, d)) for d in range(1, 5)]
        r = S.update_budget_from(obs, current=None)
        self.assertTrue(r["applied"])
        self.assertEqual(r["new"], 8.0)

    def test_l2_target_oversubscribe_until_confirmed(self):
        self.assertEqual(S.l2_target(3.0, "none"), 4.5)
        self.assertEqual(S.l2_target(3.0, "observed"), 3.0)


if __name__ == "__main__":
    unittest.main()
