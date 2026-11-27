//! Python bindings for `spikes/spike-10-model-quality/pure_bridge.py`: generated from the signatures in `port.rs` by rust-anything.
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

fn normalize_inner(text: Bound<'_, PyAny>) -> Result<serde_json::Value, String> {
    let text: serde_json::Value = crate::pyconv::FromPy::from_py(&text)?;
    let out = port::normalize(text)?;
    Ok(out)
}

/// `normalize`.
#[pyfunction]
#[pyo3(name = "normalize", signature = (text))]
fn normalize(py: Python<'_>, text: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    normalize_inner(text)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn ngrams_inner(text: Bound<'_, PyAny>, n: i64) -> Result<serde_json::Value, String> {
    let text: serde_json::Value = crate::pyconv::FromPy::from_py(&text)?;
    let out = port::ngrams(text, n)?;
    Ok(out)
}

/// `ngrams`.
#[pyfunction]
#[pyo3(name = "ngrams", signature = (text, n=3))]
fn ngrams(py: Python<'_>, text: Bound<'_, PyAny>, n: i64) -> PyResult<Py<PyAny>> {
    ngrams_inner(text, n)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn lcs_length_inner(a: Bound<'_, PyAny>, b: Bound<'_, PyAny>) -> Result<serde_json::Value, String> {
    let a: serde_json::Value = crate::pyconv::FromPy::from_py(&a)?;
    let b: serde_json::Value = crate::pyconv::FromPy::from_py(&b)?;
    let out = port::lcs_length(a, b)?;
    Ok(out)
}

/// `lcs_length`.
#[pyfunction]
#[pyo3(name = "lcs_length", signature = (a, b))]
fn lcs_length(py: Python<'_>, a: Bound<'_, PyAny>, b: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    lcs_length_inner(a, b)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn verbatim_rate_inner(
    claim: Bound<'_, PyAny>,
    source_texts: Bound<'_, PyAny>,
) -> Result<serde_json::Value, String> {
    let claim: serde_json::Value = crate::pyconv::FromPy::from_py(&claim)?;
    let source_texts: serde_json::Value = crate::pyconv::FromPy::from_py(&source_texts)?;
    let out = port::verbatim_rate(claim, source_texts)?;
    Ok(out)
}

/// `verbatim_rate`.
#[pyfunction]
#[pyo3(name = "verbatim_rate", signature = (claim, source_texts))]
fn verbatim_rate(
    py: Python<'_>,
    claim: Bound<'_, PyAny>,
    source_texts: Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    verbatim_rate_inner(claim, source_texts)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn overlap_inner(
    claim: Bound<'_, PyAny>,
    source_texts: Bound<'_, PyAny>,
) -> Result<serde_json::Value, String> {
    let claim: serde_json::Value = crate::pyconv::FromPy::from_py(&claim)?;
    let source_texts: serde_json::Value = crate::pyconv::FromPy::from_py(&source_texts)?;
    let out = port::overlap(claim, source_texts)?;
    Ok(out)
}

/// `overlap`.
#[pyfunction]
#[pyo3(name = "overlap", signature = (claim, source_texts))]
fn overlap(
    py: Python<'_>,
    claim: Bound<'_, PyAny>,
    source_texts: Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    overlap_inner(claim, source_texts)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn rubric_flags_inner(
    claim_text: Bound<'_, PyAny>,
    source_texts: Bound<'_, PyAny>,
) -> Result<serde_json::Value, String> {
    let claim_text: serde_json::Value = crate::pyconv::FromPy::from_py(&claim_text)?;
    let source_texts: serde_json::Value = crate::pyconv::FromPy::from_py(&source_texts)?;
    let out = port::rubric_flags(claim_text, source_texts)?;
    Ok(out)
}

/// `rubric_flags`.
#[pyfunction]
#[pyo3(name = "rubric_flags", signature = (claim_text, source_texts))]
fn rubric_flags(
    py: Python<'_>,
    claim_text: Bound<'_, PyAny>,
    source_texts: Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    rubric_flags_inner(claim_text, source_texts)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn is_forced_inner(route: Bound<'_, PyAny>) -> Result<serde_json::Value, String> {
    let route: serde_json::Value = crate::pyconv::FromPy::from_py(&route)?;
    let out = port::is_forced(route)?;
    Ok(out)
}

/// `is_forced`.
#[pyfunction]
#[pyo3(name = "is_forced", signature = (route))]
fn is_forced(py: Python<'_>, route: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    is_forced_inner(route)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

#[pymodule]
#[pyo3(name = "_native")]
fn native_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(normalize, m)?)?;
    m.add_function(wrap_pyfunction!(ngrams, m)?)?;
    m.add_function(wrap_pyfunction!(lcs_length, m)?)?;
    m.add_function(wrap_pyfunction!(verbatim_rate, m)?)?;
    m.add_function(wrap_pyfunction!(overlap, m)?)?;
    m.add_function(wrap_pyfunction!(rubric_flags, m)?)?;
    m.add_function(wrap_pyfunction!(is_forced, m)?)?;
    Ok(())
}
