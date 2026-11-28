//! Hand-written glue (wire generated the stub): `unit-telemetry-validation <fn> <json-array>`.
//! Calls `telemetry_validation_rs::port` for the single recorded function from
//! `src/zkc/r14_telemetry.py::_validate_report` through the spike-23 alias.
//!
//! No encoding seam: the sole argument is a plain JSON object (`dict`) and the
//! port returns `Result<Value, String>` whose error text already carries the
//! `ValueError: ` prefix, matching the oracle verbatim. Success is `null`.
//! This is the R14 telemetry field-presence gate; the three field names and
//! message texts are `recorded-literal` in the port, not CALIBRATED values.

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit};

fn take(args: &[Value], index: usize) -> Result<Value, ExitCode> {
    arg_value(args, index)
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "validate_report" => {
            let report = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            telemetry_validation_rs::port::validate_report(report)
        }
        _ => return super::fail(format!("unknown telemetry-validation fn: {name}")),
    };
    emit(result)
}
