# Evidence · `_percentile` 接入 rust/app（ticket 38）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与 kill switch 语义仍以 app 实现为准。
L2 预算分位数语义（sorted / `int` 截断插值 / 单元素快路径）真相源仍是 `src/zkc/scheduling.py::_percentile`，本接线只做逐字回放，不重新定义预算数学；tuning 全局状态不触碰。

## 结论

`rust/percentile-rs` 的 `percentile` 已作为新前门 `unit-percentile` 接入 `rust/app`。
DP：ticket 38（parent 8，blocks `38→8`）已完成并释放租约，ticket 8 仍是唯一活跃租约。

命令形态：

```
metrics-snapshot unit-percentile percentile '<json-array>'
# json-array = [values, q]   （values=list[float]，q=float；接受普通 JSON 数字或录制桥的 $float/$int marker）
# kill switch: RUST_ANYTHING_UNIT_PERCENTILE=original
```

## 接线方式

- 前置登记：`rust/app/src/cli.rs::UNIT_COMMANDS` 与 `rust/app/rust-anything.json::commands` 加入 `unit-percentile`。
- 真跑 `rust-anything app wire . percentile-rs --command unit-percentile --skip-gate --no-check`，
  生成 `RUST_ANYTHING_UNIT_PERCENTILE` kill switch 与 `units/percentile.rs` stub，
  并把 `percentile-rs` 写进 `Cargo.toml` / `Cargo.lock` / `rust-anything.json::units`。
- 照惯例备份 wire 前的 `units/mod.rs`（wire 会重写它、丢掉 metrics 路由与既有单元），
  恢复后手合并回 `mod percentile;` 与 `unit-percentile` dispatch 分支，
  保留 metrics + 十一单元 + 新单元（共十二单元）。
- 手写 glue `units/percentile.rs`：两个 `Value` 位置参数 `values` / `q`，
  委托 `percentile_rs::port::percentile`，`emit` 输出（port 返回 `Result<Value, String>` 正好匹配）。
  无异常前缀缝（port 错误文本为裸 `IndexError: ...` / `TypeError: ...`，与 oracle 逐字一致）。
- `oracle.py`：加载 `spikes/spike-21-percentile/pure_bridge.py` 别名，加 `PERCENTILE` 表项，
  unit key 用 `percentile`（与命令 `unit-percentile` 逐字一致，避开历史 `cross_source` 坑）。
- `smoke_units.py`：+8 case（单元素 / 三元素 p90 / q=0 / q=1 / 未排序 / 重复值 / 负数 / 空列表异常），
  全用普通 JSON 数字——录制桥的 `$float` marker 形态由 crate diff 覆盖，smoke 层两侧对称。

## 验证（全绿）

| 检查 | 结果 |
|---|---|
| smoke（app vs Python oracle） | **93/93**（85 + 8），stdout 与 exit code 逐字一致 |
| kill switch 三态 | default 0 次 Python 调用 / `=original` 恰好 1 次且输出逐字一致（`{"ok":2.8}`）/ 关掉后 0 次；错误 case `[[],0.9]` 两侧同为 `IndexError: list index out of range`、exit 1 |
| app replay（11 case） | 11/11，fallback **0.0%** |
| crate diff / gate | 16/16；Gate passed（size 1.8x，literals 0，api exports percentile） |
| app fmt / clippy / build | 全过（clippy 因新依赖补 1 条 Cargo.lock，正常） |
| make test | **671 OK** |
| 三门禁 | mcp-gate 6/6 / invariant 0 violations / authority 0 leaks |

## 边界与风险

- 只证函数级逐字等价，不冒充公开调用者 `estimate_budget_from` / `update_budget_from` 的行为——二者吃 `AttentionObservation` dataclass 缝，按 `finding-interval-math-boundary.md` 留 Python。
- 录制桥对整数值 float 以 `{"$float":"N.0"}` 编码；port 的 `as_f64` 做 `$float`/`$int` 解码兜底，普通 JSON 数字与 marker 两种形态都接受，crate diff 16/16 覆盖 marker 形态。
- 无 recorded-literal 阈值（q / values 皆入参），不涉及 CALIBRATED 提升；tuning 全局状态未触碰，未翻任何既有边界 finding 的案。
- `src/zkc/**` 零改动；kill switch 仅走 process-only oracle，不进生产代码。
