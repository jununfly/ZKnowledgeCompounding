//! The Rust port of `spikes/spike-25-mcp-exposure/pure_bridge.py`.
//!
//! `attack_surface_table` / `entry_names` are the deterministic MCP attack-surface
//! projection (ADR-0004 mandatory section): a pure function of the `zkc-mcp-contract v1`
//! snapshot plus recorded literals defined in `exposure.py`. The `entry` rows follow
//! `contract["tools"]` order; each tool's `kind`/`guard` prose and the `injectionGate`
//! assertions are recorded literals — the original's security contract, not a new policy
//! source. `egress` is empty (single-sided server). `trustBoundary` concatenates the
//! `exposure.py` prefix with `contract["trustBoundary"]`. `blacklist` is the contract
//! blacklist sorted. Contract values are read from the embedded `contract_v1.json` (same
//! truth source as `rust/transport-rs`), so the whitelist/blacklist is never duplicated here.

#![forbid(unsafe_code)]

use serde_json::{Map, Value, json};

const CONTRACT: &str = include_str!("../../../src/zkc/transport/contract_v1.json");

/// The `exposure.py` trustBoundary prefix prose.
const EXPOSURE_PREFIX: &str = "默认 stdio 零网络面、无需 token；外部 agent 一律零信任；写白名单 + 私人 claim 沙箱；跨机 HTTP/SSE 须端到端加密隧道，否则不变式⑤自动否决。"; // recorded-literal: exposure.py trustBoundary prefix

/// Per-tool read/write classification. The name keys are `contract["tools"]` ids; the kind
/// text is the original's `_KINDS`.
const KINDS: &[(&str, &str)] = &[
    ("zkc_capture", "write"),          // recorded-literal: exposure.py _KINDS
    ("zkc_query", "read"),             // recorded-literal: exposure.py _KINDS
    ("zkc_review_queue_list", "read"), // recorded-literal: exposure.py _KINDS
    ("zkc_review_queue_resolve", "write"), // recorded-literal: exposure.py _KINDS
    ("zkc_scheduler_due", "read"),     // recorded-literal: exposure.py _KINDS
];

/// Per-tool guard prose (the original's `_GUARDS`).
const GUARDS: &[(&str, &str)] = &[
    (
        "zkc_capture", // recorded-literal: exposure.py _GUARDS key
        "写，受 DecisionRouter 分流闸 + 双信号弃权 + review_queue 人审；capture profile 默认开启", // recorded-literal: exposure.py _GUARDS
    ),
    (
        "zkc_query", // recorded-literal: exposure.py _GUARDS key
        "读，响应强制带 evidence_refs 溯源；私人 claim 默认脱敏，须显式授权方可带隐私字段", // recorded-literal: exposure.py _GUARDS
    ),
    (
        "zkc_review_queue_list", // recorded-literal: exposure.py _GUARDS key
        "读，仅列 open 项；不暴露 resolved 历史", // recorded-literal: exposure.py _GUARDS
    ),
    (
        "zkc_review_queue_resolve", // recorded-literal: exposure.py _GUARDS key
        "写，仅标 resolved + HITL 归因；绝不写 interval / distill / meta_claim", // recorded-literal: exposure.py _GUARDS
    ),
    (
        "zkc_scheduler_due", // recorded-literal: exposure.py _GUARDS key
        "读，该关注清单（注意力语义的首个 resource）", // recorded-literal: exposure.py _GUARDS
    ),
];

fn lookup(table: &[(&'static str, &'static str)], name: &str) -> &'static str {
    table
        .iter()
        .find(|(k, _)| *k == name)
        .map(|(_, v)| *v)
        .unwrap_or("")
}

fn contract() -> Result<Value, String> {
    serde_json::from_str(CONTRACT).map_err(|e| format!("contract_v1.json parse error: {e}"))
}

