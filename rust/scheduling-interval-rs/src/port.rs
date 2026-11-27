//! Rust port of `src/zkc/scheduling.py` — the pure interval-math slice.
//!
//! Proof boundary: `cases.jsonl` was recorded from the Python original (6 public
//! functions, no Storage / dataclass / timedelta inputs). Everything that eats
//! `SchedulableNode`, `AttentionObservation` or `Storage` stays in Python, as does
//! `days_to_interval` (returns `timedelta`). See `finding-interval-math-boundary.md`.
//!
//! Every numeric constant below is a recorded literal from `zkc.tuning` or the
//! horizon rules; none is promoted to CALIBRATED by this port.

#![forbid(unsafe_code)]

use regex::Regex;
use serde_json::{Value, json};

// tuning.py values at recording time. `MIN_INTERVAL_DAYS` is the only CALIBRATED
// one, via zj's manual override; the rest are placeholder / SIMULATION.
const MIN_INTERVAL_DAYS: f64 = 0.25; // recorded-literal: tuning.py MIN_INTERVAL_DAYS (CALIB_OVERRIDE_AT)
const MAX_INTERVAL_DAYS: f64 = 180.0; // recorded-literal: tuning.py MAX_INTERVAL_DAYS (SIMULATION)
const BASELINE_SELF_LOOP_DAYS: f64 = 3.0; // recorded-literal: tuning.py BASELINE_SELF_LOOP_DAYS
const BASELINE_CAPTURED_DAYS: f64 = 28.0; // recorded-literal: tuning.py BASELINE_CAPTURED_DAYS
const BASELINE_CONNECTED_DAYS: f64 = 14.0; // recorded-literal: tuning.py BASELINE_CONNECTED_DAYS
const BASELINE_ORPHAN_DAYS: f64 = 7.0; // recorded-literal: tuning.py BASELINE_ORPHAN_DAYS
const EARLY_THRESHOLD: f64 = 0.3; // recorded-literal: tuning.py EARLY_THRESHOLD
const ROT_THRESHOLD: f64 = 0.9; // recorded-literal: tuning.py ROT_THRESHOLD (SIMULATION)
const AIMD_UP: f64 = 1.5; // recorded-literal: tuning.py AIMD_UP
const AIMD_DOWN: f64 = 0.7; // recorded-literal: tuning.py AIMD_DOWN
const OVERSUBSCRIBE_FACTOR: f64 = 1.5; // recorded-literal: tuning.py OVERSUBSCRIBE_FACTOR (SIMULATION)
const EPS: f64 = 1e-9; // recorded-literal: scheduling.py adapt_interval_math epsilon

// _HORIZON_RULES numeric values.
const HORIZON_TODAY: f64 = 1.0; // recorded-literal: scheduling.py today/tomorrow rule
const HORIZON_AFTER_TOMORROW: f64 = 2.0; // recorded-literal: scheduling.py 后天 rule
const HORIZON_WEEK: f64 = 7.0; // recorded-literal: scheduling.py week rule
const HORIZON_MONTH_DAYS: f64 = 30.0; // recorded-literal: scheduling.py month rule
const HORIZON_QUARTER: f64 = 90.0; // recorded-literal: scheduling.py quarter rule
const HORIZON_MONTH_END: f64 = 14.0; // recorded-literal: scheduling.py month-end rule
const HORIZON_DEADLINE: f64 = 7.0; // recorded-literal: scheduling.py deadline rule

/// Python `min(a, b)` / `max(a, b)` comparison order matters with NaN; `f64::min`
/// and `f64::max` do not reproduce it.
fn py_min(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

fn py_max(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}

/// Python `str(float)` for the values this port can produce.
fn py_float_str(x: f64) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf" } else { "-inf" }.to_string();
    }
    let rendered = format!("{x}");
    if rendered.contains('.') || rendered.contains('e') {
        rendered
    } else {
        format!("{rendered}.0")
    }
}

/// JSON encoding for an `f64` nested in a dict: the recorder marks non-finite
/// values with `$num`, while the generated `ToPy` wrapper decodes them back.
fn json_f64(x: f64) -> Value {
    if x.is_nan() {
        return json!({ "$num": "NaN" });
    }
    if x == f64::INFINITY {
        return json!({ "$num": "Infinity" });
    }
    if x == f64::NEG_INFINITY {
        return json!({ "$num": "-Infinity" });
    }
    json!(x)
}

