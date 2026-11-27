"""Process-only public alias for recording `zkc.cross_source.judge_r14`.

Scope
-----
The Rust port takes JSON-native inputs (a list of report dicts plus a min_runs
int) through the PyO3 bridge. This adapter exposes the single deterministic R14
aggregation function. Every decision is delegated verbatim to the Python
original; the adapter only crosses two encoding seams the bridge cannot handle.

Alias map (encoding seam, not decision behavior)
------------------------------------------------
- `judge_r14(runs, min_runs)` -> `zkc.cross_source.judge_r14(runs, min_runs=min_runs)`
  * `min_runs` is keyword-only in Python; the alias exposes it as a plain second
    positional argument and restores the keyword when delegating (same pattern
    as scheduling spike-09's `human=` normalization).
  * the returned `R14Verdict` is a plain dataclass that PyO3 `_enc` cannot encode
    (it would fall back to `$repr`); the alias encodes it to a field-fixed dict.
    total/fired/trigger_rate/medians/should_close_completion/reason and all
    threshold decisions stay the original's.

Recorded vocabulary (delegated, not reimplemented)
--------------------------------------------------
`judge_r14` counts fired runs, computes trigger_rate and the medians of main /
completion latencies (`statistics.median`: odd -> middle, even -> mean of two),
then returns one of six reason branches. Data below min_runs or with no
completion latency never fabricates a close decision. Thresholds 0.5 / 1.5 and
min_runs default 10 come from risks.md R14, not tuning calibration.

Production boundary
-------------------
This slice proves literal aggregation behavior only. It does not produce real
run data (that stays with zj's dogfood + `r14_telemetry` file IO), does not
trigger any completion shutdown, and does not turn recorded-literal thresholds
into CALIBRATED values. `combine`/`apply_combine` (LLM + Storage) and
`r14_telemetry` stay in Python.

Nothing in this adapter is production code. Deleting it only breaks re-recording
and the kill switch, not the Rust port itself.
"""
from zkc import cross_source as _cross_source


def _encode_verdict(v):
    return {
        "total": v.total,
        "fired": v.fired,
        "trigger_rate": v.trigger_rate,
        "completion_latency_median": v.completion_latency_median,
        "main_latency_median": v.main_latency_median,
        "should_close_completion": v.should_close_completion,
        "reason": v.reason,
    }


def judge_r14(runs, min_runs):
    return _encode_verdict(_cross_source.judge_r14(runs, min_runs=min_runs))
