# Evidence · MCP exposure.attack_surface_table 切片（ticket 46）

日期：2026-11-28。过程态证据，非长期权威；crate 实现与 gate 语义以 `rust/mcp-exposure-rs` 为准。

## 结论

`src/zkc/mcp/exposure.py::{attack_surface_table, entry_names}` 已 port 到 Rust
`rust/mcp-exposure-rs`，**gate 全 pass**；**未接线进 `rust/app`**（静态攻击面契约表，非 per-call 运行函数，
MCP server 若需读取再走 app-wire）。DP：ticket 46（parent 9，derived-from finding 25 transport-baseline，
task 3）已完成并释放租约。

## 选片理由

- 全 JSON-native：两个函数**零参数**、返回仅 `str`/`list`/`dict`，由 `zkc.transport.contract` 常量 +
  `exposure.py` 的 recorded-literal（`_KINDS`/`_GUARDS`/`injectionGate`/trustBoundary 前缀）确定，
  无 Storage / callable / dataclass / datetime 编码缝。
- 契约真相源（白名单 5 tool、blacklist、trustBoundary）已在 `transport-rs` port 录制（finding 25），
  本片 `include_str!` 复用同一 `contract_v1.json`，**不另起清单**。

## 录制与实现要点

- `rust-anything bridge . spikes/spike-25-mcp-exposure/pure_bridge.py --name mcp-exposure-rs -o rust/mcp-exposure-rs`；
  spike 仅纯委托原函数（alias 固定录制面）。
- `record --count 0 --inputs <2 定向 case>`：两函数零参、确定性，oracle 即唯一 case（`attack_surface_table`→dict、
  `entry_names`→5 名 list），**2/2 recorded, 0 threw**（`PYTHONPATH=<repo>/src` 让 recorder import `zkc`）。
- `entry` 按 `contract["tools"]` 顺序生成；`kind`/`guard`/`injectionGate` 文本逐字保留，每个加同行
  `// recorded-literal:` 注释（同 `injection-detection-rs` marker 模式，过 literals 检查）。
- `trustBoundary = exposure 前缀串 + contract.trustBoundary`；`blacklist` 取 contract 后 `sort()`（ASCII，字节序=码点序）。
- 键序依赖 `serde_json` `preserve_order` 复现 Python dict 字面量顺序（`entry, egress, trustBoundary, blacklist, injectionGate`）。

## 机械验证

| 检查 | 结果 |
|---|---|
| record | **2 cases（0 threw）** |
| build | PyO3 模块构建成功（`python/mcp_exposure_rs`） |
| crate diff | **2/2 recorded cases match** |
| gate | **Gate passed**：fmt / clippy（0 warn）/ cargo test / unsafe 0 / lockfile / ported / size 4.4x / literals 0 / tests 2·6 / error cases none / panics 0 / build / api（exports attack_surface_table, entry_names）/ behavior **2/2** |
| `app replay` | N/A：本片未接线，无 app 前门（与 ticket 35 注入切片一致） |

## 边界与风险

- **安全契约真相源是 Python 侧 `contract_v1.json` + `exposure.py`**；Rust port 只是录制期等价回放，
  不是策略新定义源。tool 增删 / guard 文案 / blacklist 变更须先改 Python 契约并重录，不得在 Rust 侧单独调整。
  recorded-literal 文本不 promote 为 CALIBRATED。
- 零参函数无输入空间可 fuzz，`fuzz` 步骤不适用；证明仅覆盖录制期返回结构等价，不声称对 `contract_v1.json`
  被改动后的动态行为负责（改动会触发 fingerprint 变化、需重录）。
- `egress` 恒空是「单边 server」事实，非漏洞；phase 2 双向 client 须显式决议（见 `handlers.py`/ADR-0004）。
- `src/zkc/**` 零改动；未接线进 app；未提交，按 zj 的 checkpoint 指令再拆 feat/chore 提交。
