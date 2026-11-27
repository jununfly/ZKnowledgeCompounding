//! Rust port of `src/zkc/cross_source.py`'s literal citation-enforcement layer,
//! recorded through `spikes/spike-16-cross-source-enforcement/pure_bridge.py`
//! (process-only alias). The Python original is the recording oracle.
//!
//! Proof boundary: `count_cross_source` and `enforce_citations` take JSON
//! scalars / string lists / string-keyed objects. `CrossSourceOperator` (RCS
//! funnel, tuning thresholds, bounded completion loop, R14 telemetry),
//! pydantic models, LLM callables and Storage stay in Python. This is not a
//! cross-source quality gate or a hallucination safety decision.
//!
//! Every policy literal below is recorded from the original and marked
//! `recorded-literal`; none is promoted to a tuned value here.

#![forbid(unsafe_code)]

use serde_json::{Map, Value, json};
use std::collections::HashSet;

fn want_object<'a>(value: &'a Value, label: &str) -> Result<&'a Map<String, Value>, String> {
    value
        .as_object()
        .ok_or_else(|| format!("{label}: expected object"))
}

fn want_array<'a>(value: &'a Value, label: &str) -> Result<&'a Vec<Value>, String> {
    value
        .as_array()
        .ok_or_else(|| format!("{label}: expected array"))
}

/// `claim.get("evidence_ids", [])` from the original. Missing key means no
/// citations; a non-array or non-string member is outside the recorded domain.
fn evidence_ids(claim: &Map<String, Value>) -> Result<Vec<&str>, String> {
    match claim.get("evidence_ids") {
        None => Ok(Vec::new()),
        Some(value) => want_array(value, "evidence_ids")?
            .iter()
            .map(|item| {
                item.as_str()
                    .ok_or_else(|| "evidence_ids[]: expected string".to_string())
            })
            .collect(),
    }
}

/// Port of `count_cross_source` (`src/zkc/cross_source.py:111`).
///
/// A claim is cross-source only when it cites at least two **distinct** ids;
/// repeated ids collapse through the source's `set(...)` semantics.
pub fn count_cross_source(claims: Value) -> Result<Value, String> {
    let claims = want_array(&claims, "claims")?;
    let mut total = 0usize;
    for claim in claims {
        let claim = want_object(claim, "claims[]")?;
        let distinct: HashSet<&str> = evidence_ids(claim)?.into_iter().collect();
        if distinct.len() >= 2 {
            total += 1;
        }
    }
    Ok(json!(total))
}

/// Port of `enforce_citations` (`src/zkc/cross_source.py:83`).
///
/// `source_ids` is a JSON array at the bridge seam; the process-only alias
/// converts it back to the original's `set[str]` before delegating. Membership
/// filtering, claim dropping, sorted union and the all-collapsed rejection are
/// the original's decisions, reproduced here verbatim.
///
/// `serde_json`'s `preserve_order` feature keeps the input artifact's top-level
/// and per-claim key order, so `dict(artifact, ...)` overrides land in the same
/// positions as in Python. New keys are appended in call order.
pub fn enforce_citations(artifact: Value, source_ids: Value) -> Result<Value, String> {
    let mut artifact = want_object(&artifact, "artifact")?.clone();
    let mut sources = HashSet::new();
    for item in want_array(&source_ids, "source_ids")? {
        sources.insert(
            item.as_str()
                .ok_or_else(|| "source_ids[]: expected string".to_string())?,
        );
    }

    let claims_value = artifact.get("claims").cloned().unwrap_or_else(|| json!([]));
    let claims = want_array(&claims_value, "claims")?;
    let mut kept: Vec<Value> = Vec::new();
    let mut all_refs = HashSet::new();
    let mut dropped = 0usize;

    for claim in claims {
        let claim = want_object(claim, "claims[]")?;
        let valid: Vec<&str> = evidence_ids(claim)?
            .into_iter()
            .filter(|id| sources.contains(id))
            .collect();
        if valid.is_empty() {
            dropped += 1;
            continue;
        }
        for id in &valid {
            all_refs.insert((*id).to_string());
        }
        let mut surviving = claim.clone();
        surviving.insert("evidence_ids".to_string(), json!(valid));
        kept.push(Value::Object(surviving));
    }

    let total = dropped + kept.len();
    if kept.is_empty() {
        return Err(format!(
            "ValueError: artifact rejected: all {total} claims lost their citations (hallucinated provenance)" // recorded-literal: cross_source.py all-collapsed ValueError text
        ));
    }

    let mut evidence_refs: Vec<String> = all_refs.into_iter().collect();
    evidence_refs.sort(); // Python sorts by code point; UTF-8 byte order agrees.
    artifact.insert("claims".to_string(), json!(kept));
    artifact.insert("evidence_refs".to_string(), json!(evidence_refs));
    artifact.insert("_dropped_claims".to_string(), json!(dropped));
    Ok(Value::Object(artifact))
}
