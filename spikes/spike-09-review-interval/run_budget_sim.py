"""Quick driver: run the three budget-loop paths side by side."""
import sys

from store import connect, apply_schema, truncate_all
from budget_sim import simulate_budget_loop
from budget_estimator import BOOTSTRAP_BUDGET

TRUE_CAPACITY = 3.0

PATHS = [
    ("A optimistic start (10), rich supply",
     dict(initial_budget=BOOTSTRAP_BUDGET, guardrail=True, n_items=60)),
    ("B pessimistic start (1), rich supply",
     dict(initial_budget=1.0, guardrail=True, n_items=60)),
    ("C optimistic, NO guardrail, rich supply",
     dict(initial_budget=BOOTSTRAP_BUDGET, guardrail=False, n_items=60)),
    ("D optimistic, SCARCE supply (12 items), guardrail ON",
     dict(initial_budget=BOOTSTRAP_BUDGET, guardrail=True, n_items=12)),
    ("E optimistic, SCARCE supply (12 items), guardrail OFF",
     dict(initial_budget=BOOTSTRAP_BUDGET, guardrail=False, n_items=12)),
    ("F SCARCE supply, guardrail OFF, NO oversubscribe -> collapse?",
     dict(initial_budget=BOOTSTRAP_BUDGET, guardrail=False, n_items=12,
          use_oversubscribe=False)),
    ("H capacity 8 > supply, guardrail OFF, NO oversubscribe -> false equilibrium?",
     dict(initial_budget=BOOTSTRAP_BUDGET, guardrail=False, n_items=12,
          use_oversubscribe=False, true_capacity=8.0)),
    ("I capacity 8 > supply, guardrail ON,  NO oversubscribe -> held?",
     dict(initial_budget=BOOTSTRAP_BUDGET, guardrail=True, n_items=12,
          use_oversubscribe=False, true_capacity=8.0)),
]

if __name__ == "__main__":
    apply_schema()
    verbose = "-v" in sys.argv
    for label, kw in PATHS:
        with connect() as conn, conn.cursor() as cur:
            truncate_all(cur)
            rep = simulate_budget_loop(cur, verbose=verbose, **kw)
            conn.rollback()
        print(f"\n=== {label} === (true capacity {rep['true_capacity']}/day, "
              f"{rep['n_items']} items, {rep['days']} days)")
        print(f"  final budget      : {rep['final_budget']}")
        print(f"  budget trajectory : {rep['budget_trajectory'][:14]} ... {rep['budget_trajectory'][-3:]}")
        print(f"  saturated days    : {rep['saturated_days']}/{rep['days']}")
        print(f"  pushed (first 8)  : {rep['pushed_trajectory'][:8]}")
        print(f"  pushed (last 5)   : {rep['pushed_trajectory'][-5:]}")
        print(f"  total completed   : {rep['total_completed']}")
        print(f"  final avg interval: {rep['final_avg_interval']}d")
        print(f"  final estimate    : {rep['final_estimate']['estimate']} "
              f"({rep['final_estimate']['confidence']})")
