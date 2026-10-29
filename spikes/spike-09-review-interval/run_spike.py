"""Spike 09 runner: apply schema, run the test suite, print a demo of the three layers."""
import sys
import unittest

from store import connect, apply_schema, truncate_all, seed_interval, interval_to_days
from interval_policy import (
    assign_baselines, fit_budget, adapt_interval, load_schedulable, daily_demand,
    priority, effective_days,
)


def demo():
    apply_schema()
    with connect() as conn, conn.cursor() as cur:
        truncate_all(cur)
        s = seed_interval(cur)

        print("=== L1 baseline (individual rot rate) ===")
        assign_baselines(cur)
        for key in ("s1", "d1", "d2", "d3", "d4", "d5", "d6", "d7"):
            cur.execute("SELECT review_interval, interval_source FROM node WHERE id=%s::uuid",
                        (s[key],))
            iv, src = cur.fetchone()
            days = interval_to_days(iv)
            print(f"  {key}: interval={'-' if days is None else round(days, 2)} "
                  f"source={src}")

        rows = load_schedulable(cur)
        print(f"\n  demand at baselines = {daily_demand(rows):.3f} reviews/day")

        print("\n=== L2 budget normalisation (budget = 1.2 reviews/day) ===")
        rep = fit_budget(cur, 1.2)
        print(f"  demand {rep['demand_before']:.3f} -> {rep['demand_after']:.3f} "
              f"(budget {rep['budget']})")
        for d in rep["degraded"]:
            print(f"    deferred {d['id'][:8]} (priority {d['priority']}): "
                  f"{d['old_days']:g}d -> {d['new_days']:g}d")
        print(f"  infeasible={rep['infeasible']}  max_dynamic_items={rep['max_dynamic_items']}")

        print("\n=== L3 feedback (reviewer found it still fresh) ===")
        res = adapt_interval(cur, s["d4"], decay_at_review=0.1)
        print(f"  d4 {res['old_days']:g}d -> {res['new_days']:g}d :: {res['reason']}")

        print("\n=== L3 convergence check (true staleness = 10d) ===")
        from convergence import convergence_summary
        for labeled in (False, True):
            rep = convergence_summary(10.0, 7.0, labeled=labeled)
            print(f"  labeled={labeled!s:5} -> final={rep['final']}d "
                  f"(target {rep['target']}d) corrected={rep['changed']} "
                  f"steps_to_band={rep['n_steps_to_band']}")
            print(f"      trajectory: {rep['trajectory']}")

        conn.rollback()   # demo leaves no trace


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        demo()
    else:
        unittest.main(verbosity=2)
