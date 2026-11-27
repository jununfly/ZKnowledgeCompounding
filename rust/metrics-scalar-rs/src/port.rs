//! Rust port of `src/zkc/metrics.py` (behavioral slice: `compounding_factor`).
/*!
 * Behavior is pinned by `cases.jsonl` recorded from the Python original with
 * `rust-anything record`. The recordable slice is the scalar pure-function layer:
 * `compounding_factor` takes only JSON scalars, so every valid recorded case
 * (incl. NaN / Infinity / negative targets) crosses the PyO3 bridge intact.
 *
 * The other functions in this module take a `MetricInputs` dataclass (or a Storage
 * object); the recorder's wrapper `_enc` cannot encode a dataclass (it falls back
 * to `{"$repr": ...}`), so those cases recorded only original exceptions and cannot
 * prove a Rust port. They are declared `--keep` in `rust-anything.json` and stay in
 * Python. See finding `finding-metrics-boundary.md`.
 *
 * Constants mirror `zkc.tuning.REGISTRY`: the four METRIC_W_* = 0.25 and
 * METRIC_METHOD_TARGET = 10.0 are the CALIBRATED overrides from 1-26 and must
 * not be promoted or silently changed here.
 */

#![forbid(unsafe_code)]

use serde_json::Value;

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

fn as_f64(v: &Value) -> Option<f64> {
    match v {
        Value::Number(n) => Some(n.as_f64()?),
        Value::Bool(b) => Some(if *b { 1.0 } else { 0.0 }),
        _ => marker_number(v),
    }
}

const DEFAULT_WEIGHTS: [f64; 4] = [0.25, 0.25, 0.25, 0.25]; // recorded-literal: zkc.tuning CALIBRATED seeds (1-26)

fn is_undefined(v: &Value) -> bool {
    v.as_object()
        .and_then(|o| o.get("$undefined"))
        .and_then(Value::as_bool)
        .unwrap_or(false)
}

/// Python `weights[i]`: a 4-tuple crosses as `{"$tuple":[...]}`, a list as array,
/// `None` / `{"$undefined":true}` means "use the CALIBRATED default".
/// Items stay as `Value` so an invalid item raises at multiplication time, matching
/// CPython's left-to-right evaluation of `w0*cd + w1*rr + ...`.
fn decode_weights(v: Option<&Value>) -> Result<Vec<Value>, String> {
    let Some(v) = v else { return Ok(vec![]) };
    if v.is_null() || is_undefined(v) {
        return Ok(vec![]);
    }
    match v {
        Value::Array(a) => Ok(a.clone()),
        Value::Object(o) => match o.get("$tuple").or_else(|| o.get("$list")) {
            Some(Value::Array(a)) => Ok(a.clone()),
            // A mapping is subscriptable, but `weights[0]` (int key) misses a string-keyed dict.
            _ => Err("KeyError: 0".to_string()), // recorded-literal: CPython KeyError text for a missing int key
        },
        _ => Err("TypeError: 'int' object is not subscriptable".to_string()), // recorded-literal: CPython TypeError text for a non-subscriptable int
    }
}

/// Python `w * scalar` for a numeric `w`. A non-numeric `w` (e.g. str) is a
/// sequence repetition with a float multiplier, which CPython rejects.
fn mul_weight(w: &Value, scalar: f64) -> Result<f64, String> {
    match as_f64(w) {
        Some(n) => Ok(n * scalar),
        None => Err("TypeError: can't multiply sequence by non-int of type 'float'".to_string()), // recorded-literal: CPython TypeError text for str * float
    }
}

/// Python `min(1.0, x)` — Rust `f64::min` treats NaN as no-op (returns 1.0),
/// matching CPython's `min` which keeps the first operand on an inconclusive compare.
fn py_min_one(x: f64) -> f64 {
    1.0_f64.min(x)
}

