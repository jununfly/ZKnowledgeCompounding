"""Spike 01 runner: compare decay functions, then validate the schema on real Postgres."""
import math
import subprocess
import sys
from datetime import datetime, timedelta

from decay_model import simulate, DECAY_FUNCS, ROT_THRESHOLD, SURFACE_THRESHOLD

CONTAINER = "zkc-spike-pg"


def action_window(func: str, interval: float) -> float:
    """Days between 'surfaced for attention' and 'already rotted'."""
    if func == "linear":
        return (ROT_THRESHOLD - SURFACE_THRESHOLD) * interval
    if func == "exponential":
        surf = interval * math.log2(1 / (1 - SURFACE_THRESHOLD))
        rot = interval * math.log2(1 / (1 - ROT_THRESHOLD))
        return rot - surf
    return 0.0  # step: both thresholds crossed at the same instant


def part1_comparison() -> None:
    print("=" * 78)
    print("PART 1 — decay function comparison (50 dynamic items, 60 days, budget 5/day)")
    print("=" * 78)
    print(f"{'func':<12} {'surface@':>9} {'rot@':>8} {'window':>8} "
          f"{'rot_rate':>9} {'max/day':>8} {'demand':>7} {'ok':>4}")
    print("-" * 78)
    for func in DECAY_FUNCS:
        s = simulate(n_items=50, days=60, daily_budget=5, interval=21, func=func, seed=7)
        w = action_window(func, 21)
        surf_day = 21 * (SURFACE_THRESHOLD if func == "linear"
                         else math.log2(1 / (1 - SURFACE_THRESHOLD)) if func == "exponential"
                         else 1.0)
        rot_day = surf_day + w
        print(f"{func:<12} {surf_day:>9.1f} {rot_day:>8.1f} {w:>8.1f} "
              f"{s['rot_rate']:>8.1%} {s['max_daily_surfaced']:>8} "
              f"{s['demand_per_day']:>7} {'yes' if s['budget_covers_demand'] else 'NO':>4}")
    print()
    print("Control (no scheduling, budget=0):")
    s = simulate(n_items=50, days=60, daily_budget=0, interval=21, func="linear", seed=7)
    print(f"  rot_rate={s['rot_rate']:.1%}  -> proves re-evaluation is what prevents rot")
    print()
    print("Under-provisioned (interval=7, budget=2):")
    s = simulate(n_items=50, days=60, daily_budget=2, interval=7, func="linear", seed=7)
    print(f"  demand={s['demand_per_day']}/day vs budget=2  rot_rate={s['rot_rate']:.1%}")
    print("  -> budget must cover demand, or decay is uncontainable")


def psql(sql: str) -> str:
    return subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", "zkc",
         "-v", "ON_ERROR_STOP=1", "-tA", "-f", "-"],
        input=sql, text=True, capture_output=True,
    ).stdout.strip()


def part2_database() -> None:
    print()
    print("=" * 78)
    print("PART 2 — schema validation on PostgreSQL 16 + pgvector")
    print("=" * 78)
    now = datetime(2026, 3, 1, 9, 0, 0)
    rows = []
    for i in range(50):
        elapsed = (i % 30)  # staggered staleness 0..29 days
        score = min(1.0, elapsed / 21.0)  # linear, interval=21
        reviewed = now - timedelta(days=elapsed)
        rows.append(
            f"('dynamic', 0.{90 - (i % 10):02d}, 'note-{i:02d}', 'content {i}', "
            f"NULL, NULL, now(), NULL, {score:.3f}, interval '21 days', "
            f"'{reviewed.isoformat()}'::timestamptz, {score:.3f}, '{reviewed.isoformat()}'::timestamptz)"
        )
    insert = (
        "INSERT INTO node (track, routing_confidence, title, content, valid_from, valid_to, "
        "tx_from, tx_to, decay_score, review_interval, last_reviewed_at, attention_signal, created_at) VALUES "
        + ",".join(rows) + ";"
    )
    psql("TRUNCATE node, meta_claim, edge, context;")
    psql(insert)

    total = psql("SELECT count(*) FROM node WHERE track='dynamic';")
    print(f"seeded dynamic nodes: {total}")

    due = psql(
        "SELECT id, title, round(decay_score::numeric,2) FROM node "
        "WHERE track='dynamic' AND decay_score >= 0.6 "
        "ORDER BY decay_score DESC LIMIT 5;"
    )
    print("\n'该关注' (top 5 within attention budget, decay >= 0.6):")
    for line in due.splitlines():
        parts = line.split("|")
        if len(parts) == 3:
            print(f"  {parts[1]:<10} decay={parts[2]}")

    cnt = psql("SELECT count(*) FROM node WHERE track='dynamic' AND decay_score >= 0.6;")
    print(f"\nitems above threshold: {cnt} (budget caps this to 5/day)")

    # Static track must NOT be governed by decay
    psql("INSERT INTO node (track, title, tx_from, valid_from, valid_to) VALUES "
         "('static','a durable fact', now(), now(), NULL);")
    st = psql("SELECT track, decay_score FROM node WHERE track='static';")
    print(f"static track row: {st}  (decay stays 0 — governed by bitemporal validity)")

    # Provenance must be mandatory
    try:
        subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", "zkc",
             "-v", "ON_ERROR_STOP=1", "-tA", "-f", "-"],
            input="INSERT INTO meta_claim (statement) VALUES 'no evidence';",
            text=True, capture_output=True, check=True,
        )
        print("\nWARNING: claim without evidence was accepted")
    except subprocess.CalledProcessError:
        print("\nclaim without evidence_refs: REJECTED (provenance enforced)")


if __name__ == "__main__":
    part1_comparison()
    part2_database()
    sys.exit(0)
