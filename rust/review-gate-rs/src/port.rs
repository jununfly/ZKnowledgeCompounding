//! The Rust port of `spikes/spike-27-review-gate/pure_bridge.py`.
//!
//! `review_payload_gate(outcome, content, stale_branch)` exposes only the **Human-only
//! payload gate** of `zkc.review.decide_review` (ADR-0011/0012 HITL contract). The gate is
//! a pure function of three JSON scalars: it accepts a combination (returns `true`) or
//! raises `ValueError` with the original's exact message. The Storage-bound orchestration
//! that follows (OCC version writes, archive, attention accumulation, `datetime.now`) stays
//! in Python — this slice never claims to port it (Q5-class encoding seam, see finding 26).
//!
//! The five error messages are `// recorded-literal:` quotes from `zkc/review.py`; the
//! original (the spike wrapper) spells out none of them — they are the Python HITL contract.

#![forbid(unsafe_code)]

use serde_json::{Value, json};

/// `decide_review`: changed requires a content payload.
const CHANGED_NEEDS_CONTENT: &str =
    "changed 需要内容载荷（--content），且只能由人工逐条给出；缺失即拒收"; // recorded-literal: zkc/review.py decide_review
/// `decide_review`: stale needs a legal branch cover|purge.
const STALE_NEEDS_BRANCH: &str =
    "stale 需要 --stale-branch cover|purge，且只能由人工逐条给出；缺失或非法即拒收，绝不默认 purge"; // recorded-literal: zkc/review.py decide_review
/// `decide_review`: stale cover requires a content payload.
const STALE_COVER_NEEDS_CONTENT: &str = "stale cover 需要内容载荷（--content）；缺失即拒收"; // recorded-literal: zkc/review.py decide_review
/// `decide_review`: still_valid / browse must not carry payload.
const NON_CONTENT_REJECTS_PAYLOAD: &str =
    " 不接受 --content / --stale-branch；请仅用于 changed / stale"; // recorded-literal: zkc/review.py decide_review (suffix; outcome prefixed)

/// Python falsiness for a `str | None` payload value: `None` or `""` are both "absent".
fn not_present(value: &Value) -> bool {
    match value {
        Value::Null => true,
        Value::String(s) => s.is_empty(),
        _ => false,
    }
}

/// Python `x is not None` for a `str | None` value (note: `""` counts as present here).
fn is_not_none(value: &Value) -> bool {
    !value.is_null()
}

/// Port of `review_payload_gate` (`spikes/spike-27-review-gate/pure_bridge.py:40`).
pub fn review_payload_gate(
    outcome: Value,
    content: Value,
    stale_branch: Value,
) -> Result<Value, String> {
    // `outcome` is always a str in the original (dispatch keys); reject a non-str like Python's
    // string comparison simply falling through to the unknown-outcome branch.
    let outcome = outcome.as_str().unwrap_or_default();

    match outcome {
        "changed" => {
            if not_present(&content) {
                return Err(CHANGED_NEEDS_CONTENT.to_string());
            }
        }
        "stale" => {
            let branch = stale_branch.as_str();
            if !matches!(branch, Some("cover") | Some("purge")) {
                return Err(STALE_NEEDS_BRANCH.to_string());
            }
            if branch == Some("cover") && not_present(&content) {
                return Err(STALE_COVER_NEEDS_CONTENT.to_string());
            }
        }
        "still_valid" | "browse" => {
            if is_not_none(&content) || is_not_none(&stale_branch) {
                return Err(format!("{outcome}{NON_CONTENT_REJECTS_PAYLOAD}"));
            }
        }
        _ => return Err(format!("unknown outcome: {outcome}")),
    }

    Ok(json!(true))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn accepts_valid_combinations() {
        assert_eq!(
            review_payload_gate(json!("changed"), json!("x"), Value::Null).unwrap(),
            json!(true)
        );
        assert_eq!(
            review_payload_gate(json!("stale"), Value::Null, json!("purge")).unwrap(),
            json!(true)
        );
        assert_eq!(
            review_payload_gate(json!("still_valid"), Value::Null, Value::Null).unwrap(),
            json!(true)
        );
    }

    #[test]
    fn rejects_with_original_messages() {
        assert_eq!(
            review_payload_gate(json!("changed"), Value::Null, Value::Null).unwrap_err(),
            CHANGED_NEEDS_CONTENT
        );
        // empty string is falsy → still rejected for changed
        assert!(review_payload_gate(json!("changed"), json!(""), Value::Null).is_err());
        assert!(review_payload_gate(json!("stale"), Value::Null, json!("bogus")).is_err());
        assert!(review_payload_gate(json!("stale"), Value::Null, json!("cover")).is_err());
        // browse carrying payload → rejected (is not None, even empty string)
        assert!(review_payload_gate(json!("browse"), json!("x"), Value::Null).is_err());
        assert_eq!(
            review_payload_gate(json!("weird"), Value::Null, Value::Null).unwrap_err(),
            "unknown outcome: weird"
        );
    }
}
