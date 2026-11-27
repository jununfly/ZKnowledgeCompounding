//! Hand-written glue (wire generated the stub): `unit-routing <fn> <json-array>`.
//! Calls `zkc_routing_tfidf_rs::port` for the 3 recorded lexical TF-IDF functions
//! from `src/zkc/routing.py` through the spike-15 alias adapter.
//! Values stay as JSON end to end, so the port owns every decision (including
//! its error text); no second encoding layer is introduced here.

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit};

fn take(args: &[Value], index: usize) -> Result<Value, ExitCode> {
    arg_value(args, index)
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "tokenize" => zkc_routing_tfidf_rs::port::tokenize(match take(args, 0) {
            Ok(value) => value,
            Err(code) => return code,
        }),
        "tfidf_vector" => {
            let tokens = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let idf = match take(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_routing_tfidf_rs::port::tfidf_vector(tokens, idf)
        }
        "cosine" => {
            let a = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let b = match take(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_routing_tfidf_rs::port::cosine(a, b)
        }
        _ => return super::fail(format!("unknown routing fn: {name}")),
    };
    emit(result)
}
