//! Wire-generated glue, filled in by hand: `unit-expiry <fn> <json-array>`.
//! Calls `zkc_expiry_pure_rs::port` for the `route_expired` decision table
//! recorded from `src/zkc/expiry.py` through the spike-08 snapshot adapter.

use std::process::ExitCode;

use serde_json::{Value, json};

use super::{arg_f64, arg_str, arg_values, emit, fail};

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "route_decision" => {
            let node_id = match arg_str(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let rows = match arg_values(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let pressure = match arg_f64(args, 2) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_expiry_pure_rs::port::route_decision(node_id, rows, pressure)
                .map(|value| json!(value))
        }
        _ => return fail(format!("unknown expiry fn: {name}")),
    };
    emit(result)
}
