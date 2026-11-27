//! Hand-written glue (wire generated the stub): `unit-distill <fn> <json-array>`.
//! Calls `distill_parse_rs::port` for the four recorded functions from
//! `src/zkc/distill.py` through the spike-17 alias adapter.
//!
//! The port returns a dotted exception kind (`zkc.distill.DistillationError`)
//! so the generated PyO3 binding can reconstruct the custom Python class. At
//! this front door there is no PyO3 layer, so the dotted prefix is stripped to
//! match the oracle's `<ClassName>: <text>` output. This is an encoding seam;
//! the decision text itself is untouched.

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit, fail};

fn take(args: &[Value], index: usize) -> Result<Value, ExitCode> {
    arg_value(args, index)
}

fn normalize_error(message: String) -> String {
    if let Some(rest) = message.strip_prefix("zkc.distill.") {
        rest.to_string()
    } else {
        message
    }
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "extract_json" => distill_parse_rs::port::extract_json(match take(args, 0) {
            Ok(value) => value,
            Err(code) => return code,
        }),
        "parse_json_output" => {
            let raw = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let sources = match take(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            distill_parse_rs::port::parse_json_output(raw, sources)
        }
        "parse_llm_output" => {
            let raw = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let sources = match take(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            distill_parse_rs::port::parse_llm_output(raw, sources)
        }
        "validate_result" => distill_parse_rs::port::validate_result(match take(args, 0) {
            Ok(value) => value,
            Err(code) => return code,
        }),
        _ => return fail(format!("unknown distill fn: {name}")),
    };
    emit(result.map_err(normalize_error))
}
