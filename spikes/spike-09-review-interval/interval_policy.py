"""Spike 09: automatic `review_interval` assignment (架构 §9 剩余项 ④).

`review_interval` is the proxy for an item's rot rate — "this goes stale in N days".
Setting it automatically is a THREE-LAYER rule, not a single predictor:

  L1 baseline  (individual) : what does the item itself say about how fast it rots?
  L2 budget    (global)     : attention is a HARD budget, so per-item baselines must be
                              normalised globally. Individually optimal != collectively
                              feasible (spike 01: demand = SUM(1 / (0.6 * I_i))).
  L3 feedback  (closed loop): priors are unreliable; the only trustworthy signal is what
                              the reviewer actually found at review time. Multiplicative
                              increase/decrease (AIMD), no ML, fully explainable.

Key design stance (a finding, not a silent choice):
  When the budget cannot be met, this module does NOT silently stretch intervals. It
  stretches low-priority items first, and if even the maximum interval is not enough it
  reports `infeasible=True` with `max_dynamic_items` — i.e. "you must shrink the dynamic
  set (distill/archive, spike 08), otherwise rot is unavoidable". Unbounded stretching
  would be a lie: an interval far beyond an item's real half-life is a decision to let it
  rot, and that decision must be visible.
"""
from __future__ import annotations

import re

import re

from budget_estimator import labeling_rate, MIN_LABEL_RATE
from store import days_to_interval, interval_to_days, new_transform

# --- constants (mirror architecture §6.3 / spike 01) ---------------------------------
ROT_THRESHOLD = 0.9          # decay at/above which the item has already rotted
SURFACE_THRESHOLD = 0.6      # decay at which the item enters attention (effective cadence)
EARLY_THRESHOLD = 0.3        # reviewed while still this fresh -> we reviewed too early

MIN_INTERVAL_DAYS = 1.0
MAX_INTERVAL_DAYS = 180.0

# L1 baseline ladder (days)
BASELINE_SELF_LOOP = 3.0     # 项目躬身入局：变化最快
BASELINE_ORPHAN = 7.0        # 无连接、无 context：默认档
BASELINE_CONNECTED = 14.0    # 有连接或在共享更高维 context：中等
BASELINE_CAPTURED = 28.0     # 价值已升入元认知层：原始记录不必频繁复审

# L2 budget normalisation
BUDGET_EXPAND = 2.0          # 降级一步：interval ×2

# L3 feedback (AIMD)
FEEDBACK_EXPAND = 1.5        # 复审太早 -> 拉长
FEEDBACK_SHRINK = 0.7        # 复审太晚 -> 缩短

# L1 horizon parsing: explicit temporal anchors are the strongest evidence of rot rate.
# Chinese + English, conservative (shortest matched horizon wins).
_HORIZON_RULES = [
    (re.compile(r"今天|今日|今夜|tonight|today"), 1.0),
    (re.compile(r"明天|明日|明早|tomorrow"), 1.0),
    (re.compile(r"后天"), 2.0),
    (re.compile(r"本周|这周|这星期|this week"), 7.0),
    (re.compile(r"下周|下星期|next week"), 7.0),
    (re.compile(r"(\d+)\s*天(内|后|以内|之后)?|in\s+(\d+)\s+days?"), "days"),
    (re.compile(r"(\d+)\s*周(内|后)?|in\s+(\d+)\s+weeks?"), "weeks"),
    (re.compile(r"(\d+)\s*个?月(内|后)?|in\s+(\d+)\s+months?"), "months"),
    (re.compile(r"本月|这个月|this month"), 30.0),
    (re.compile(r"下个?月|next month"), 30.0),
    (re.compile(r"本季度|这季度|this quarter|Q[1-4]"), 90.0),
    (re.compile(r"月底|月末|end of month"), 14.0),
    (re.compile(r"截止|deadline|ddl|DDL|due"), 7.0),
]


def _rule_days(rule, text: str):
    pattern, value = rule
    m = pattern.search(text)
    if not m:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    digits = [g for g in m.groups() if g and g.isdigit()]
    if not digits:
        return None
    n = float(digits[0])
    return n if value == "days" else n * 7.0 if value == "weeks" else n * 30.0


def extract_horizon_days(text: str | None):
    """Shortest explicit temporal horizon found in the text, else None.

    Conservative by construction: several anchors -> take the soonest one, because
    reviewing too early merely costs a little attention, while reviewing too late means
    the item already rotted (spike 01 / PRD §8「宁少勿错」).
    """
    if not text:
        return None
    found = [d for d in (_rule_days(r, text) for r in _HORIZON_RULES) if d]
    return min(found) if found else None