/// Port of `attack_surface_table` (`spikes/spike-25-mcp-exposure/pure_bridge.py:40`).
pub fn attack_surface_table() -> Result<Value, String> {
    let snapshot = contract()?;

    let tools = snapshot
        .get("tools")
        .and_then(Value::as_array)
        .ok_or_else(|| "contract: 'tools' is not an array".to_string())?;

    let mut entry = Vec::with_capacity(tools.len());
    for tool in tools {
        let name = tool
            .get("name")
            .and_then(Value::as_str)
            .ok_or_else(|| "contract: tool without 'name'".to_string())?;
        let mut row = Map::new();
        row.insert("name".into(), json!(name));
        row.insert("kind".into(), json!(lookup(KINDS, name)));
        row.insert("guard".into(), json!(lookup(GUARDS, name)));
        entry.push(Value::Object(row));
    }

    let trust_boundary = snapshot
        .get("trustBoundary")
        .and_then(Value::as_str)
        .ok_or_else(|| "contract: 'trustBoundary' missing".to_string())?;

    let mut blacklist: Vec<String> = snapshot
        .get("blacklist")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default();
    blacklist.sort();

    let injection_gate = json!([
        {
            "id": "unauthorized_write_rejected", // recorded-literal: exposure.py injectionGate
            "assertion": "distill/trigger、interval_adjustment、meta_claim 等未授权写返回权限拒绝" // recorded-literal: exposure.py injectionGate
        },
        {
            "id": "private_claim_absent_in_query", // recorded-literal: exposure.py injectionGate
            "assertion": "私人 claim 内容不出现在 zkc_query 响应体（默认脱敏）" // recorded-literal: exposure.py injectionGate
        },
        {
            "id": "review_queue_overreach_audited", // recorded-literal: exposure.py injectionGate
            "assertion": "越权企图回写 review_queue 留痕（tool_denied / hitl_attribution 审计事件）" // recorded-literal: exposure.py injectionGate
        }
    ]);

    // Key order mirrors the Python dict literal (serde_json preserve_order).
    let mut table = Map::new();
    table.insert("entry".into(), Value::Array(entry));
    table.insert("egress".into(), json!([]));
    table.insert(
        "trustBoundary".into(),
        json!(format!("{EXPOSURE_PREFIX}{trust_boundary}")),
    );
    table.insert(
        "blacklist".into(),
        Value::Array(blacklist.into_iter().map(Value::from).collect()),
    );
    table.insert("injectionGate".into(), injection_gate);
    Ok(Value::Object(table))
}

/// Port of `entry_names` (`spikes/spike-25-mcp-exposure/pure_bridge.py:44`).
pub fn entry_names() -> Result<Value, String> {
    let names = attack_surface_table()?
        .get("entry")
        .and_then(Value::as_array)
        .map(|rows| {
            rows.iter()
                .filter_map(|r| r.get("name").cloned())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    Ok(Value::Array(names))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn attack_surface_projection_is_well_formed() {
        let t = attack_surface_table().unwrap();
        let entry = t["entry"].as_array().unwrap();
        assert_eq!(entry.len(), 5);
        assert!(t["egress"].as_array().unwrap().is_empty());
        let bl = t["blacklist"].as_array().unwrap();
        let mut sorted = bl.clone();
        sorted.sort_by(|a, b| a.as_str().unwrap().cmp(b.as_str().unwrap()));
        assert_eq!(*bl, sorted);
        assert_eq!(t["injectionGate"].as_array().unwrap().len(), 3);
        assert!(
            t["trustBoundary"]
                .as_str()
                .unwrap()
                .starts_with(EXPOSURE_PREFIX)
        );
    }

    #[test]
    fn entry_names_matches_contract_order() {
        let arr = entry_names().unwrap();
        let arr = arr.as_array().unwrap();
        assert_eq!(
            arr.iter().map(|v| v.as_str().unwrap()).collect::<Vec<_>>(),
            vec![
                "zkc_capture",
                "zkc_query",
                "zkc_review_queue_list",
                "zkc_review_queue_resolve",
                "zkc_scheduler_due"
            ]
        );
    }
}
