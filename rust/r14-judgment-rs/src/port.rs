//! The Rust port of `spikes/spike-18-r14-judgment/pure_bridge.py`.
//!
//! `judge_r14` aggregates a list of cross-source completion run reports into the
//! R14 verdict. Every decision below mirrors `src/zkc/cross_source.py::judge_r14`
//! verbatim; thresholds are recorded literals from risks.md R14, not calibrated
//! tuning values. The Python alias only crosses two encoding seams (min_runs
//! keyword-only -> positional, R14Verdict dataclass -> fixed-key dict).

#![forbid(unsafe_code)]

use serde_json::{Map, Value, json};

// R14 判据阈值，来自 risks.md R14 / 架构 §8，经录制 case 固化，非 tuning 校准值。
const TRIGGER_RATE_THRESHOLD: f64 = 0.5; // recorded-literal: risks.md R14 trigger rate > 0.5
const LATENCY_FACTOR: f64 = 1.5; // recorded-literal: risks.md R14 completion median > main median * 1.5
const MIN_RUNS_DEFAULT: i64 = 10; // recorded-literal: cross_source.py R14_MIN_RUNS_DEFAULT=10

/// Python truthiness for `r.get("completion_fired")` (bool / int 0-1 / str in recorded cases).
fn py_truthy(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) | Some(Value::Bool(false)) => false,
        Some(Value::Bool(true)) => true,
        Some(Value::Number(n)) => n.as_f64().is_none_or(|v| v != 0.0),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

/// `float(v)` for latency values that reach the list comprehensions. Recorded inputs
/// are JSON numbers or numeric strings; None fields were already filtered out.
fn py_float(value: &Value) -> Result<f64, String> {
    match value {
        Value::Number(n) => n
            .as_f64()
            .ok_or_else(|| "ValueError: invalid number".to_string()),
        Value::String(s) => s
            .trim()
            .parse::<f64>()
            .map_err(|_| format!("ValueError: could not convert string to float: '{s}'")),
        Value::Bool(b) => Ok(if *b { 1.0 } else { 0.0 }),
        _ => Err("TypeError: float() argument must be a string or a real number".to_string()),
    }
}

/// Python `statistics.median`: sort ascending, odd -> middle, even -> mean of the two middle.
fn statistics_median(mut values: Vec<f64>) -> f64 {
    values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let n = values.len();
    if n % 2 == 1 {
        values[n / 2]
    } else {
        (values[n / 2 - 1] + values[n / 2]) / 2.0
    }
}

/// Port of `judge_r14` (`spikes/spike-18-r14-judgment/pure_bridge.py`).
pub fn judge_r14(
    runs: serde_json::Value,
    min_runs: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let runs = runs
        .as_array()
        .ok_or_else(|| "TypeError: runs must be a list".to_string())?;
    let min_runs = match &min_runs {
        Value::Number(n) => n.as_i64().unwrap_or(MIN_RUNS_DEFAULT),
        _ => MIN_RUNS_DEFAULT,
    };

    let total = runs.len();
    let fired = runs
        .iter()
        .filter(|r| py_truthy(r.get("completion_fired")))
        .count();
    let trigger_rate = if total == 0 {
        0.0
    } else {
        fired as f64 / total as f64
    };

    let main_latencies = runs
        .iter()
        .filter_map(|r| r.get("main_latency_ms"))
        .filter(|v| !v.is_null())
        .map(py_float)
        .collect::<Result<Vec<f64>, String>>()?;
    let completion_latencies = runs
        .iter()
        .filter_map(|r| r.get("completion_latency_ms"))
        .filter(|v| !v.is_null())
        .map(py_float)
        .collect::<Result<Vec<f64>, String>>()?;

    let main_latency_median = if main_latencies.is_empty() {
        0.0
    } else {
        statistics_median(main_latencies)
    };
    let completion_latency_median = if completion_latencies.is_empty() {
        None
    } else {
        Some(statistics_median(completion_latencies))
    };

    let (should_close, reason) = if total < min_runs as usize {
        (false, "insufficient_data") // recorded-literal: cross_source.py R14 reason branch
    } else if fired == 0 {
        (false, "no_completion_fired") // recorded-literal: cross_source.py R14 reason branch
    } else if trigger_rate > TRIGGER_RATE_THRESHOLD
        && completion_latency_median.is_some_and(|m| m > main_latency_median * LATENCY_FACTOR)
    {
        (true, "trigger_rate_and_latency_exceed_budget") // recorded-literal: cross_source.py R14 reason branch
    } else if trigger_rate <= TRIGGER_RATE_THRESHOLD {
        (false, "trigger_rate_within_budget") // recorded-literal: cross_source.py R14 reason branch
    } else {
        (false, "completion_latency_within_budget") // recorded-literal: cross_source.py R14 reason branch
    };

    let mut verdict = Map::new();
    verdict.insert("total".to_string(), json!(total));
    verdict.insert("fired".to_string(), json!(fired));
    verdict.insert("trigger_rate".to_string(), json!(trigger_rate));
    verdict.insert(
        "completion_latency_median".to_string(),
        completion_latency_median.map_or(Value::Null, |m| json!(m)),
    );
    verdict.insert(
        "main_latency_median".to_string(),
        json!(main_latency_median),
    );
    verdict.insert("should_close_completion".to_string(), json!(should_close));
    verdict.insert("reason".to_string(), json!(reason));
    Ok(Value::Object(verdict))
}
