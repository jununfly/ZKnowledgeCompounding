# Evidence · judge_r14 接入 rust/app（ticket 32）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与 kill switch 语义仍以 app 实现为准。

## 结论

`rust/r14-judgment-rs` 的 `judge_r14` 已作为新前门 `unit-r14` 接入 `rust/app`。
DP：ticket 32（parent 8，blocks `32→8`）已完成并释放租约，ticket 8 仍是唯一活跃租约。

命令形态：

```
metrics-snapshot unit-r14 judge_r14 '<json-array>'
# json-array = [runs, min_runs]
# kill switch: RUST_ANYTHING_UNIT_R14_JUDGMENT=original
```

## 接线方式

- 前置登记：`rust/app/src/cli.rs::UNIT_COMMANDS` 与
  `rust/app/rust-anything.json::commands` 加入 `unit-r14`。
- 真跑 `rust-anything app wire . r14-judgment-rs --command unit-r14 --skip-gate --no-check`：
  生成 Cargo path 依赖、unit 记录、switch 名与 glue stub；switch 由工具命名为
  `RUST_ANYTHING_UNIT_R14_JUDGMENT`（由 crate 名生成，不是 oracle key `r14`）。
- 照例重写 `units/mod.rs` 丢 `metrics_report`：接线前备份，wire 后手合并回
  metrics 路由 + 八个既有单元 + r14，统一 `<fn> <json-array>` 协议。
- 新 glue `rust/app/src/units/r14_judgment.rs`：1 函数 `Value` 端到端透传；
  port 错误是裸 `TypeError: ...` 文本，与 oracle 一致，**无异常前缀缝**（区别于
  `unit-distill` 的 `zkc.distill.` 剥离）。
- `oracle.py` 按路径加载 spike-18 alias（unit key `r14`）；alias 的
  `judge_r14(runs, min_runs)` 直接接受两个位置参数（内部还原 keyword-only
  `min_runs=`），与统一入口 `target(*args)` 一致，无需 kwargs 特判（区别于
  scheduling spike-09 的 `human=`）。
- `smoke_units.py` 新增 8 个 case（来自 20 录制 case 的代表样本）：覆盖全部
  5 个 reason 分支、median 奇偶、min_runs 0/1/2/10、空输入 floor。

## 机械验证

| 检查 | 结果 |
|---|---|
| `smoke_units.py` | **69/69** 逐字匹配（既有 61 + r14 8） |
| kill switch（假 python3 包装器） | default 不调 Python；`=original` 恰好调一次 oracle 且输出一致；关掉后不再调用 |
| `app replay --build`（既有 11 case） | **11/11 passed**，fallback **0.0%** |
| crate diff / gate | **20/20**；Gate passed（size 2.3x，literals 0） |
| app fmt / clippy -D warnings / build | 全过 |
| `make test` | **671 OK** |
| mcp-gate / invariant / authority | **6/6** / **0 violations** / **0 leaks** |

## 边界与风险

- **新前门，不是 lift**：69 smoke case 是人工选定输入，非全输入空间证明；录制期
  Python 原实现仍是唯一 oracle。
- 本片只证 R14 判据的确定性聚合，不产生真实 run、不触发补全关闭（R14 仍 open；
  真实数据经 zj 的 dogfood + `r14_telemetry` 落库）。阈值 0.5 / 1.5 / min_runs 默认
  10 仍是 recorded-literal，不 promote 为 CALIBRATED。
- 再次跑 `app wire` 会重写 `units/mod.rs`，必须重新手合并；`refresh` 之后需按
  crate 纪律重新验证 gate。
- `src/zkc/**` 零改动；未提交，按 zj 的 checkpoint 指令再拆 feat/chore 提交。