def clamp_days(days: float) -> float:
    return max(MIN_INTERVAL_DAYS, min(MAX_INTERVAL_DAYS, float(days)))


# --- signal reading ------------------------------------------------------------------
_LOAD_SQL = """
SELECT
  n.id,
  n.title,
  n.content,
  n.review_interval,
  n.baseline_interval,
  n.interval_source,
  ( EXISTS(SELECT 1 FROM meta_claim m        WHERE m.evidence_refs @> ARRAY[n.id] LIMIT 1)
    OR EXISTS(SELECT 1 FROM modeling_artifact a WHERE a.evidence_refs @> ARRAY[n.id] LIMIT 1)
  ) AS captured,
  (SELECT count(*) FROM edge e WHERE e.src = n.id OR e.dst = n.id) AS conn_count,
  (SELECT count(*) FROM context_member cm JOIN context c ON c.id = cm.context_id
     WHERE cm.node_id = n.id AND c.scope = 'self_loop')   AS self_loop_count,
  (SELECT count(*) FROM context_member cm JOIN context c ON c.id = cm.context_id
     WHERE cm.node_id = n.id AND c.scope = 'higher_dim')  AS higher_dim_count
FROM node n
WHERE n.track = 'dynamic' AND n.archived_at IS NULL
"""


def load_schedulable(cur) -> list[dict]:
    """Dynamic, non-archived nodes with every signal the rule needs."""
    cur.execute(_LOAD_SQL)
    rows = []
    for r in cur.fetchall():
        (nid, title, content, rev_iv, base_iv, source,
         captured, conn, self_loop, higher_dim) = r
        rows.append(dict(
            id=str(nid), title=title, content=content or "",
            interval=interval_to_days(rev_iv),
            baseline=interval_to_days(base_iv),
            source=source,
            captured=bool(captured),
            conn_count=int(conn),
            self_loop_count=int(self_loop),
            higher_dim_count=int(higher_dim),
        ))
    return rows


def priority(row: dict) -> int:
    """Higher = more urgent to keep its cadence (deferred last under budget pressure)."""
    if extract_horizon_days(f"{row['title']} {row['content']}") is not None:
        return 3                      # 显式时间锚：过期就是真过期
    if row["self_loop_count"] >= 1:
        return 2                      # 项目躬身入局
    if row["higher_dim_count"] >= 1 or row["conn_count"] >= 1:
        return 1                      # 有复用迹象 / 在共享更高维 context
    return 0                          # 孤儿或价值已沉淀


def effective_days(row: dict) -> float:
    return row["interval"] if row["interval"] else (row["baseline"] or BASELINE_ORPHAN)


def daily_demand(rows: list[dict]) -> float:
    """Reviews required per day: each item needs one every SURFACE x I days."""
    return sum(1.0 / (SURFACE_THRESHOLD * effective_days(r)) for r in rows)


