//! Hand-written glue (wire generated a stub in a newer call style the hand-merged
//! `mod.rs` does not use): `unit-review-gate <fn> <json-array>`.
//!
//! Calls `review_gate_rs::port::review_payload_gate` — the Human-only payload gate of
//! `zkc.review.decide_review` (ticket 49). Single recorded function; three positional
//! `Value` args (`outcome`, `content`, `stale_branch`, the last two `null` when absent).
//! No error-prefix seam in the port; the front door has no PyO3 wrapper to add the
//! exception class, so the glue prefixes errors with `ValueError: ` to match `oracle.py`
//! (every gate rejection in `decide_review` is a `ValueError`). The decision text is untouched.

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit};

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "review_payload_gate" => {
            let outcome = match arg_value(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let content = match arg_value(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let stale_branch = match arg_value(args, 2) {
                Ok(value) => value,
                Err(code) => return code,
            };
            review_gate_rs::port::review_payload_gate(outcome, content, stale_branch)
        }
        _ => return super::fail(format!("unknown review-gate fn: {name}")),
    };
    emit(result.map_err(|message| format!("ValueError: {message}")))
}
