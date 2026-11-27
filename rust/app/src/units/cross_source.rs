//! Hand-written glue (wire generated the stub): `unit-cross-source <fn> <json-array>`.
//! Calls `cross_source_rs::port` for the two recorded functions from
//! `src/zkc/cross_source.py` through the spike-16 alias adapter.
//! Values stay as JSON end to end, so the port owns every decision (including
//! its all-collapsed error text); no second encoding layer is introduced here.

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit};

fn take(args: &[Value], index: usize) -> Result<Value, ExitCode> {
    arg_value(args, index)
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "count_cross_source" => cross_source_rs::port::count_cross_source(match take(args, 0) {
            Ok(value) => value,
            Err(code) => return code,
        }),
        "enforce_citations" => {
            let artifact = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let source_ids = match take(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            cross_source_rs::port::enforce_citations(artifact, source_ids)
        }
        _ => return super::fail(format!("unknown cross-source fn: {name}")),
    };
    emit(result)
}
