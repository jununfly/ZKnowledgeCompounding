//! Rust port of the `route_expired` decision table (`src/zkc/expiry.py:52`).
//!
//! The bridge cannot pass a `Storage` through the PyO3 JSON boundary, so a
//! process-only adapter in spike-08 constructs the original `SchedulableNode`
//! and a one-method fake store, then calls the original function. Every value
//! below is pinned by 57 recorded cases; the Rust tests are regression only.
//! `apply_archive`, `enqueue_review`, `apply_distill`, `route_and_apply` and
//! `process_expired_dynamic_nodes` remain Python (Storage / callable / datetime).

#![forbid(unsafe_code)]

use serde_json::{Map, Value, json};

const ROT_THRESHOLD: f64 = 0.9; // recorded-literal: tuning.get("ROT_THRESHOLD"), SIMULATION not CALIBRATED
const PRESSURE_DEFER: f64 = 0.8; // recorded-literal: tuning.get("PRESSURE_DEFER"), SIMULATION not CALIBRATED

fn py_truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_none_or(|x| x != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

fn as_f64(v: &Value) -> Option<f64> {
    match v {
        Value::Number(n) => n.as_f64(),
        Value::Bool(b) => Some(if *b { 1.0 } else { 0.0 }),
        Value::Object(o) if o.len() == 1 => {
            let (k, inner) = o.iter().next()?;
            let s = inner.as_str()?;
            match (k.as_str(), s) {
                ("$float", _) | ("$int", _) => s.parse().ok(),
                ("$num", "NaN") => Some(f64::NAN),
                ("$num", "Infinity") => Some(f64::INFINITY), // recorded-literal: pyconv infinity marker
                ("$num", "-Infinity") => Some(f64::NEG_INFINITY), // recorded-literal: pyconv infinity marker
                ("$num", "-0") => Some(-0.0), // recorded-literal: pyconv negative-zero marker
                _ => None,
            }
        }
        _ => None,
    }
}

/// Python format spec `:g` (6 significant digits) for the reason string.
fn py_g(x: f64) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf" } else { "-inf" }.to_string();
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0" } else { "0" }.to_string();
    }
    let exp = x.abs().log10().floor() as i32;
    if !(-4..6).contains(&exp) {
        let sci = format!("{x:.5e}");
        let (mant, exponent) = sci.split_once('e').unwrap_or((&sci, "0"));
        let mant = mant.trim_end_matches('0').trim_end_matches('.');
        let e: i32 = exponent.parse().unwrap_or(0);
        format!("{}e{}{:02}", mant, if e < 0 { '-' } else { '+' }, e.abs())
    } else {
        let decimals = (5 - exp).max(0) as usize;
        let fixed = format!("{:.*}", decimals, x);
        if fixed.contains('.') {
            fixed
                .trim_end_matches('0')
                .trim_end_matches('.')
                .to_string()
        } else {
            fixed
        }
    }
}

/// `UUID(str(node_id))` canonicalization for the 36-char hyphenated form.
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

fn invalid_row_error(v: &Value) -> String {
    match v {
        Value::Bool(_) => "TypeError: 'bool' object is not iterable".to_string(), // recorded-literal: CPython dict(bool) text
        Value::String(_) | Value::Object(_) => {
            "ValueError: dictionary update sequence element #0 has length 1; 2 is required"
                .to_string() // recorded-literal: CPython dict(one-char iterable) text
        }
        _ => "TypeError: 'NoneType' object is not iterable".to_string(), // recorded-literal: CPython dict(None) text
    }
}

struct Row {
    id: String,
    decay: Value,
    captured: Value,
    conn: Value,
    self_loop: Value,
    higher_dim: Value,
}

fn parse_rows(rows: &[Value]) -> Result<Vec<Row>, String> {
    let mut out = Vec::new();
    for raw in rows {
        let row = raw.as_object().ok_or_else(|| invalid_row_error(raw))?;
        if row.get("archived").is_some_and(py_truthy) {
            continue;
        }
        let id = row
            .get("id")
            .filter(|v| !v.is_null())
            .map(|v| {
                let s = v.as_str().unwrap_or("");
                canonical_uuid(s).ok_or_else(|| {
                    "ValueError: badly formed hexadecimal UUID string".to_string() // recorded-literal: CPython UUID error text
                })
            })
            .transpose()?
            .unwrap_or_default();
        out.push(Row {
            id,
            decay: row.get("decay_score").cloned().unwrap_or(json!(0.0)),
            captured: row.get("captured").cloned().unwrap_or(json!(false)),
            conn: row.get("conn_count").cloned().unwrap_or(json!(0)),
            self_loop: row.get("self_loop_count").cloned().unwrap_or(json!(0)),
            higher_dim: row.get("higher_dim_count").cloned().unwrap_or(json!(0)),
        });
    }
    Ok(out)
}

