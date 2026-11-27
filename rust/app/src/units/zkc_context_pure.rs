//! Wire-generated glue, filled in by hand: `unit-context <fn> <json-array>`.
//! Calls `zkc_context_pure_rs::port` for the two helpers recorded from
//! `src/zkc/context.py` through the spike-06 public aliases.

use std::process::ExitCode;

use serde_json::{Value, json};

use super::{arg_i64, arg_str, arg_strings, emit, fail};

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "clean_title" => {
            let raw = match arg_str(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_context_pure_rs::port::clean_title(raw).map(|value| json!(value))
        }
        "fallback_name" => {
            let member_texts = match arg_strings(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let n_members = match arg_i64(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_context_pure_rs::port::fallback_name(member_texts, n_members)
                .map(|value| json!(value))
        }
        _ => return fail(format!("unknown context fn: {name}")),
    };
    emit(result)
}
