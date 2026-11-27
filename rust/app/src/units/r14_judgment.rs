//! Hand-written glue (wire generated the stub): `unit-r14 <fn> <json-array>`.
//! Calls `r14_judgment_rs::port` for the single recorded function from
//! `src/zkc/cross_source.py::judge_r14` through the spike-18 alias adapter.
//!
//! No error-prefix seam here (unlike `unit-distill`): the port's errors are
//! plain `TypeError: ...` texts, which match the oracle verbatim.

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit, fail};

fn take(args: &[Value], index: usize) -> Result<Value, ExitCode> {
    arg_value(args, index)
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "judge_r14" => {
            let runs = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let min_runs = match take(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            r14_judgment_rs::port::judge_r14(runs, min_runs)
        }
        _ => return fail(format!("unknown r14 fn: {name}")),
    };
    emit(result)
}
