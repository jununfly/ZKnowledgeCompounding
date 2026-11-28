//! The Rust port of `spikes/spike-23-telemetry-validation/pure_bridge.py`.
//!
//! `validate_report(report: dict) -> None` is the R14 telemetry field-presence
//! gate from `src/zkc/r14_telemetry.py::_validate_report`. It checks that the
//! report is a dict and carries the three `REQUIRED_FIELDS`, raising `ValueError`
//! otherwise. No dataclass / Storage / file-IO / datetime / LLM seam: the sole
//! argument is a JSON object and the return is `null` or an error string.
//!
//! This is not an R14-close runtime guarantee: real runs are produced by zj via
//! dogfood and persisted by `record_run` (file IO), which stays in Python.

#![forbid(unsafe_code)]

/// Field names from `REQUIRED_FIELDS` (`src/zkc/r14_telemetry.py:33`), in the
/// declaration order the original reports missing fields. Recorded verbatim
/// from the Python constant; not a CALIBRATED value.
const REQUIRED_FIELDS: [&str; 3] = [
    "completion_fired", // recorded-literal: REQUIRED_FIELDS[0] from src/zkc/r14_telemetry.py
    "main_latency_ms",  // recorded-literal: REQUIRED_FIELDS[1] from src/zkc/r14_telemetry.py
    "completion_latency_ms", // recorded-literal: REQUIRED_FIELDS[2] from src/zkc/r14_telemetry.py
];

/// Port of `validate_report` (`spikes/spike-23-telemetry-validation/pure_bridge.py:26`,
/// original `src/zkc/r14_telemetry.py::_validate_report`).
pub fn validate_report(report: serde_json::Value) -> Result<serde_json::Value, String> {
    let map = match report {
        serde_json::Value::Object(map) => map,
        _ => {
            return Err(
                "ValueError: report must be a dict".to_string(), // recorded-literal: original isinstance guard text, src/zkc/r14_telemetry.py
            );
        }
    };
    let missing: Vec<&str> = REQUIRED_FIELDS
        .iter()
        .copied()
        .filter(|field| !map.contains_key(*field))
        .collect();
    if !missing.is_empty() {
        return Err(format!(
            "ValueError: report missing required field(s): {}", // recorded-literal: original missing-fields message prefix, src/zkc/r14_telemetry.py
            missing.join(", ") // recorded-literal: ", ".join(missing) separator, src/zkc/r14_telemetry.py
        ));
    }
    Ok(serde_json::Value::Null)
}
