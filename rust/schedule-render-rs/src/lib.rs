//! Python bindings for `spikes/spike-24-schedule-render/pure_bridge.py`: generated from the signatures in `port.rs` by rust-anything.
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

fn build_task_action_inner(wrapper: Bound<'_, PyAny>) -> Result<serde_json::Value, String> {
    let wrapper: serde_json::Value = crate::pyconv::FromPy::from_py(&wrapper)?;
    let out = port::build_task_action(wrapper)?;
    Ok(out)
}

/// `build_task_action`.
#[pyfunction]
#[pyo3(name = "build_task_action", signature = (wrapper))]
fn build_task_action(py: Python<'_>, wrapper: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    build_task_action_inner(wrapper)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn build_register_command_inner(
    wrapper: Bound<'_, PyAny>,
    task_name: Bound<'_, PyAny>,
    at: Bound<'_, PyAny>,
) -> Result<serde_json::Value, String> {
    let wrapper: serde_json::Value = crate::pyconv::FromPy::from_py(&wrapper)?;
    let task_name: serde_json::Value = crate::pyconv::FromPy::from_py(&task_name)?;
    let at: serde_json::Value = crate::pyconv::FromPy::from_py(&at)?;
    let out = port::build_register_command(wrapper, task_name, at)?;
    Ok(out)
}

/// `build_register_command`.
#[pyfunction]
#[pyo3(name = "build_register_command", signature = (wrapper, task_name, at))]
fn build_register_command(
    py: Python<'_>,
    wrapper: Bound<'_, PyAny>,
    task_name: Bound<'_, PyAny>,
    at: Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    build_register_command_inner(wrapper, task_name, at)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn build_unregister_command_inner(
    task_name: Bound<'_, PyAny>,
) -> Result<serde_json::Value, String> {
    let task_name: serde_json::Value = crate::pyconv::FromPy::from_py(&task_name)?;
    let out = port::build_unregister_command(task_name)?;
    Ok(out)
}

/// `build_unregister_command`.
#[pyfunction]
#[pyo3(name = "build_unregister_command", signature = (task_name))]
fn build_unregister_command(py: Python<'_>, task_name: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    build_unregister_command_inner(task_name)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

#[pymodule]
#[pyo3(name = "_native")]
fn native_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(build_task_action, m)?)?;
    m.add_function(wrap_pyfunction!(build_register_command, m)?)?;
    m.add_function(wrap_pyfunction!(build_unregister_command, m)?)?;
    Ok(())
}
