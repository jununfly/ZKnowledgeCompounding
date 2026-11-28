//! The Rust port of `spikes/spike-21-percentile/pure_bridge.py`.
//!
//! `_percentile(values, q)` is the L2 budget-percentile math from
//! `src/zkc/scheduling.py`: sort a copy, return the single element for len==1,
//! otherwise linearly interpolate at `pos = q * (len-1)` using `int` truncation.
//! No tuning globals, no dataclass/Storage seam — all inputs are scalars/lists.

#![forbid(unsafe_code)]

use serde_json::Value;

/// Decode a recorded number: a plain JSON number, or a `{"$float": "..."}` /
/// `{"$int": "..."}` marker emitted by the Python recording bridge.
fn as_f64(v: &Value) -> Option<f64> {
    match v {
        Value::Number(n) => n.as_f64(),
        Value::Bool(b) => Some(if *b { 1.0 } else { 0.0 }),
        Value::Object(o) if o.len() == 1 => {
            let (k, inner) = o.iter().next()?;
            if matches!(k.as_str(), "$float" | "$int") {
                inner.as_str()?.parse::<f64>().ok()
            } else {
                None
            }
        }
        _ => None,
    }
}

/// Port of `percentile` (`spikes/spike-21-percentile/pure_bridge.py:34`,
/// original `src/zkc/scheduling.py::_percentile`).
pub fn percentile(values: Value, q: Value) -> Result<Value, String> {
    let arr = values
        .as_array()
        .ok_or_else(|| "TypeError: 'float' object is not iterable".to_string())?;
    let mut sorted: Vec<f64> = arr
        .iter()
        .map(as_f64)
        .collect::<Option<Vec<f64>>>()
        .ok_or_else(|| "TypeError: unsupported operand type".to_string())?;
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

    let n = sorted.len();
    if n == 1 {
        return Ok(Value::from(sorted[0]));
    }
    // Python raises IndexError on s[0] for an empty list (reached before any
    // interpolation): `pos = q*(0-1)`, `lo=int(pos)`, then `s[lo]` / `s[hi]`.
    if n == 0 {
        return Err("IndexError: list index out of range".to_string());
    }

    let q = as_f64(&q).ok_or_else(|| "TypeError: unsupported operand type".to_string())?;
    let pos = q * ((n - 1) as f64);
    // Python `int(pos)` truncates toward zero; Rust `as i64` does the same.
    let lo = pos as i64;
    let hi = (lo + 1).min((n - 1) as i64);
    let frac = pos - lo as f64;
    // Negative/out-of-range q can drive lo/hi negative; Python's s[lo] then
    // indexes from the end. Recorded out-of-range cases stay in [-(n), n-1].
    let pick = |i: i64| -> Option<f64> {
        let idx = if i < 0 { n as i64 + i } else { i };
        if idx >= 0 && idx < n as i64 {
            Some(sorted[idx as usize])
        } else {
            None
        }
    };
    let a = pick(lo).ok_or_else(|| "IndexError: list index out of range".to_string())?;
    let b = pick(hi).ok_or_else(|| "IndexError: list index out of range".to_string())?;
    Ok(Value::from(a + (b - a) * frac))
}
