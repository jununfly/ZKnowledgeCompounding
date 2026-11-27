//! Python bindings for `src/zkc/transport/`: generated from the signatures in `port.rs` by rust-anything.
//! Regenerate with `rust-anything refresh` after changing them.

#![allow(clippy::too_many_arguments)]

use pyo3::prelude::*;

pub mod js;
pub mod port;
pub mod pyconv;
pub mod pynum;

#[allow(unused_imports)]
use pynum::Num;

/// Map the recorded `JsonRpcError: <text>` prefix back to the original exception
/// class. The generic `named_error` below cannot do it: `JsonRpcError.__init__`
/// takes `(code, message, data)`, while the generated helper passes a single text.
/// This is a local patch to generated bindings; `refresh` overwrites it.
fn jsonrpc_error(text: &str) -> (i64, &str) {
    if text.starts_with("Parse error") {
        (-32700, text) // recorded-literal: protocol.py PARSE_ERROR
    } else if text.starts_with("Invalid Request") {
        (-32600, text) // recorded-literal: protocol.py INVALID_REQUEST
    } else if text.starts_with("Method not found") {
        (-32601, text) // recorded-literal: protocol.py METHOD_NOT_FOUND
    } else if text.starts_with("Invalid params") {
        (-32602, text) // recorded-literal: protocol.py INVALID_PARAMS
    } else {
        (-32603, text) // recorded-literal: protocol.py INTERNAL_ERROR
    }
}

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
        "JsonRpcError" => Python::attach(|py| {
            let class = py
                .import("zkc.transport.protocol")
                .ok()?
                .getattr("JsonRpcError")
                .ok()?;
            let (code, text) = jsonrpc_error(&text);
            let value = class.call1((code, text)).ok()?;
            Some(PyErr::from_value(value))
        })
        .unwrap_or_else(|| e::PyValueError::new_err(message)),
        _ => named_error(kind, &text).unwrap_or_else(|| e::PyValueError::new_err(message)),
    }
}

fn contract_snapshot_inner() -> Result<serde_json::Value, String> {
    let out = port::contract_snapshot()?;
    Ok(out)
}

