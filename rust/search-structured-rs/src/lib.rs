//! Python bindings for `spikes/spike-30-search-structured/pure_bridge.py`: generated from the signatures in `port.rs` by rust-anything.
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

fn filter_sort_nodes_inner(
    nodes: Bound<'_, PyAny>,
    track: Bound<'_, PyAny>,
    q: Bound<'_, PyAny>,
    decay_min: Bound<'_, PyAny>,
    decay_max: Bound<'_, PyAny>,
    include_archived: Bound<'_, PyAny>,
    order: Bound<'_, PyAny>,
    limit: Bound<'_, PyAny>,
) -> Result<serde_json::Value, String> {
    let nodes: serde_json::Value = crate::pyconv::FromPy::from_py(&nodes)?;
    let track: serde_json::Value = crate::pyconv::FromPy::from_py(&track)?;
    let q: serde_json::Value = crate::pyconv::FromPy::from_py(&q)?;
    let decay_min: serde_json::Value = crate::pyconv::FromPy::from_py(&decay_min)?;
    let decay_max: serde_json::Value = crate::pyconv::FromPy::from_py(&decay_max)?;
    let include_archived: serde_json::Value = crate::pyconv::FromPy::from_py(&include_archived)?;
    let order: serde_json::Value = crate::pyconv::FromPy::from_py(&order)?;
    let limit: serde_json::Value = crate::pyconv::FromPy::from_py(&limit)?;
    let out = port::filter_sort_nodes(
        nodes,
        track,
        q,
        decay_min,
        decay_max,
        include_archived,
        order,
        limit,
    )?;
    Ok(out)
}

/// `filter_sort_nodes`.
#[pyfunction]
#[pyo3(name = "filter_sort_nodes", signature = (nodes, track, q, decay_min, decay_max, include_archived, order, limit))]
fn filter_sort_nodes(
    py: Python<'_>,
    nodes: Bound<'_, PyAny>,
    track: Bound<'_, PyAny>,
    q: Bound<'_, PyAny>,
    decay_min: Bound<'_, PyAny>,
    decay_max: Bound<'_, PyAny>,
    include_archived: Bound<'_, PyAny>,
    order: Bound<'_, PyAny>,
    limit: Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    filter_sort_nodes_inner(
        nodes,
        track,
        q,
        decay_min,
        decay_max,
        include_archived,
        order,
        limit,
    )
    .map_err(error)
    .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

#[pymodule]
#[pyo3(name = "_native")]
fn native_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(filter_sort_nodes, m)?)?;
    Ok(())
}
