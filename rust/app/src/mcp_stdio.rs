//! Rust MCP stdio front-door: newline-delimited JSON-RPC over stdin→stdout. Dispatches
//! `initialize`, `tools/list`, `notifications/*`, `tools/call`, and error paths
//! (METHOD_NOT_FOUND, blacklist/unregistered denial, argument-validation failure, handler raise).
//!
//! Byte-parity with `src/zkc/transport/{stdio,mcp_server,protocol,contract}.py`:
//!   * frame = `json.dumps(obj, ensure_ascii=False, separators=(",",":"), default=str)` → serde_json::to_string.
//!   * tools/list = `_public_tool_view` order {name,description,inputSchema}, from the SAME
//!     contract_v1.json snapshot Python reads (embedded via include_str! so bytes match by source).
//!   * tools/call result = _tool_result: text = py_json(payload) (Python default separators) for a
//!     dict payload, or the raw string for a denial/validation/handler-failure; isError flag set.
//!   * JSON-RPC errors (bad name/arguments, unknown method) → error_response frame (not a result).
//! Verified via Python↔Rust transcript parity (NOT app record, to protect the 199-case baseline).

use std::io::{self, BufRead, Write};
use std::process::ExitCode;
use std::sync::OnceLock;

use serde_json::Value;
use serde_json::json;

const JSONRPC: &str = "2.0"; // JSONRPC_VERSION
const METHOD_NOT_FOUND: i64 = -32601;
const INVALID_PARAMS: i64 = -32602;
const PROTOCOL_VERSION: &str = "2024-11-05"; // recorded-literal: contract.MCP_PROTOCOL_VERSION
const CONTRACT_VERSION: &str = "zkc-mcp-contract/v1"; // recorded-literal: contract.CONTRACT_VERSION
const SERVER_INFO: &str = r#"{"name": "zkc", "version": "0.1.0"}"#; // recorded-literal: contract.SERVER_INFO
const CAPABILITIES: &str =
    r#"{"tools": {"listChanged": false}, "resources": {"subscribe": false, "listChanged": false}}"#; // recorded-literal: contract.CAPABILITIES
const INSTRUCTIONS: &str = "默认 stdio 零网络面、无需 token；外部 agent 一律零信任；写白名单 + 私人 claim 默认脱敏；跨机 HTTP/SSE 须端到端加密隧道，否则不变式⑤（本地优先/隐私）自动否决"; // recorded-literal: contract.TRUST_BOUNDARY

const CONTRACT_JSON: &str = include_str!("../../../src/zkc/transport/contract_v1.json");

fn contract() -> &'static Value {
    static C: OnceLock<Value> = OnceLock::new();
    C.get_or_init(|| serde_json::from_str(CONTRACT_JSON).expect("contract_v1.json"))
}

