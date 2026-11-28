# Evidence · detect_injection_markers 注入标记检测切片（ticket 35）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与 gate 语义以 crate 实现为准。

## 结论

`src/zkc/mcp/injection.py::detect_injection_markers` 已 port 到 Rust
`rust/injection-detection-rs`，**未接线进 `rust/app`**（无前门命令）。
DP：finding 17（观察 memo 保留未完成）+ ticket 35（parent 8，derived-from finding 17，
blocks `35→8`）已完成并释放租约；ticket 8 仍是唯一活跃租约。

## 选片理由

- 全 JSON-native：`str -> List[str]`，无 dataclass / Storage / LLM / callable /
  datetime 编码缝——是少数不需要 process-only alias 也能逐字录制的函数（本片仍用
  spike-20 固定录制面，避免把混合的 `src/zkc/mcp/` unit 整包 bridge）。
- 有既有测试锚点 `test_mcp_capture_profile.py::test_injection_marker_detection`；
  契合 mcp-gate（CI required check）所在的安全域。
- 避开混合 mcp unit 中吃 callable / Storage / CaptureProfile dataclass 的
  `capture_documents` / `build_handlers` / `build_zkc_server`（Q5=C 边界未翻案）。

## 录制与实现要点

- `rust-anything bridge . spikes/spike-20-injection-detection/pure_bridge.py --name
  injection-detection-rs -o rust/injection-detection-rs`；`spikes/spike-20-*/pure_bridge.py`
  仅纯委托原函数（无编码缝，alias 只固定单函数录制面）。
- `record --inputs <18 定向 case> --count 0`：覆盖空串/空白、普通文本（无 marker）、
  单 marker、大小写混合、子串匹配、去重、中文 marker、`call/invoke tool` 家族；
  **15/15 个 marker 文本全部在 case 中被触发**。
- 关键语义：按 `INJECTION_MARKERS` **声明顺序**返回命中（非文本出现顺序，
  case 6/9 实证），大小写不敏感（`str.lower()`），子串匹配，去重保序；空串返回 []。
- port 中 15 个 marker 逐字保留，每个加 `// recorded-literal:` 同行注释（同
  `r14-judgment-rs` reason 分支模式）；fmt 重排后注释仍与字面量同行。

## 机械验证

| 检查 | 结果 |
|---|---|
| crate diff | **18/18** recorded cases match（0 threw） |
| gate | **Gate passed**：fmt / clippy / cargo test / unsafe / lockfile / ported / size 1.2x / literals 0 / tests / error cases / panics / build / api / behavior 18/18 |
| `app replay --build rust/app/target/debug/metrics-snapshot`（既有 11 case） | **11/11 passed**，fallback **0.0%**（本片未接线，零回退） |
| `make test` | **671 OK** |
| mcp-gate / invariant / authority | **6/6** / **0 violations** / **0 leaks** |

## 边界与风险

- **安全契约真相源是 Python 侧 `INJECTION_MARKERS` + ADR-0004**；Rust port 只是
  录制期等价回放，不是安全策略新定义源。marker 增删须先改 Python 契约并重录，
  不得在 Rust 侧单独调整。15 个 marker 文本是 recorded-literal，不 promote 为 CALIBRATED。
- 检测只用于留痕/标记，绝不把命中当可执行指令；白黑名单与 HITL 归因闸在
  `handlers.py`，不在本片范围。`capture_documents` / server builders 留 Python。
- 录制 case 是人工定向输入，非全输入空间；`str.lower()` 的 Unicode 特殊映射
  （如 İ→i̇）未单独录制，不得声称覆盖。非 str 入参（None / int）未录制，port 中
  的 `AttributeError` 分支是防御性兜底、非等价证据。
- `src/zkc/**` 零改动；未接线进 app；未提交，按 zj 的 checkpoint 指令再拆 feat/chore 提交。
