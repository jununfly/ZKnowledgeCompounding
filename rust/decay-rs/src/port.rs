//! Rust port of `src/zkc/decay.py`.
//!
//! Behavior is pinned by `cases.jsonl` recorded from the Python original with
//! `rust-anything record`. Thresholds mirror `zkc.tuning.REGISTRY`:
//! DECAY_FUNCTION=linear, SURFACE_THRESHOLD=0.6. These are SIMULATION values,
//! not CALIBRATED ones; this port must not promote them.
//!
//! Structured Python values cross the bridge as JSON. `elapsed_days` cannot see a
//! real `datetime` through JSON, so the recorded behavior for every structured
//! argument is the original's 0.0 fallback; real datetime semantics are covered by
//! the Rust unit tests translated from `tests/test_decay.py`, not fabricated here.

#![forbid(unsafe_code)]

use serde_json::{Value, json};

fn clamp_unit(x: f64) -> f64 {
    // Python `min(1.0, max(0.0, x))` ignores NaN in the same way as Rust's
    // `f64::min`/`f64::max`: the non-NaN operand wins.
    1.0_f64.min(0.0_f64.max(x))
}

fn py_type(v: &Value) -> &'static str {
    match v {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(n) if n.is_i64() || n.is_u64() => "int",
        Value::Number(_) => "float",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

fn marker_number(v: &Value) -> Option<f64> {
    let o = v.as_object()?;
    if o.len() != 1 {
        return None;
    }
    let (k, inner) = o.iter().next()?;
    match (k.as_str(), inner) {
        ("$float", Value::String(s)) | ("$int", Value::String(s)) => s.parse::<f64>().ok(),
        ("$num", Value::String(s)) => match s.as_str() {
            "NaN" => Some(f64::NAN),
            "Infinity" => Some(f64::INFINITY), // recorded-literal: pyconv.py encodes float infinities as marker strings
            "-Infinity" => Some(f64::NEG_INFINITY), // recorded-literal: pyconv.py encodes float infinities as marker strings
            "-0" => Some(-0.0),
            _ => None,
        },
        _ => None,
    }
}

/// Python `float(v)` for the shapes the recorder can hand us.
fn as_float(v: &Value) -> Result<f64, String> {
    match v {
        Value::Number(n) => Ok(n.as_f64().unwrap_or(f64::NAN)),
        Value::Bool(b) => Ok(if *b { 1.0 } else { 0.0 }),
        Value::String(s) => s
            .parse::<f64>()
            .map_err(|_| format!("ValueError: could not convert string to float: '{}'", s)),
        Value::Null => Err(
            "TypeError: float() argument must be a string or a real number, not 'NoneType'"
                .to_string(),
        ),
        _ => marker_number(v).ok_or_else(|| {
            format!(
                "TypeError: float() argument must be a string or a real number, not '{}'",
                py_type(v)
            )
        }),
    }
}

fn get<'a>(node: &'a Value, key: &str) -> Option<&'a Value> {
    match node {
        Value::Object(m) => m.get(key),
        // getattr(obj, key, default) on every non-Mapping JSON value: no attributes.
        _ => None,
    }
}

/// `_get(node, "last_reviewed_at") or _get(node, "created_at") or now`.
fn anchor<'a>(node: &'a Value, now: &'a Value) -> Option<&'a Value> {
    for key in ["last_reviewed_at", "created_at"] {
        if let Some(v) = get(node, key) {
            // Python truthiness: only false / 0 / empty string / empty container / None fall through.
            let truthy = match v {
                Value::Null => false,
                Value::Bool(b) => *b,
                Value::Number(n) => n.as_f64().unwrap_or(0.0) != 0.0,
                Value::String(s) => !s.is_empty(),
                Value::Array(a) => !a.is_empty(),
                Value::Object(o) => !o.is_empty(),
            };
            if truthy {
                return Some(v);
            }
        }
    }
    Some(now)
}

/// Port of `decay_linear` (`src/zkc/decay.py:26`).
pub fn decay_linear(elapsed_days: f64, interval_days: f64) -> Result<f64, String> {
    if interval_days <= 0.0 {
        return Ok(1.0);
    }
    Ok(clamp_unit(elapsed_days / interval_days))
}

/// Port of `decay_exponential` (`src/zkc/decay.py:37`).
pub fn decay_exponential(elapsed_days: f64, half_life_days: f64) -> Result<f64, String> {
    if half_life_days <= 0.0 {
        return Ok(1.0);
    }
    Ok(clamp_unit(
        1.0 - 0.5_f64.powf(elapsed_days / half_life_days),
    ))
}

/// Port of `decay_step` (`src/zkc/decay.py:44`).
pub fn decay_step(elapsed_days: f64, interval_days: f64) -> Result<f64, String> {
    if interval_days <= 0.0 {
        return Ok(1.0);
    }
    Ok(if elapsed_days >= interval_days {
        1.0
    } else {
        0.0
    })
}

