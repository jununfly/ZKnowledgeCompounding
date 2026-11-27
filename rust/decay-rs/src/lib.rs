//! Python bindings for `src/zkc/decay.py`: generated from the signatures in `port.rs` by rust-anything.
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

fn decay_linear_inner(elapsed_days: f64, interval_days: f64) -> Result<f64, String> {
    let out = port::decay_linear(elapsed_days, interval_days)?;
    Ok(out)
}

/// `decay_linear`.
#[pyfunction]
#[pyo3(name = "decay_linear", signature = (elapsed_days, interval_days))]
fn decay_linear(elapsed_days: f64, interval_days: f64) -> PyResult<f64> {
    decay_linear_inner(elapsed_days, interval_days).map_err(error)
}

fn decay_exponential_inner(elapsed_days: f64, half_life_days: f64) -> Result<f64, String> {
    let out = port::decay_exponential(elapsed_days, half_life_days)?;
    Ok(out)
}

/// `decay_exponential`.
#[pyfunction]
#[pyo3(name = "decay_exponential", signature = (elapsed_days, half_life_days))]
fn decay_exponential(elapsed_days: f64, half_life_days: f64) -> PyResult<f64> {
    decay_exponential_inner(elapsed_days, half_life_days).map_err(error)
}

fn decay_step_inner(elapsed_days: f64, interval_days: f64) -> Result<f64, String> {
    let out = port::decay_step(elapsed_days, interval_days)?;
    Ok(out)
}

/// `decay_step`.
#[pyfunction]
#[pyo3(name = "decay_step", signature = (elapsed_days, interval_days))]
fn decay_step(elapsed_days: f64, interval_days: f64) -> PyResult<f64> {
    decay_step_inner(elapsed_days, interval_days).map_err(error)
}

fn elapsed_days_inner(node: Bound<'_, PyAny>, now: Bound<'_, PyAny>) -> Result<f64, String> {
    let node: Value = crate::pyconv::FromPy::from_py(&node)?;
    let now: Value = crate::pyconv::FromPy::from_py(&now)?;
    let out = port::elapsed_days(node, now)?;
    Ok(out)
}

/// `elapsed_days`.
#[pyfunction]
#[pyo3(name = "elapsed_days", signature = (node, now))]
fn elapsed_days(node: Bound<'_, PyAny>, now: Bound<'_, PyAny>) -> PyResult<f64> {
    elapsed_days_inner(node, now).map_err(error)
}

fn compute_decay_score_inner(node: Bound<'_, PyAny>, now: Bound<'_, PyAny>) -> Result<f64, String> {
    let node: Value = crate::pyconv::FromPy::from_py(&node)?;
    let now: Value = crate::pyconv::FromPy::from_py(&now)?;
    let out = port::compute_decay_score(node, now)?;
    Ok(out)
}

/// `compute_decay_score`.
#[pyfunction]
#[pyo3(name = "compute_decay_score", signature = (node, now))]
fn compute_decay_score(node: Bound<'_, PyAny>, now: Bound<'_, PyAny>) -> PyResult<f64> {
    compute_decay_score_inner(node, now).map_err(error)
}

fn surface_inner(
    items: Bound<'_, PyAny>,
    now: Bound<'_, PyAny>,
    threshold: Option<f64>,
    budget: Option<i64>,
) -> Result<Vec<Value>, String> {
    let items: Value = crate::pyconv::FromPy::from_py(&items)?;
    let now: Value = crate::pyconv::FromPy::from_py(&now)?;
    let out = port::surface(items, now, threshold, budget)?;
    Ok(out)
}

/// `surface`.
#[pyfunction]
#[pyo3(name = "surface", signature = (items, now, threshold=None, budget=None))]
fn surface(
    py: Python<'_>,
    items: Bound<'_, PyAny>,
    now: Bound<'_, PyAny>,
    threshold: Option<f64>,
    budget: Option<i64>,
) -> PyResult<Py<PyAny>> {
    surface_inner(items, now, threshold, budget)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn review_reset_inner(node: Bound<'_, PyAny>, now: Bound<'_, PyAny>) -> Result<Value, String> {
    let node: Value = crate::pyconv::FromPy::from_py(&node)?;
    let now: Value = crate::pyconv::FromPy::from_py(&now)?;
    let out = port::review_reset(node, now)?;
    Ok(out)
}

/// `review_reset`.
#[pyfunction]
#[pyo3(name = "review_reset", signature = (node, now))]
fn review_reset(
    py: Python<'_>,
    node: Bound<'_, PyAny>,
    now: Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    review_reset_inner(node, now)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn refresh_decay_inner(repo: Bound<'_, PyAny>, now: Bound<'_, PyAny>) -> Result<i64, String> {
    let repo: Value = crate::pyconv::FromPy::from_py(&repo)?;
    let now: Value = crate::pyconv::FromPy::from_py(&now)?;
    let out = port::refresh_decay(repo, now)?;
    Ok(out)
}

/// `refresh_decay`.
#[pyfunction]
#[pyo3(name = "refresh_decay", signature = (repo, now))]
fn refresh_decay(repo: Bound<'_, PyAny>, now: Bound<'_, PyAny>) -> PyResult<i64> {
    refresh_decay_inner(repo, now).map_err(error)
}

#[pymodule]
#[pyo3(name = "_native")]
fn native_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(decay_linear, m)?)?;
    m.add_function(wrap_pyfunction!(decay_exponential, m)?)?;
    m.add_function(wrap_pyfunction!(decay_step, m)?)?;
    m.add_function(wrap_pyfunction!(elapsed_days, m)?)?;
    m.add_function(wrap_pyfunction!(compute_decay_score, m)?)?;
    m.add_function(wrap_pyfunction!(surface, m)?)?;
    m.add_function(wrap_pyfunction!(review_reset, m)?)?;
    m.add_function(wrap_pyfunction!(refresh_decay, m)?)?;
    Ok(())
}
