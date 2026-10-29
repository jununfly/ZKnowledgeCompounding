import unittest

from store import (
    connect, apply_schema, truncate_all, seed_interval, interval_to_days,
)
from interval_policy import (
    baseline_interval, assign_baselines, fit_budget, adapt_interval,
    classify_review, revert_transform, load_schedulable, daily_demand,
    extract_horizon_days, clamp_days,
    BASELINE_SELF_LOOP, BASELINE_ORPHAN, BASELINE_CONNECTED, BASELINE_CAPTURED,
    MIN_INTERVAL_DAYS, MAX_INTERVAL_DAYS, SURFACE_THRESHOLD,
)
from convergence import simulate, ON_TIME_BAND


class TestReviewIntervalPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apply_schema()

    def setUp(self):
        with connect() as conn, conn.cursor() as cur:
            truncate_all(cur)
            self.s = seed_interval(cur)
            assign_baselines(cur)          # L1 applied for every test
            conn.commit()

    # ---------- L1 baseline ----------
    def test_static_track_has_no_interval(self):
        with connect() as conn, conn.cursor() as cur:
            sug = baseline_interval(cur, self.s["s1"])
            self.assertIsNone(sug["days"])
            cur.execute("SELECT review_interval FROM node WHERE id=%s::uuid",
                        (self.s["s1"],))
            self.assertIsNone(cur.fetchone()[0])

    def test_explicit_horizon_beats_context_membership(self):
        # d1 is a self_loop member (baseline 3) but says "下周三" -> horizon 7 wins
        with connect() as conn, conn.cursor() as cur:
            sug = baseline_interval(cur, self.s["d1"])
        self.assertEqual(sug["tier"], "horizon")
        self.assertEqual(sug["days"], 7.0)

    def test_self_loop_baseline(self):
        with connect() as conn, conn.cursor() as cur:
            self.assertEqual(baseline_interval(cur, self.s["d2"])["days"],
                             BASELINE_SELF_LOOP)

    def test_connected_baseline(self):
        with connect() as conn, conn.cursor() as cur:
            self.assertEqual(baseline_interval(cur, self.s["d3"])["days"],
                             BASELINE_CONNECTED)

    def test_orphan_baseline(self):
        with connect() as conn, conn.cursor() as cur:
            self.assertEqual(baseline_interval(cur, self.s["d4"])["days"],
                             BASELINE_ORPHAN)

    def test_captured_value_gets_longer_cadence(self):
        with connect() as conn, conn.cursor() as cur:
            self.assertEqual(baseline_interval(cur, self.s["d5"])["days"],
                             BASELINE_CAPTURED)

    def test_assign_baselines_persists_but_preserves_human_override(self):
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT review_interval, baseline_interval FROM node "
                        "WHERE id=%s::uuid", (self.s["d2"],))
            eff, base = cur.fetchone()
            self.assertAlmostEqual(interval_to_days(eff), BASELINE_SELF_LOOP)
            self.assertAlmostEqual(interval_to_days(base), BASELINE_SELF_LOOP)
            # d7 was pinned by a human at 10 days and must survive automation
            cur.execute("SELECT review_interval FROM node WHERE id=%s::uuid",
                        (self.s["d7"],))
            self.assertAlmostEqual(interval_to_days(cur.fetchone()[0]), 10.0)

    # ---------- L2 budget ----------
    def test_generous_budget_changes_nothing(self):
        with connect() as conn, conn.cursor() as cur:
            rep = fit_budget(cur, 5.0)
            self.assertFalse(rep["applied"])
            self.assertEqual(rep["degraded"], [])
            self.assertLessEqual(rep["demand_after"], 5.0)
            conn.commit()

    def test_budget_pressure_defers_lowest_priority_first_and_spares_humans(self):
        with connect() as conn, conn.cursor() as cur:
            rep = fit_budget(cur, 1.2)
            conn.commit()
        self.assertTrue(rep["applied"])
        self.assertLessEqual(rep["demand_after"], 1.2)
        ids = [d["id"] for d in rep["degraded"]]
        self.assertEqual(ids[0], self.s["d4"])              # 孤儿最先被延后
        self.assertNotIn(self.s["d7"], ids)                 # 人工设定豁免
        for d in rep["degraded"]:
            self.assertGreater(d["new_days"], d["old_days"])

    def test_infeasible_budget_is_reported_not_hidden(self):
        with connect() as conn, conn.cursor() as cur:
            rep = fit_budget(cur, 0.001)
            conn.commit()
        self.assertTrue(rep["infeasible"])
        self.assertGreater(rep["demand_after"], 0.001)
        self.assertEqual(rep["max_dynamic_items"], 0)

    def test_demand_matches_spike01_formula(self):
        # uniform interval I over n items -> demand = n / (0.6 * I)
        with connect() as conn, conn.cursor() as cur:
            rows = load_schedulable(cur)
            manual = sum(1.0 / (0.6 * (r["interval"] or r["baseline"])) for r in rows)
            self.assertAlmostEqual(daily_demand(rows), manual, places=6)
            n = len(rows)
            for r in rows:
                cur.execute("UPDATE node SET review_interval = interval '14 days' "
                            "WHERE id=%s::uuid", (r["id"],))
            rows2 = load_schedulable(cur)
            self.assertAlmostEqual(daily_demand(rows2), n / (0.6 * 14.0), places=6)

    # ---------- L3 feedback ----------
    def test_feedback_expands_when_reviewed_too_early(self):
        with connect() as conn, conn.cursor() as cur:
            res = adapt_interval(cur, self.s["d4"], decay_at_review=0.10)
            conn.commit()
        self.assertEqual(res["verdict"], "too_early")
        self.assertAlmostEqual(res["new_days"], res["old_days"] * 1.5)
        self.assertTrue(res["applied"])

    def test_feedback_shrinks_when_reviewed_too_late(self):
        with connect() as conn, conn.cursor() as cur:
            res = adapt_interval(cur, self.s["d4"], decay_at_review=0.95)
            conn.commit()
        self.assertEqual(res["verdict"], "too_late")
        self.assertAlmostEqual(res["new_days"], res["old_days"] * 0.7)

    def test_feedback_on_time_is_a_noop(self):
        with connect() as conn, conn.cursor() as cur:
            res = adapt_interval(cur, self.s["d4"], decay_at_review=0.5)
        self.assertEqual(res["verdict"], "on_time")
        self.assertFalse(res["applied"])

    def test_feedback_clamps_to_bounds(self):
        with connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE node SET review_interval = interval '170 days' "
                        "WHERE id=%s::uuid", (self.s["d4"],))
            res = adapt_interval(cur, self.s["d4"], decay_at_review=0.0)
            self.assertAlmostEqual(res["new_days"], MAX_INTERVAL_DAYS)
            cur.execute("UPDATE node SET review_interval = interval '1 day' "
                        "WHERE id=%s::uuid", (self.s["d4"],))
            res = adapt_interval(cur, self.s["d4"], decay_at_review=1.0)
            self.assertAlmostEqual(res["new_days"], MIN_INTERVAL_DAYS)
            conn.commit()

    def test_human_override_immune_to_feedback(self):
        with connect() as conn, conn.cursor() as cur:
            res = adapt_interval(cur, self.s["d7"], decay_at_review=0.95)
        self.assertFalse(res["applied"])
        self.assertAlmostEqual(res["new_days"], 10.0)

    # ---------- audit + rollback (§6.4 C2) ----------
    def test_revert_transform_restores_every_interval(self):
        with connect() as conn, conn.cursor() as cur:
            before = {r["id"]: r["interval"] for r in load_schedulable(cur)}
            rep = fit_budget(cur, 1.2)
            tid = rep["transform_id"]
            changed = {d["id"]: d["old_days"] for d in rep["degraded"]}
            self.assertTrue(changed)
            n = revert_transform(cur, tid)
            self.assertEqual(n, len(changed))
            after = {r["id"]: r["interval"] for r in load_schedulable(cur)}
            cur.execute("SELECT count(*) FROM interval_adjustment WHERE produced_by=%s::uuid",
                        (tid,))
            self.assertEqual(cur.fetchone()[0], 0)
            conn.commit()
        for nid, old in changed.items():
            self.assertAlmostEqual(after[nid], old, places=6)
        for nid, val in before.items():
            if nid not in changed:
                self.assertAlmostEqual(after[nid], val, places=6)

    def test_every_change_is_audited_with_a_reason(self):
        with connect() as conn, conn.cursor() as cur:
            fit_budget(cur, 1.2)
            cur.execute("SELECT count(*) FROM interval_adjustment WHERE reason IS NULL "
                        "OR reason = ''")
            self.assertEqual(cur.fetchone()[0], 0)
            cur.execute("SELECT count(*) FROM interval_adjustment WHERE kind='budget'")
            self.assertGreater(cur.fetchone()[0], 0)
            conn.commit()

    # ---------- L3: does the closed loop actually carry information? ----------
    def test_decay_only_feedback_is_a_permanent_noop(self):
        # A scheduler that fires exactly at decay=0.6 always sees 0.6 -> "on_time".
        # Safe (never oscillates) but it can never correct a wrong baseline.
        traj = simulate(h_true=10.0, i0=7.0, labeled=False)
        self.assertEqual(set(traj), {7.0})

    def test_labeled_feedback_converges_to_the_true_rot_rate(self):
        h = 10.0
        target = h / SURFACE_THRESHOLD          # review lands exactly at staleness
        traj = simulate(h, 7.0, labeled=True)
        self.assertGreater(traj[-1], 7.0)       # it did correct the too-short baseline
        self.assertLess(abs(SURFACE_THRESHOLD * traj[-1] - h), ON_TIME_BAND * h)
        self.assertAlmostEqual(target, 16.667, places=2)

    def test_labeled_feedback_also_shrinks_a_too_long_baseline(self):
        h = 10.0
        traj = simulate(h, 90.0, labeled=True)
        self.assertLess(traj[-1], 90.0)
        self.assertLess(abs(SURFACE_THRESHOLD * traj[-1] - h), ON_TIME_BAND * h)

    # ---------- horizon parser ----------
    def test_horizon_parser_prefers_the_soonest_anchor(self):
        self.assertEqual(extract_horizon_days("3 天内跟进"), 3.0)
        self.assertEqual(extract_horizon_days("下周三前提交"), 7.0)
        self.assertEqual(extract_horizon_days("本季度目标，月底前交付"), 14.0)
        self.assertIsNone(extract_horizon_days("一段没有时间锚的随想"))
        self.assertEqual(clamp_days(9999), MAX_INTERVAL_DAYS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
