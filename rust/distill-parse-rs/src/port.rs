//! Rust port of `src/zkc/distill.py`'s deterministic parse/validation layer,
//! recorded through `spikes/spike-17-distill-parse/pure_bridge.py` (process-only
//! alias). The Python original is the recording oracle.
//!
//! Proof boundary: `extract_json`, `_parse_json_output`, `_parse_llm_output`
//! and `validate_result` take JSON scalars / string pairs / string-keyed
//! objects. `distill_node`'s retry loop, prompt/schema text, LLM callables,
//! `revert_claim` / `revert_artifact` Storage effects and tuning calibration
//! stay in Python. This is not a distillation quality gate.
//!
//! Policy literals below are recorded from the original and marked
//! `recorded-literal`; none is promoted to a tuned value here.

#![forbid(unsafe_code)]

use serde_json::{Map, Value, json};

/// Port of `re.compile(r"\{.*\}", re.DOTALL)` + `json.loads` from
/// `src/zkc/distill.py:110`. The match is greedy: first `{` through last `}`.
/// Non-dict JSON, broken JSON and no-match all become `None` (`Value::Null`).
fn extract_json_value(raw: &Value) -> Option<Map<String, Value>> {
    let text = raw.as_str().unwrap_or("");
    let open = text.find('{')?;
    let close = text.rfind('}')?;
    if close < open {
        return None;
    }
    let obj: Value = serde_json::from_str(&text[open..=close]).ok()?;
    obj.as_object().cloned()
}

/// Python `str(value)` for the JSON vocabulary recorded here. The alias
/// restores UUIDs before the original sees them, so only scalars need this.
fn py_str(value: &Value) -> String {
    match value {
        Value::Null => "None".to_string(),
        Value::Bool(true) => "True".to_string(),
        Value::Bool(false) => "False".to_string(),
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        other => other.to_string(),
    }
}

/// Python truthiness, used by `value or <default>` in the original.
fn py_truthy(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) | Some(Value::Bool(false)) => false,
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Number(n)) => n.as_f64().is_none_or(|v| v != 0.0),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
        _ => true,
    }
}

/// `str(value or default)` as used for `text` and `topic`.
fn py_str_or(value: Option<&Value>, default: &str) -> String {
    if py_truthy(value) {
        value.map(py_str).unwrap_or_default()
    } else {
        default.to_string()
    }
}

/// Python `uuid.UUID(str(tok))` canonicalization: strip `urn:uuid:` / braces,
/// drop all hyphens, require 32 hex digits, emit lowercase hyphenated form.
fn uuid_canonical(token: &str) -> Option<String> {
    let mut s = token;
    if s.len() >= 9 && s[..9].eq_ignore_ascii_case("urn:uuid:") {
        s = &s[9..];
    }
    let s = s
        .strip_prefix('{')
        .and_then(|v| v.strip_suffix('}'))
        .unwrap_or(s);
    let hex: String = s.chars().filter(|c| *c != '-').collect();
    if hex.len() != 32 || !hex.bytes().all(|b| b.is_ascii_hexdigit()) {
        return None;
    }
    let h = hex.to_ascii_lowercase();
    Some(format!(
        "{}-{}-{}-{}-{}",
        &h[0..8],
        &h[8..12],
        &h[12..16],
        &h[16..20],
        &h[20..32]
    ))
}

/// Canonical source ids from the alias's `[[uuid_string, text], ...]` pairs.
fn source_ids(value: &Value) -> Result<Vec<String>, String> {
    let pairs = value
        .as_array()
        .ok_or_else(|| "source_texts: expected array".to_string())?;
    pairs
        .iter()
        .map(|pair| {
            let id = pair
                .as_array()
                .and_then(|p| p.first())
                .map(py_str)
                .ok_or_else(|| "source_texts[]: expected [id, text]".to_string())?;
            uuid_canonical(&id).ok_or_else(|| format!("source_texts[]: invalid uuid {id:?}"))
        })
        .collect()
}

