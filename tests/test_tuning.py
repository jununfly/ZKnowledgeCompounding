"""zkc/tuning.py 的契约测试（P1.4）。

测的是「阈值治理」这个机制本身，不是数值对不对（数值在拍板时已定，
且大部分是 placeholder，正确性由校准流程保证）。
"""
from __future__ import annotations

import unittest
from datetime import date

from zkc import tuning
from zkc.tuning import CALIBRATED, PLACEHOLDER, SIMULATION


class TestRegistry(unittest.TestCase):
    def test_every_param_has_source_tag(self):
        for name, p in tuning.REGISTRY.items():
            self.assertIn(p.source, (PLACEHOLDER, SIMULATION, CALIBRATED),
                          f"{name} 缺少合法 source 标签")

    def test_calibrated_requires_date(self):
        for name, p in tuning.REGISTRY.items():
            if p.source == CALIBRATED:
                self.assertIsNotNone(p.calibrated_at, f"{name} 标了 calibrated 却没有日期")

    def test_bad_source_rejected(self):
        with self.assertRaises(ValueError):
            tuning.Parameter(name="X", value=1, source="guessed")

    def test_unknown_param_rejected(self):
        with self.assertRaises(KeyError):
            tuning.get("NO_SUCH_PARAM")


class TestPinnedValues(unittest.TestCase):
    """zj 拍板 2026-10-31 定死的值，回归保护。"""

    def test_decay_thresholds(self):
        self.assertEqual(tuning.get("SURFACE_THRESHOLD"), 0.6)
        self.assertEqual(tuning.get("ROT_THRESHOLD"), 0.9)
        self.assertEqual(tuning.get("DECAY_FUNCTION"), "linear")

    def test_budget_default_is_1_0_not_1_2(self):
        self.assertEqual(tuning.get("BUDGET_PER_DAY_DEFAULT"), 1.0)

    def test_aimd_kept(self):
        self.assertEqual(tuning.get("AIMD_UP"), 1.5)
        self.assertEqual(tuning.get("AIMD_DOWN"), 0.7)

    def test_embedding_locked_to_768(self):
        self.assertEqual(tuning.get("EMBEDDING_DIM"), 768)
        self.assertEqual(tuning.get("EMBEDDING_MODEL"), "nomic-embed-text:latest")
        self.assertEqual(tuning.param("EMBEDDING_DIM").source, CALIBRATED)

    def test_single_way_ticket_baseline(self):
        self.assertEqual(tuning.get("BASELINE_CAPTURED_DAYS"), 28)

    def test_label_gate(self):
        self.assertEqual(tuning.get("LABEL_RATE_MIN"), 0.70)
        self.assertEqual(tuning.get("LABEL_MIN_SAMPLES"), 10)


class TestCalibrationGate(unittest.TestCase):
    """门禁是这套机制的核心：无数据不得改数。"""

    def test_gate_closed_without_observations(self):
        self.assertFalse(tuning.can_calibrate(days_with_observation=0, saturated_days=0))

    def test_gate_closed_when_only_days(self):
        self.assertFalse(tuning.can_calibrate(days_with_observation=14, saturated_days=0))

    def test_gate_closed_when_only_saturated(self):
        self.assertFalse(tuning.can_calibrate(days_with_observation=3, saturated_days=9))

    def test_gate_open(self):
        self.assertTrue(tuning.can_calibrate(days_with_observation=14, saturated_days=3))

    def test_calibrate_refused_when_gate_closed(self):
        with self.assertRaises(PermissionError):
            tuning.calibrate("BUDGET_PER_DAY_DEFAULT", 3.0, date(2026, 11, 1),
                             "凭直觉改", days_with_observation=2, saturated_days=0)
        # 必须原封不动
        self.assertEqual(tuning.get("BUDGET_PER_DAY_DEFAULT"), 1.0)

    def test_calibrate_leaves_trace(self):
        tuning.calibrate("BUDGET_PER_DAY_DEFAULT", 2.5, date(2026, 12, 1),
                         "14 天埋点 + 4 个饱和日，p25=2.5",
                         days_with_observation=14, saturated_days=4)
        p = tuning.param("BUDGET_PER_DAY_DEFAULT")
        self.assertEqual(p.value, 2.5)
        self.assertEqual(p.source, CALIBRATED)
        self.assertEqual(len(p.history), 1)
        h = p.history[0]
        self.assertEqual(h["from"], 1.0)
        self.assertEqual(h["to"], 2.5)
        self.assertEqual(h["to_source"], CALIBRATED)
        self.assertIn("饱和日", h["reason"])
        # 还原，避免测试间互相污染
        p.value, p.source, p.calibrated_at, p.history = 1.0, PLACEHOLDER, None, []


class TestDisplay(unittest.TestCase):
    def test_rows_carry_source(self):
        rows = {r["name"]: r for r in tuning.as_rows()}
        self.assertEqual(rows["ROT_THRESHOLD"]["source"], SIMULATION)
        self.assertIn("value", rows["ROT_THRESHOLD"])


if __name__ == "__main__":
    unittest.main()
