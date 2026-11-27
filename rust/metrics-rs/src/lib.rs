//! Python bindings for `src/zkc/metrics.py`: generated from the signatures in `port.rs` by rust-anything.
//! Regenerate with `rust-anything refresh` after changing them.

#![allow(clippy::too_many_arguments)]

use pyo3::prelude::*;

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

fn connection_density_inner(inp: Bound<'_, PyAny>) -> Result<f64, String> {
    let inp: serde_json::Value = crate::pyconv::FromPy::from_py(&inp)?;
    let out = port::connection_density(inp)?;
    Ok(out)
}

/// `connection_density`.
#[pyfunction]
#[pyo3(name = "connection_density", signature = (inp))]
fn connection_density(inp: Bound<'_, PyAny>) -> PyResult<f64> {
    connection_density_inner(inp).map_err(error)
}

fn reuse_rate_inner(inp: Bound<'_, PyAny>) -> Result<serde_json::Value, String> {
    let inp: serde_json::Value = crate::pyconv::FromPy::from_py(&inp)?;
    let out = port::reuse_rate(inp)?;
    Ok(out)
}

/// `reuse_rate`.
#[pyfunction]
#[pyo3(name = "reuse_rate", signature = (inp))]
fn reuse_rate(py: Python<'_>, inp: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    reuse_rate_inner(inp)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn methodology_output_inner(inp: Bound<'_, PyAny>) -> Result<i64, String> {
    let inp: serde_json::Value = crate::pyconv::FromPy::from_py(&inp)?;
    let out = port::methodology_output(inp)?;
    Ok(out)
}

/// `methodology_output`.
#[pyfunction]
#[pyo3(name = "methodology_output", signature = (inp))]
fn methodology_output(inp: Bound<'_, PyAny>) -> PyResult<i64> {
    methodology_output_inner(inp).map_err(error)
}

fn decay_controllability_inner(
    inp: Bound<'_, PyAny>,
    rot_threshold: Option<f64>,
) -> Result<f64, String> {
    let inp: serde_json::Value = crate::pyconv::FromPy::from_py(&inp)?;
    let out = port::decay_controllability(inp, rot_threshold)?;
    Ok(out)
}

/// `decay_controllability`.
#[pyfunction]
#[pyo3(name = "decay_controllability", signature = (inp, rot_threshold=None))]
fn decay_controllability(inp: Bound<'_, PyAny>, rot_threshold: Option<f64>) -> PyResult<f64> {
    decay_controllability_inner(inp, rot_threshold).map_err(error)
}

fn rot_rate_inner(inp: Bound<'_, PyAny>, rot_threshold: Option<f64>) -> Result<f64, String> {
    let inp: serde_json::Value = crate::pyconv::FromPy::from_py(&inp)?;
    let out = port::rot_rate(inp, rot_threshold)?;
    Ok(out)
}

/// `rot_rate`.
#[pyfunction]
#[pyo3(name = "rot_rate", signature = (inp, rot_threshold=None))]
fn rot_rate(inp: Bound<'_, PyAny>, rot_threshold: Option<f64>) -> PyResult<f64> {
    rot_rate_inner(inp, rot_threshold).map_err(error)
}

fn compounding_factor_inner(
    cd: f64,
    rr: f64,
    mo: i64,
    dc: f64,
    weights: Option<Bound<'_, PyAny>>,
    method_target: Option<f64>,
) -> Result<f64, String> {
    let weights: Option<serde_json::Value> = match &weights {
        None => None,
        Some(v) => Some(crate::pyconv::FromPy::from_py(v)?),
    };
    let out = port::compounding_factor(cd, rr, mo, dc, weights, method_target)?;
    Ok(out)
}

/// `compounding_factor`.
#[pyfunction]
#[pyo3(name = "compounding_factor", signature = (cd, rr, mo, dc, weights=None, method_target=None))]
fn compounding_factor(
    cd: f64,
    rr: f64,
    mo: i64,
    dc: f64,
    weights: Option<Bound<'_, PyAny>>,
    method_target: Option<f64>,
) -> PyResult<f64> {
    compounding_factor_inner(cd, rr, mo, dc, weights, method_target).map_err(error)
}

fn build_report_inner(inp: Bound<'_, PyAny>) -> Result<serde_json::Value, String> {
    let inp: serde_json::Value = crate::pyconv::FromPy::from_py(&inp)?;
    let out = port::build_report(inp)?;
    Ok(out)
}

/// `build_report`.
#[pyfunction]
#[pyo3(name = "build_report", signature = (inp))]
fn build_report(py: Python<'_>, inp: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    build_report_inner(inp)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn build_report_dict_inner(inp: Bound<'_, PyAny>) -> Result<serde_json::Value, String> {
    let inp: serde_json::Value = crate::pyconv::FromPy::from_py(&inp)?;
    let out = port::build_report_dict(inp)?;
    Ok(out)
}

/// `build_report_dict`.
#[pyfunction]
#[pyo3(name = "build_report_dict", signature = (inp))]
fn build_report_dict(py: Python<'_>, inp: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    build_report_dict_inner(inp)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn metrics_report_inner(store: Bound<'_, PyAny>) -> Result<serde_json::Value, String> {
    let store: serde_json::Value = crate::pyconv::FromPy::from_py(&store)?;
    let out = port::metrics_report(store)?;
    Ok(out)
}

/// `metrics_report`.
#[pyfunction]
#[pyo3(name = "metrics_report", signature = (store))]
fn metrics_report(py: Python<'_>, store: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    metrics_report_inner(store)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

#[pymodule]
#[pyo3(name = "_native")]
fn native_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(connection_density, m)?)?;
    m.add_function(wrap_pyfunction!(reuse_rate, m)?)?;
    m.add_function(wrap_pyfunction!(methodology_output, m)?)?;
    m.add_function(wrap_pyfunction!(decay_controllability, m)?)?;
    m.add_function(wrap_pyfunction!(rot_rate, m)?)?;
    m.add_function(wrap_pyfunction!(compounding_factor, m)?)?;
    m.add_function(wrap_pyfunction!(build_report, m)?)?;
    m.add_function(wrap_pyfunction!(build_report_dict, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_report, m)?)?;
    Ok(())
}