/// `re.findall(r"\[\[([0-9a-fA-F-]{36})\]\]", text)` with fixed-width body.
fn inline_markers(text: &str) -> Vec<String> {
    let bytes = text.as_bytes();
    let mut out = Vec::new();
    let mut i = 0usize;
    while i + 2 <= bytes.len() {
        if bytes[i] == b'[' && bytes.get(i + 1) == Some(&b'[') {
            let body_end = i + 2 + 36;
            if body_end + 2 <= bytes.len()
                && bytes[i + 2..body_end]
                    .iter()
                    .all(|b| b.is_ascii_hexdigit() || *b == b'-')
                && bytes[body_end] == b']'
                && bytes[body_end + 1] == b']'
            {
                out.push(String::from_utf8_lossy(&bytes[i + 2..body_end]).into_owned());
                i = body_end + 2;
                continue;
            }
        }
        i += 1;
    }
    out
}

/// Add a citation if it is a known source and not already present (first
/// occurrence wins, matching the original's `uid not in cited` check).
fn push_citation(cited: &mut Vec<String>, token: &str, sources: &[String]) {
    if let Some(uid) = uuid_canonical(token)
        && sources.contains(&uid)
        && !cited.contains(&uid)
    {
        cited.push(uid);
    }
}

fn citation_array(cited: &[String]) -> Value {
    Value::Array(
        cited
            .iter()
            .map(|uid| json!({"source_node_id": uid, "snippet": Value::Null}))
            .collect(),
    )
}

fn result_value(claims: Vec<Value>) -> Value {
    json!({"claims": Value::Array(claims), "notes": "", "attempts": 1})
}

/// Port of `_extract_json` (`src/zkc/distill.py:113`).
pub fn extract_json(raw: Value) -> Result<Value, String> {
    Ok(extract_json_value(&raw)
        .map(Value::Object)
        .unwrap_or(Value::Null))
}

/// Port of `_parse_json_output` (`src/zkc/distill.py:125`).
pub fn parse_json_output(raw: Value, source_texts: Value) -> Result<Value, String> {
    let sources = source_ids(&source_texts)?;
    let Some(obj) = extract_json_value(&raw) else {
        return Ok(Value::Null);
    };
    let Some(Value::Array(items)) = obj.get("claims") else {
        return Ok(Value::Null);
    };

    let mut claims = Vec::new();
    for item in items {
        let Some(claim) = item.as_object() else {
            return Ok(Value::Null);
        };
        let text = py_str_or(claim.get("text"), "");
        if text.trim().is_empty() {
            return Ok(Value::Null); // structural failure: retry, never partial
        }

        let mut cited: Vec<String> = Vec::new();
        if let Some(Value::Array(tokens)) = claim.get("citations") {
            for token in tokens {
                push_citation(&mut cited, &py_str(token), &sources);
            }
        }
        // A truthy string is iterated character-by-character by the original;
        // every single character fails UUID parsing, so it is a no-op.
        for token in inline_markers(&text) {
            push_citation(&mut cited, &token, &sources);
        }

        let topic = py_str_or(claim.get("topic"), "(unclassified)"); // recorded-literal: distill.py:160 default topic "(unclassified)"
        claims.push(json!({
            "text": text.trim(),
            "topic": topic,
            "citations": citation_array(&cited),
            "reverse_links": Value::Array(cited.iter().cloned().map(Value::String).collect()),
        }));
    }

    if claims.is_empty() {
        return Ok(Value::Null);
    }
    Ok(result_value(claims))
}

/// Port of `_parse_llm_output` (`src/zkc/distill.py:169`).
pub fn parse_llm_output(raw: Value, source_texts: Value) -> Result<Value, String> {
    let sources = source_ids(&source_texts)?;
    let text = py_str(&raw).trim().to_string();
    let mut cited: Vec<String> = Vec::new();
    for token in inline_markers(&text) {
        push_citation(&mut cited, &token, &sources);
    }
    let claim_text = if text.is_empty() {
        "(empty)".to_string() // recorded-literal: distill.py:186 fallback text "(empty)"
    } else {
        text
    };
    Ok(result_value(vec![json!({
        "text": claim_text,
        "topic": "(unclassified)", // recorded-literal: distill.py:188 default topic "(unclassified)"
        "citations": citation_array(&cited),
        "reverse_links": Value::Array(cited.iter().cloned().map(Value::String).collect()),
    })]))
}

