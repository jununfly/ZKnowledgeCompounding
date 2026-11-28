# Finding 17 · 注入标记检测的可证边界（ticket 8 / task 2）

> 2026-11-28。类型：纯函数可证切片（无编码缝）。归属 task 2。

## 观察

`src/zkc/mcp/injection.py::detect_injection_markers(text: str) -> List[str]`：
对不可信文档做提示注入标记检测——`text.lower()` 后按 `INJECTION_MARKERS`
声明顺序返回命中的 marker 子串，去重保序；空串 / None-like 返回空列表。
15 个 marker 由常量元组 `INJECTION_MARKERS` 给出（ADR-0004 黑名单四类危险写
`distill/trigger` / `interval_adjustment` / `meta_claim` / `history/delete` /
`history/update` + 常见注入话术 `ignore previous instructions` / `忽略之前的指令` /
`调用工具` 等）。

**为何可直接录原实现**：入参 str、返回 List[str]，全 JSON-native；无 dataclass /
Storage / LLM / callable / datetime，PyO3 bridge 无编码缝，无需 process-only alias
即可逐字录制。分析 `rust-anything analyze --whole-app`：`src/zkc/mcp/` unit
readiness 71 / wave 1 / ready，但它是混合 unit（capture/handlers 吃注入 callable 与
datetime），本片只切 `injection.py` 的单个纯函数，不宣称 mcp unit 等价。

## 纪律与 gate

- 录制期 Python 原实现仍是唯一 oracle；Rust 单测只做已证明行为的日常回归（Q3）。
- 15 个 marker 文本在 port 中逐字保留，每个加 `// recorded-literal: ...` 同行注释
  （同 `r14-judgment-rs` 的 5 个 reason 分支），不 promote 为 CALIBRATED——它们来自
  ADR-0004 安全黑名单，不是 tuning 校准参数。
- `test_mcp_capture_profile.py::test_injection_marker_detection` 提供既有测试锚点。

## 边界（不得读成）

- **安全契约真相源仍是 Python 侧 `INJECTION_MARKERS` + ADR-0004**；Rust port 只是
  录制期等价回放，不是安全策略的新定义源。任何 marker 增删须先改 Python 契约并重录，
  不得在 Rust 侧单独调整。
- 检测只用于留痕与标记，绝不把命中当可执行指令；白黑名单与 HITL 归因闸在
  `handlers.py`，不在本片范围。
- `capture_documents` / `build_handlers` / `build_zkc_server`（吃 callable / Storage /
  CaptureProfile dataclass）留 Python，Q5=C 编码边界未翻案。
- 录制 case 是人工定向输入，非全输入空间；大小写/子串/Unicode 的覆盖以 cases.jsonl 为准。
