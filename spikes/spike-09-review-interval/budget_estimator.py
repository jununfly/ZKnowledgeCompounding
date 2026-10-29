"""Spike 09 切片 B: estimate `budget_per_day` from observed behaviour.

`budget_per_day` is a CAPACITY. Capacities can only be observed, not declared — and this
one is observed under *censoring*, which is the whole difficulty:

  budget -> (L2) intervals -> how many items surface -> how many reviews happen -> budget

That loop is self-referential and, left alone, collapses: a too-low initial budget stretches
intervals, which reduces supply, which makes every day look supply-limited, which "proves"
the low budget was right. The system settles into an equilibrium where it reviews almost
nothing and reports itself healthy — self-deception, not correctness.

Three defences, each targeting one edge of that loop:

  1. CENSORING-AWARE ESTIMATE. A day that ends with a backlog (`queue_remaining > 0`) is
     capacity-limited: `completed` is evidence of the ceiling. A day that ends empty is
     supply-limited: `completed` is only a LOWER BOUND. Mixing them without the flag is
     what makes the estimate collapse.

  2. MONOTONIC GUARDRAIL. A non-saturated day may only ever RAISE the budget (it proves
     capacity >= completed); it can never lower it. Only saturated days may lower it.
     This is what actually severs the positive feedback — see budget_sim.py for the
     with/without comparison.

  3. DAMPED EMA. Single-day noise moves the budget by at most +/-30%, and the estimate is
     smoothed, so one bad day cannot reconfigure the whole schedule.

Bootstrap consequence (validated by simulation, not assumed):
  Start OPTIMISTIC. An over-estimate produces backlog, backlog produces saturated days,
  saturated days produce the corrective signal. An under-estimate produces an empty queue,
  which produces no signal at all — it is absorbent. So `BOOTSTRAP_BUDGET` is deliberately
  generous and L2 stays passive until real observations exist.
"""
from __future__ import annotations

from datetime import date, timedelta

MIN_BUDGET = 0.1
MAX_BUDGET = 500.0

# estimator
LOOKBACK_DAYS = 28
SATURATED_QUANTILE = 0.25      # conservative: the low end of the "hit the ceiling" samples
MIN_SATURATED_SAMPLES = 3      # below this the estimate is 'provisional'

# update dynamics
EMA_ALPHA = 0.3                # smoothing
DOWN_DAMP = 0.7                # a single update may not cut the budget by more than 30%
UP_DAMP = 1.3                  # ... nor raise it by more than 30%
BOOTSTRAP_BUDGET = 10.0        # cold start is optimistic on purpose (see module docstring)

# While the estimate is still unconfirmed there is a second failure mode: if L2 fits the
# schedule to exactly `budget`, supply lands at or below capacity, the queue always empties,
# and no saturated day ever happens — the budget can never be corrected upward (path B in
# budget_sim.py). So during calibration we deliberately OVERSUBSCRIBE: keep supply a bit
# above the believed capacity so the ceiling stays observable. Once the estimate is
# confirmed ('observed') we go back to fitting exactly, otherwise the backlog would grow
# without bound.
OVERSUBSCRIBE_CALIBRATING = 1.5

# --- L3 标注率闸门（zj 定：>= 70% 起步）---------------------------------------------
# L3 只认显式结果标注；decay 数值在按阈值调度下恒为 0.6，不携带信息（切片 A F1）。
# 所以标注率必须被观测，低于门槛时 L3 停机——宁可 interval 停在基线，也不能用
# "无声的划过"冒充信号去改写节奏。
MIN_LABEL_RATE = 0.70
LABEL_WINDOW_DAYS = 7      # 滚动窗口：单日样本太小，不足以判率
MIN_LABEL_SAMPLES = 10     # 窗口内完成复审少于此数 -> 样本不足，闸门放行（不因缺数据而停机）


def labeling_rate(cur, window_days: int = LABEL_WINDOW_DAYS) -> dict:
    """Share of completed reviews that carried an explicit outcome label.

    Insufficient evidence never blocks L3 (we would otherwise freeze the loop during
    warm-up); only a *measured* rate below the threshold does.
    """
    rows = load_observations(cur, window_days)
    completed = sum(r["completed"] for r in rows)
    labeled = sum(r["labeled_completed"] for r in rows)
    if completed < MIN_LABEL_SAMPLES:
        return dict(rate=None, completed=completed, labeled=labeled,
                    threshold=MIN_LABEL_RATE, gate="open",
                    reason=f"only {completed} completed reviews in the last "
                           f"{window_days}d (< {MIN_LABEL_SAMPLES}) -> insufficient "
                           f"evidence, gate stays open")
    rate = labeled / completed
    ok = rate >= MIN_LABEL_RATE
    return dict(rate=round(rate, 3), completed=completed, labeled=labeled,
                threshold=MIN_LABEL_RATE,
                gate="open" if ok else "closed",
                reason=(f"labeling rate {rate:.0%} over {completed} completed reviews "
                        f"{'meets' if ok else 'is below'} the {MIN_LABEL_RATE:.0%} "
                        f"threshold -> L3 {'runs' if ok else 'is halted'}"))