/// Python `repr(str)`: quote choice and escaping used in DistillationError text.
/// Non-printable non-ASCII code points are outside the recorded vocabulary.
fn py_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::new();
    out.push(quote);
    for ch in text.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if ('\u{0}'..='\u{1f}').contains(&c) || c == '\u{7f}' => {
                out.push_str(&format!("\\x{:02x}", c as u32));
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

/// Rebuild the alias's encoded `DistillationResult` with the original's key
/// order before returning it (the original returns the same object).
fn normalize_result(value: &Value) -> Result<Value, String> {
    let obj = value
        .as_object()
        .ok_or_else(|| "validate_result: expected object".to_string())?;
    let items = obj
        .get("claims")
        .and_then(Value::as_array)
        .ok_or_else(|| "validate_result: claims expected array".to_string())?;
    let mut claims = Vec::new();
    for item in items {
        let claim = item
            .as_object()
            .ok_or_else(|| "validate_result: claims[] expected object".to_string())?;
        let text = py_str_or(claim.get("text"), "");
        let topic = py_str_or(claim.get("topic"), "");
        let cites = claim
            .get("citations")
            .and_then(Value::as_array)
            .ok_or_else(|| "validate_result: citations expected array".to_string())?
            .iter()
            .map(|cit| {
                let cit = cit
                    .as_object()
                    .ok_or_else(|| "validate_result: citations[] expected object".to_string())?;
                Ok(json!({
                    "source_node_id": py_str_or(cit.get("source_node_id"), ""),
                    "snippet": cit.get("snippet").cloned().unwrap_or(Value::Null),
                }))
            })
            .collect::<Result<Vec<_>, String>>()?;
        let links = claim
            .get("reverse_links")
            .and_then(Value::as_array)
            .ok_or_else(|| "validate_result: reverse_links expected array".to_string())?
            .iter()
            .map(py_str)
            .map(Value::String)
            .collect::<Vec<_>>();
        claims.push(json!({
            "text": text,
            "topic": topic,
            "citations": Value::Array(cites),
            "reverse_links": Value::Array(links),
        }));
    }
    Ok(json!({
        "claims": Value::Array(claims),
        "notes": py_str_or(obj.get("notes"), ""),
        "attempts": obj.get("attempts").cloned().unwrap_or_else(|| json!(1)),
    }))
}

/// Port of `validate_result` (`src/zkc/distill.py:74`).
pub fn validate_result(result: Value) -> Result<Value, String> {
    let obj = result
        .as_object()
        .ok_or_else(|| "validate_result: expected object".to_string())?;
    let claims = obj
        .get("claims")
        .and_then(Value::as_array)
        .ok_or_else(|| "validate_result: claims expected array".to_string())?;
    if claims.is_empty() {
        return Err("zkc.distill.DistillationError: distillation produced no claims".to_string());
    }
    let min_c: usize = 1; // recorded-literal: DISTILL_MIN_CITATIONS_PER_CLAIM=1 (tuning.py:136, PLACEHOLDER; not CALIBRATED)
    for claim in claims {
        let claim = claim
            .as_object()
            .ok_or_else(|| "validate_result: claims[] expected object".to_string())?;
        let count = claim
            .get("citations")
            .and_then(Value::as_array)
            .map_or(0, Vec::len);
        if count < min_c {
            return Err(format!(
                "zkc.distill.DistillationError: claim has {count} citations, need >= {min_c}: {}",
                py_repr(&py_str_or(claim.get("text"), ""))
            ));
        }
    }
    normalize_result(&result)
}
