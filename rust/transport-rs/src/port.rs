//! Rust port of `src/zkc/transport/` — the recordable pure-function slice.
//!
//! Proof boundary: `cases.jsonl` was recorded from the Python original (429 cases,
//! 57 expected exceptions). `McpServer`, `ToolSpec`, `ResourceSpec`, `JsonRpcError`,
//! `build_server`, `main` and the stdio loop stay in Python — they are stateful,
//! callable-bearing, class-based or I/O, so the JSON bridge cannot give them a
//! deterministic oracle. See `finding-pure-slices.md`.
//!
//! The contract snapshot is embedded from `contract_v1.json`, the module's single
//! source of truth; altering that file requires re-recording the cases.

#![forbid(unsafe_code)]

use serde_json::{Map, Value, json};

const SNAPSHOT: &str = include_str!("../../../src/zkc/transport/contract_v1.json");

fn snapshot() -> Result<Value, String> {
    serde_json::from_str(SNAPSHOT).map_err(|e| format!("ValueError: {e}"))
}

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

/// Python `str(value)` for the scalar values the recorder can produce; composite
/// values are rendered as compact JSON (no such case is in the recorded set).
fn py_str(v: &Value) -> String {
    match v {
        Value::Null => "None".to_string(),
        Value::Bool(b) => if *b { "True" } else { "False" }.to_string(),
        Value::String(s) => s.clone(),
        Value::Number(_) => v.to_string(),
        Value::Array(_) | Value::Object(_) => v.to_string(),
    }
}

