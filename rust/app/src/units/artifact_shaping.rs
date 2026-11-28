//! Hand-written glue (wire generated the stub): `unit-artifact-shaping <fn> <json-array>`.
//! Calls `artifact_shaping_rs::port` for the single recorded function from
//! `src/zkc/cross_source.py::to_modeling_artifact` through the spike-19 alias adapter.
//!
//! No error-prefix seam here (unlike `unit-distill`): the port's errors are plain
//! `ValueError: ...` / `TypeError: ...` texts, which match the oracle verbatim.
//! Both `artifact` and `produced_by` are plain positional `Value`s (the original's
//! keyword-only `produced_by` is already restored by the spike-19 alias).

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit, fail};

fn take(args: &[Value], index: usize) -> Result<Value, ExitCode> {
    arg_value(args, index)
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "to_modeling_artifact" => {
            let artifact = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let produced_by = match take(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            artifact_shaping_rs::port::to_modeling_artifact(artifact, produced_by)
        }
        _ => return fail(format!("unknown artifact-shaping fn: {name}")),
    };
    emit(result)
}
