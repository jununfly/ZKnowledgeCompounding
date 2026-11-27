//! Rust port of `src/zkc/metrics.py` (behavioral slice: `compounding_factor`).
/*!
 * Behavior is pinned by `cases.jsonl` recorded from the Python original with
 * `rust-anything record`. The recordable slice is the scalar pure-function layer:
 * `compounding_factor` takes only JSON scalars, so all 103 valid recorded cases
 * (incl. NaN / Infinity / negative targets) cross the PyO3 bridge intact.
 *
 * The other functions in this module take a `MetricInputs` **dataclass**. The
 * recorder's wrapper `_enc` cannot encode a dataclass (it falls back to `{"$repr": ...}`),
 * so those cases recorded only original exceptions and cannot prove a Rust port;
 * they stay in Python. See finding `finding-metrics-boundary.md`.
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

/// Python `weights[0..3]`: a 4-tuple crosses as `{"$tuple":[...]}`, a list as array,
/// `None` / `{"$undefined":true}` means "use the CALIBRATED default".
fn default_weights() -> [f64; 4] {
    [0.25, 0.25, 0.25, 0.25]
}

fn decode_weights(v: Option<&Value>) -> Result<[f64; 4], String> {
    let Some(v) = v else {
        return Ok(default_weights());
    };
    let is_undefined = v
        .as_object()
        .and_then(|o| o.get("$undefined"))
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if v.is_null() || is_undefined {
        return Ok(default_weights());
    }
    let arr: &[Value] = match v {
        Value::Array(a) => a,
        Value::Object(o) => match o.get("$tuple").or_else(|| o.get("$num")) {
            Some(Value::Array(a)) => a,
            _ => return Err("KeyError: 0".to_string()),
        },
        _ => return Err("TypeError: 'int' object is not subscriptable".to_string()),
    };
    if arr.len() < 4 {
        return Err("IndexError: list index out of range".to_string());
    }
    let mut out = [0.0; 4];
    for (i, slot) in out.iter_mut().enumerate() {
        *slot = as_f64(&arr[i]).ok_or_else(|| {
            "TypeError: can't multiply sequence by non-int of type 'float'".to_string()
        })?;
    }
    Ok(out)
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
    let w = decode_weights(weights.as_ref())?;
    // weights=None path enforces the normalization invariant; explicit weights skip it.
    let weights_is_default = weights.as_ref().map_or(true, |v| {
        v.is_null()
            || v.as_object()
                .and_then(|o| o.get("$undefined"))
                .and_then(Value::as_bool)
                .unwrap_or(false)
    });
    if weights_is_default && (w.iter().sum::<f64>() - 1.0).abs() > 1e-9 {
        return Err("ValueError: METRIC_W_* 必须归一（和为 1）".to_string());
    }
    let target = method_target.unwrap_or(10.0);
    let mo_norm = if target != 0.0 && !target.is_nan() {
        py_min_one(mo as f64 / target)
    } else {
        0.0
    };
    Ok(w[0] * cd + w[1] * rr + w[2] * mo_norm + w[3] * dc)
}

// ---- Below: dataclass/Storage-taking functions stay unported. ----
// The bridge cannot carry a MetricInputs dataclass (`_enc` falls back to `$repr`)
// nor a Storage object across PyO3; their recorded cases are all original errors
// and prove nothing about a Rust port. Kept as signatures so bindings compile.

/// Not ported: `connection_density` takes a `MetricInputs` dataclass.
pub fn connection_density(inp: Value) -> Result<f64, String> {
    let _ = &inp;
    Err("E_NOT_PORTED: MetricInputs dataclass cannot cross the bridge".to_string())
}

/// Not ported: `reuse_rate` takes a `MetricInputs` dataclass.
pub fn reuse_rate(inp: Value) -> Result<Value, String> {
    let _ = &inp;
    Err("E_NOT_PORTED: MetricInputs dataclass cannot cross the bridge".to_string())
}

/// Not ported: `methodology_output` takes a `MetricInputs` dataclass.
pub fn methodology_output(inp: Value) -> Result<i64, String> {
    let _ = &inp;
    Err("E_NOT_PORTED: MetricInputs dataclass cannot cross the bridge".to_string())
}

/// Not ported: `decay_controllability` takes a `MetricInputs` dataclass.
pub fn decay_controllability(inp: Value, rot_threshold: Option<f64>) -> Result<f64, String> {
    let _ = (&inp, &rot_threshold);
    Err("E_NOT_PORTED: MetricInputs dataclass cannot cross the bridge".to_string())
}

/// Not ported: `rot_rate` takes a `MetricInputs` dataclass.
pub fn rot_rate(inp: Value, rot_threshold: Option<f64>) -> Result<f64, String> {
    let _ = (&inp, &rot_threshold);
    Err("E_NOT_PORTED: MetricInputs dataclass cannot cross the bridge".to_string())
}

/// Not ported: `build_report` takes a `MetricInputs` dataclass.
pub fn build_report(inp: Value) -> Result<Value, String> {
    let _ = &inp;
    Err("E_NOT_PORTED: MetricInputs dataclass cannot cross the bridge".to_string())
}

/// Not ported: `build_report_dict` takes a `MetricInputs` dataclass.
pub fn build_report_dict(inp: Value) -> Result<Value, String> {
    let _ = &inp;
    Err("E_NOT_PORTED: MetricInputs dataclass cannot cross the bridge".to_string())
}

/// Not ported: `metrics_report` takes a `Storage` object.
pub fn metrics_report(store: Value) -> Result<Value, String> {
    let _ = &store;
    Err("E_NOT_PORTED: Storage object cannot cross the bridge".to_string())
}
