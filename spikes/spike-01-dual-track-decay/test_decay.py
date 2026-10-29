"""Spike 01 tests: dual-track decay model + resource-aware scheduling.

Written BEFORE the implementation (TDD red step).
Acceptance thresholds come from the spike README.
"""
import unittest
from datetime import datetime, timedelta

from decay_model import (
    decay_linear,
    decay_exponential,
    decay_step,
    compute_score,
    surface,
    review,
    simulate,
    DECAY_FUNCS,
)

T0 = datetime(2026, 1, 1, 9, 0, 0)


class TestDecayFunctions(unittest.TestCase):
    """Each decay function: 0 at origin, monotonic, clamped at 1."""

    def test_linear_matches_fraction_of_interval(self):
        self.assertAlmostEqual(decay_linear(0, 7), 0.0)
        self.assertAlmostEqual(decay_linear(3.5, 7), 0.5)
        self.assertAlmostEqual(decay_linear(7, 7), 1.0)

    def test_linear_clamps_above_interval(self):
        self.assertAlmostEqual(decay_linear(30, 7), 1.0)

    def test_exponential_half_life(self):
        self.assertAlmostEqual(decay_exponential(0, 3.5), 0.0)
        self.assertAlmostEqual(decay_exponential(3.5, 3.5), 0.5)
        self.assertTrue(decay_exponential(7, 3.5) < 1.0)

    def test_exponential_never_exceeds_one(self):
        self.assertLessEqual(decay_exponential(1000, 3.5), 1.0)

    def test_step_stays_zero_before_trigger(self):
        self.assertAlmostEqual(decay_step(3, 7), 0.0)
        self.assertAlmostEqual(decay_step(7, 7), 1.0)

    def test_all_functions_monotonic(self):
        for name, fn in DECAY_FUNCS.items():
            prev = -1.0
            for day in range(0, 15):
                val = fn(day, 7)
                self.assertGreaterEqual(val, prev, msg=f"{name} not monotonic at {day}")
                self.assertGreaterEqual(val, 0.0)
                self.assertLessEqual(val, 1.0)
                prev = val


class TestScoring(unittest.TestCase):
    def test_score_uses_time_since_last_review(self):
        item = {"review_interval": 7, "last_reviewed_at": T0, "decay_score": 0.0}
        now = T0 + timedelta(days=7)
        self.assertAlmostEqual(compute_score(item, now, "linear"), 1.0)

    def test_score_ignores_decay_for_static_track(self):
        """Static items are governed by bitemporal validity, not decay."""
        item = {"track": "static", "review_interval": 7, "last_reviewed_at": T0}
        now = T0 + timedelta(days=30)
        self.assertAlmostEqual(compute_score(item, now, "linear"), 0.0)


class TestScheduling(unittest.TestCase):
    def _items(self):
        return [
            {"id": i, "track": "dynamic", "review_interval": 7,
             "last_reviewed_at": T0 - timedelta(days=d), "decay_score": 0.0}
            for i, d in enumerate([1, 2, 3, 8, 9, 10])
        ]

    def test_surface_returns_only_items_above_threshold(self):
        picked = surface(self._items(), T0, threshold=0.5, budget=10, func="linear")
        ids = {p["id"] for p in picked}
        # elapsed 1,2,3 -> score .14/.29/.43 (below .5); 8,9,10 -> clamped 1.0
        self.assertEqual(ids, {3, 4, 5})

    def test_surface_respects_attention_budget(self):
        picked = surface(self._items(), T0, threshold=0.5, budget=2, func="linear")
        self.assertEqual(len(picked), 2)

    def test_surface_orders_most_decayed_first(self):
        picked = surface(self._items(), T0, threshold=0.5, budget=10, func="linear")
        scores = [compute_score(p, T0, "linear") for p in picked]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_review_resets_decay_clock(self):
        item = {"track": "dynamic", "review_interval": 7,
                "last_reviewed_at": T0 - timedelta(days=10), "decay_score": 1.0}
        reviewed = review(item, T0)
        self.assertEqual(reviewed["last_reviewed_at"], T0)
        self.assertAlmostEqual(compute_score(reviewed, T0, "linear"), 0.0)


class TestSimulation(unittest.TestCase):
    """Acceptance: decay + scheduled re-evaluation must actually prevent rot."""

    # Feasible provisioning uses interval=21: effective review cadence is
    # SURFACE_THRESHOLD * interval, so demand = 50/(0.6*21) = 3.97/day < budget 5.
    def test_linear_contains_rot_when_provisioned(self):
        stats = simulate(n_items=50, days=60, daily_budget=5,
                         interval=21, func="linear", seed=7)
        self.assertLessEqual(stats["rot_rate"], 0.10,
                             msg=f"linear rot rate {stats['rot_rate']:.3f}")

    def test_exponential_contains_rot_when_provisioned(self):
        stats = simulate(n_items=50, days=60, daily_budget=5,
                         interval=21, func="exponential", seed=7)
        self.assertLessEqual(stats["rot_rate"], 0.10,
                             msg=f"exponential rot rate {stats['rot_rate']:.3f}")

    def test_step_has_no_action_window(self):
        """Finding: step decay crosses SURFACE and ROT thresholds at the same
        instant, so an item is already rotted the moment it is surfaced.
        This is why step decay is rejected."""
        stats = simulate(n_items=50, days=60, daily_budget=5,
                         interval=21, func="step", seed=7)
        self.assertGreater(stats["rot_rate"], 0.10,
                           msg="step unexpectedly contained rot")

    def test_daily_surfaced_stays_within_budget(self):
        stats = simulate(n_items=50, days=60, daily_budget=5,
                         interval=21, func="linear", seed=7)
        self.assertLessEqual(stats["max_daily_surfaced"], 5)

    def test_without_scheduling_everything_rots(self):
        """Control: no re-evaluation => rot is near total (proves the mechanic matters)."""
        stats = simulate(n_items=50, days=60, daily_budget=0,
                         interval=21, func="linear", seed=7)
        self.assertGreater(stats["rot_rate"], 0.5)

    def test_under_provisioned_budget_still_rots(self):
        """Documented finding: when budget < demand, decay cannot be contained."""
        stats = simulate(n_items=50, days=60, daily_budget=2,
                         interval=7, func="linear", seed=7)
        self.assertFalse(stats["budget_covers_demand"])
        self.assertGreater(stats["rot_rate"], 0.10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
