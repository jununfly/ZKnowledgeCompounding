//! The Rust port of `spikes/spike-19-artifact-shaping/pure_bridge.py`.
//!
//! `to_modeling_artifact` is a pure dict -> ModelingArtifact shaping: title/kind
//! from the artifact dict (default ""), body = full dict minus `_`-prefixed
//! internal keys and the promoted `evidence_refs` column, evidence_refs str ->
//! canonical UUID, produced_by carried through. All thresholds/defaults here
//! are recorded literals from the original, never promoted to CALIBRATED.

#![forbid(unsafe_code)]

use serde_json::{Map, Value, json};

/// `UUID(str(e))` canonicalization: drop hyphens, require 32 hex digits, emit
/// lowercase hyphenated form (same as expiry-pure-rs / distill-parse-rs).
fn canonical_uuid(raw: &str) -> Option<String> {
    let compact: String = raw
        .chars()
        .filter(|c| *c != '-')
        .flat_map(char::to_lowercase)
        .collect();
    if compact.len() != 32 || !compact.bytes().all(|b| b.is_ascii_hexdigit()) {
        return None;
    }
    Some(format!(
        "{}-{}-{}-{}-{}",
        &compact[0..8],
        &compact[8..12],
        &compact[12..16],
        &compact[16..20],
        &compact[20..32]
    ))
}

/// Port of `to_modeling_artifact` (`spikes/spike-19-artifact-shaping/pure_bridge.py:65`).
pub fn to_modeling_artifact(artifact: Value, produced_by: Value) -> Result<Value, String> {
    let obj = artifact
        .as_object()
        .ok_or_else(|| "TypeError: artifact must be a dict".to_string())?;

    let title = obj
        .get("title")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let kind = obj
        .get("kind")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();

    // body: preserve insertion order, drop underscore-prefixed internal keys
    // and the promoted `evidence_refs` column (Python dict comprehension order).
    let mut body = Map::new();
    for (key, value) in obj {
        if key.starts_with('_') || key == "evidence_refs" {
            continue;
        }
        body.insert(key.clone(), value.clone());
    }

    // evidence_refs: str -> canonical UUID; invalid text -> original's ValueError.
    let mut refs = Vec::new();
    if let Some(list) = obj.get("evidence_refs").and_then(Value::as_array) {
        for item in list {
            let raw = item.as_str().ok_or_else(|| {
                "AttributeError: 'int' object has no attribute 'replace'".to_string()
            })?;
            let canonical = canonical_uuid(raw).ok_or_else(|| {
                "ValueError: badly formed hexadecimal UUID string".to_string() // recorded-literal: CPython UUID error text
            })?;
            refs.push(Value::String(canonical));
        }
    }

    // produced_by is carried through verbatim: the original assigns it to the
    // dataclass field without coercion (str stays str, None stays None).
    Ok(json!({
        "id": Value::Null,
        "title": title,
        "kind": kind,
        "body": Value::Object(body),
        "evidence_refs": Value::Array(refs),
        "produced_by": produced_by,
        "revises": Value::Null,
        "created_at": Value::Null,
    }))
}
