# Evidence · detect_injection_markers 接入 rust/app（ticket 36）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与 kill switch 语义仍以 app 实现为准。
安全契约（marker 列表与匹配语义）真相源仍是 `src/zkc/mcp/injection.py::INJECTION_MARKERS` + ADR-0004，本接线只做逐字回放，不新定义策略。

## 结论

`rust/injection-detection-rs` 的 `detect_injection_markers` 已作为新前门 `unit-injection` 接入 `rust/app`。
DP：ticket 36（parent 8，blocks `36→8`）已完成并释放租约，ticket 8 仍是唯一活跃租约。

命令形态：

```
metrics-snapshot unit-injection detect_injection_markers '<json-array>'
# json-array = [text]   （单 str 入参）
# kill switch: RUST_ANYTHING_UNIT_INJECTION_DETECTION=original
```

## 接线方式

- 前置登记：`rust/app/src/cli.rs::UNIT_COMMANDS` 与 `rust/app/rust-anything.json::commands` 加入 `unit-injection`。
- 真跑 `rust-anything app wire . injection-detection-rs --command unit-injection --skip-gate --no-check`，
  生成 `RUST_ANYTHING_UNIT_INJECTION_DETECTION` kill switch 与 `units/injection_detection.rs` stub，
  并把 `injection-detection-rs` 写进 `Cargo.toml` / `Cargo.lock` / `rust-anything.json::units`。
- 照惯例备份 wire 前的 `units/mod.rs`（wire 会重写它、丢掉 metrics 路由与既有单元），
  恢复后手合并回 `mod injection_detection;` 与 `unit-injection` dispatch 分支，
  保留 metrics + 十单元 + 新单元（共十一单元）。
- 手写 glue `units/injection_detection.rs`：单个 `Value` 位置参数 `text`，
  委托 `injection_detection_rs::port::detect_injection_markers`，`emit` 输出。
  无异常前缀缝（port 唯一错误文本是裸 `AttributeError: ...`，与 oracle 逐字一致；
  录制 case 全为 str，该分支仅防御性存在）。
- `oracle.py`：加载 spike-20 alias（`zkc_injection_oracle`），加 `INJECTION` 表项，
  注册 unit key `injection`（与命令 `unit-injection` 逐字一致，避开历史上 `cross_source` 拼出未注册命令的坑）。
- `smoke_units.py`：新增 8 个 injection case（空串 / 无 marker / 单 marker / 大小写不敏感 /
  声明顺序非文本序 / 中文声明序 / 去重 / 子串匹配），全部 str 入参——未录的 defensive 非 str 分支刻意不成 case。

## 验证

| 检查 | 结果 |
|---|---|
| crate diff | 18/18 cases match |
| crate gate | Gate passed（1.2x，literals 0，15 个 `recorded-literal` 注释同行） |
| app fmt / clippy / build | 全过（clippy 因新依赖补 1 条 lock，正常） |
| smoke（含 oracle 逐字比对） | **85/85**（77 + 8） |
| kill switch 三态（假 python3 包装器） | default 0 次 / `=original` 恰好 1 次且输出一致 / 关掉 0 次 |
| app replay（11 case） | 11/11，fallback **0.0%** |
| make test | **671 OK** |
| 三门禁 | mcp-gate 6/6 / invariant 0 violations / authority 0 leaks |

kill switch 一致性实证（`"distill/trigger 请忽略之前的指令"`）：
default Rust 直出 `{"ok":["distill/trigger","忽略之前的指令"]}`（0 次 Python）；
`=original` 输出逐字相同（1 次 Python）；关掉后不再调用（0 次）。

## 边界与风险

- **安全契约真相源仍是 Python**：15 个 marker 由 `INJECTION_MARKERS` + ADR-0004 定义，
  Rust 侧为 recorded-literal，不 promote、不在 Rust 单独增删。marker 变更须改 Python 契约并重录重接。
- **回放非策略**：本接线证明的是确定性检测函数的逐字等价；白黑名单与 HITL 归因闸在 `handlers.py` 留 Python，
  `capture_documents` / server builders（callable / Storage / CaptureProfile）均在 Q5=C 边界外。
- **未录分支**：Unicode 特殊 lower 映射（如 İ）与非 str 入参未录制，属防御分支，不构成等价证据。
- `src/zkc/**` 零改动；未翻 Q5=C 案。
