"""R14 补全回路延迟成本 — 判据聚合（TDD，1-19 Q3=A 收口衔接）。

判据（risks.md R14 / roadmap 1-19 EC3）：触发率 > 50% 且 补全延迟中位 > 主生成延迟中位 × 1.5
→ 关补全（should_close_completion=True）。否则保持 open。

本测试只验证纯聚合/判定函数 ``judge_r14`` 的行为，不读真实数据、不碰 IO。
R14 节点本身保持 open（关闭挂未来真实生产 run 落库聚合）；本函数是「判据可执行就绪」的落地——
把 1-19 Q3=A 所说的「判据不可执行」转化为可机械判定的纯函数，待真实 run 聚合即可裁决。
"""
from __future__ import annotations

import unittest

from zkc.cross_source import R14Verdict, judge_r14


def _run(fired: bool, main: float = 100.0, completion: float | None = None) -> dict:
    return {
        "completion_fired": fired,
        "main_latency_ms": main,
        # 仅触发补全的 run 有补全延迟；未触发的 run 该字段为 None（与 cross_source.combine 一致）
        "completion_latency_ms": completion if fired else None,
    }


class TestR14Judgment(unittest.TestCase):
    def test_trigger_rate_and_latency_exceed_budget_closes(self) -> None:
        # 6/10 触发(>0.5)，补全延迟 200 > 主生成 100*1.5=150 → 关补全
        runs = [_run(True, 100.0, 200.0) for _ in range(6)] + \
               [_run(False, 100.0) for _ in range(4)]
        v = judge_r14(runs)
        self.assertEqual(v.total, 10)
        self.assertEqual(v.fired, 6)
        self.assertAlmostEqual(v.trigger_rate, 0.6)
        self.assertTrue(v.should_close_completion)
        self.assertEqual(v.reason, "trigger_rate_and_latency_exceed_budget")

    def test_trigger_rate_below_threshold_stays_open(self) -> None:
        # 4/10 触发(0.4<=0.5) → 即使延迟超预算也保持 open（首要门槛是触发率）
        runs = [_run(True, 100.0, 300.0) for _ in range(4)] + \
               [_run(False, 100.0) for _ in range(6)]
        v = judge_r14(runs)
        self.assertFalse(v.should_close_completion)
        self.assertEqual(v.reason, "trigger_rate_within_budget")

    def test_latency_within_budget_stays_open(self) -> None:
        # 6/10 触发，但补全延迟 120 ≤ 主生成 100*1.5=150 → 保持 open
        runs = [_run(True, 100.0, 120.0) for _ in range(6)] + \
               [_run(False, 100.0) for _ in range(4)]
        v = judge_r14(runs)
        self.assertFalse(v.should_close_completion)
        self.assertEqual(v.reason, "completion_latency_within_budget")

    def test_no_completion_fired_stays_open(self) -> None:
        # 0 触发 → 无补全延迟中位 → 保持 open
        runs = [_run(False, 100.0) for _ in range(10)]
        v = judge_r14(runs)
        self.assertEqual(v.fired, 0)
        self.assertIsNone(v.completion_latency_median)
        self.assertFalse(v.should_close_completion)
        self.assertEqual(v.reason, "no_completion_fired")

    def test_insufficient_data_stays_open(self) -> None:
        # 默认 min_runs=10，3 条样本不足 → 保持 open（防小样本误判）
        runs = [_run(True, 100.0, 300.0) for _ in range(3)]
        v = judge_r14(runs)
        self.assertFalse(v.should_close_completion)
        self.assertEqual(v.reason, "insufficient_data")

    def test_custom_min_runs_accepts_small_sample(self) -> None:
        # 显式放宽 min_runs=2：3 条且全触发、延迟超预算 → 关补全（验证 min_runs 可控）
        runs = [_run(True, 100.0, 300.0) for _ in range(3)]
        v = judge_r14(runs, min_runs=2)
        self.assertTrue(v.should_close_completion)
        self.assertEqual(v.reason, "trigger_rate_and_latency_exceed_budget")

    def test_does_not_mutate_input(self) -> None:
        runs = [_run(True, 100.0, 200.0) for _ in range(6)] + \
               [_run(False, 100.0) for _ in range(4)]
        snapshot = [dict(r) for r in runs]
        judge_r14(runs)
        self.assertEqual(runs, snapshot)


if __name__ == "__main__":
    unittest.main()
