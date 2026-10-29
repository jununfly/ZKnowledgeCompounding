import unittest
from datetime import date

from store import connect, apply_schema, truncate_all
from budget_estimator import (
    record_day, load_observations, estimate_budget, update_budget, percentile,
    l2_target, labeling_rate, MIN_BUDGET, BOOTSTRAP_BUDGET, DOWN_DAMP,
    OVERSUBSCRIBE_CALIBRATING, MIN_LABEL_RATE, MIN_LABEL_SAMPLES,
)
from interval_policy import fit_budget, adapt_interval
from budget_sim import simulate_budget_loop

D0 = date(2026, 3, 1)


def _seed_days(cur, rows):
    """rows: list of (pushed, completed, queue_remaining)."""
    for i, (pushed, completed, remaining) in enumerate(rows):
        record_day(cur, D0 + __import__("datetime").timedelta(days=i),
                   pushed, completed, remaining)


class TestBudgetEstimator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apply_schema()

    def setUp(self):
        with connect() as conn, conn.cursor() as cur:
            truncate_all(cur)
            conn.commit()

    # ---------- observation model ----------
    def test_no_observations_means_no_estimate_and_l2_stays_passive(self):
        with connect() as conn, conn.cursor() as cur:
            rep = estimate_budget(cur)
            self.assertIsNone(rep["estimate"])
            self.assertEqual(rep["confidence"], "none")
            out = update_budget(cur, current=7.0)
            self.assertFalse(out["applied"])
            self.assertEqual(out["new"], 7.0)

    def test_record_day_is_idempotent_per_day(self):
        with connect() as conn, conn.cursor() as cur:
            record_day(cur, D0, 5, 3, 2)
            record_day(cur, D0, 9, 4, 5)
            cur.execute("SELECT count(*) FROM attention_observation")
            self.assertEqual(cur.fetchone()[0], 1)
            self.assertEqual(load_observations(cur)[0]["completed"], 4)
            conn.commit()

    # ---------- censoring-aware estimate ----------
    def test_saturated_days_confirm_the_ceiling(self):
        with connect() as conn, conn.cursor() as cur:
            _seed_days(cur, [(9, 3, 6)] * 4)          # 4 capacity-limited days
            rep = estimate_budget(cur)
            conn.commit()
        self.assertEqual(rep["confidence"], "observed")
        self.assertEqual(rep["estimate"], 3.0)
        self.assertEqual(rep["n_saturated"], 4)

    def test_emptied_queue_is_only_a_lower_bound(self):
        with connect() as conn, conn.cursor() as cur:
            _seed_days(cur, [(1, 1, 0), (2, 2, 0), (1, 1, 0)])
            rep = estimate_budget(cur)
            conn.commit()
        self.assertEqual(rep["confidence"], "lower_bound")
        self.assertEqual(rep["estimate"], 2.0)       # max completed, NOT the mean

    def test_mixed_samples_use_only_the_saturated_ones(self):
        with connect() as conn, conn.cursor() as cur:
            _seed_days(cur, [(1, 1, 0), (1, 1, 0), (8, 4, 4), (8, 4, 4), (8, 4, 4)])
            rep = estimate_budget(cur)
            conn.commit()
        self.assertEqual(rep["estimate"], 4.0)
        self.assertEqual(rep["confidence"], "observed")

    def test_percentile_helper(self):
        self.assertAlmostEqual(percentile([2, 3, 4, 10], 0.25), 2.75)
        self.assertEqual(percentile([5], 0.25), 5.0)

    # ---------- anti-collapse defences ----------
    def test_guardrail_blocks_lowering_on_a_lower_bound(self):
        with connect() as conn, conn.cursor() as cur:
            _seed_days(cur, [(1, 1, 0), (2, 2, 0)])
            out = update_budget(cur, current=10.0)
            conn.commit()
        self.assertFalse(out["applied"])
        self.assertEqual(out["new"], 10.0)
        self.assertIn("guardrail", out["reason"])

    def test_without_the_guardrail_the_budget_is_lowered(self):
        with connect() as conn, conn.cursor() as cur:
            _seed_days(cur, [(1, 1, 0), (2, 2, 0)])
            out = update_budget(cur, current=10.0, guardrail=False)
            conn.commit()
        self.assertTrue(out["applied"])
        self.assertLess(out["new"], 10.0)

    def test_a_lower_bound_may_still_raise_the_budget(self):
        with connect() as conn, conn.cursor() as cur:
            _seed_days(cur, [(1, 1, 0), (3, 3, 0)])
            out = update_budget(cur, current=1.0)
            conn.commit()
        self.assertGreater(out["new"], 1.0)

    def test_single_update_is_damped(self):
        with connect() as conn, conn.cursor() as cur:
            _seed_days(cur, [(9, 1, 8)] * 5)         # ceiling really is 1
            out = update_budget(cur, current=10.0)
            conn.commit()
        self.assertGreaterEqual(out["new"], 10.0 * DOWN_DAMP - 1e-9)

    def test_bootstrap_takes_the_estimate_directly(self):
        with connect() as conn, conn.cursor() as cur:
            _seed_days(cur, [(9, 4, 5)] * 4)
            out = update_budget(cur, current=None)
            conn.commit()
        self.assertEqual(out["new"], 4.0)
        self.assertTrue(out["applied"])

    # ---------- oversubscribe while calibrating ----------
    def test_l2_target_oversubscribes_only_while_unconfirmed(self):
        self.assertAlmostEqual(l2_target(4.0, "lower_bound"),
                               4.0 * OVERSUBSCRIBE_CALIBRATING)
        self.assertEqual(l2_target(4.0, "observed"), 4.0)
        self.assertIsNone(l2_target(None, "none"))

    # ---------- L3 标注率闸门（zj 定：>= 70% 起步）----------
    def _seed_labeled(self, cur, labeled: int, total: int):
        """One observed day: `total` completed reviews, `labeled` of them labelled."""
        record_day(cur, D0, pushed=total, completed=total, queue_remaining=0,
                   labeled_completed=labeled)

    def test_labeling_rate_and_gate_threshold(self):
        with connect() as conn, conn.cursor() as cur:
            self._seed_labeled(cur, labeled=8, total=20)      # 40% -> below 70%
            rep = labeling_rate(cur)
            conn.commit()
        self.assertAlmostEqual(rep["rate"], 0.4)
        self.assertEqual(rep["gate"], "closed")
        self.assertEqual(rep["threshold"], MIN_LABEL_RATE)

    def test_labeling_rate_at_or_above_threshold_opens_gate(self):
        with connect() as conn, conn.cursor() as cur:
            self._seed_labeled(cur, labeled=14, total=20)     # exactly 70%
            rep = labeling_rate(cur)
            conn.commit()
        self.assertEqual(rep["gate"], "open")

    def test_insufficient_evidence_never_blocks_l3(self):
        with connect() as conn, conn.cursor() as cur:
            self._seed_labeled(cur, labeled=0, total=3)       # 0% but only 3 samples
            rep = labeling_rate(cur)
            conn.commit()
        self.assertIsNone(rep["rate"])
        self.assertEqual(rep["gate"], "open")
        self.assertLess(rep["completed"], MIN_LABEL_SAMPLES)

    def test_closed_gate_stops_adapt_interval(self):
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO node (track, title, content, review_interval) "
                "VALUES ('dynamic','d','x', interval '7 days') RETURNING id")
            nid = str(cur.fetchone()[0])
            self._seed_labeled(cur, labeled=2, total=20)      # 10% -> closed
            res = adapt_interval(cur, nid, decay_at_review=0.1)
            conn.commit()
        self.assertFalse(res["applied"])
        self.assertIn("label gate closed", res["reason"])
        self.assertEqual(res["new_days"], 7.0)

    def test_explicit_outcome_bypasses_the_gate(self):
        """A human-supplied verdict IS the signal the gate exists to require."""
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO node (track, title, content, review_interval) "
                "VALUES ('dynamic','d','x', interval '7 days') RETURNING id")
            nid = str(cur.fetchone()[0])
            self._seed_labeled(cur, labeled=0, total=20)      # gate would be closed
            res = adapt_interval(cur, nid, decay_at_review=0.1, outcome="too_early")
            conn.commit()
        self.assertTrue(res["applied"])

    def test_labeled_cannot_exceed_completed(self):
        with connect() as conn, conn.cursor() as cur:
            with self.assertRaises(Exception):
                record_day(cur, D0, pushed=5, completed=5, queue_remaining=0,
                           labeled_completed=9)
            conn.rollback()

    def test_fit_budget_with_no_estimate_changes_nothing(self):
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO node (track, title, content, review_interval) "
                "VALUES ('dynamic','x','y', interval '7 days')")
            rep = fit_budget(cur, None)
            conn.commit()
        self.assertFalse(rep["applied"])
        self.assertIn("warm-up", rep["note"])


