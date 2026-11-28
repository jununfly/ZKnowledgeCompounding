//! Hand-written glue (wire generated a stub in a newer call style the hand-merged `mod.rs` does not
//! use): `unit-search-structured <fn> <json-array>`.
//!
//! Calls `search_structured_rs::port::filter_sort_nodes` — the structured filter/sort core of
//! `MemoryNodeRepository.search` (ticket 50 prereq). Eight positional args
//! (`nodes, track, q, decay_min, decay_max, include_archived, order, limit`). The port returns the
//! bare message (`invalid order: …`); the glue prefixes `ValueError: ` to match `oracle.py` (the
//! original raises `ValueError`). No other error path.

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit};

fn a(args: &[Value], i: usize) -> Result<Value, ExitCode> {
    arg_value(args, i)
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "filter_sort_nodes" => {
            let nodes = match a(args, 0) {
                Ok(v) => v,
                Err(code) => return code,
            };
            let track = match a(args, 1) {
                Ok(v) => v,
                Err(code) => return code,
            };
            let q = match a(args, 2) {
                Ok(v) => v,
                Err(code) => return code,
            };
            let decay_min = match a(args, 3) {
                Ok(v) => v,
                Err(code) => return code,
            };
            let decay_max = match a(args, 4) {
                Ok(v) => v,
                Err(code) => return code,
            };
            let include_archived = match a(args, 5) {
                Ok(v) => v,
                Err(code) => return code,
            };
            let order = match a(args, 6) {
                Ok(v) => v,
                Err(code) => return code,
            };
            let limit = match a(args, 7) {
                Ok(v) => v,
                Err(code) => return code,
            };
            search_structured_rs::port::filter_sort_nodes(
                nodes,
                track,
                q,
                decay_min,
                decay_max,
                include_archived,
                order,
                limit,
            )
        }
        _ => return super::fail(format!("unknown search-structured fn: {name}")),
    };
    emit(result.map_err(|message| format!("ValueError: {message}")))
}
