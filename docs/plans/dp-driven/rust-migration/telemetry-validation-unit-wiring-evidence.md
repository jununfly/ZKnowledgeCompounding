# Evidence · `_validate_report` 接入 rust/app（ticket 42）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与 kill switch 语义仍以 app 实现为准。
R14 遥测字段契约真相源是 `src/zkc/r14_telemetry.py` 的 `REQUIRED_FIELDS` + `tests/test_r14_telemetry.py`，本接线只做逐字回放，不新定义字段策略、不产真实 run、不触发 R14 关闭。

## 结论

`rust/telemetry-validation-rs` 的 `validate_report` 已作为新前门 `unit-telemetry-validation` 接入 `rust/app`。
DP：ticket 42（parent 8，blocks `42→8`）已完成并释放租约，ticket 8 仍是唯一活跃租约。

命令形态：

```
metrics-snapshot unit-telemetry-validation validate_report '<json-array>'
# json-array = [report]   （report = dict；缺字段/非 dict 抛 ValueError，成功返回 null）
# kill switch: RUST_ANYTHING_UNIT_TELEMETRY_VALIDATION=original
```

## 接线方式

- 前置登记：`rust/app/src/cli.rs::UNIT_COMMANDS` 与 `rust/app/rust-anything.json::commands` 加入 `unit-telemetry-validation`。
- 真跑 `rust-anything app wire . telemetry-validation-rs --command unit-telemetry-validation --skip-gate --no-check`，
  生成 `RUST_ANYTHING_UNIT_TELEMETRY_VALIDATION` kill switch 与 `units/telemetry_validation.rs` stub，
  并把 `telemetry-validation-rs` 写进 `Cargo.toml` / `Cargo.lock` / `rust-anything.json::units`。
- 照惯例备份 wire 前的 `units/mod.rs`（wire 会重写它、丢掉 metrics 路由与既有单元），
  恢复后手合并回 `mod telemetry_validation;` 与 `unit-telemetry-validation` dispatch 分支，
  保留 metrics + 十三单元 + 新单元（共十四单元）。
- 手写 glue `units/telemetry_validation.rs`：单 `Value` 位置参数 `report`（JSON object），
  委托 `telemetry_validation_rs::port::validate_report`，`emit` 输出（port 返回 `Result<Value, String>` 正好匹配）。
  **无异常前缀缝**（port 错误文本自带 `ValueError: `，与 oracle 逐字一致，同 operator-guard/percentile/r14/artifact-shaping）。
- `oracle.py`：加载 `spikes/spike-23-telemetry-validation/pure_bridge.py` 别名，加 `TELEMETRY_VALIDATION` 表项，
  unit key 用 kebab `telemetry-validation`（与命令 `unit-telemetry-validation` 逐字一致，避开历史 `cross_source` 坑）。
- `smoke_units.py`：+8 case（合法 report / 额外键忽略 / 全缺失 / 单字段缺失 / 两字段缺失声明序 /
  乱序键仍按声明序 / 非 dict ValueError / 字段值不做类型校验）。

## 验证（全绿）

| 检查 | 结果 |
|---|---|
| smoke（app vs Python oracle） | **109/109**（101 + 8），stdout 与 exit code 逐字一致 |
| kill switch 三态 | default 0 次 Python 调用 / `=original` 恰好 1 次且输出逐字一致（成功 `{"ok":null}`；错误 `[{}]` 两侧同为 `ValueError: report missing required field(s): completion_fired, main_latency_ms, completion_latency_ms` exit 1）/ 关掉后 0 次 |
| app replay（11 case） | 11/11，fallback **0.0%** |
| crate diff | 16/16 cases match |
| app fmt / clippy / build | 全过（clippy 因新依赖补 1 条 Cargo.lock，正常） |
| make test | **671 OK** |
| 三门禁 | mcp-gate 6/6 / invariant 0 violations / authority 0 leaks |

## 边界与风险

- 只证函数级逐字等价，不冒充公开调用者 `record_run` / `load_runs` / `aggregate` 的行为——三者吃文件 IO，按 Q5 文件 IO 边界留 Python。
- 不是 R14 关闭的运行时保证：R14 已于 2026-11-12 由 zj 真实 10 run 裁决收口，真实数据经 dogfood + `r14_telemetry` 落库（过程态）；本片不产真实 run、不触发关闭。
- 缺失字段按 `REQUIRED_FIELDS` 声明序报告（非入参键序）；字段值不做类型校验（值校验在下游 `record_run` 的 `bool()/float()` 与 `judge_r14`）：接线不改这两点。
- 三字段名、错误消息文本、`, ` 分隔符均为 `recorded-literal`（port 同行注释），不 promote 为 CALIBRATED。
- `src/zkc/**` 零改动；kill switch 仅走 process-only oracle，不进生产代码。