/// Port of `compounding_factor` (`src/zkc/metrics.py:99`).
pub fn compounding_factor(
    cd: f64,
    rr: f64,
    mo: i64,
    dc: f64,
    weights: Option<Value>,
    method_target: Option<f64>,
) -> Result<f64, String> {
    let explicit = weights
        .as_ref()
        .is_some_and(|v| !v.is_null() && !is_undefined(v));
    let w: Vec<Value> = if explicit {
        decode_weights(weights.as_ref())?
    } else {
        if (DEFAULT_WEIGHTS.iter().sum::<f64>() - 1.0).abs() > 1e-9 {
            return Err("ValueError: METRIC_W_* 必须归一（和为 1）".to_string());
        }
        DEFAULT_WEIGHTS.iter().map(|x| Value::from(*x)).collect()
    };

    // Python `if method_target`: NaN is truthy, 0.0 / -0.0 are falsy.
    let target = method_target.unwrap_or(10.0);
    let mo_norm = if target != 0.0 {
        py_min_one(mo as f64 / target)
    } else {
        0.0
    };

    // CPython evaluates `w[0]*cd + w[1]*rr + w[2]*mo_norm + w[3]*dc` left to
    // right: each index is read then multiplied. A bad item raises at its own
    // term, and a short list only raises IndexError once that index is reached.
    let mut acc = 0.0;
    for (i, scalar) in [cd, rr, mo_norm, dc].into_iter().enumerate() {
        let item = w
            .get(i)
            .ok_or_else(|| "IndexError: list index out of range".to_string())?; // recorded-literal: CPython IndexError text
        acc += mul_weight(item, scalar)?;
    }
    Ok(acc)
}

// Daily regression tests — translated from tests/test_metrics.py semantics.
// These are NOT an oracle: the 243 recorded cases from the Python original are
// the proof; these tests only guard the already-proven behavior in daily runs.
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn empty_defaults_match_calibrated_blended_value() {
        // test_compounding_factor_blended: 0.25 × (1 + 2/3 + 0.3 + 2/3)
        let got = compounding_factor(1.0, 2.0 / 3.0, 3, 2.0 / 3.0, None, None).unwrap();
        assert!((got - (0.25 * (1.0 + 2.0 / 3.0 + 0.3 + 2.0 / 3.0))).abs() < 1e-9);
    }

    #[test]
    fn default_is_zero_on_all_zero_inputs() {
        assert_eq!(
            compounding_factor(0.0, 0.0, 0, 0.0, None, None).unwrap(),
            0.0
        );
    }

    #[test]
    fn method_target_saturates_methodology_output() {
        // mo/target capped at 1: mo=100, target=10 → 0.25 contribution
        let a = compounding_factor(0.0, 0.0, 100, 0.0, None, Some(10.0)).unwrap();
        let b = compounding_factor(0.0, 0.0, 10, 0.0, None, Some(10.0)).unwrap();
        assert!((a - b).abs() < 1e-12);
        assert!((a - 0.25).abs() < 1e-12);
    }

    #[test]
    fn zero_target_makes_methodology_zero() {
        let got = compounding_factor(0.0, 0.0, 7, 0.0, None, Some(0.0)).unwrap();
        assert_eq!(got, 0.0);
    }

    #[test]
    fn nan_target_is_truthy_and_yields_one() {
        // Python `if nan` is truthy → min(1.0, mo/nan)=1.0 → 0.25
        let got = compounding_factor(0.0, 0.0, 7, 0.0, None, Some(f64::NAN)).unwrap();
        assert!((got - 0.25).abs() < 1e-12);
    }

    #[test]
    fn explicit_weights_are_used_verbatim() {
        let w = json!({"$tuple": [1.0, 0.0, 0.0, 0.0]});
        let got = compounding_factor(2.5, 9.9, 3, 8.8, Some(w), None).unwrap();
        assert!((got - 2.5).abs() < 1e-12);
    }

    #[test]
    fn string_weight_raises_type_error_at_its_term() {
        let w = json!(["a", 1]);
        let err =
            compounding_factor(f64::INFINITY, 1.0, 100, 10.0, Some(w), Some(0.0)).unwrap_err();
        assert!(err.starts_with("TypeError: can't multiply sequence"));
    }

    #[test]
    fn short_weight_list_raises_index_error_when_reached() {
        let w = json!([0.25, 0.25]);
        let err = compounding_factor(1.0, 1.0, 1, 1.0, Some(w), None).unwrap_err();
        assert!(err.starts_with("IndexError: list index"));
    }
}
