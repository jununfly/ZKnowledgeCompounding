# 三单元接入 `rust/app` + transport lib.rs patch 持久化（ticket 20）

日期：2026-11-27。过程态证据，非长期权威；权威仍以 ADR/PRD/架构为准。

## 做了什么

把 ticket 16–19 的三个纯函数切片接到同一个 Rust 前门 `rust/app`：

| 命令 | 单元 crate | 入口 | 录制 oracle |
|---|---|---|---|
| `unit-transport` | `rust/transport-rs` | 10 个纯函数 | Python `src/zkc/transport/`（429 case） |
| `unit-context` | `rust/context-pure-rs` | `clean_title` / `fallback_name` | Python `src/zkc/context.py`（131 case，spike-06 别名） |
| `unit-expiry` | `rust/expiry-pure-rs` | `route_decision` | Python `src/zkc/expiry.py::route_expired`（57 case，spike-08 快照适配器） |

协议统一为 `metrics-snapshot unit-<unit> <fn> '<json-array>'`，stdout 输出
`{"ok":<value>}` 或 `{"error":"<Type>: <text>"}`，退出码 0/1。

接线方式：对三个 crate **逐个真实执行** `rust-anything app wire`（`--skip-gate --no-check`），
它生成 Cargo path 依赖、`rust-anything.json` 的 units 记录、三个 glue stub 和 kill-switch
名字（`RUST_ANYTHING_UNIT_ZKC_TRANSPORT` / `_CONTEXT_PURE` / `_EXPIRY_PURE`）。生成的
`units/mod.rs` 会被每次 wire 重写并丢掉手写的 `metrics_report` 路由，因此最后**手写合并**
`mod.rs`：保留 metrics 路由 + 三个 glue 模块 + 三个 kill switch。`main.rs` 在记录的
`metrics-snapshot` 命令行之前解析三个 unit 命令，因此 `app replay` 的 11 个 case 不受影响。
没有使用官方 `app wire` 生成的 mod.rs 作为最终形态。

`rust/app/oracle.py` 是 **process-only** kill-switch 目标：设置
`RUST_ANYTHING_UNIT_<UNIT>=original` 时，glue 把同一 `<fn> <json>` 交给 Python 原实现
（context/expiry 经 spike 别名按文件路径加载，避免两个 `pure_bridge.py` 互相遮蔽）。
它不是生产代码，也不是迁移目标。`rust/app/smoke_units.py` 是可重跑的黑盒对比脚本。

## 机械验证

| 检查 | 结果 |
|---|---|
| 三次 `app wire` | 全部生成 unit 记录 / 依赖 / glue / switch，无错误 |
| `rust-anything gate`（三个 crate） | transport **429/429**、context **131/131**、expiry **57/57**，全过 |
| `python3 rust/app/smoke_units.py` | **13/13** stdout 与退出码逐字一致（含异常文本与 0.899999976 的 `:g` 渲染） |
| kill switch 双向 | 默认走 Rust；设 `RUST_ANYTHING_UNIT_ZKC_TRANSPORT=original` 后，前置假 `python3` 包装器记录到一次真实 `oracle.py transport decode_message ...` 调用，输出与 Rust 一致 |
| `app replay --build <rust/app/target/debug/metrics-snapshot>` | **11/11 passed，fallback 0.0%**（既有 `metrics-snapshot` case 零回退） |
| `cargo fmt` + `cargo clippy --all-targets -- -D warnings`（app） | 通过；修过 clap `'static` 名与 let-chain/collapsible-if 两处 lint |
| `make test` | 671 tests OK |
| `make mcp-gate` / `make invariant` / `zkc_authority_check.py` | 6/6；0 violations；0 leaks |

## transport `lib.rs` patch 持久化

`rust-anything refresh` 会重写生成的绑定。实测：把 `rust/transport-rs` 复制到临时目录运行
`rust-anything refresh` 后，`jsonrpc_error` helper 与 `"JsonRpcError"` match arm **均消失**
（grep 计数 0），57 个异常 case 会退回 `ValueError`。

解决：新增 `rust/transport-rs/restore_lib_patch.py`，幂等地重放这两段 patch。
在 refresh 后的临时副本上运行：第一次 `patched`，第二次 `already patched`；
与当前 `src/lib.rs` 的 diff **只剩 refresh 自动把 `serde_json::Value` 简写成 `Value` 的别名差异**，
patch 区域逐字一致。纪律：`refresh` 之后必须运行该脚本，再跑 `rust-anything gate`。

## 边界（不可写成什么）

- **不是 lift**：三个 unit 是新前门，不是已有 `app replay` case 的接管；metrics 路由与
  `RUST_ANYTHING_UNIT_METRICS_SNAPSHOT` kill switch 仍保留。
- unit CLI 协议没有 `app record` case；13 个 smoke case 是人工选定的代表性输入，
  只证明这些输入上 Rust glue 与 Python 原实现逐字一致，不是全输入空间证明。
- `oracle.py` / `smoke_units.py` / spike 别名是 process-only 验证工具；删除它们只影响
  复验与 kill switch，不影响 Rust port 本身。
- `rust-anything app wire` 再次运行会重写 `units/mod.rs`；必须重新手工合并，否则丢失
  `metrics_report` 路由。
- transport 阈值仍是 recorded-literal，未 promote 为 CALIBRATED；`src/zkc/**` 零改动，
  `zkc` CLI 未新增命令；未 commit/push。

## 复现

```sh
cargo build --manifest-path rust/app/Cargo.toml
python3 rust/app/smoke_units.py
rust-anything app replay . --build rust/app/target/debug/metrics-snapshot
rust-anything gate rust/transport-rs && rust-anything gate rust/context-pure-rs && rust-anything gate rust/expiry-pure-rs
python3 rust/transport-rs/restore_lib_patch.py   # 仅 refresh 之后需要
```
