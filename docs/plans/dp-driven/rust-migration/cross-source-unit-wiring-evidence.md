# Evidence · cross_source 两函数接入 rust/app（ticket 28）

> 过程态证据，非持久权威。长期结论以 ADR/PRD/架构/代码为准。

## 结论

`rust/cross-source-rs` 的 2 个纯函数（`count_cross_source` / `enforce_citations`）
已作为新前门 `unit-cross-source` 接入 `rust/app`。录制期 Python 原实现仍是唯一 oracle；
Rust 侧只做黑盒等价复刻，不是全仓 lift，也没有改 `src/zkc/**`。

DP：ticket 28（parent 8，blocks `28→8`）已完成，租约释放，`validate` 0 errors；
ticket 8 仍在进行。

## 接线方式

- 前置登记：命令必须同时出现在 `src/cli.rs::UNIT_COMMANDS` 与 front-door
  `rust-anything.json::commands`，否则 `app wire` 报 `front door has no command`。
- 真跑 `rust-anything app wire . cross-source-rs --command unit-cross-source
  --skip-gate --no-check`：新增 path 依赖 `cross-source-rs`、`rust-anything.json`
  unit 记录（switch `RUST_ANYTHING_UNIT_CROSS_SOURCE`）与 glue stub。gate 上一片已过，
  此处跳过重复 gate/check，改由合并后手工做全链验证。
- wire 照例重写 `src/units/mod.rs` 并丢 `metrics_report`：先备份到
  `/tmp/zkc-cross-source-wire-backup`，wire 后手写合并回 metrics + 六个 unit 路由，
  再追加 cross-source 路由；统一走原 `unit_args` 协议（`<fn> <json-array>`），
  不用生成的 `(command, matches)` 签名。
- glue `src/units/cross_source.rs` 手写填充 2 个函数；`Value` 端到端透传，
  `{"ok":...}` / `{"error":...}` 与 exit code 均由 port 决定，无第二层编码。
- spike-16 的 `pure_bridge.py` 按路径加载进 `oracle.py`；
  `RUST_ANYTHING_UNIT_CROSS_SOURCE=original` 时逐字委托原实现（含 `set(source_ids)`
  编码缝），Rust port 不参与。

## 踩坑与修正

初版把 oracle/smoke 的 unit key 写成 `cross_source`，而 CLI 命令是 kebab 的
`unit-cross-source`；smoke 用 `f"unit-{unit}"` 拼命令，生成了未注册的
`unit-cross_source`，落回原 `metrics_snapshot.py` 参数错误（43/51 matched）。
把 oracle 表键、dispatch 的 `original_unit(...)` 参数与 smoke case 首字段统一成
`cross-source` 后，51/51 逐字匹配。多词 unit 的 key 必须和 CLI 命令名逐字一致。

## 机械验证

| 检查 | 命令 / 口径 | 结果 |
|---|---|---|
| 单元黑盒对比 | `python3 rust/app/smoke_units.py`（stdout + exit code 逐字） | **51/51 matched**（既有 43 + cross-source 8，含全崩塌 ValueError） |
| kill switch | 前置假 `python3` 包装器，`RUST_ANYTHING_UNIT_CROSS_SOURCE=original` | 日志出现一次 `oracle.py cross-source count_cross_source [...]`；输出 `{"ok":1}` 与默认路径一致；关掉后不再调用 Python |
| 既有 app case | `rust-anything app replay --build rust/app/target/debug/metrics-snapshot` | **11/11 passed**，fallback **0.0%** |
| 单元 diff / gate | `rust-anything diff/gate rust/cross-source-rs` | **26/26** match；**Gate passed**（size 1.4x，全项绿） |
| Rust 静态 | `cargo fmt --all -- --check` / `cargo clippy --all-targets -- -D warnings` / `cargo build` | 全过 |
| Python 全量 | `make test` | **671 OK** |
| 门禁 | `make mcp-gate` / `make invariant` / `scripts/zkc_authority_check.py` | **6/6** / **0 violations** / **0 leaks** |

## 纪律与边界

- **不是 lift**：七个 unit 都是新前门；metrics 路由与
  `RUST_ANYTHING_UNIT_METRICS_SNAPSHOT` kill switch 保留。51 个 smoke case 是人工选定
  输入，不是全输入空间证明。
- `app wire` 再次运行会重写 `units/mod.rs`，必须重新手工合并。本片未改 crate 源码，
  不涉及 `restore_lib_patch.py`；若之后 `refresh` 改动生成文件，需重新跑 gate。
- 只覆盖 2 个纯函数 × 26 录制输入；`CrossSourceOperator`（RCS 漏斗、tuning 阈值、
  单次有界补全、R14 埋点）、pydantic 模型、LLM callable 与 repository 落库留 Python。
  本片不证跨源质量、幻觉防护或引用真实性；recorded-literal 未 promote，
  不写回 tuning REGISTRY。
- `src/zkc/**` 零改动；`zkc` CLI 未新增命令。
