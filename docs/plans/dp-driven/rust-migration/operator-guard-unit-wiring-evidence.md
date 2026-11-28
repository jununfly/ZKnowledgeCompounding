# Evidence · `_require_operator` 接入 rust/app（ticket 40）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与 kill switch 语义仍以 app 实现为准。
人环 operator 守卫真相源是 ADR-0013 + PRD 节点生命周期三态段 + `src/zkc/tombstone.py`，本接线只做逐字回放，不新定义 operator 策略，也不代替 `mark_tombstone` / `restore_node` 的人环门。

## 结论

`rust/operator-guard-rs` 的 `require_operator` 已作为新前门 `unit-operator-guard` 接入 `rust/app`。
DP：ticket 40（parent 8，blocks `40→8`）已完成并释放租约，ticket 8 仍是唯一活跃租约。

命令形态：

```
metrics-snapshot unit-operator-guard require_operator '<json-array>'
# json-array = [operator]   （operator = str | null）
# kill switch: RUST_ANYTHING_UNIT_OPERATOR_GUARD=original
```

## 接线方式

- 前置登记：`rust/app/src/cli.rs::UNIT_COMMANDS` 与 `rust/app/rust-anything.json::commands` 加入 `unit-operator-guard`。
- 真跑 `rust-anything app wire . operator-guard-rs --command unit-operator-guard --skip-gate --no-check`，
  生成 `RUST_ANYTHING_UNIT_OPERATOR_GUARD` kill switch 与 `units/operator_guard.rs` stub，
  并把 `operator-guard-rs` 写进 `Cargo.toml` / `Cargo.lock` / `rust-anything.json::units`。
- 照惯例备份 wire 前的 `units/mod.rs`（wire 会重写它、丢掉 metrics 路由与既有单元），
  恢复后手合并回 `mod operator_guard;` 与 `unit-operator-guard` dispatch 分支，
  保留 metrics + 十二单元 + 新单元（共十三单元）。
- 手写 glue `units/operator_guard.rs`：单 `Value` 位置参数 `operator`，
  委托 `operator_guard_rs::port::require_operator`，`emit` 输出（port 返回 `Result<Value, String>` 正好匹配）。
  **无异常前缀缝**（port 错误文本自带 `ValueError: ` / `TypeError: `，与 oracle 逐字一致，同 percentile/r14/artifact-shaping）。
- `oracle.py`：加载 `spikes/spike-22-operator-guard/pure_bridge.py` 别名，加 `OPERATOR_GUARD` 表项，
  unit key 用 kebab `operator-guard`（与命令 `unit-operator-guard` 逐字一致，避开历史 `cross_source` 坑）。
- `smoke_units.py`：+8 case（普通/中文 operator、空白 strip、NBSP、`\x1c` isspace 边界缝、空白/None ValueError、内嵌 NUL 保留），
  刻意不覆盖未录制的非 str 防御分支。

## 验证（全绿）

| 检查 | 结果 |
|---|---|
| smoke（app vs Python oracle） | **101/101**（93 + 8），stdout 与 exit code 逐字一致 |
| kill switch 三态 | default 0 次 Python 调用 / `=original` 恰好 1 次且输出逐字一致（`{"ok":"zj"}`；错误 case `[null]` 两侧同为 `ValueError: ...` exit 1）/ 关掉后 0 次；`\x1cZJ\x1c` 两侧同为 `{"ok":"ZJ"}` |
| app replay（11 case） | 11/11，fallback **0.0%** |
| crate diff / gate | 16/16；Gate passed（size 0.8x，literals 0，api exports require_operator） |
| app fmt / clippy / build | 全过（clippy 因新依赖补 1 条 Cargo.lock，正常） |
| make test | **671 OK** |
| 三门禁 | mcp-gate 6/6 / invariant 0 violations / authority 0 leaks |

## 边界与风险

- 只证函数级逐字等价，不冒充公开调用者 `mark_tombstone` / `restore_node` 的行为——二者吃 Storage/UUID/datetime，按 Q5=C 与 finding 19 留 Python。
- 关键边界：Python `str.strip()` 的 `isspace()` 含 `\x1c..\x1f`（FS/GS/RS/US），Rust `char::is_whitespace()` 不含；port 以 `py_isspace` 补齐后 trim 字符集与 CPython 逐字符一致，smoke 的 `\x1c` case 与 crate diff 的 `\x1c..\x1f` case 双侧证明。
- 中文 ValueError 文本是 ADR-0013 人环契约的 recorded-literal（同行注释），不 promote 为 CALIBRATED。
- 非 str / 非 None 入参的防御分支未被录制（spike-22 只导 str|None），不构等价证据；`TypeError` 文本是 Python 通用文本非 recorded value。
- `src/zkc/**` 零改动；kill switch 仅走 process-only oracle，不进生产代码。