# --- L1: individual baseline ----------------------------------------------------------
def baseline_interval(cur, node_id: str) -> dict:
    """Suggest the individual (pre-budget) cadence for one node.

    Returns {days, reason, tier}. days is None for items that do not decay at all
    (static track, already archived) — they must never be given an interval.
    """
    cur.execute(
        "SELECT track, title, content, archived_at FROM node WHERE id = %s::uuid",
        (node_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"node {node_id} not found")
    track, title, content, archived = row

    if track != "dynamic":
        return dict(days=None, reason="static track does not decay", tier="n/a")
    if archived is not None:
        return dict(days=None, reason="already archived", tier="n/a")

    text = f"{title or ''} {content or ''}"
    horizon = extract_horizon_days(text)
    if horizon is not None:
        return dict(days=clamp_days(horizon),
                    reason=f"explicit temporal anchor -> {horizon:g}d horizon",
                    tier="horizon")

    cur.execute(
        """
        SELECT
          ( EXISTS(SELECT 1 FROM meta_claim m        WHERE m.evidence_refs @> ARRAY[%s]::uuid[] LIMIT 1)
            OR EXISTS(SELECT 1 FROM modeling_artifact a WHERE a.evidence_refs @> ARRAY[%s]::uuid[] LIMIT 1)
          ) AS captured,
          (SELECT count(*) FROM context_member cm JOIN context c ON c.id = cm.context_id
             WHERE cm.node_id = %s::uuid AND c.scope = 'self_loop')  AS self_loop_count,
          (SELECT count(*) FROM context_member cm JOIN context c ON c.id = cm.context_id
             WHERE cm.node_id = %s::uuid AND c.scope = 'higher_dim') AS higher_dim_count,
          (SELECT count(*) FROM edge e WHERE e.src = %s::uuid OR e.dst = %s::uuid) AS conn_count
        """,
        (node_id, node_id, node_id, node_id, node_id, node_id),
    )
    captured, self_loop, higher_dim, conn = cur.fetchone()

    if captured:
        return dict(days=BASELINE_CAPTURED,
                    reason="value already lifted to meta layer -> raw record needs less attention",
                    tier="captured")
    if self_loop >= 1:
        return dict(days=BASELINE_SELF_LOOP,
                    reason="member of a self-loop context (active project) -> fastest rot",
                    tier="self_loop")
    if higher_dim >= 1 or conn >= 1:
        return dict(days=BASELINE_CONNECTED,
                    reason="connected / in a shared higher-dim context -> medium rot",
                    tier="connected")
    return dict(days=BASELINE_ORPHAN,
                reason="orphan dynamic item -> default cadence", tier="orphan")


def _audit(cur, node_id, kind, old_days, new_days, reason, produced_by=None) -> None:
    cur.execute(
        "INSERT INTO interval_adjustment "
        "(node_id, kind, old_days, new_days, reason, produced_by) VALUES (%s,%s,%s,%s,%s,%s)",
        (node_id, kind, old_days, new_days, reason, produced_by),
    )


def assign_baselines(cur, produced_by=None) -> list[dict]:
    """Compute + persist L1 baselines for every dynamic node. Skips human overrides."""
    out = []
    cur.execute("SELECT id FROM node WHERE track='dynamic' AND archived_at IS NULL")
    for (nid,) in cur.fetchall():
        nid = str(nid)
        cur.execute("SELECT interval_source, review_interval FROM node WHERE id=%s::uuid",
                    (nid,))
        source, current = cur.fetchone()
        if source == "human":
            out.append(dict(id=nid, days=interval_to_days(current),
                            reason="human override preserved", tier="human", applied=False))
            continue
        sug = baseline_interval(cur, nid)
        if sug["days"] is None:
            continue
        old = interval_to_days(current)
        cur.execute(
            "UPDATE node SET baseline_interval=%s, review_interval=%s, interval_source='auto' "
            "WHERE id=%s::uuid",
            (days_to_interval(sug["days"]), days_to_interval(sug["days"]), nid),
        )
        _audit(cur, nid, "baseline", old, sug["days"], sug["reason"], produced_by)
        out.append(dict(id=nid, applied=True, **sug))
    return out


# --- L2: global budget normalisation ---------------------------------------------------
def fit_budget(cur, budget_per_day: float, transform_id=None) -> dict:
    """Stretch low-priority cadences until the daily review demand fits the budget.

    Honest-degradation contract:
      - human overrides are never touched;
      - stretching stops at MAX_INTERVAL_DAYS (never pretend an item keeps its value);
      - if even the all-MAX configuration exceeds the budget, `infeasible=True` and
        `max_dynamic_items` says how many dynamic items the budget can actually carry —
        the only real remedy is shrinking the dynamic set (spike 08: distill/archive).
    """
    rows = load_schedulable(cur)
    demand = daily_demand(rows)
    report = dict(
        budget=budget_per_day,
        demand_before=round(demand, 6),
        demand_after=round(demand, 6),
        degraded=[],
        infeasible=False,
        max_dynamic_items=(int(budget_per_day * SURFACE_THRESHOLD * MAX_INTERVAL_DAYS)
                           if budget_per_day is not None else None),
        applied=False,
    )
    if budget_per_day is None:
        # Warm-up: no capacity estimate exists yet. Normalising now would fabricate a
        # ceiling out of nothing and, because it shrinks supply, destroy the very signal
        # we need (see budget_estimator). L2 stays passive until real observations exist.
        report["note"] = "no budget estimate yet (warm-up): L2 stays passive"
        return report
    if demand <= budget_per_day:
        return report

    if transform_id is None:
        transform_id = new_transform(
            cur, "budget_fit",
            {"budget_per_day": budget_per_day, "demand_before": report["demand_before"]},
        )
    report["transform_id"] = transform_id

    # defer lowest priority first; within a priority, shortest interval first
    # (halving demand on a 3-day item saves far more attention than on a 28-day one).
    order = sorted(rows, key=lambda r: (priority(r), effective_days(r)))
    for row in order:
        if demand <= budget_per_day:
            break
        if row["source"] == "human":
            continue
        old = effective_days(row)
        new = clamp_days(old * BUDGET_EXPAND)
        if new <= old:              # already at MAX, nothing to gain
            continue
        demand += 1.0 / (SURFACE_THRESHOLD * new) - 1.0 / (SURFACE_THRESHOLD * old)
        cur.execute(
            "UPDATE node SET review_interval=%s, interval_source='auto' WHERE id=%s::uuid",
            (days_to_interval(new), row["id"]),
        )
        _audit(cur, row["id"], "budget", old, new,
               f"attention budget {budget_per_day:g}/day exceeded -> deferred "
               f"(priority={priority(row)})", transform_id)
        report["degraded"].append(dict(id=row["id"], old_days=old, new_days=new,
                                       priority=priority(row)))

    report["demand_after"] = round(demand, 6)
    report["applied"] = bool(report["degraded"])
    report["infeasible"] = demand > budget_per_day
    return report


# --- L3: closed-loop feedback -----------------------------------------------------------
def classify_review(decay_at_review: float) -> str:
    if decay_at_review < EARLY_THRESHOLD:
        return "too_early"
    if decay_at_review >= ROT_THRESHOLD:
        return "too_late"
    return "on_time"


def adapt_interval(cur, node_id: str, decay_at_review: float,
                   outcome: str | None = None, enforce_label_gate: bool = True) -> dict:
    """AIMD correction from what the reviewer actually found.

    too_early (decay < 0.3) -> the cadence is shorter than the item's real rot rate: x1.5
    on_time                 -> no change
    too_late  (decay >= 0.9)-> we only looked after it had already rotted:      x0.7

    LABEL GATE: an explicit `outcome` (or a measured labeling rate >= MIN_LABEL_RATE) is
    required, because the decay number alone carries no information under a scheduler that
    fires at the surface threshold (finding F1). Below the measured rate L3 halts: an
    unlabelled review must never rewrite the cadence. Insufficient evidence does NOT halt
    (otherwise the loop would be frozen during warm-up).
    """
    verdict = outcome or classify_review(decay_at_review)
    cur.execute(
        "SELECT interval_source, review_interval FROM node WHERE id=%s::uuid", (node_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"node {node_id} not found")
    source, current = row
    old = interval_to_days(current)

    if enforce_label_gate and outcome is None:
        gate = labeling_rate(cur)
        if gate["rate"] is not None and gate["rate"] < MIN_LABEL_RATE:
            return dict(id=node_id, old_days=old, new_days=old, verdict=verdict,
                        applied=False,
                        reason=f"label gate closed: {gate['reason']} -> interval unchanged")

    if source == "human":
        return dict(id=node_id, old_days=old, new_days=old, verdict=verdict,
                    applied=False, reason="human override preserved")
    if old is None:
        old = BASELINE_ORPHAN
    factor = {"too_early": FEEDBACK_EXPAND, "on_time": 1.0, "too_late": FEEDBACK_SHRINK}[verdict]
    new = clamp_days(old * factor)
    cur.execute("UPDATE node SET review_interval=%s WHERE id=%s::uuid",
                (days_to_interval(new), node_id))
    _audit(cur, node_id, "feedback", old, new,
           f"review at decay={decay_at_review:.2f} -> {verdict} (x{factor})", None)
    return dict(id=node_id, old_days=old, new_days=new, verdict=verdict,
                applied=abs(new - old) > 1e-9,
                reason=f"{verdict}: x{factor} correction")


# --- rollback (architecture §6.4 C2) ------------------------------------------------------
def revert_transform(cur, transform_id: str) -> int:
    """Undo every interval change produced by one transform, then drop its audit trail.

    Adjustments are replayed newest-first so `old_days` is restored exactly.
    """
    cur.execute(
        "SELECT node_id, old_days FROM interval_adjustment "
        "WHERE produced_by=%s::uuid ORDER BY created_at DESC",
        (transform_id,),
    )
    changes = cur.fetchall()
    for node_id, old_days in changes:
        cur.execute("UPDATE node SET review_interval=%s WHERE id=%s",
                    (days_to_interval(old_days), str(node_id)))
    cur.execute("DELETE FROM transform WHERE id=%s::uuid", (transform_id,))
    return len(changes)