fn type_name(v: &Value) -> &'static str {
    match v {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(n) => {
            if n.is_i64() || n.is_u64() {
                "int"
            } else {
                "float"
            }
        }
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

fn object_or_error(v: &Value) -> Result<&Map<String, Value>, String> {
    v.as_object().ok_or_else(|| {
        format!(
            "AttributeError: '{}' object has no attribute 'get'",
            type_name(v)
        )
    })
}

/// Port of `contract_snapshot` (`src/zkc/transport/contract.py:48`): a deep copy of
/// the JSON fact source. `serde_json` with `preserve_order` keeps the file's key
/// order, matching `json.loads(json.dumps(...))`.
pub fn contract_snapshot() -> Result<Value, String> {
    snapshot()
}

/// Port of `tool_schema` (`src/zkc/transport/contract.py:53`).
pub fn tool_schema(name: String) -> Result<Option<Value>, String> {
    let snap = snapshot()?;
    let tools = snap.get("tools").and_then(Value::as_array).ok_or_else(|| {
        "KeyError: 'tools'".to_string() // recorded-literal: CPython KeyError text for a missing snapshot key
    })?;
    Ok(tools
        .iter()
        .find(|t| t.get("name").and_then(Value::as_str) == Some(name.as_str()))
        .cloned())
}

/// Port of `is_blacklisted` (`src/zkc/transport/contract.py:58`).
///
/// Note the source normalizes `-` and `.` to `_` but keeps `/`; tokens like
/// `"interval.adjustment"` therefore never match after normalization, while
/// `"interval_adjustment"` does. Reproduce that asymmetry exactly.
pub fn is_blacklisted(name: String) -> Result<bool, String> {
    let snap = snapshot()?;
    let blacklist: Vec<String> = snap
        .get("blacklist")
        .and_then(Value::as_array)
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default();
    let trimmed = name.trim();
    let lowered = trimmed.to_lowercase();
    let normalized = lowered.replace(['-', '.'], "_");
    if blacklist.iter().any(|b| b == &normalized || b == &lowered) {
        return Ok(true);
    }
    if normalized.starts_with("history/") || normalized.starts_with("history_") {
        return Ok(true); // recorded-literal: ADR-0004 blacklist prefix
    }
    const DANGEROUS: [&str; 6] = [
        "distill",             // recorded-literal: ADR-0004 dangerous token
        "interval_adjustment", // recorded-literal: ADR-0004 dangerous token
        "interval.adjustment", // recorded-literal: ADR-0004 dangerous token
        "meta_claim",          // recorded-literal: ADR-0004 dangerous token
        "meta.claim",          // recorded-literal: ADR-0004 dangerous token
        "delete_history",      // recorded-literal: ADR-0004 dangerous token
    ];
    Ok(DANGEROUS.iter().any(|token| normalized.contains(token)))
}

/// Port of `is_allowlisted` (`src/zkc/transport/contract.py:68`).
pub fn is_allowlisted(name: String) -> Result<bool, String> {
    let snap = snapshot()?;
    let tools = snap
        .get("tools")
        .and_then(Value::as_array)
        .map_or(&[][..], Vec::as_slice);
    Ok(tools
        .iter()
        .filter_map(|t| t.get("name").and_then(Value::as_str))
        .any(|n| n == name))
}

/// Port of `_type_ok` (`src/zkc/transport/mcp_server.py:65`).
fn type_ok(value: &Value, expected: &Value) -> bool {
    if !py_truthy(expected) {
        return true;
    }
    match expected.as_str().unwrap_or("") {
        "object" => value.is_object(),
        "array" => value.is_array(),
        "string" => value.is_string(),
        "integer" => value.as_i64().is_some() || value.as_u64().is_some(),
        "number" => value.is_number(),
        "boolean" => value.as_bool().is_some(),
        _ => true,
    }
}

/// Port of `validate_arguments` (`src/zkc/transport/mcp_server.py:83`): minimal
/// JSON Schema validation (required + top-level type), no third-party dependency.
pub fn validate_arguments(schema: Value, arguments: Value) -> Result<Option<String>, String> {
    let args = match arguments.as_object() {
        Some(o) => o,
        None => {
            return Ok(Some("arguments 必须是 object".to_string())); // recorded-literal: Python source error text
        }
    };
    let schema_obj = object_or_error(&schema)?;
    let empty = Vec::new();
    let required = schema_obj
        .get("required")
        .and_then(Value::as_array)
        .unwrap_or(&empty);
    for key in required {
        if !args.contains_key(py_str(key).as_str()) {
            return Ok(Some(format!("缺少必需参数 {}", py_str(key))));
        }
    }
    let no_props = Map::new();
    let props = schema_obj
        .get("properties")
        .filter(|v| py_truthy(v))
        .and_then(Value::as_object)
        .unwrap_or(&no_props);
    for (key, spec) in props {
        if let Some(value) = args.get(key) {
            let expected = object_or_error(spec)?
                .get("type")
                .cloned()
                .unwrap_or(Value::Null);
            if !type_ok(value, &expected) {
                return Ok(Some(format!("参数 {} 类型应为 {}", key, py_str(&expected))));
            }
        }
    }
    Ok(None)
}

/// Port of `decode_message` (`src/zkc/transport/protocol.py:37`).
///
/// `JsonRpcError` stays in Python (class with Exception base), but its message
/// text is part of the recorded oracle and is reproduced verbatim here.
pub fn decode_message(raw: String) -> Result<Value, String> {
    let obj: Value = serde_json::from_str(&raw)
        .map_err(|_| "JsonRpcError: Parse error: invalid JSON".to_string())?; // recorded-literal: protocol.py PARSE_ERROR text
    if !obj.is_object() {
        return Err("JsonRpcError: Invalid Request: expected a JSON object".to_string()); // recorded-literal: protocol.py INVALID_REQUEST text
    }
    if obj.get("jsonrpc").and_then(Value::as_str) != Some("2.0") {
        return Err("JsonRpcError: Invalid Request: jsonrpc must be '2.0'".to_string()); // recorded-literal: protocol.py INVALID_REQUEST text
    }
    let method_ok = obj
        .get("method")
        .and_then(Value::as_str)
        .is_some_and(|m| !m.trim().is_empty());
    if !method_ok {
        return Err("JsonRpcError: Invalid Request: method is required".to_string()); // recorded-literal: protocol.py INVALID_REQUEST text
    }
    Ok(obj)
}

/// Port of `encode_message` (`src/zkc/transport/protocol.py:52`): single-line
/// compact JSON with raw UTF-8, matching `ensure_ascii=False` and the separators.
pub fn encode_message(obj: Value) -> Result<String, String> {
    serde_json::to_string(&obj).map_err(|e| format!("TypeError: {e}"))
}

/// Port of `is_notification` (`src/zkc/transport/protocol.py:57`).
pub fn is_notification(message: Value) -> Result<bool, String> {
    match &message {
        Value::Object(o) => Ok(!o.contains_key("id")),
        Value::String(s) => Ok(!s.contains("id")),
        Value::Array(a) => Ok(!a.iter().any(|v| v.as_str() == Some("id"))),
        Value::Null | Value::Bool(_) | Value::Number(_) => Err(format!(
            "TypeError: argument of type '{}' is not iterable",
            type_name(&message)
        )),
    }
}

fn response_obj(fields: Vec<(&str, Value)>) -> Value {
    let mut map = Map::new();
    for (k, v) in fields {
        map.insert(k.to_string(), v);
    }
    Value::Object(map)
}

/// Port of `result_response` (`src/zkc/transport/protocol.py:62`).
pub fn result_response(request_id: Value, result: Value) -> Result<Value, String> {
    Ok(response_obj(vec![
        ("jsonrpc", json!("2.0")), // recorded-literal: JSON-RPC version constant
        ("id", request_id),
        ("result", result),
    ]))
}

/// Port of `error_response` (`src/zkc/transport/protocol.py:66`).
pub fn error_response(
    request_id: Value,
    code: i64,
    message: String,
    data: Option<Value>,
) -> Result<Value, String> {
    let mut err = Map::new();
    err.insert("code".to_string(), json!(code));
    err.insert("message".to_string(), json!(message));
    if let Some(data) = data
        && !data.is_null()
    {
        err.insert("data".to_string(), data);
    }
    Ok(response_obj(vec![
        ("jsonrpc", json!("2.0")), // recorded-literal: JSON-RPC version constant
        ("id", request_id),
        ("error", Value::Object(err)),
    ]))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn contract_snapshot_preserves_file_key_order() {
        let snap = contract_snapshot().unwrap();
        let keys: Vec<&str> = snap
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect();
        assert_eq!(keys.first(), Some(&"version"));
        assert_eq!(keys.last(), Some(&"blacklist"));
    }

    #[test]
    fn blacklist_normalization_keeps_slash_but_folds_dot_and_dash() {
        assert!(is_blacklisted("DISTILL".into()).unwrap());
        assert!(is_blacklisted("meta.claim".into()).unwrap());
        assert!(!is_blacklisted("zkc_capture".into()).unwrap());
    }

    #[test]
    fn decode_rejects_bad_frames_with_recorded_text() {
        assert_eq!(
            decode_message("not json".into()).unwrap_err(),
            "JsonRpcError: Parse error: invalid JSON"
        );
        assert_eq!(
            decode_message("{}".into()).unwrap_err(),
            "JsonRpcError: Invalid Request: jsonrpc must be '2.0'"
        );
    }

    #[test]
    fn encode_emits_compact_utf8_and_escaped_newline() {
        assert_eq!(
            encode_message(json!({"text": "你好\n行"})).unwrap(),
            "{\"text\":\"你好\\n行\"}"
        );
    }

    #[test]
    fn validation_reports_missing_required_and_type() {
        let schema = json!({"required": ["query"], "properties": {"query": {"type": "string"}}});
        assert_eq!(
            validate_arguments(schema.clone(), json!({})).unwrap(),
            Some("缺少必需参数 query".to_string())
        );
        assert_eq!(
            validate_arguments(schema, json!({"query": 1})).unwrap(),
            Some("参数 query 类型应为 string".to_string())
        );
    }
}
