//! Hand-written glue (wire generated the stub): `unit-percentile <fn> <json-array>`.
//! Calls `percentile_rs::port` for the single recorded function from
//! `src/zkc/scheduling.py::_percentile` through the spike-21 alias.
//!
//! No error-prefix seam here (unlike `unit-distill`): the port returns plain
//! `IndexError: ...` / `TypeError: ...` text, which the oracle emits verbatim.
//! The two arguments (`values` list, `q` scalar) are plain positional `Value`s.
//! The recording bridge's `$float`/`$int` marker decoding lives in the port's
//! `as_f64`, so both recorded-marker form and plain-JSON numbers are accepted.

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit};

fn take(args: &[Value], index: usize) -> Result<Value, ExitCode> {
    arg_value(args, index)
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "percentile" => {
            let values = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let q = match take(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            percentile_rs::port::percentile(values, q)
        }
        _ => return super::fail(format!("unknown percentile fn: {name}")),
    };
    emit(result)
}
