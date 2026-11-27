//! Python bindings for `spikes/spike-09-review-interval/pure_bridge.py`: generated from the signatures in `port.rs` by rust-anything.
//! Regenerate with `rust-anything refresh` after changing them.

#![allow(clippy::too_many_arguments)]

use pyo3::prelude::*;
use serde_json::Value;

pub mod js;
pub mod port;
pub mod pyconv;
pub mod pynum;

#[allow(unused_imports)]
use pynum::Num;

fn error(message: String) -> PyErr {
    use pyo3::exceptions as e;
    /// `Err("Kind: text")` for a `Kind` the match below does not know: a built-in exception's name or
    /// `package.module.Class`, called with the text. None when it names no `Exception` subclass or the
    /// class cannot be made from the text alone (its constructor takes more arguments).
    fn named_error(kind: &str, text: &str) -> Option<PyErr> {
        Python::attach(|py| {
            // Each dotted part must be a Python identifier, by Python's own rules (`str.isidentifier`).
            let identifier = |part: &str| {
                pyo3::types::PyString::new(py, part)
                    .call_method0("isidentifier")
                    .and_then(|ok| ok.extract::<bool>())
                    .unwrap_or(false)
            };
            if !kind.split('.').all(identifier) {
                return None;
            }
            let (module, name) = kind.rsplit_once('.').unwrap_or(("builtins", kind));
            let class = py.import(module).ok()?.getattr(name).ok()?;
            let class = class.cast_into::<pyo3::types::PyType>().ok()?;
            if !class
                .is_subclass_of::<pyo3::exceptions::PyException>()
                .ok()?
            {
                return None;
            }
            let value = class.call1((text,)).ok()?;
            if !value.is_instance(&class).ok()? {
                return None;
            }
            Some(PyErr::from_value(value))
        })
    }
    let (kind, text) = message.split_once(": ").unwrap_or(("", message.as_str()));
    let text = text.to_string();
    match kind {
        "TypeError" => e::PyTypeError::new_err(text),
        "KeyError" => e::PyKeyError::new_err(text),
        "IndexError" => e::PyIndexError::new_err(text),
        "OverflowError" => e::PyOverflowError::new_err(text),
        "ZeroDivisionError" => e::PyZeroDivisionError::new_err(text),
        "AttributeError" => e::PyAttributeError::new_err(text),
        "RuntimeError" => e::PyRuntimeError::new_err(text),
        "NotImplementedError" => e::PyNotImplementedError::new_err(text),
        "LookupError" => e::PyLookupError::new_err(text),
        "ArithmeticError" => e::PyArithmeticError::new_err(text),
        "UnicodeError" => e::PyUnicodeError::new_err(text),
        "ValueError" => e::PyValueError::new_err(text),
        _ => named_error(kind, &text).unwrap_or_else(|| e::PyValueError::new_err(message)),
    }
}

fn extract_horizon_days_inner(text: Option<String>) -> Result<Option<f64>, String> {
    let out = port::extract_horizon_days(text)?;
    Ok(out)
}

/// `extract_horizon_days`.
#[pyfunction]
#[pyo3(name = "extract_horizon_days", signature = (text))]
fn extract_horizon_days(text: Option<String>) -> PyResult<Option<f64>> {
    extract_horizon_days_inner(text).map_err(error)
}

fn clamp_days_inner(days: f64) -> Result<f64, String> {
    let out = port::clamp_days(days)?;
    Ok(out)
}

/// `clamp_days`.
#[pyfunction]
#[pyo3(name = "clamp_days", signature = (days))]
fn clamp_days(days: f64) -> PyResult<f64> {
    clamp_days_inner(days).map_err(error)
}

fn baseline_for_signals_inner(
    track: String,
    archived: bool,
    title: String,
    content: Option<String>,
    captured: bool,
    self_loop_count: i64,
    higher_dim_count: i64,
    conn_count: i64,
) -> Result<Value, String> {
    let out = port::baseline_for_signals(
        track,
        archived,
        title,
        content,
        captured,
        self_loop_count,
        higher_dim_count,
        conn_count,
    )?;
    Ok(out)
}

/// `baseline_for_signals`.
#[pyfunction]
#[pyo3(name = "baseline_for_signals", signature = (track, archived, title, content, captured, self_loop_count, higher_dim_count, conn_count))]
fn baseline_for_signals(
    py: Python<'_>,
    track: String,
    archived: bool,
    title: String,
    content: Option<String>,
    captured: bool,
    self_loop_count: i64,
    higher_dim_count: i64,
    conn_count: i64,
) -> PyResult<Py<PyAny>> {
    baseline_for_signals_inner(
        track,
        archived,
        title,
        content,
        captured,
        self_loop_count,
        higher_dim_count,
        conn_count,
    )
    .map_err(error)
    .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn classify_review_inner(decay_at_review: f64) -> Result<String, String> {
    let out = port::classify_review(decay_at_review)?;
    Ok(out)
}

/// `classify_review`.
#[pyfunction]
#[pyo3(name = "classify_review", signature = (decay_at_review))]
fn classify_review(decay_at_review: f64) -> PyResult<String> {
    classify_review_inner(decay_at_review).map_err(error)
}

fn adapt_interval_math_inner(old_days: f64, verdict: String, human: bool) -> Result<Value, String> {
    let out = port::adapt_interval_math(old_days, verdict, human)?;
    Ok(out)
}

/// `adapt_interval_math`.
#[pyfunction]
#[pyo3(name = "adapt_interval_math", signature = (old_days, verdict, *, human=false))]
fn adapt_interval_math(
    py: Python<'_>,
    old_days: f64,
    verdict: String,
    human: bool,
) -> PyResult<Py<PyAny>> {
    adapt_interval_math_inner(old_days, verdict, human)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn l2_target_inner(budget: Option<f64>, confidence: String) -> Result<Option<f64>, String> {
    let out = port::l2_target(budget, confidence)?;
    Ok(out)
}

/// `l2_target`.
#[pyfunction]
#[pyo3(name = "l2_target", signature = (budget, confidence))]
fn l2_target(budget: Option<f64>, confidence: String) -> PyResult<Option<f64>> {
    l2_target_inner(budget, confidence).map_err(error)
}

#[pymodule]
#[pyo3(name = "_native")]
fn native_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_horizon_days, m)?)?;
    m.add_function(wrap_pyfunction!(clamp_days, m)?)?;
    m.add_function(wrap_pyfunction!(baseline_for_signals, m)?)?;
    m.add_function(wrap_pyfunction!(classify_review, m)?)?;
    m.add_function(wrap_pyfunction!(adapt_interval_math, m)?)?;
    m.add_function(wrap_pyfunction!(l2_target, m)?)?;
    Ok(())
}
