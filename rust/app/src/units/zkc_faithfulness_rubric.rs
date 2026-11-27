//! Hand-written glue (wire generated the stub): `unit-faithfulness <fn> <json-array>`.
//! Calls `zkc_faithfulness_rubric_rs::port` for the 7 recorded literal-rubric
//! functions from `src/zkc/faithfulness.py` through the spike-10 alias adapter.
//! Values stay as JSON scalars / strings / string lists end to end, so the
//! port owns every decision (including its error text).

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_i64, arg_value, emit};

fn take(args: &[Value], index: usize) -> Result<Value, ExitCode> {
    arg_value(args, index)
}

fn take_i64(args: &[Value], index: usize) -> Result<i64, ExitCode> {
    arg_i64(args, index)
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "normalize" => zkc_faithfulness_rubric_rs::port::normalize(match take(args, 0) {
            Ok(value) => value,
            Err(code) => return code,
        }),
        "ngrams" => {
            let text = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            // The original has `n=3`; keep the same default when the caller omits it.
            let n = if args.len() > 1 {
                match take_i64(args, 1) {
                    Ok(value) => value,
                    Err(code) => return code,
                }
            } else {
                3
            };
            zkc_faithfulness_rubric_rs::port::ngrams(text, n)
        }
        "lcs_length" => {
            let a = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let b = match take(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_faithfulness_rubric_rs::port::lcs_length(a, b)
        }
        "verbatim_rate" | "overlap" | "rubric_flags" => {
            let claim = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let sources = match take(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            match name {
                "verbatim_rate" => zkc_faithfulness_rubric_rs::port::verbatim_rate(claim, sources),
                "overlap" => zkc_faithfulness_rubric_rs::port::overlap(claim, sources),
                _ => zkc_faithfulness_rubric_rs::port::rubric_flags(claim, sources),
            }
        }
        "is_forced" => zkc_faithfulness_rubric_rs::port::is_forced(match take(args, 0) {
            Ok(value) => value,
            Err(code) => return code,
        }),
        _ => return super::fail(format!("unknown faithfulness fn: {name}")),
    };
    emit(result)
}
