//! Hand-written glue (wire generated a stub in a newer call style the hand-merged `mod.rs` does not
//! use): `unit-search-embedding <fn> <json-array>`.
//!
//! Calls `search_embedding_rs::port::search_embedding_knn` — the cosine top-k of
//! `MemoryNodeRepository.search_by_embedding` (ticket 50 prereq). Five positional args
//! (`nodes, vector, k, include_archived, column`). The port returns the bare message
//! (`invalid embedding column: …`); the glue prefixes `ValueError: ` to match `oracle.py`.

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit};

fn a(args: &[Value], i: usize) -> Result<Value, ExitCode> {
    arg_value(args, i)
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "search_embedding_knn" => {
            let nodes = match a(args, 0) {
                Ok(v) => v,
                Err(code) => return code,
            };
            let vector = match a(args, 1) {
                Ok(v) => v,
                Err(code) => return code,
            };
            let k = match a(args, 2) {
                Ok(v) => v,
                Err(code) => return code,
            };
            let include_archived = match a(args, 3) {
                Ok(v) => v,
                Err(code) => return code,
            };
            let column = match a(args, 4) {
                Ok(v) => v,
                Err(code) => return code,
            };
            search_embedding_rs::port::search_embedding_knn(nodes, vector, k, include_archived, column)
        }
        _ => return super::fail(format!("unknown search-embedding fn: {name}")),
    };
    emit(result.map_err(|message| format!("ValueError: {message}")))
}
