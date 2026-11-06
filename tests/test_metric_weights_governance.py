"""spike07 复利度量权重 / method_target 的治理契约（1-25 校准切片的回归护栏）。

守住四件事：
1. 五个参数 source=SIMULATION（不是 PLACEHOLDER，更不是 CALIBRATED），数值一律不改；
2. 校准门禁对仿真结论同样关闭 —— 受控仿真不得冒充真实埋点；
3. ``metrics.compounding_factor`` 默认权重确实来自 tuning、且必须归一；
4. 证据脚本的核心结论（等权在均匀先验下 MSE 最小 / 真实快照零信息量）可复跑。
"""
from __future__ import annotations

import importlib.util
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from zkc import metrics as M
from zkc import tuning
from zkc.tuning import PLACEHOLDER, SIMULATION

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
    def test_four_weights_equal_and_simulated(self):
        for name in W_NAMES:
            p = tuning.param(name)
            self.assertEqual(p.value, 0.25, name)
            self.assertEqual(p.source, SIMULATION, name)
            self.assertNotEqual(p.source, PLACEHOLDER, name)

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(tuning.get(n) for n in W_NAMES), 1.0, delta=1e-9)

    def test_method_target_unchanged_and_simulated(self):
        p = tuning.param("METRIC_METHOD_TARGET")
        self.assertEqual(p.value, 10.0)
        self.assertEqual(p.source, SIMULATION)

    def test_none_is_calibrated(self):
        for name in ALL_NAMES:
            self.assertFalse(tuning.is_calibrated(name), name)

    def test_calibrate_gate_refuses_simulation_as_telemetry(self):
        """即便拿仿真结论当理由，无真实埋点也不得升 CALIBRATED。"""
        for name in ALL_NAMES:
            with self.subTest(name=name):
                before = tuning.get(name)
                with self.assertRaises(PermissionError):
                    tuning.calibrate(name, 0.3, date(2026, 11, 6),
                                     "受控仿真结论冒充真实埋点",
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
