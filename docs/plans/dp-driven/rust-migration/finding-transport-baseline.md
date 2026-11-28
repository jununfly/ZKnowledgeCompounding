# Finding · transport/contract/protocol 层已在 transport-rs port（ticket 9 的基线事实）

状态：未完成（观察 memo，保留至 task 3 编排落定）。

## 事实

`src/zkc/transport/` 的协议与契约层**已在 `rust/transport-rs` port**，非本 ticket 新增工作：

| Python（transport） | Rust（transport-rs/src/port.rs） |
|---|---|
| `contract.contract_snapshot` | `contract_snapshot`（`include_str!` 内嵌 `contract_v1.json`） |
| `contract.tool_schema` / `is_blacklisted` / `is_allowlisted` | 同名 port |
| `protocol` 报文 | `decode_message` / `encode_message` / `is_notification` / `result_response` / `error_response` |
| schema 校验 | `validate_arguments` |

## 对 ticket 9 的影响

MCP 适配器**真正剩余的边界是业务层**（`src/zkc/mcp/*`）：`exposure`（攻击面枚举表）、`handlers`（五 tool 编排）、`capture`（capture_documents）、`wiring`（composition root）。其中：

- `exposure.attack_surface_table` 是 `transport.contract` 常量之上的纯函数（无 Storage / callable / datetime），可直接切片 port；本 finding 即其「常量真相源已证」的依据。
- `injection.detect_injection_markers` 已 port 并接线（ticket 35/36，`injection-detection-rs` + `unit-injection`），不重复。

故 ticket 9 拆分不再包含 transport/contract 本体，只覆盖 CLI 前门 + MCP 业务层 + 编排接线。
