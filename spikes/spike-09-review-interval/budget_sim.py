"""Spike 09 切片 B: does a statistically-assigned `budget_per_day` actually converge?

The loop under test is self-referential:

    budget -> L2 stretches intervals -> fewer items surface -> fewer reviews observed
           -> lower observed "capacity" -> lower budget -> ...

This module runs that loop against a *known* ground-truth capacity so we can see whether
the estimate converges to it, gets stuck, or collapses. Three paths:

  A  optimistic start (budget 10, true capacity 3)      -> should converge near 3
  B  pessimistic start (budget 1,  true capacity 3)     -> does it climb, or lock in?
  C  optimistic start with the monotonic guardrail OFF  -> should collapse (the control)

C is the experiment that matters: if the guardrail makes no difference, it is decoration.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from budget_estimator import (
    record_day, update_budget, estimate_budget, l2_target, MIN_BUDGET, BOOTSTRAP_BUDGET,
)
from interval_policy import fit_budget, SURFACE_THRESHOLD


def _seed_items(cur, n: int, start: date, rng: random.Random, interval_days: float = 7.0):
    ids = []
    for i in range(n):
        cur.execute(
            "INSERT INTO node (track, title, content, decay_score, review_interval, "
            "last_reviewed_at) VALUES ('dynamic',%s,%s,0,%s,%s) RETURNING id",
            (f"N{i}", "simulated dynamic item",
             timedelta(days=interval_days), start - timedelta(days=rng.randint(0, 6))),
        )
        ids.append(str(cur.fetchone()[0]))
    return ids


def _intervals(cur) -> dict:
    cur.execute("SELECT id, review_interval, last_reviewed_at FROM node WHERE track='dynamic'")
    out = {}
    for nid, iv, last in cur.fetchall():
        out[str(nid)] = (iv.total_seconds() / 86400.0, last.date())
    return out


def simulate_budget_loop(cur, n_items: int = 60, true_capacity: float = 3.0,
                         days: int = 40, initial_budget: float | None = BOOTSTRAP_BUDGET,
                         guardrail: bool = True, seed: int = 7,
                         use_oversubscribe: bool = True,
                         start: date = date(2026, 1, 1), verbose: bool = False) -> dict:
    rng = random.Random(seed)
    ids = _seed_items(cur, n_items, start, rng)

    budget = initial_budget
    traj, pushed_traj, completed_traj, saturated_days, avg_intervals = [], [], [], 0, []

    for d in range(days):
        day = start + timedelta(days=d)
        ivs = _intervals(cur)
        surfaced = []
        for nid, (iv, last) in ivs.items():
            elapsed = (day - last).days
            decay = min(1.0, elapsed / iv) if iv else 1.0
            if decay >= SURFACE_THRESHOLD:
                surfaced.append((decay, nid))
        surfaced.sort(reverse=True)
        pushed = len(surfaced)

        # a human with `true_capacity` reviews/day (fractional capacity -> expectation)
        cap = int(true_capacity) + (1 if rng.random() < true_capacity - int(true_capacity) else 0)
        completed = min(pushed, cap)
        queue_remaining = pushed - completed
        if queue_remaining > 0:
            saturated_days += 1

        for _, nid in surfaced[:completed]:
            cur.execute("UPDATE node SET last_reviewed_at=%s, decay_score=0 WHERE id=%s::uuid",
                        (day, nid))

        record_day(cur, day, pushed, completed, queue_remaining)
        res = update_budget(cur, budget, guardrail=guardrail)
        if res["new"] is not None:
            budget = res["new"]
        target = l2_target(budget, res["confidence"]) if use_oversubscribe else budget
        fit_budget(cur, target)

        traj.append(round(budget, 3) if budget is not None else None)
        pushed_traj.append(pushed)
        completed_traj.append(completed)
        avg_intervals.append(round(sum(v[0] for v in ivs.values()) / len(ivs), 1))
        if verbose:
            print(f"  day {d:02d}: pushed={pushed:3d} completed={completed:2d} "
                  f"queue={queue_remaining:3d} budget={budget}")

    return dict(
        n_items=n_items, true_capacity=true_capacity, days=days,
        initial_budget=initial_budget, guardrail=guardrail,
        final_budget=traj[-1],
        budget_trajectory=traj,
        pushed_trajectory=pushed_traj,
        total_completed=sum(completed_traj),
        saturated_days=saturated_days,
        avg_interval_trajectory=avg_intervals,
        final_avg_interval=avg_intervals[-1],
        final_estimate=estimate_budget(cur),
    )
