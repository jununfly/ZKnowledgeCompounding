//! The Rust port of `spikes/spike-20-injection-detection/pure_bridge.py`.
//!
//! `detect_injection_markers` is a pure `str -> List[str]` detector: lowercase the
//! input, then return the markers from the source's `INJECTION_MARKERS` tuple that
//! occur as substrings, in declaration order and deduplicated. All 15 marker texts
//! are recorded literals from the Python security contract (ADR-0004 + injection
//! phrases) — never promoted to CALIBRATED, never a new policy source.

#![forbid(unsafe_code)]

use serde_json::{Value, json};

/// The source's `INJECTION_MARKERS`, in declaration order (lower-cased).
/// Each text is a recorded literal, not a tunable threshold.
const INJECTION_MARKERS: &[&str] = &[
    "distill/trigger", // recorded-literal: injection.py INJECTION_MARKERS (ADR-0004 blacklist)
    "interval_adjustment", // recorded-literal: injection.py INJECTION_MARKERS (ADR-0004 blacklist)
    "meta_claim",      // recorded-literal: injection.py INJECTION_MARKERS (ADR-0004 blacklist)
    "history/delete",  // recorded-literal: injection.py INJECTION_MARKERS (ADR-0004 blacklist)
    "history/update",  // recorded-literal: injection.py INJECTION_MARKERS (ADR-0004 blacklist)
    "ignore previous instructions", // recorded-literal: injection.py INJECTION_MARKERS (prompt-injection phrase)
    "ignore all previous", // recorded-literal: injection.py INJECTION_MARKERS (prompt-injection phrase)
    "忽略之前的指令", // recorded-literal: injection.py INJECTION_MARKERS (prompt-injection phrase)
    "忽略上述",       // recorded-literal: injection.py INJECTION_MARKERS (prompt-injection phrase)
    "忽略前面",       // recorded-literal: injection.py INJECTION_MARKERS (prompt-injection phrase)
    "覆盖系统指令",   // recorded-literal: injection.py INJECTION_MARKERS (prompt-injection phrase)
    "call tool",      // recorded-literal: injection.py INJECTION_MARKERS (prompt-injection phrase)
    "invoke tool",    // recorded-literal: injection.py INJECTION_MARKERS (prompt-injection phrase)
    "调用工具",       // recorded-literal: injection.py INJECTION_MARKERS (prompt-injection phrase)
    "调用 tool",      // recorded-literal: injection.py INJECTION_MARKERS (prompt-injection phrase)
];

/// Port of `detect_injection_markers` (`spikes/spike-20-injection-detection/pure_bridge.py:35`).
pub fn detect_injection_markers(text: Value) -> Result<Value, String> {
    let raw = text
        .as_str()
        .ok_or_else(|| "AttributeError: 'NoneType' object has no attribute 'lower'".to_string())?;

    // Python `if not text: return []` — for a str this is the empty string.
    if raw.is_empty() {
        return Ok(json!([]));
    }

    let lowered = raw.to_lowercase();
    let hits: Vec<&str> = INJECTION_MARKERS
        .iter()
        .copied()
        .filter(|marker| lowered.contains(marker))
        .collect();
    Ok(json!(hits))
}
