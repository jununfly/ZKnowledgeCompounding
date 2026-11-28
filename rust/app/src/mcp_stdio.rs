//! Rust MCP stdio front-door: newline-delimited JSON-RPC over stdin→stdout, dispatching
//! `initialize`, `notifications/*`, and `tools/call` for the four A-pathed handlers
//! (zkc_query / zkc_review_queue_list / zkc_scheduler_due / zkc_review_queue_resolve).
//!
//! Byte-parity with `src/zkc/transport/{stdio,mcp_server,protocol}.py`:
//!   * frame = `json.dumps(obj, ensure_ascii=False, separators=(",",":"), default=str)`
//!     → `serde_json::to_string` (compact, non-ASCII raw).
//!   * tools/call result = `{"content":[{"type":"text","text": <json.dumps(payload,ensure_ascii=False)>}],"isError":b}`
//!     where success text = `py_json(payload)` (Python DEFAULT separators, insertion-order keys),
//!     and error text = the handler-failure STRING verbatim (payload is str → text = the string).
//!   * notification (no `id`) → no frame; blank lines skipped; flush per frame.
//! Verified via Python↔Rust transcript parity (NOT app record, to protect the 199-case baseline).

use std::io::{self, BufRead, Write};
use std::process::ExitCode;

use serde_json::{Value, json};

const JSONRPC: &str = "2.0";
const PROTOCOL_VERSION: &str = "2024-11-05"; // recorded-literal: contract.MCP_PROTOCOL_VERSION
const CONTRACT_VERSION: &str = "zkc-mcp-contract/v1"; // recorded-literal: contract.CONTRACT_VERSION
const SERVER_INFO: &str = r#"{"name": "zkc", "version": "0.1.0"}"#; // recorded-literal: contract.SERVER_INFO
const CAPABILITIES: &str =
    r#"{"tools": {"listChanged": false}, "resources": {"subscribe": false, "listChanged": false}}"#; // recorded-literal: contract.CAPABILITIES
const INSTRUCTIONS: &str = "默认 stdio 零网络面、无需 token；外部 agent 一律零信任；写白名单 + 私人 claim 默认脱敏；跨机 HTTP/SSE 须端到端加密隧道，否则不变式⑤（本地优先/隐私）自动否决"; // recorded-literal: contract.TRUST_BOUNDARY

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

/// `mcp_server._tool_result(payload, is_error)`: str payload → text is the raw string; else py_json.
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

/// Route a tools/call, returning the tool-result envelope.
fn call_tool(name: &str, arguments: &Value, dsn: Option<&str>) -> Value {
    let Some(dsn) = dsn else {
        return tool_result("handler 执行失败：RuntimeError: ZKC_PG_DSN not set".into(), true);
    };
    let rt = match tokio::runtime::Builder::new_current_thread().enable_all().build() {
        Ok(rt) => rt,
        Err(e) => return tool_result(format!("handler 执行失败：RuntimeError: {e}"), true),
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
        "zkc_review_queue_resolve" => {
            rt.block_on(crate::units::search_sql::resolve_raw(dsn, arguments))
        }
        other => {
            // unregistered / blacklisted tool → denial string as isError text (matches _call_tool).
            return tool_result(
                format!("拒绝调用 {:?}：未注册的 tool；暴露面仅含 contract v1 白名单五 tool", other),
                true,
            );
        }
    };
    match result {
        Ok(payload) => tool_result(py_json(&payload), false),
        Err(msg) => tool_result(format!("handler 执行失败：ValueError: {msg}"), true),
    }
}

/// The stdio event loop (mirrors transport/stdio.serve_stdio). Returns at EOF.
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
        let message: Value = match serde_json::from_str(line) {
            Ok(m) => m,
            Err(_) => continue,
        };
        if message.get("id").is_none() {
            continue; // notification → no reply frame
        }
        let id = message.get("id").cloned().unwrap_or(Value::Null);
        let method = message.get("method").and_then(Value::as_str).unwrap_or("");
        let params = message.get("params").cloned().unwrap_or(Value::Null);

        let result: Value = match method {
            "initialize" => initialize_result(params.get("protocolVersion").and_then(Value::as_str)),
            "tools/call" => {
                let name = params.get("name").and_then(Value::as_str).unwrap_or("");
                let arguments = params
                    .get("arguments")
                    .cloned()
                    .unwrap_or_else(|| Value::Object(Default::default()));
                call_tool(name, &arguments, dsn.as_deref())
            }
            _ => continue,
        };
        let frame = json!({"jsonrpc": JSONRPC, "id": id, "result": result});
        let _ = writeln!(out, "{}", serde_json::to_string(&frame).unwrap_or_default());
        let _ = out.flush();
    }
    ExitCode::SUCCESS
}
