"""spike07 复利度量权重 / method_target 的治理契约（1-25 校准切片 + 2026-11-11 覆盖）。

守住四件事：
1. 五个参数 source=CALIBRATED（2026-11-11 zj 显式拍板，覆盖自动门禁；数值一律不改、calibrated_at 已落）；
2. 自动校准门禁 calibrate() 对**未授权**参数仍关闭 —— 本文件用仍 SIMULATION 的参数证明门禁机制未失效；
3. ``metrics.compounding_factor`` 默认权重确实来自 tuning、且必须归一；
4. 证据脚本的核心结论（等权在均匀先验下 MSE 最小 / 真实快照零信息量）可复跑。

⚠️ 历史口径：原契约锁死这五个参数为 SIMULATION（防无门禁升 CALIBRATED）。
2026-11-11 zj 以「多天累计真实复审已构成真实使用场景」为由，显式覆盖自动门禁，
直接把 seed 标定为 CALIBRATED（带 calibrated_at），**不经 calibrate() 自动门禁**
（当时 days_with_obs=8/14 未达 14）。这是人工决策记录，不表示门禁机制失效。
"""
from __future__ import annotations

import importlib.util
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from zkc import metrics as M
from zkc import tuning
from zkc.tuning import CALIBRATED, SIMULATION

W_NAMES = (
    "METRIC_W_DENSITY", "METRIC_W_REUSE", "METRIC_W_METHOD", "METRIC_W_DECAY",
)
ALL_NAMES = (*W_NAMES, "METRIC_METHOD_TARGET")

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "metric_weights_sim.py"


def _load_sim_module():
    spec = importlib.util.spec_from_file_location("zkc_metric_weights_sim", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestMetricWeightsGovernance(unittest.TestCase):
    def test_four_weights_equal_and_calibrated(self):
        for name in W_NAMES:
            p = tuning.param(name)
            self.assertEqual(p.value, 0.25, name)
            self.assertEqual(p.source, CALIBRATED, name)
            self.assertIsNotNone(p.calibrated_at, name)
            self.assertNotEqual(p.source, SIMULATION, name)

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(tuning.get(n) for n in W_NAMES), 1.0, delta=1e-9)

    def test_method_target_unchanged_and_calibrated(self):
        p = tuning.param("METRIC_METHOD_TARGET")
        self.assertEqual(p.value, 10.0)
        self.assertEqual(p.source, CALIBRATED)
        self.assertIsNotNone(p.calibrated_at)

    def test_all_are_calibrated(self):
        for name in ALL_NAMES:
            self.assertTrue(tuning.is_calibrated(name), name)

    def test_calibrate_gate_still_refuses_unauthorized_upgrade(self):
        """门禁机制未失效：仍 SIMULATION 的参数未经真实埋点不得升 CALIBRATED。

        注意：本测试不复测被人工覆盖的五个参数（它们已被显式标定为 CALIBRATED），
        而是用 ROT_THRESHOLD（仍 SIMULATION、不在本次覆盖范围）证明 calibrate()
        门禁本身仍然关闭。
        """
        name = "ROT_THRESHOLD"  # 仍 SIMULATION，未被本次覆盖
        before = tuning.get(name)
        with self.assertRaises(PermissionError):
            tuning.calibrate(name, 0.95, date(2026, 11, 11),
                             "借本次覆盖顺手改别的数",
                             days_with_observation=2, saturated_days=0)
        self.assertEqual(tuning.get(name), before)
        self.assertEqual(tuning.param(name).source, SIMULATION)

    def test_default_compounding_factor_is_normalized_sum(self):
        # cd=rr=dc=1、mo=target → 四项均 1，CF 必须恰为权重和 1.0
        self.assertAlmostEqual(M.compounding_factor(1.0, 1.0, 10, 1.0), 1.0, delta=1e-9)

    def test_default_weights_follow_tuning_not_hardcoded(self):
        patched = {
            "METRIC_W_DENSITY": tuning.Parameter("METRIC_W_DENSITY", 0.4, SIMULATION),
            "METRIC_W_DECAY": tuning.Parameter("METRIC_W_DECAY", 0.1, SIMULATION),
        }
        with mock.patch.dict(tuning.REGISTRY, patched):
            # 只让 density 分量为 1，其余为 0 → CF 应等于被改后的 0.4
            self.assertAlmostEqual(M.compounding_factor(1.0, 0.0, 0, 0.0), 0.4,
                                   delta=1e-9)

    def test_default_weights_must_be_normalized(self):
        patched = {
            "METRIC_W_DENSITY": tuning.Parameter("METRIC_W_DENSITY", 0.4, SIMULATION),
        }
        with mock.patch.dict(tuning.REGISTRY, patched):
            with self.assertRaises(ValueError):
                M.compounding_factor(1.0, 0.0, 0, 0.0)


class TestSimulationEvidence(unittest.TestCase):
    """证据不是一张静态表：脚本核心结论必须在 CI 里可复跑。"""

    def test_equal_weight_is_bayes_optimal_in_simulation(self):
        mod = _load_sim_module()
        r = mod.simulate_weights(samples=5000, seed=20261106)
        self.assertTrue(r["equal_is_best"])
        self.assertLess(r["mse"]["equal"], r["mse"]["skew"])

    def test_real_snapshot_has_no_weight_information(self):
        mod = _load_sim_module()
        real = {
            "connection_density": 0.0, "reuse_rate": 0.0,
            "methodology_output": 0, "decay_controllability": 1.0,
        }
        ident = mod.identifiability(real)
        self.assertEqual(ident["nonzero_component_count"], 1)
        self.assertEqual(ident["identifiable_weights"], ["METRIC_W_DECAY"])
        self.assertEqual(len(ident["unidentifiable_weights"]), 3)

    def test_all_targets_equivalent_when_real_output_is_zero(self):
        mod = _load_sim_module()
        real = {
            "connection_density": 0.0, "reuse_rate": 0.0,
            "methodology_output": 0, "decay_controllability": 1.0,
        }
        self.assertTrue(mod.target_analysis(real)["all_targets_equivalent_on_real"])


if __name__ == "__main__":
    unittest.main()