/// Python `json.dumps(v, ensure_ascii=False)` default separators (", " / ": "), insertion-order keys.
fn py_json(v: &Value) -> String {
    match v {
        Value::Null => "null".into(),
        Value::Bool(b) => (if *b { "true" } else { "false" }).into(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => serde_json::to_string(s).unwrap_or_else(|_| "\"\"".into()),
        Value::Array(a) => format!("[{}]", a.iter().map(py_json).collect::<Vec<_>>().join(", ")),
        Value::Object(o) => format!(
            "{{{}}}",
            o.iter()
                .map(|(k, val)| format!("{}: {}", serde_json::to_string(k).unwrap(), py_json(val)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

/// Python `repr(str)` for the denial message: single-quoted, backslash/quote escapes.
fn py_repr(s: &str) -> String {
    let mut out = String::from("'");
    for c in s.chars() {
        match c {
            '\'' => out.push_str("\\'"),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            _ => out.push(c),
        }
    }
    out.push('\'');
    out
}

fn tool_result(text: String, is_error: bool) -> Value {
    json!({"content": [{"type": "text", "text": text}], "isError": is_error})
}

fn initialize_result(requested: Option<&str>) -> Value {
    let obj = format!(
        "{{\"protocolVersion\": \"{req}\", \"capabilities\": {caps}, \"serverInfo\": {info}, \
         \"contractVersion\": \"{cv}\", \"instructions\": {instr}}}",
        req = requested.unwrap_or(PROTOCOL_VERSION),
        caps = CAPABILITIES,
        info = SERVER_INFO,
        cv = CONTRACT_VERSION,
        instr = serde_json::to_string(INSTRUCTIONS).unwrap(),
    );
    serde_json::from_str(&obj).expect("static initialize json")
}

/// `contract.is_blacklisted`: normalized (- and . → _, lower) in blacklist, history/ prefix, or a
/// dangerous token substring.
fn is_blacklisted(name: &str) -> bool {
    let normalized = name.trim().to_lowercase().replace('-', "_").replace('.', "_");
    let raw = name.trim().to_lowercase();
    let blacklist: Vec<String> = contract()["blacklist"]
        .as_array()
        .map(|a| a.iter().filter_map(Value::as_str).map(str::to_string).collect())
        .unwrap_or_default();
    if blacklist.contains(&normalized) || blacklist.contains(&raw) {
        return true;
    }
    if normalized.starts_with("history/") || normalized.starts_with("history_") {
        return true;
    }
    const TOKENS: &[&str] = &[
        "distill", "interval_adjustment", "interval.adjustment", "meta_claim", "meta.claim",
        "delete_history", "update_history",
    ]; // recorded-literal: contract._DANGEROUS_TOKENS
    TOKENS.iter().any(|t| normalized.contains(t))
}

fn registered(name: &str) -> bool {
    contract()["tools"]
        .as_array()
        .map(|a| a.iter().any(|t| t["name"].as_str() == Some(name)))
        .unwrap_or(false)
}

fn tool_schema(name: &str) -> Option<Value> {
    contract()["tools"]
        .as_array()?
        .iter()
        .find(|t| t["name"].as_str() == Some(name))
        .and_then(|t| t.get("inputSchema")).cloned()
}

fn type_ok(value: &Value, expected: Option<&str>) -> bool {
    match expected {
        None | Some("") => true,
        Some("object") => value.is_object(),
        Some("array") => value.is_array(),
        Some("string") => value.is_string(),
        Some("integer") => (value.is_i64() || value.is_u64()) && !value.is_boolean(),
        Some("number") => value.is_number() && !value.is_boolean(),
        Some("boolean") => value.is_boolean(),
        _ => true,
    }
}

/// `mcp_server.validate_arguments`: required-present, then per-property type check.
fn validate_arguments(schema: &Value, arguments: &Value) -> Option<String> {
    let args = arguments.as_object()?;
    if let Some(required) = schema.get("required").and_then(Value::as_array) {
        for key in required.iter().filter_map(Value::as_str) {
            if !args.contains_key(key) {
                return Some(format!("缺少必需参数 {key}"));
            }
        }
    }
    if let Some(props) = schema.get("properties").and_then(Value::as_object) {
        for (key, spec) in props {
            if let Some(val) = args.get(key) {
                let expected = spec.get("type").and_then(Value::as_str);
                if !type_ok(val, expected) {
                    return Some(format!(
                        "参数 {key} 类型应为 {}",
                        expected.unwrap_or("null")
                    ));
                }
            }
        }
    }
    None
}

/// tools/list result: {_public_tool_view} in contract order, keys name/description/inputSchema.
fn tools_list() -> Value {
    let tools: Vec<Value> = contract()["tools"]
        .as_array()
        .map(|a| {
            a.iter()
                .map(|t| {
                    let mut o = serde_json::Map::new();
                    o.insert("name".into(), t["name"].clone());
                    o.insert("description".into(), t["description"].clone());
                    o.insert("inputSchema".into(), t["inputSchema"].clone());
                    Value::Object(o)
                })
                .collect()
        })
        .unwrap_or_default();
    json!({"tools": tools})
}

/// `contract.RESOURCE_SCHEMAS` → {_public resource view} uri/name/description/mimeType.
fn resources_list() -> Value {
    let resources: Vec<Value> = contract()["resources"]
        .as_array()
        .map(|a| {
            a.iter()
                .map(|r| {
                    let mut o = serde_json::Map::new();
                    o.insert("uri".into(), r["uri"].clone());
                    o.insert("name".into(), r["name"].clone());
                    o.insert("description".into(), r["description"].clone());
                    o.insert("mimeType".into(), r["mimeType"].clone());
                    Value::Object(o)
                })
                .collect()
        })
        .unwrap_or_default();
    json!({"resources": resources})
}

fn resource_mime(uri: &str) -> Option<String> {
    contract()["resources"]
        .as_array()?
        .iter()
        .find(|r| r["uri"].as_str() == Some(uri))
        .and_then(|r| r["mimeType"].as_str())
        .map(str::to_string)
}

/// `datetime.now(timezone.utc).isoformat()` — microsecond-resolution UTC, format YYYY-MM-DDTHH:MM:SS.ffffff+00:00.
fn now_utc_iso() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let d = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default();
    let secs = d.as_secs() as i64;
    let micros = d.subsec_micros();
    let days = secs.div_euclid(86400);
    let rem = secs.rem_euclid(86400);
    // Howard Hinnant civil_from_days
    let z = days + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = (z - era * 146097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = (doy - (153 * mp + 2) / 5 + 1) as i64;
    let month = if mp < 10 { (mp + 3) as i64 } else { (mp - 9) as i64 };
    let year = if month <= 2 { y + 1 } else { y };
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}.{:06}+00:00",
        year, month, day, rem / 3600, (rem % 3600) / 60, rem % 60, micros
    )
}

/// `mcp_server._read_resource`: the due resource runs zkc_scheduler_due with NO as_of ⇒ live now().
fn resources_read(uri: &str, dsn: Option<&str>) -> Outcome {
    let Some(mime) = resource_mime(uri) else {
        return Outcome::Error(INVALID_PARAMS, format!("未知 resource: {uri}"));
    };
    let Some(dsn) = dsn else {
        return Outcome::Result(json!({"contents": [{"uri": uri, "mimeType": mime,
            "text": "handler 执行失败：RuntimeError: ZKC_PG_DSN not set"}]}));
    };
    let as_of = now_utc_iso();
    let rt = match tokio::runtime::Builder::new_current_thread().enable_all().build() {
        Ok(rt) => rt,
        Err(e) => return Outcome::Result(json!({"contents": [{"uri": uri, "mimeType": mime,
            "text": format!("handler 执行失败：RuntimeError: {e}")}]})),
    };
    // handler invoked with {"uri": uri} → scheduler_due reads no as_of → live now; items stable.
    let params = json!({"as_of": as_of, "limit": 50});
    let payload: Value = match rt.block_on(crate::units::search_sql::run_due(dsn, &params)) {
        Ok((items, due_count)) => json!({"as_of": as_of, "items": items, "due_count": due_count,
            "semantics": "注意力预算：该关注清单（decay 到期且需投入注意力）"}),
        Err(e) => Value::String(format!("handler 执行失败：ValueError: {e}")),
    };
    let text = match &payload {
        Value::String(s) => s.clone(),
        other => py_json(other),
    };
    Outcome::Result(json!({"contents": [{"uri": uri, "mimeType": mime, "text": text}]}))
}

enum Outcome {
    Result(Value),
    Error(i64, String),
}

fn call_tool(name: &str, arguments: &Value, dsn: Option<&str>) -> Outcome {
    if !registered(name) {
        let reason = if is_blacklisted(name) {
            "命中 ADR-0004 黑名单：该写操作绝不暴露"
        } else {
            "未注册的 tool；暴露面仅含 contract v1 白名单五 tool"
        };
        return Outcome::Result(tool_result(
            format!("拒绝调用 {}：{}", py_repr(name), reason),
            true,
        ));
    }
    if let Some(problem) = tool_schema(name).and_then(|s| validate_arguments(&s, arguments)) {
        return Outcome::Result(tool_result(format!("参数校验失败：{problem}"), true));
    }
    let Some(dsn) = dsn else {
        return Outcome::Result(tool_result("handler 执行失败：RuntimeError: ZKC_PG_DSN not set".into(), true));
    };
    let rt = match tokio::runtime::Builder::new_current_thread().enable_all().build() {
        Ok(rt) => rt,
        Err(e) => return Outcome::Result(tool_result(format!("handler 执行失败：RuntimeError: {e}"), true)),
    };
    let result: Result<Value, String> = match name {
        "zkc_query" => {
            let scope = arguments.get("scope").and_then(Value::as_str).unwrap_or("public").to_string();
            rt.block_on(crate::units::search_sql::run_mcp_query(dsn, arguments)).map(|items| {
                let count = items.len();
                json!({"items": items, "count": count, "scope": scope, "degraded": false,
                       "privacy": "node.content / meta_claim.statement 不出现在响应体"})
            })
        }
        "zkc_review_queue_list" => rt
            .block_on(crate::units::search_sql::run_rqlist(dsn, arguments))
            .map(|items| {
                let count = items.len();
                json!({"items": items, "count": count, "include_resolved": false})
            }),
        "zkc_scheduler_due" => {
            let as_of = arguments.get("as_of").and_then(Value::as_str).unwrap_or("").to_string();
            rt.block_on(crate::units::search_sql::run_due(dsn, arguments)).map(|(items, due_count)| {
                json!({"as_of": as_of, "items": items, "due_count": due_count,
                       "semantics": "注意力预算：该关注清单（decay 到期且需投入注意力）"})
            })
        }
        "zkc_review_queue_resolve" => rt.block_on(crate::units::search_sql::resolve_raw(dsn, arguments)),
        // zkc_capture: only the PRE-INGEST validations are deterministic (before any uuid4 node id /
        // now() / Ollama routing / DB write). The successful ingest path is a Q5+write boundary and is
        // NOT ported / not byte-reproducible; we reproduce exactly what raises before ingest.
        "zkc_capture" => {
            const MAX_DOCS: usize = 1000; // recorded-literal: capture.MAX_DOCUMENTS_PER_CALL
            let docs = arguments.get("documents").and_then(Value::as_array).cloned().unwrap_or_default();
            if docs.len() > MAX_DOCS {
                return Outcome::Result(tool_result(
                    format!("handler 执行失败：ValueError: 单次 capture 文档数上限 {MAX_DOCS}（收到 {}），请分批", docs.len()),
                    true,
                ));
            }
            for d in &docs {
                let title = d.get("title").and_then(Value::as_str).unwrap_or("").trim();
                if title.is_empty() {
                    return Outcome::Result(tool_result(
                        "handler 执行失败：ValueError: 每条 document 必须带非空 title".into(),
                        true,
                    ));
                }
            }
            // All pre-ingest checks pass → real path needs ingest (uuid4 + now + Ollama) → not ported.
            return Outcome::Result(tool_result(
                "handler 执行失败：ValueError: zkc_capture ingest path not ported (uuid4/now/Ollama — Q5 write boundary)".into(),
                true,
            ));
        }
        other => Err(format!("{other} handler not ported")),
    };
    match result {
        Ok(payload) => Outcome::Result(tool_result(py_json(&payload), false)),
        Err(msg) => Outcome::Result(tool_result(format!("handler 执行失败：ValueError: {msg}"), true)),
    }
}

pub fn serve() -> ExitCode {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let dsn = std::env::var("ZKC_PG_DSN").ok();
    let mut out = stdout.lock();
    for line in stdin.lock().lines() {
        let Ok(raw) = line else { break };
        let line = raw.trim_end_matches(['\r', '\n']);
        if line.trim().is_empty() {
            continue;
        }
        let Ok(message) = serde_json::from_str::<Value>(line) else { continue };
        if message.get("id").is_none() {
            continue; // notification → no frame
        }
        let id = message.get("id").cloned().unwrap_or(Value::Null);
        let method = message.get("method").and_then(Value::as_str).unwrap_or("");
        let params = message.get("params").cloned().unwrap_or(Value::Null);

        let outcome: Outcome = match method {
            "initialize" => Outcome::Result(initialize_result(params.get("protocolVersion").and_then(Value::as_str))),
            "tools/list" => Outcome::Result(tools_list()),
            "resources/list" => Outcome::Result(resources_list()),
            "ping" => Outcome::Result(json!({})),
            "resources/read" => match params.get("uri").and_then(Value::as_str) {
                Some(uri) if !uri.is_empty() => resources_read(uri, dsn.as_deref()),
                _ => Outcome::Error(INVALID_PARAMS, "resources/read 需要 uri".into()),
            },
            "tools/call" => match params.get("name").and_then(Value::as_str) {
                None => Outcome::Error(INVALID_PARAMS, "tools/call 需要 name".into()),
                Some(name) => {
                    let arguments = params.get("arguments").cloned().unwrap_or(Value::Null);
                    let arguments = if arguments.is_null() { json!({}) } else { arguments };
                    if !arguments.is_object() {
                        Outcome::Error(INVALID_PARAMS, "arguments 必须是 object".into())
                    } else {
                        call_tool(name, &arguments, dsn.as_deref())
                    }
                }
            },
            other => Outcome::Error(METHOD_NOT_FOUND, format!("Method not found: {other}")),
        };

        let frame = match outcome {
            Outcome::Result(result) => json!({"jsonrpc": JSONRPC, "id": id, "result": result}),
            Outcome::Error(code, msg) => {
                json!({"jsonrpc": JSONRPC, "id": id, "error": {"code": code, "message": msg}})
            }
        };
        let _ = writeln!(out, "{}", serde_json::to_string(&frame).unwrap_or_default());
        let _ = out.flush();
    }
    ExitCode::SUCCESS
}
