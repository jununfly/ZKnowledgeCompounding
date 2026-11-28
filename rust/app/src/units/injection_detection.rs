//! Hand-written glue (wire generated the stub): `unit-injection <fn> <json-array>`.
//! Calls `injection_detection_rs::port` for the single recorded function from
//! `src/zkc/mcp/injection.py::detect_injection_markers` through the spike-20 alias.
//!
//! No error-prefix seam here (unlike `unit-distill`): the port's only error text is
//! the plain `AttributeError: ...` for a non-string argument, which the oracle also
//! emits verbatim. Recorded cases are all strings, so that branch is defensive only.
//! The single `text` argument is a plain positional `Value`.

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit, fail};

fn take(args: &[Value], index: usize) -> Result<Value, ExitCode> {
    arg_value(args, index)
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "detect_injection_markers" => {
            let text = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            injection_detection_rs::port::detect_injection_markers(text)
        }
        _ => return fail(format!("unknown injection fn: {name}")),
    };
    emit(result)
}
