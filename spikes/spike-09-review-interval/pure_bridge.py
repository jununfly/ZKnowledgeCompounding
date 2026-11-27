"""Process-only public aliases for recording `zkc.scheduling`'s interval math.

Scope
-----
The Rust port takes `f64` through the PyO3 JSON bridge, so integer inputs and
`zkc.tuning`'s integer baseline constants would otherwise be recorded as Python
`int` while the port can only emit floats. This adapter normalizes **only those
bridge encodings**; every decision is delegated verbatim to the Python original.
It is not production code and not a migration target.

Normalizations (encoding seam, not decision behavior)
-----------------------------------------------------
- numeric inputs are cast to `float` before calling the original;
- `baseline_for_signals` converts a non-null `days` result to `float`;
- keyword-only `human` stays keyword-only, matching the original signature.

Recorded horizon vocabulary (delegated, not reimplemented)
-----------------------------------------------------------
The original's `_HORIZON_RULES` searches for these tokens in title + content:

- same-day: 今天 / 今日 / 今夜 / tonight / today
- next-day: 明天 / 明日 / 明早 / tomorrow
- day-after: 后天
- week: 本周 / 这周 / 这星期 / this week / 下周 / 下星期 / next week
- numeric day: 天 with optional 内 / 后 / 以内 / 之后, or `in N days`
- numeric week: 周 with optional 内 / 后, or `in N weeks`
- numeric month: 个月 / 月 with optional 内 / 后, or `in N months`
- month: 本月 / 这个月 / this month / 下月 / 下个月 / next month
- quarter: 本季度 / 这季度 / this quarter / Q1 / Q2 / Q3 / Q4
- month end: 月底 / 月末 / end of month
- deadline: 截止 / deadline / ddl / DDL / due

Several anchors can match one text; the original takes the minimum (earliest
review), dropping zero-length matches. The Rust port records the same tokens
and the same rule order; none is calibrated by this slice.

Decision table under test
-------------------------
1. Non-dynamic track returns days=null with reason "static track does not decay"
   and tier "n/a"; already archived returns "already archived" with tier "n/a".
2. An explicit anchor wins with tier "horizon" and reason spelt as
   "explicit temporal anchor -> <days>d horizon" using Python's `:g` format.
3. L1 signal priority: self_loop (tier "self_loop", reason "self-loop context
   (active project) -> fastest rot") beats captured (tier "captured", reason
   "value lifted to meta layer -> raw needs less attention"), which beats
   connected (tier "connected", reason "connected / shared higher-dim context
   -> medium rot"), which beats orphan (tier "orphan", reason "orphan dynamic
   item -> default cadence").
4. L3 verdicts are "too_early", "on_time" and "too_late". Human override keeps
   the interval unchanged with reason "human override preserved"; otherwise
   AIMD multiplies by 1.5 / 1.0 / 0.7 and clamps to the MIN/MAX interval.
   A too_late verdict clamped at the lower bound sets floor_hit, never silently
   no-op (ADR-0009).
5. L2 `l2_target` oversubscribes by 1.5 for confidence "none", "lower_bound"
   and "provisional"; other confidence strings keep the budget unchanged.
   This function has no production caller and is ported only as math.

Recording contract
------------------
`rust-anything record --count 0 --inputs tmp/scheduling-inputs.jsonl` produced
208 cases: 49 horizon, 14 clamp, 19 baseline, 12 classify, 84 AIMD and 30 L2.
The targeted families include empty / whitespace / unicode anchors, multiple
anchors in one text, zero and huge day counts, NaN / Infinity budgets and old
days, all three verdicts with human true/false, unknown verdict strings (whose
`KeyError` text is part of the oracle), and every L2 confidence branch.

Why the Rust port is longer than this shim
-------------------------------------------
- Python hands regex compilation, `:g` formatting, `repr` and dict construction
  to the standard library; Rust needs explicit helpers for each.
- The bridge cannot pass NaN / Infinity inside a JSON dict, so `json_f64`
  writes the recorder's `$num` marker explicitly.
- Python `min` / `max` comparison order with NaN differs from `f64::min` /
  `f64::max`, so both are hand-written.
- Every tuning-derived constant carries a `recorded-literal` annotation and
  must not be promoted to CALIBRATED here.

Out of scope
------------
`SchedulableNode` / `AttentionObservation` / `Storage` orchestration functions
and `days_to_interval` (timedelta) stay in Python under the bridge boundary.
This slice proves the interval math only, not the production scheduling loop.

Exact baseline reason strings in the recording oracle (verbatim, single line):
"static track does not decay" / "already archived" /
"self-loop context (active project) -> fastest rot" /
"value lifted to meta layer -> raw needs less attention" /
"connected / shared higher-dim context -> medium rot" /
"orphan dynamic item -> default cadence" /
"explicit temporal anchor -> {days}d horizon" /
"human override preserved"

Nothing in this adapter is production code. Deleting it only breaks re-recording
and the kill switch, not the Rust port itself.
"""
from zkc import scheduling as _scheduling


def extract_horizon_days(text):
    return _scheduling.extract_horizon_days(text)


def clamp_days(days):
    return _scheduling.clamp_days(float(days))


def baseline_for_signals(
    track,
    archived,
    title,
    content,
    captured,
    self_loop_count,
    higher_dim_count,
    conn_count,
):
    result = _scheduling.baseline_for_signals(
        track,
        archived,
        title,
        content,
        captured,
        self_loop_count,
        higher_dim_count,
        conn_count,
    )
    if result["days"] is not None:
        result["days"] = float(result["days"])
    return result


def classify_review(decay_at_review):
    return _scheduling.classify_review(float(decay_at_review))


def adapt_interval_math(old_days, verdict, *, human=False):
    return _scheduling.adapt_interval_math(float(old_days), verdict, human=human)


def l2_target(budget, confidence):
    if budget is None:
        return None
    return _scheduling.l2_target(float(budget), confidence)