def l2_target(budget, confidence: str):
    """The demand ceiling L2 should fit to.

    Returns None while there is no estimate at all (L2 must stay passive).
    """
    if budget is None:
        return None
    if confidence in ("none", "lower_bound", "provisional"):
        return budget * OVERSUBSCRIBE_CALIBRATING
    return budget


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile over a sorted-or-not list."""
    if not values:
        raise ValueError("percentile of an empty sample")
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return float(s[lo] + (s[hi] - s[lo]) * frac)


def record_day(cur, day: date, pushed: int, completed: int, queue_remaining: int,
               labeled_completed: int = 0) -> None:
    """Persist one day of observation (idempotent per day).

    `labeled_completed` = 完成的复审中**带结果标注**的条数（D8）。它是 L3 的燃料：
    没有它，L3 只剩恒为 0.6 的 decay 数值，等于没有信号（切片 A F1）。
    """
    cur.execute(
        "INSERT INTO attention_observation "
        "(day, pushed, completed, queue_remaining, labeled_completed) "
        "VALUES (%s,%s,%s,%s,%s) "
        "ON CONFLICT (day) DO UPDATE SET pushed=EXCLUDED.pushed, "
        "completed=EXCLUDED.completed, queue_remaining=EXCLUDED.queue_remaining, "
        "labeled_completed=EXCLUDED.labeled_completed",
        (day, pushed, completed, queue_remaining, labeled_completed),
    )


def load_observations(cur, lookback_days: int = LOOKBACK_DAYS) -> list[dict]:
    """Recent observations, windowed relative to the newest row (not `today`).

    Anchoring on `CURRENT_DATE` would silently return nothing for any replayed/backfilled
    history, which is exactly what the simulation does.
    """
    cur.execute(
        "SELECT day, pushed, completed, queue_remaining, labeled_completed "
        "FROM attention_observation "
        "WHERE day > (SELECT COALESCE(MAX(day), CURRENT_DATE) FROM attention_observation) "
        "       - %s::int ORDER BY day",
        (lookback_days,),
    )
    return [
        dict(day=r[0], pushed=r[1], completed=r[2], queue_remaining=r[3],
             labeled_completed=r[4], saturated=r[3] > 0)
        for r in cur.fetchall()
    ]


def estimate_budget(cur, lookback_days: int = LOOKBACK_DAYS) -> dict:
    """Point estimate of daily review capacity from recent observations.

    confidence:
      'observed'    - enough saturated days; estimate ≈ real ceiling.
      'provisional' - some saturated days but too few to trust.
      'lower_bound' - NO saturated day: we only ever saw an emptied queue, so all we know
                      is capacity >= max(completed). Reporting this honestly matters: it is
                      exactly the state in which a naive estimator would silently
                      ratchet the budget down.
      'none'        - warm-up, no data at all; caller must not normalise.
    """
    rows = load_observations(cur, lookback_days)
    if not rows:
        return dict(estimate=None, confidence="none", n_days=0, n_saturated=0,
                    saturated_samples=[], max_completed=0,
                    reason="no observations yet (warm-up): L2 must stay passive")

    saturated = [r for r in rows if r["saturated"]]
    max_completed = max(r["completed"] for r in rows)
    if saturated:
        vals = [float(r["completed"]) for r in saturated]
        est = max(MIN_BUDGET, percentile(vals, SATURATED_QUANTILE))
        confidence = "observed" if len(saturated) >= MIN_SATURATED_SAMPLES else "provisional"
        reason = (f"{len(saturated)} saturated day(s): capacity hit the ceiling at "
                  f"{vals} -> p{int(SATURATED_QUANTILE*100)} = {est:g}")
    else:
        est = max(MIN_BUDGET, float(max_completed))
        confidence = "lower_bound"
        reason = (f"no saturated day: queue always emptied, so capacity >= {max_completed}; "
                  f"this is a LOWER BOUND and must never be used to lower the budget")
    est = min(est, MAX_BUDGET)
    return dict(estimate=round(est, 3), confidence=confidence, n_days=len(rows),
                n_saturated=len(saturated),
                saturated_samples=[r["completed"] for r in saturated],
                max_completed=max_completed, reason=reason)


def update_budget(cur, current=None, lookback_days: int = LOOKBACK_DAYS,
                  guardrail: bool = True) -> dict:
    """Fold the latest observations into the budget, with anti-collapse defences.

    `guardrail=False` disables the monotonic rule (non-saturated days may then lower the
    budget). It exists ONLY so budget_sim.py can demonstrate the collapse it prevents.
    """
    obs = estimate_budget(cur, lookback_days)
    out = dict(old=current, new=current, applied=False, **obs)

    if obs["estimate"] is None:
        out["reason"] += " -> budget unchanged (warm-up)"
        return out

    target = obs["estimate"]
    if current is None:
        out.update(new=round(target, 3), applied=True,
                   reason=obs["reason"] + f" -> bootstrap budget = {target:g}")
        return out

    if target < current and obs["confidence"] == "lower_bound" and guardrail:
        out["reason"] += (" -> guardrail: a lower-bound observation cannot LOWER the budget "
                          "(that is the collapse path)")
        return out

    smoothed = current + EMA_ALPHA * (target - current)
    new = max(current * DOWN_DAMP, min(current * UP_DAMP, smoothed))
    new = max(MIN_BUDGET, min(MAX_BUDGET, new))
    direction = "raised" if new > current else "lowered" if new < current else "held"
    out.update(new=round(new, 3), applied=abs(new - current) > 1e-9,
               reason=f"{obs['reason']} -> EMA {current:g}->{smoothed:.2f}, "
                      f"damped to {new:.2f} ({direction})")
    return out
