"""Spike 01: decay model + resource-aware scheduling for the DYNAMIC track.

Scope: this module models rot and attention scheduling only.
The STATIC track is governed by bitemporal validity (valid_from/valid_to,
tx_from/tx_to) and is explicitly NOT subject to decay.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

# An item is considered "rotted" once it decays past this point without review.
ROT_THRESHOLD = 0.9
# An item is surfaced (enters attention) once it decays past this point.
SURFACE_THRESHOLD = 0.6


def decay_linear(elapsed_days: float, interval_days: float) -> float:
    """Rot grows proportionally with elapsed time; saturates at the interval."""
    if interval_days <= 0:
        return 1.0
    return min(1.0, max(0.0, elapsed_days / interval_days))


def decay_exponential(elapsed_days: float, half_life_days: float) -> float:
    """Rot halves every half-life; asymptotic, never quite reaching 1."""
    if half_life_days <= 0:
        return 1.0
    return min(1.0, max(0.0, 1.0 - 0.5 ** (elapsed_days / half_life_days)))


def decay_step(elapsed_days: float, interval_days: float) -> float:
    """Fresh until the interval elapses, then fully stale. Coarse but predictable."""
    if interval_days <= 0:
        return 1.0
    return 1.0 if elapsed_days >= interval_days else 0.0


DECAY_FUNCS = {
    "linear": decay_linear,
    "exponential": decay_exponential,
    "step": decay_step,
}


def _elapsed_days(item: dict, now: datetime) -> float:
    anchor = item.get("last_reviewed_at") or item.get("created_at") or now
    return (now - anchor).total_seconds() / 86400.0


def compute_score(item: dict, now: datetime, func: str = "linear") -> float:
    """Current decay score. Static items never decay."""
    if item.get("track") == "static":
        return 0.0
    fn = DECAY_FUNCS[func]
    interval = item.get("review_interval") or 7
    return fn(_elapsed_days(item, now), interval)


def surface(items: list[dict], now: datetime, threshold: float = SURFACE_THRESHOLD,
            budget: int | None = None, func: str = "linear") -> list[dict]:
    """Pick the most-decayed items above threshold, capped by the attention budget."""
    scored = [(compute_score(i, now, func), idx, i) for idx, i in enumerate(items)]
    above = [(s, idx, i) for s, idx, i in scored if s >= threshold]
    above.sort(key=lambda t: (-t[0], t[1]))  # most decayed first, stable by input order
    picked = [i for _, _, i in above]
    if budget is not None:
        picked = picked[:budget]
    return picked


def review(item: dict, now: datetime) -> dict:
    """Human (or distillation) touched the item: reset its decay clock."""
    updated = dict(item)
    updated["last_reviewed_at"] = now
    updated["decay_score"] = 0.0
    return updated


def simulate(n_items: int = 50, days: int = 60, daily_budget: int = 5,
             interval: float = 14, func: str = "linear", seed: int = 7,
             start: datetime | None = None) -> dict:
    """Simulate `n_items` dynamic items over `days` days with a daily attention budget.

    Returns rot_rate (share of items that ever passed ROT_THRESHOLD unreviewed),
    max_daily_surfaced, total reviews, and the implied demand/budget ratio.
    """
    rng = random.Random(seed)
    start = start or datetime(2026, 1, 1, 9, 0, 0)

    items = []
    for i in range(n_items):
        # Stagger creation so demand is spread rather than synchronised.
        created = start + timedelta(days=rng.uniform(0, min(days, 30)))
        items.append({
            "id": i,
            "track": "dynamic",
            "review_interval": interval,
            "created_at": created,
            "last_reviewed_at": created,
            "decay_score": 0.0,
        })

    rotted: set[int] = set()
    total_reviews = 0
    max_daily = 0
    day = start
    for _ in range(days):
        day = day + timedelta(days=1)
        live = [it for it in items if it["last_reviewed_at"] <= day]
        for it in live:
            if compute_score(it, day, func) >= ROT_THRESHOLD:
                rotted.add(it["id"])
        picked = surface(live, day, SURFACE_THRESHOLD, daily_budget, func)
        max_daily = max(max_daily, len(picked))
        for it in picked:
            it.update(review(it, day))
            total_reviews += 1

    demand_per_day = n_items / interval if interval else float("inf")
    return {
        "func": func,
        "n_items": n_items,
        "days": days,
        "daily_budget": daily_budget,
        "interval": interval,
        "rot_rate": len(rotted) / n_items,
        "rotted_count": len(rotted),
        "total_reviews": total_reviews,
        "max_daily_surfaced": max_daily,
        "demand_per_day": round(demand_per_day, 2),
        "budget_covers_demand": daily_budget >= demand_per_day,
    }
