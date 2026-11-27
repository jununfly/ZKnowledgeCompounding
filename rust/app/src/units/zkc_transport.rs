//! Wire-generated glue, filled in by hand: `unit-transport <fn> <json-array>`.
//! Calls `zkc_transport_rs::port` for the pure-function slice recorded from
//! `src/zkc/transport/`. The kill switch is handled by `super::dispatch`.

use std::process::ExitCode;

use serde_json::{Value, json};

use super::{arg_i64, arg_str, arg_value, emit, fail};

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "contract_snapshot" => zkc_transport_rs::port::contract_snapshot().map(|v| json!(v)),
        "tool_schema" => {
            let value = match arg_str(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_transport_rs::port::tool_schema(value).map(|v| json!(v))
        }
        "is_blacklisted" => {
            let value = match arg_str(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_transport_rs::port::is_blacklisted(value).map(|v| json!(v))
        }
        "is_allowlisted" => {
            let value = match arg_str(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_transport_rs::port::is_allowlisted(value).map(|v| json!(v))
        }
        "validate_arguments" => {
            let schema = match arg_value(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let arguments = match arg_value(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_transport_rs::port::validate_arguments(schema, arguments).map(|v| json!(v))
        }
        "decode_message" => {
            let raw = match arg_str(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_transport_rs::port::decode_message(raw).map(|v| json!(v))
        }
        "encode_message" => {
            let obj = match arg_value(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_transport_rs::port::encode_message(obj).map(|v| json!(v))
        }
        "is_notification" => {
            let message = match arg_value(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_transport_rs::port::is_notification(message).map(|v| json!(v))
        }
        "result_response" => {
            let id = match arg_value(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let result = match arg_value(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            zkc_transport_rs::port::result_response(id, result).map(|v| json!(v))
        }
        "error_response" => {
            let id = match arg_value(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let code = match arg_i64(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let message = match arg_str(args, 2) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let data = args.get(3).cloned();
            zkc_transport_rs::port::error_response(id, code, message, data).map(|v| json!(v))
        }
        _ => return fail(format!("unknown transport fn: {name}")),
    };
    emit(result)
}
