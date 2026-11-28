//! Hand-written glue (wire generated a stub in a newer call style the hand-merged
//! `mod.rs` does not use): `unit-mcp-exposure <fn> <json-array>`.
//!
//! Calls `mcp_exposure_rs::port::{attack_surface_table, entry_names}` — the MCP attack-surface
//! projection (ticket 46). Both are zero-argument deterministic functions; the recorded
//! `<json-array>` is empty. Neither raises, so no error-prefix handling.

use std::process::ExitCode;

use serde_json::Value;

use super::emit;

pub fn run(name: &str, _args: &[Value]) -> ExitCode {
    let result = match name {
        "attack_surface_table" => mcp_exposure_rs::port::attack_surface_table(),
        "entry_names" => mcp_exposure_rs::port::entry_names(),
        _ => return super::fail(format!("unknown mcp-exposure fn: {name}")),
    };
    emit(result)
}
