//! Hand-written glue (wire generated a stub in a newer call style the hand-merged
//! `mod.rs` does not use): `unit-capture-profile <fn> <json-array>`.
//!
//! Calls `capture_profile_rs::port::validate_capture_profile` — the write-set overlap
//! invariant of `zkc.mcp.capture.CaptureProfile.__post_init__` (ticket 48). The port already
//! returns the original's exact `ValueError: ...` text (it reproduces Python's list-repr of the
//! sorted overlap), so the glue emits it verbatim — no prefix normalization needed.

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit};

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "validate_capture_profile" => {
            let allowed = match arg_value(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let forbidden = match arg_value(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            capture_profile_rs::port::validate_capture_profile(allowed, forbidden)
        }
        _ => return super::fail(format!("unknown capture-profile fn: {name}")),
    };
    emit(result)
}