fn obj(fields: Vec<(&str, Value)>) -> Value {
    let mut map = Map::new();
    for (k, v) in fields {
        map.insert(k.to_string(), v);
    }
    Value::Object(map)
}

/// Port of `route_decision`, the process-only adapter over `route_expired`.
pub fn route_decision(
    node_id: String,
    rows: Vec<Value>,
    attention_pressure: f64,
) -> Result<Value, String> {
    // The adapter builds every row before the original compares the node id.
    let parsed = parse_rows(&rows)?;
    let nid = canonical_uuid(&node_id).ok_or_else(|| {
        "ValueError: badly formed hexadecimal UUID string".to_string() // recorded-literal: CPython UUID error text
    })?;
    let Some(row) = parsed.iter().find(|r| r.id == nid) else {
        return Ok(obj(vec![
            ("routable", json!(false)),
            ("action", Value::Null),
            (
                "reason",
                json!("not an expired dynamic node (static/archived/not schedulable)"), // recorded-literal: expiry.py reason text
            ),
            ("signals", json!({})),
        ]));
    };

    let decay = as_f64(&row.decay).unwrap_or(f64::NAN);
    if decay < ROT_THRESHOLD {
        let reason = format!(
            "decay {} < ROT {}: not yet expired", // recorded-literal: expiry.py reason template
            py_g(decay),
            py_g(ROT_THRESHOLD)
        );
        return Ok(obj(vec![
            ("routable", json!(false)),
            ("action", Value::Null),
            ("reason", json!(reason)),
            ("signals", obj(vec![("decay_score", row.decay.clone())])),
        ]));
    }

    let signals = obj(vec![
        ("decay_score", row.decay.clone()),
        ("captured", row.captured.clone()),
        ("conn_count", row.conn.clone()),
        ("self_loop_count", row.self_loop.clone()),
        ("higher_dim_count", row.higher_dim.clone()),
    ]);
    let routed = |action: &str, reason: &str| {
        obj(vec![
            ("routable", json!(true)),
            ("action", json!(action)),
            ("reason", json!(reason)),
            ("signals", signals.clone()),
        ])
    };
    if py_truthy(&row.captured) {
        return Ok(routed(
            "archive", // recorded-literal: expiry.py DECISION_ARCHIVE
            "value already lifted to meta layer (claim/artifact evidence) -> archive raw", // recorded-literal: expiry.py reason text
        ));
    }
    let contextual = [&row.conn, &row.self_loop, &row.higher_dim]
        .iter()
        .any(|v| as_f64(v).is_some_and(|n| n >= 1.0));
    if contextual {
        if attention_pressure >= PRESSURE_DEFER {
            return Ok(routed(
                "abstain", // recorded-literal: expiry.py DECISION_ABSTAIN
                "would distill but attention budget full -> defer to human", // recorded-literal: expiry.py reason text
            ));
        }
        return Ok(routed(
            "distill", // recorded-literal: expiry.py DECISION_DISTILL
            "connected/contextual but not captured -> lift insight", // recorded-literal: expiry.py reason text
        ));
    }
    Ok(routed(
        "abstain", // recorded-literal: expiry.py DECISION_ABSTAIN
        "orphan (no connection/context) -> human decides, never silently drop", // recorded-literal: expiry.py reason text
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(id: &str, decay: f64, captured: bool, conn: i64) -> Value {
        json!({"id": id, "decay_score": decay, "captured": captured,
               "conn_count": conn, "self_loop_count": 0, "higher_dim_count": 0})
    }

    const ID: &str = "11111111-1111-4111-8111-111111111111";

    #[test]
    fn expired_and_connected_distills_unless_pressure_full() {
        let rows = vec![row(ID, 0.9, false, 1)];
        assert_eq!(
            route_decision(ID.into(), rows.clone(), 0.2).unwrap()["action"],
            "distill"
        );
        assert_eq!(
            route_decision(ID.into(), rows, 0.8).unwrap()["action"],
            "abstain"
        );
    }

    #[test]
    fn captured_evidence_archives_even_under_pressure() {
        let rows = vec![row(ID, 1.0, true, 9)];
        assert_eq!(
            route_decision(ID.into(), rows, 0.99).unwrap()["action"],
            "archive"
        );
    }

    #[test]
    fn float32_expansion_stays_not_routable() {
        let rows = vec![row(ID, 0.8999999761581421, false, 1)];
        let out = route_decision(ID.into(), rows, 0.2).unwrap();
        assert_eq!(out["routable"], false);
        assert_eq!(out["reason"], "decay 0.9 < ROT 0.9: not yet expired");
    }

    #[test]
    fn orphan_is_never_silently_dropped() {
        let rows = vec![row(ID, 1.0, false, 0)];
        assert_eq!(
            route_decision(ID.into(), rows, 0.0).unwrap()["reason"],
            "orphan (no connection/context) -> human decides, never silently drop"
        );
    }
}
