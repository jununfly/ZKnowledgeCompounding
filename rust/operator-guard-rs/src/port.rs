//! The Rust port of `spikes/spike-22-operator-guard/pure_bridge.py`.
//!
//! `_require_operator(operator: str | None) -> str` is the human-in-the-loop
//! guard from `src/zkc/tombstone.py` (ADR-0013): strip surrounding whitespace
//! and return the operator, or raise `ValueError` when empty/blank/None.
//! No dataclass / datetime / Storage / tuning seam — all JSON-native.

#![forbid(unsafe_code)]

/// Python `str.isspace()` set (29 chars). Rust `char::is_whitespace()` is the
/// Unicode White_Space property, which omits ASCII FS/GS/RS/US (`\x1c..\x1f`)
/// that Python treats as whitespace. Adding those four makes it character-for-
/// character identical to CPython's set, so `trim_matches` matches `str.strip()`.
fn py_isspace(c: char) -> bool {
    c.is_whitespace() || matches!(c, '\u{001c}' | '\u{001d}' | '\u{001e}' | '\u{001f}')
}

/// Port of `require_operator` (`spikes/spike-22-operator-guard/pure_bridge.py:31`,
/// original `src/zkc/tombstone.py::_require_operator`).
///
/// The error text is the ADR-0013 human-in-the-loop contract, recorded verbatim
/// from the Python original; it is a `recorded-literal`, not a CALIBRATED value.
pub fn require_operator(operator: serde_json::Value) -> Result<serde_json::Value, String> {
    let required_error =
        "ValueError: operator 必填且非空：墓碑标记/恢复是 zj 本人的人环操作，不得缺省"; // recorded-literal: ADR-0013 human-in-the-loop operator contract, truth source src/zkc/tombstone.py
    let text = match operator {
        serde_json::Value::String(s) => s,
        serde_json::Value::Null => return Err(required_error.to_string()), // `not None` is True in Python
        _ => return Err("TypeError: expected string or None".to_string()),
    };
    if text.is_empty() {
        return Err(required_error.to_string());
    }
    let stripped = text.trim_matches(py_isspace);
    if stripped.is_empty() {
        return Err(required_error.to_string());
    }
    Ok(serde_json::Value::String(stripped.to_string()))
}