/// `contract_snapshot`.
#[pyfunction]
#[pyo3(name = "contract_snapshot", signature = ())]
fn contract_snapshot(py: Python<'_>) -> PyResult<Py<PyAny>> {
    contract_snapshot_inner()
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn tool_schema_inner(name: String) -> Result<Option<serde_json::Value>, String> {
    let out = port::tool_schema(name)?;
    Ok(out)
}

/// `tool_schema`.
#[pyfunction]
#[pyo3(name = "tool_schema", signature = (name))]
fn tool_schema(py: Python<'_>, name: String) -> PyResult<Py<PyAny>> {
    tool_schema_inner(name)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn is_blacklisted_inner(name: String) -> Result<bool, String> {
    let out = port::is_blacklisted(name)?;
    Ok(out)
}

/// `is_blacklisted`.
#[pyfunction]
#[pyo3(name = "is_blacklisted", signature = (name))]
fn is_blacklisted(name: String) -> PyResult<bool> {
    is_blacklisted_inner(name).map_err(error)
}

fn is_allowlisted_inner(name: String) -> Result<bool, String> {
    let out = port::is_allowlisted(name)?;
    Ok(out)
}

/// `is_allowlisted`.
#[pyfunction]
#[pyo3(name = "is_allowlisted", signature = (name))]
fn is_allowlisted(name: String) -> PyResult<bool> {
    is_allowlisted_inner(name).map_err(error)
}

fn validate_arguments_inner(
    schema: Bound<'_, PyAny>,
    arguments: Bound<'_, PyAny>,
) -> Result<Option<String>, String> {
    let schema: serde_json::Value = crate::pyconv::FromPy::from_py(&schema)?;
    let arguments: serde_json::Value = crate::pyconv::FromPy::from_py(&arguments)?;
    let out = port::validate_arguments(schema, arguments)?;
    Ok(out)
}

/// `validate_arguments`.
#[pyfunction]
#[pyo3(name = "validate_arguments", signature = (schema, arguments))]
fn validate_arguments(
    schema: Bound<'_, PyAny>,
    arguments: Bound<'_, PyAny>,
) -> PyResult<Option<String>> {
    validate_arguments_inner(schema, arguments).map_err(error)
}

fn decode_message_inner(raw: String) -> Result<serde_json::Value, String> {
    let out = port::decode_message(raw)?;
    Ok(out)
}

/// `decode_message`.
#[pyfunction]
#[pyo3(name = "decode_message", signature = (raw))]
fn decode_message(py: Python<'_>, raw: String) -> PyResult<Py<PyAny>> {
    decode_message_inner(raw)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn encode_message_inner(obj: Bound<'_, PyAny>) -> Result<String, String> {
    let obj: serde_json::Value = crate::pyconv::FromPy::from_py(&obj)?;
    let out = port::encode_message(obj)?;
    Ok(out)
}

/// `encode_message`.
#[pyfunction]
#[pyo3(name = "encode_message", signature = (obj))]
fn encode_message(obj: Bound<'_, PyAny>) -> PyResult<String> {
    encode_message_inner(obj).map_err(error)
}

fn is_notification_inner(message: Bound<'_, PyAny>) -> Result<bool, String> {
    let message: serde_json::Value = crate::pyconv::FromPy::from_py(&message)?;
    let out = port::is_notification(message)?;
    Ok(out)
}

/// `is_notification`.
#[pyfunction]
#[pyo3(name = "is_notification", signature = (message))]
fn is_notification(message: Bound<'_, PyAny>) -> PyResult<bool> {
    is_notification_inner(message).map_err(error)
}

fn result_response_inner(
    request_id: Bound<'_, PyAny>,
    result: Bound<'_, PyAny>,
) -> Result<serde_json::Value, String> {
    let request_id: serde_json::Value = crate::pyconv::FromPy::from_py(&request_id)?;
    let result: serde_json::Value = crate::pyconv::FromPy::from_py(&result)?;
    let out = port::result_response(request_id, result)?;
    Ok(out)
}

/// `result_response`.
#[pyfunction]
#[pyo3(name = "result_response", signature = (request_id, result))]
fn result_response(
    py: Python<'_>,
    request_id: Bound<'_, PyAny>,
    result: Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    result_response_inner(request_id, result)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

fn error_response_inner(
    request_id: Bound<'_, PyAny>,
    code: i64,
    message: String,
    data: Option<Bound<'_, PyAny>>,
) -> Result<serde_json::Value, String> {
    let request_id: serde_json::Value = crate::pyconv::FromPy::from_py(&request_id)?;
    let data: Option<serde_json::Value> = match &data {
        None => None,
        Some(v) => Some(crate::pyconv::FromPy::from_py(v)?),
    };
    let out = port::error_response(request_id, code, message, data)?;
    Ok(out)
}

/// `error_response`.
#[pyfunction]
#[pyo3(name = "error_response", signature = (request_id, code, message, data=None))]
fn error_response(
    py: Python<'_>,
    request_id: Bound<'_, PyAny>,
    code: i64,
    message: String,
    data: Option<Bound<'_, PyAny>>,
) -> PyResult<Py<PyAny>> {
    error_response_inner(request_id, code, message, data)
        .map_err(error)
        .and_then(|v| crate::pyconv::ToPy::to_py(&v, py))
}

#[pymodule]
#[pyo3(name = "_native")]
fn native_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(contract_snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(tool_schema, m)?)?;
    m.add_function(wrap_pyfunction!(is_blacklisted, m)?)?;
    m.add_function(wrap_pyfunction!(is_allowlisted, m)?)?;
    m.add_function(wrap_pyfunction!(validate_arguments, m)?)?;
    m.add_function(wrap_pyfunction!(decode_message, m)?)?;
    m.add_function(wrap_pyfunction!(encode_message, m)?)?;
    m.add_function(wrap_pyfunction!(is_notification, m)?)?;
    m.add_function(wrap_pyfunction!(result_response, m)?)?;
    m.add_function(wrap_pyfunction!(error_response, m)?)?;
    Ok(())
}
