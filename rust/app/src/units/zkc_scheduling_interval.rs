//! Wire-generated glue, filled in by hand: `unit-scheduling <fn> <json-array>`.
//! Calls `zkc_scheduling_interval_rs::port` for the 6 recorded interval-math
//! functions from `src/zkc/scheduling.py` through the spike-09 alias adapter.
//! Keyword-only `human` is accepted as the third positional argument here and
//! forwarded to the Rust port, matching the oracle's recorded protocol.

use std::process::ExitCode;

use serde_json::{Value, json};

use super::{arg_f64, arg_i64, arg_str, arg_value, emit, fail};

fn arg_bool(values: &[Value], index: usize) -> Result<bool, ExitCode> {
    values
        .get(index)
        .and_then(Value::as_bool)
        .ok_or_else(|| fail(format!("arg {index}: expected boolean")))
}

fn arg_opt_str(values: &[Value], index: usize) -> Result<Option<String>, ExitCode> {
    match arg_value(values, index)? {
        Value::Null => Ok(None),
        Value::String(text) => Ok(Some(text)),
        _ => Err(fail(format!("arg {index}: expected string or null"))),
    }
}

fn arg_opt_f64(values: &[Value], index: usize) -> Result<Option<f64>, ExitCode> {
    match arg_value(values, index)? {
        Value::Null => Ok(None),
        value => value
            .as_f64()
            .map(Some)
            .ok_or_else(|| fail(format!("arg {index}: expected number or null"))),
    }
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "extract_horizon_days" => {
            let text = match arg_opt_str(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_scheduling_interval_rs::port::extract_horizon_days(text).map(|v| json!(v))
        }
        "clamp_days" => {
            let days = match arg_f64(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_scheduling_interval_rs::port::clamp_days(days).map(|v| json!(v))
        }
        "baseline_for_signals" => {
            let track = match arg_str(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let archived = match arg_bool(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let title = match arg_str(args, 2) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let content = match arg_opt_str(args, 3) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let captured = match arg_bool(args, 4) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let self_loop_count = match arg_i64(args, 5) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let higher_dim_count = match arg_i64(args, 6) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let conn_count = match arg_i64(args, 7) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_scheduling_interval_rs::port::baseline_for_signals(
                track,
                archived,
                title,
                content,
                captured,
                self_loop_count,
                higher_dim_count,
                conn_count,
            )
        }
        "classify_review" => {
            let decay = match arg_f64(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_scheduling_interval_rs::port::classify_review(decay).map(|v| json!(v))
        }
        "adapt_interval_math" => {
            let old_days = match arg_f64(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let verdict = match arg_str(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let human = match arg_bool(args, 2) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_scheduling_interval_rs::port::adapt_interval_math(old_days, verdict, human)
        }
        "l2_target" => {
            let budget = match arg_opt_f64(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let confidence = match arg_str(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_scheduling_interval_rs::port::l2_target(budget, confidence).map(|v| json!(v))
        }
        _ => return fail(format!("unknown scheduling fn: {name}")),
    };
    emit(result)
}