class TestBudgetLoopConvergence(unittest.TestCase):
    """System-level: does the observed budget actually find the true capacity?"""

    @classmethod
    def setUpClass(cls):
        apply_schema()

    def setUp(self):
        with connect() as conn, conn.cursor() as cur:
            truncate_all(cur)
            conn.commit()

    def _run(self, **kw):
        kw.setdefault("n_items", 60)
        kw.setdefault("days", 30)
        kw.setdefault("true_capacity", 3.0)
        with connect() as conn, conn.cursor() as cur:
            rep = simulate_budget_loop(cur, **kw)
            conn.rollback()
        return rep

    def test_optimistic_start_converges_to_true_capacity(self):
        rep = self._run(initial_budget=BOOTSTRAP_BUDGET)
        self.assertAlmostEqual(rep["final_budget"], rep["true_capacity"], delta=0.5)
        self.assertEqual(rep["final_estimate"]["confidence"], "observed")
        self.assertGreater(rep["saturated_days"], 0)

    def test_pessimistic_start_climbs_instead_of_locking_in(self):
        rep = self._run(initial_budget=1.0)
        self.assertGreater(rep["final_budget"], 2.0)
        self.assertAlmostEqual(rep["final_budget"], rep["true_capacity"], delta=0.5)

    def test_guardrail_holds_the_budget_when_supply_never_reaches_capacity(self):
        held = self._run(initial_budget=BOOTSTRAP_BUDGET, n_items=12, days=25,
                         true_capacity=8.0, use_oversubscribe=False, guardrail=True)
        free = self._run(initial_budget=BOOTSTRAP_BUDGET, n_items=12, days=25,
                         true_capacity=8.0, use_oversubscribe=False, guardrail=False)
        self.assertEqual(held["final_budget"], BOOTSTRAP_BUDGET)   # refused to lower
        self.assertLess(free["final_budget"], BOOTSTRAP_BUDGET)    # lowered on a lower bound


if __name__ == "__main__":
    unittest.main(verbosity=2)