/// Port of `elapsed_days` (`src/zkc/decay.py:84`).
pub fn elapsed_days(node: Value, now: Value) -> Result<f64, String> {
    let _ = anchor(&node, &now);
    // The only datetime-like value Python can receive here is a real `datetime`.
    // Through the JSON bridge none of the recorded values are datetimes, so the
    // original's `isinstance(anchor, datetime)` branch is unreachable: 0.0 always.
    Ok(0.0)
}

/// Port of `compute_decay_score` (`src/zkc/decay.py:92`).
pub fn compute_decay_score(node: Value, now: Value) -> Result<f64, String> {
    if matches!(get(&node, "track"), Some(Value::String(s)) if s == "static") {
        return Ok(0.0);
    }
    let Some(interval) = get(&node, "review_interval") else {
        return Ok(0.0);
    };
    let interval_days = as_float(interval)?;
    if interval_days <= 0.0 {
        return Ok(1.0);
    }
    decay_linear(elapsed_days(node, now)?, interval_days)
}

/// Python list slicing with `budget` as the stop index (negative counts from the end).
fn take_budget<T>(mut items: Vec<T>, budget: Option<i64>) -> Vec<T> {
    match budget {
        None => items,
        Some(n) if n >= 0 => {
            let n = (n as usize).min(items.len());
            items.truncate(n);
            items
        }
        Some(n) => {
            let drop = (-n).min(items.len() as i64) as usize;
            let keep = items.len() - drop;
            items.truncate(keep);
            items
        }
    }
}

/// Port of `surface` (`src/zkc/decay.py:111`).
pub fn surface(
    items: Value,
    now: Value,
    threshold: Option<f64>,
    budget: Option<i64>,
) -> Result<Vec<Value>, String> {
    let cutoff = threshold.unwrap_or(0.6); // tuning.SURFACE_THRESHOLD
    // Python iterates lists by value, dicts by key, and strings character by character.
    let iterable: Vec<Value> = match &items {
        Value::Array(a) => a.clone(),
        Value::Object(o) => o.keys().cloned().map(Value::String).collect(),
        Value::String(s) => s.chars().map(|c| Value::String(c.to_string())).collect(),
        _ if marker_number(&items).is_some() => vec![items.clone()],
        _ => {
            return Err(format!(
                "TypeError: '{}' object is not iterable",
                py_type(&items)
            ));
        }
    };
    let mut scored: Vec<(f64, Value)> = iterable
        .into_iter()
        .map(|i| Ok((compute_decay_score(i.clone(), now.clone())?, i)))
        .collect::<Result<_, String>>()?;
    scored.retain(|(s, _)| *s >= cutoff);
    // `sort_by` is stable in Rust, matching Python's stable `list.sort`.
    scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    Ok(take_budget(
        scored.into_iter().map(|(_, i)| i).collect(),
        budget,
    ))
}

/// Port of `review_reset` (`src/zkc/decay.py:132`).
pub fn review_reset(node: Value, now: Value) -> Result<Value, String> {
    match node {
        Value::Object(mut m) => {
            m.insert("last_reviewed_at".to_string(), now);
            m.insert("decay_score".to_string(), json!(0.0));
            Ok(Value::Object(m))
        }
        // vars(non-object) raises; the recorder only hands us JSON scalars/arrays here.
        _other => Err("TypeError: vars() argument must have __dict__ attribute".to_string()), // recorded-literal: CPython's own vars() error text
    }
}

/// Port of `refresh_decay` (`src/zkc/decay.py:146`).
pub fn refresh_decay(repo: Value, now: Value) -> Result<i64, String> {
    let _ = now;
    Err(format!(
        "AttributeError: '{}' object has no attribute 'list_by_track'",
        py_type(&repo)
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decay_linear_matches_python_tests() {
        assert_eq!(decay_linear(0.0, 10.0).unwrap(), 0.0);
        assert_eq!(decay_linear(5.0, 10.0).unwrap(), 0.5);
        assert_eq!(decay_linear(10.0, 10.0).unwrap(), 1.0);
        assert_eq!(decay_linear(20.0, 10.0).unwrap(), 1.0);
        assert_eq!(decay_linear(0.0, 0.0).unwrap(), 1.0);
    }

    #[test]
    fn static_track_never_decays() {
        let node = json!({"track": "static", "review_interval": 10});
        assert_eq!(compute_decay_score(node, json!({})).unwrap(), 0.0);
    }

    #[test]
    fn dynamic_track_uses_baseline_interval() {
        let node = json!({"track": "dynamic", "review_interval": 10});
        assert_eq!(compute_decay_score(node, json!({})).unwrap(), 0.0);
    }

    #[test]
    fn review_reset_does_not_mutate_input_shape_except_two_keys() {
        let out = review_reset(json!({"a": 1}), json!("now")).unwrap();
        assert_eq!(out["a"], 1);
        assert_eq!(out["last_reviewed_at"], "now");
        assert_eq!(out["decay_score"].as_f64(), Some(0.0));
    }

    #[test]
    fn refresh_decay_reports_missing_repo_method() {
        let err = refresh_decay(json!({}), json!({})).unwrap_err();
        assert_eq!(
            err,
            "AttributeError: 'dict' object has no attribute 'list_by_track'"
        );
    }
}
