//! Hand-written glue (wire generated the stub): `unit-operator-guard <fn> <json-array>`.
//! Calls `operator_guard_rs::port` for the single recorded function from
//! `src/zkc/tombstone.py::_require_operator` through the spike-22 alias.
//!
//! No encoding seam: the sole argument is a plain `Value` (`str | None`) and the
//! port returns `Result<Value, String>` whose error text already carries the
//! `ValueError: ` / `TypeError: ` prefix, matching the oracle verbatim. This is
//! the ADR-0013 human-in-the-loop guard; the Chinese contract text is a
//! `recorded-literal` in the port, not a CALIBRATED value.

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit};

fn take(args: &[Value], index: usize) -> Result<Value, ExitCode> {
    arg_value(args, index)
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "require_operator" => {
            let operator = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            operator_guard_rs::port::require_operator(operator)
        }
        _ => return super::fail(format!("unknown operator-guard fn: {name}")),
    };
    emit(result)
}
