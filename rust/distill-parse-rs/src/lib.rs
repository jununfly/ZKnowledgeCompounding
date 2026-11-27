//! Python bindings for `spikes/spike-17-distill-parse/pure_bridge.py`: generated from the signatures in `port.rs` by rust-anything.
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

fn extract_json_inner(raw: Bound<'_, PyAny>) -> Result<serde_json::Value, String> {
    let raw: serde_json::Value = crate::pyconv::FromPy::from_py(&raw)?;
    let out = port::extract_json(raw)?;
    Ok(out)
}

/// `extract_json`.
#[pyfunction]
#[pyo3(name = "extract_json", signature = (raw))]
fn extract_json(py: Python<'_>, raw: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    extract_json_inner(raw)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn parse_json_output_inner(
    raw: Bound<'_, PyAny>,
    source_texts: Bound<'_, PyAny>,
) -> Result<serde_json::Value, String> {
    let raw: serde_json::Value = crate::pyconv::FromPy::from_py(&raw)?;
    let source_texts: serde_json::Value = crate::pyconv::FromPy::from_py(&source_texts)?;
    let out = port::parse_json_output(raw, source_texts)?;
    Ok(out)
}

/// `parse_json_output`.
#[pyfunction]
#[pyo3(name = "parse_json_output", signature = (raw, source_texts))]
fn parse_json_output(
    py: Python<'_>,
    raw: Bound<'_, PyAny>,
    source_texts: Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    parse_json_output_inner(raw, source_texts)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn parse_llm_output_inner(
    raw: Bound<'_, PyAny>,
    source_texts: Bound<'_, PyAny>,
) -> Result<serde_json::Value, String> {
    let raw: serde_json::Value = crate::pyconv::FromPy::from_py(&raw)?;
    let source_texts: serde_json::Value = crate::pyconv::FromPy::from_py(&source_texts)?;
    let out = port::parse_llm_output(raw, source_texts)?;
    Ok(out)
}

/// `parse_llm_output`.
#[pyfunction]
#[pyo3(name = "parse_llm_output", signature = (raw, source_texts))]
fn parse_llm_output(
    py: Python<'_>,
    raw: Bound<'_, PyAny>,
    source_texts: Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    parse_llm_output_inner(raw, source_texts)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn validate_result_inner(result: Bound<'_, PyAny>) -> Result<serde_json::Value, String> {
    let result: serde_json::Value = crate::pyconv::FromPy::from_py(&result)?;
    let out = port::validate_result(result)?;
    Ok(out)
}

/// `validate_result`.
#[pyfunction]
#[pyo3(name = "validate_result", signature = (result))]
fn validate_result(py: Python<'_>, result: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    validate_result_inner(result)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

#[pymodule]
#[pyo3(name = "_native")]
fn native_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_json, m)?)?;
    m.add_function(wrap_pyfunction!(parse_json_output, m)?)?;
    m.add_function(wrap_pyfunction!(parse_llm_output, m)?)?;
    m.add_function(wrap_pyfunction!(validate_result, m)?)?;
    Ok(())
}