/// Python's `:g` format, reused from `rust/expiry-pure-rs/src/port.rs`.
fn py_g(x: f64) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf" } else { "-inf" }.to_string();
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0" } else { "0" }.to_string();
    }
    let exp = x.abs().log10().floor() as i32;
    if !(-4..6).contains(&exp) {
        let sci = format!("{x:.5e}");
        let (mant, exponent) = sci.split_once('e').unwrap_or((&sci, "0"));
        let mant = mant.trim_end_matches('0').trim_end_matches('.');
        let e: i32 = exponent.parse().unwrap_or(0);
        format!("{}e{}{:02}", mant, if e < 0 { '-' } else { '+' }, e.abs())
    } else {
        let decimals = (5 - exp).max(0) as usize;
        let fixed = format!("{:.*}", decimals, x);
        if fixed.contains('.') {
            fixed
                .trim_end_matches('0')
                .trim_end_matches('.')
                .to_string()
        } else {
            fixed
        }
    }
}

/// Python `repr(str)` for the short verdict strings recorded here.
fn py_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::new();
    out.push(quote);
    for ch in text.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\u{feff}' => out.push_str("\\ufeff"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if c.is_control() => out.push_str(&format!("\\x{:02x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

/// First digit group that Python's `m.groups()` filter would accept.
fn first_digits(caps: &regex::Captures<'_>) -> Option<f64> {
    [1usize, 3]
        .iter()
        .filter_map(|i| caps.get(*i))
        .find_map(|m| {
            let raw = m.as_str();
            if !raw.is_empty() && raw.chars().all(|c| c.is_ascii_digit()) {
                raw.parse::<f64>().ok()
            } else {
                None
            }
        })
}

/// Port of `extract_horizon_days` (`src/zkc/scheduling.py:65`).
pub fn extract_horizon_days(text: Option<String>) -> Result<Option<f64>, String> {
    let Some(text) = text else {
        return Ok(None);
    };
    if text.is_empty() {
        return Ok(None);
    }
    let literal_rules: &[(&str, f64)] = &[
        ("今天", HORIZON_TODAY),
        ("今日", HORIZON_TODAY),
        ("今夜", HORIZON_TODAY),
        ("tonight", HORIZON_TODAY),
        ("today", HORIZON_TODAY),
        ("明天", HORIZON_TODAY),
        ("明日", HORIZON_TODAY),
        ("明早", HORIZON_TODAY),
        ("tomorrow", HORIZON_TODAY),
        ("后天", HORIZON_AFTER_TOMORROW),
        ("本周", HORIZON_WEEK),
        ("这周", HORIZON_WEEK),
        ("这星期", HORIZON_WEEK),
        ("this week", HORIZON_WEEK),
        ("下周", HORIZON_WEEK),
        ("下星期", HORIZON_WEEK),
        ("next week", HORIZON_WEEK),
        ("本月", HORIZON_MONTH_DAYS),
        ("这个月", HORIZON_MONTH_DAYS),
        ("this month", HORIZON_MONTH_DAYS),
        ("下月", HORIZON_MONTH_DAYS),
        ("下个月", HORIZON_MONTH_DAYS),
        ("next month", HORIZON_MONTH_DAYS),
        ("本季度", HORIZON_QUARTER),
        ("这季度", HORIZON_QUARTER),
        ("this quarter", HORIZON_QUARTER),
        ("月底", HORIZON_MONTH_END),
        ("月末", HORIZON_MONTH_END),
        ("end of month", HORIZON_MONTH_END),
        ("截止", HORIZON_DEADLINE),
        ("deadline", HORIZON_DEADLINE),
        ("ddl", HORIZON_DEADLINE),
        ("DDL", HORIZON_DEADLINE),
        ("due", HORIZON_DEADLINE),
    ];
    let mut found: Vec<f64> = literal_rules
        .iter()
        .filter(|(needle, _)| text.contains(*needle))
        .map(|(_, value)| *value)
        .collect();
    for q in 1..=4 {
        if text.contains(&format!("Q{q}")) {
            found.push(HORIZON_QUARTER); // recorded-literal: scheduling.py Q[1-4]
        }
    }
    let days_re = Regex::new(r"(\d+)\s*天(内|后|以内|之后)?|in\s+(\d+)\s+days?")
        .map_err(|e| format!("ValueError: {e}"))?;
    if let Some(caps) = days_re.captures(&text)
        && let Some(n) = first_digits(&caps)
    {
        found.push(n);
    }
    let weeks_re = Regex::new(r"(\d+)\s*周(内|后)?|in\s+(\d+)\s+weeks?")
        .map_err(|e| format!("ValueError: {e}"))?;
    if let Some(caps) = weeks_re.captures(&text)
        && let Some(n) = first_digits(&caps)
    {
        found.push(n * HORIZON_WEEK);
    }
    let months_re = Regex::new(r"(\d+)\s*个?月(内|后)?|in\s+(\d+)\s+months?")
        .map_err(|e| format!("ValueError: {e}"))?;
    if let Some(caps) = months_re.captures(&text)
        && let Some(n) = first_digits(&caps)
    {
        found.push(n * HORIZON_MONTH_DAYS);
    }
    // Python filters `if d`, which drops 0.0 and -0.0.
    found.retain(|d| *d != 0.0);
    Ok(found
        .into_iter()
        .fold(None, |acc, d| Some(acc.map_or(d, |a: f64| py_min(a, d)))))
}

