# Evidence · scheduling interval unit 接入 rust/app（ticket 22）

> 过程态证据，非持久权威。长期结论以 ADR/PRD/架构/代码为准。

## 结论

`rust/scheduling-interval-rs` 的 6 个纯函数（L1 基线 / L3 AIMD / L2 目标）已作为新前门
`unit-scheduling` 接入 `rust/app`。录制期 Python 原实现仍是唯一 oracle；
Rust 侧只做黑盒等价复刻，不是全仓 lift，也没有改 `src/zkc/**`。

DP：ticket 22（parent 16，derived-from finding 10，blocked-by 21）已完成，租约释放，`validate` 0 errors。

## 接线方式

- 真跑 `rust-anything app wire <repo> scheduling-interval-rs --command unit-scheduling`：
  生成 `zkc-scheduling-interval-rs` path 依赖、`rust-anything.json` unit 记录（switch
  `RUST_ANYTHING_UNIT_ZKC_SCHEDULING_INTERVAL`）与 glue stub。
- 与之前三个单元同样的工具约束：`wire` **每次重写 `src/units/mod.rs` 并丢掉
  `metrics_report`**。因此先把既有 `mod.rs` 备份到 `/tmp/zkc-app-wire-scheduling-backup`，
  wire 后手写合并：保留 metrics 路由 + transport/context/expiry 路由，再追加 scheduling 路由。
- glue `src/units/zkc_scheduling_interval.rs` 手写填充 6 个函数；协议沿用
  `metrics-snapshot unit-scheduling <fn> '<json-array>'` → `{"ok":...}` / `{"error":...}`。
- spike-09 的 `adapt_interval_math` 把 `human` 保留为 keyword-only；CLI 用第三个位置槽传它，
  glue 直接转给 Rust 的普通参数，`oracle.py` 在调用前把第 3 个值还原为 `human=` 关键字，
  保证 kill switch 与原实现调用形状一致。

## 机械验证

| 检查 | 命令 / 口径 | 结果 |
|---|---|---|
| 单元黑盒对比 | `python3 rust/app/smoke_units.py`（23 case，stdout + exit code 逐字） | **23/23 matched**（既有 13 + scheduling 10） |
| kill switch | 前置假 `python3` 包装器，`RUST_ANYTHING_UNIT_ZKC_SCHEDULING_INTERVAL=original` | 日志出现一次 `oracle.py scheduling extract_horizon_days ["明天交"]`；输出 `{"ok":1.0}` 与 Rust 默认路径一致 |
| 既有 app case | `rust-anything app replay --build rust/app/target/debug/metrics-snapshot` | **11/11 passed**，fallback **0.0%** |
| 单元 gate | `rust-anything gate rust/scheduling-interval-rs` | **Gate passed**（size 2.6x，behavior **208/208**，全项绿） |
| Rust 静态 | `cargo fmt` / `cargo clippy --all-targets -- -D warnings` / `cargo build` | 全过 |
| Python 全量 | `make test` | **671 OK** |
| 门禁 | `make mcp-gate` / `make invariant` / `scripts/zkc_authority_check.py` | **6/6** / **0 violations** / **0 leaks** |

## 纪律与边界

- **不是 lift**：四个 unit 都是新前门；metrics 路由与
  `RUST_ANYTHING_UNIT_METRICS_SNAPSHOT` kill switch 保留。23 个 smoke case 是人工选定
  输入，不是全输入空间证明。
- `app wire` 再次运行会重写 `units/mod.rs`，必须重新手工合并；`scheduling-interval-rs`
  若执行 `refresh`，会丢掉 `regex` 依赖和 `use serde_json::Value;`，需运行
  `rust/scheduling-interval-rs/restore_lib_patch.py`（幂等）后再 gate。
- 只覆盖 6 个纯函数 × 208 录制输入；`SchedulableNode` / `AttentionObservation` /
  `Storage` / `timedelta` 编排层仍留 Python；阈值全是 recorded-literal
  （`CALIB_OVERRIDE_AT` caveat 仍在）；`l2_target` 无生产调用者。
- `src/zkc/**` 零改动；`zkc` CLI 未新增命令。
