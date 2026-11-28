//! The Rust port of `spikes/spike-26-capture-profile/pure_bridge.py`.
//!
//! `validate_capture_profile(allowed, forbidden)` delegates the `CaptureProfile.__post_init__`
//! write-set invariant to the Python original: the profile is invalid when
//! `allowed_writes ∩ forbidden_writes` is non-empty, raising
//! `ValueError: capture profile 写集合自相矛盾：<sorted(overlap) as a Python list repr>`.
//! Otherwise it is valid and returns `true`.
//!
//! The overlap is computed with a `BTreeSet` (UTF-8 byte order == Python `str` code-point
//! order for these ASCII identifiers), so `sorted(overlap)` matches. The error string is
//! reproduced verbatim: `[` + each item single-quoted + joined by `", "` + `]`.

#![forbid(unsafe_code)]

use std::collections::BTreeSet;

use serde_json::Value;

fn as_set(value: &Value) -> Result<BTreeSet<String>, String> {
    let arr = value
        .as_array()
        .ok_or_else(|| "TypeError: capture profile write-set is not a list".to_string())?;
    let mut out = BTreeSet::new();
    for item in arr {
        let text = item
            .as_str()
            .ok_or_else(|| "TypeError: capture profile write-set items must be str".to_string())?;
        out.insert(text.to_string());
    }
    Ok(out)
}

/// Port of `validate_capture_profile` (`spikes/spike-26-capture-profile/pure_bridge.py:28`).
pub fn validate_capture_profile(allowed: Value, forbidden: Value) -> Result<Value, String> {
    let allowed = as_set(&allowed)?;
    let forbidden = as_set(&forbidden)?;

    let overlap: Vec<String> = allowed.intersection(&forbidden).cloned().collect(); // BTreeSet → sorted
    if overlap.is_empty() {
        return Ok(Value::Bool(true));
    }

    // Python `sorted(overlap)` list repr: ['a', 'b', ...]
    let inner = overlap
        .iter()
        .map(|s| format!("'{s}'"))
        .collect::<Vec<_>>()
        .join(", ");
    Err(format!(
        "ValueError: capture profile 写集合自相矛盾：[{inner}]"
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn disjoint_sets_are_valid() {
        assert_eq!(
            validate_capture_profile(json!(["node"]), json!(["meta_claim"])).unwrap(),
            Value::Bool(true)
        );
        assert_eq!(
            validate_capture_profile(json!([]), json!(["interval_adjustment"])).unwrap(),
            Value::Bool(true)
        );
    }

    #[test]
    fn overlap_raises_with_python_list_repr() {
        let err = validate_capture_profile(json!(["node", "meta_claim"]), json!(["meta_claim"]))
            .unwrap_err();
        assert_eq!(
            err,
            "ValueError: capture profile 写集合自相矛盾：['meta_claim']"
        );
        let err = validate_capture_profile(json!(["b", "a"]), json!(["a", "b"])).unwrap_err();
        assert_eq!(
            err,
            "ValueError: capture profile 写集合自相矛盾：['a', 'b']"
        );
    }
}