/// Port of `clamp_days` (`src/zkc/scheduling.py:77`).
pub fn clamp_days(days: f64) -> Result<f64, String> {
    Ok(py_max(MIN_INTERVAL_DAYS, py_min(MAX_INTERVAL_DAYS, days)))
}

/// Port of `baseline_for_signals` (`src/zkc/scheduling.py:83`).
pub fn baseline_for_signals(
    track: String,
    archived: bool,
    title: String,
    content: Option<String>,
    captured: bool,
    self_loop_count: i64,
    higher_dim_count: i64,
    conn_count: i64,
) -> Result<Value, String> {
    if track != "dynamic" {
        return Ok(json!({
            "days": Value::Null,
            "reason": "static track does not decay",
            "tier": "n/a",
        }));
    }
    if archived {
        return Ok(json!({
            "days": Value::Null,
            "reason": "already archived",
            "tier": "n/a",
        }));
    }
    let text = format!("{} {}", title, content.unwrap_or_default());
    if let Some(horizon) = extract_horizon_days(Some(text))? {
        return Ok(json!({
            "days": json_f64(clamp_days(horizon)?),
            "reason": format!("explicit temporal anchor -> {}d horizon", py_g(horizon)),
            "tier": "horizon",
        }));
    }
    if self_loop_count >= 1 {
        return Ok(json!({
            "days": json_f64(BASELINE_SELF_LOOP_DAYS),
            "reason": "self-loop context (active project) -> fastest rot",
            "tier": "self_loop",
        }));
    }
    if captured {
        return Ok(json!({
            "days": json_f64(BASELINE_CAPTURED_DAYS),
            "reason": "value lifted to meta layer -> raw needs less attention",
            "tier": "captured",
        }));
    }
    if higher_dim_count >= 1 || conn_count >= 1 {
        return Ok(json!({
            "days": json_f64(BASELINE_CONNECTED_DAYS),
            "reason": "connected / shared higher-dim context -> medium rot",
            "tier": "connected",
        }));
    }
    Ok(json!({
        "days": json_f64(BASELINE_ORPHAN_DAYS),
        "reason": "orphan dynamic item -> default cadence",
        "tier": "orphan",
    }))
}

/// Port of `classify_review` (`src/zkc/scheduling.py:212`).
pub fn classify_review(decay_at_review: f64) -> Result<String, String> {
    if decay_at_review < EARLY_THRESHOLD {
        Ok("too_early".to_string())
    } else if decay_at_review >= ROT_THRESHOLD {
        Ok("too_late".to_string())
    } else {
        Ok("on_time".to_string())
    }
}

/// Port of `adapt_interval_math` (`src/zkc/scheduling.py:224`).
pub fn adapt_interval_math(old_days: f64, verdict: String, human: bool) -> Result<Value, String> {
    if human {
        return Ok(json!({
            "old_days": json_f64(old_days),
            "new_days": json_f64(old_days),
            "verdict": verdict,
            "applied": false,
            "reason": "human override preserved",
            "floor_hit": false,
        }));
    }
    let factor = match verdict.as_str() {
        "too_early" => AIMD_UP,
        "on_time" => 1.0, // recorded-literal: scheduling.py _aimd_factor on_time
        "too_late" => AIMD_DOWN,
        _ => return Err(format!("KeyError: {}", py_repr(&verdict))),
    };
    let new = clamp_days(old_days * factor)?;
    let applied = (new - old_days).abs() > EPS;
    let floor_hit = verdict == "too_late" && !applied && old_days <= MIN_INTERVAL_DAYS + EPS;
    Ok(json!({
        "old_days": json_f64(old_days),
        "new_days": json_f64(new),
        "verdict": verdict,
        "applied": applied,
        "reason": format!("{}: x{} correction", verdict, py_float_str(factor)),
        "floor_hit": floor_hit,
    }))
}

/// Port of `l2_target` (`src/zkc/scheduling.py:369`).
pub fn l2_target(budget: Option<f64>, confidence: String) -> Result<Option<f64>, String> {
    let Some(budget) = budget else {
        return Ok(None);
    };
    if matches!(confidence.as_str(), "none" | "lower_bound" | "provisional") {
        Ok(Some(budget * OVERSUBSCRIBE_FACTOR))
    } else {
        Ok(Some(budget))
    }
}
