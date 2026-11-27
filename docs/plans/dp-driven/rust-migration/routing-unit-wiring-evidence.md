# Evidence · routing TF-IDF unit 接入 rust/app（ticket 26）

> 过程态证据，非持久权威。长期结论以 ADR/PRD/架构/代码为准。

## 结论

`rust/routing-tfidf-rs` 的 3 个纯函数（`_tokenize` / `_tfidf_vector` / `_cosine`）
已作为新前门 `unit-routing` 接入 `rust/app`。录制期 Python 原实现仍是唯一 oracle；
Rust 侧只做黑盒等价复刻，不是全仓 lift，也没有改 `src/zkc/**`。

DP：ticket 26（parent 8，blocks `26→8`）已完成，租约释放，`validate` 0 errors。

## 接线方式

- 真跑 `rust-anything app wire <repo> routing-tfidf-rs --command unit-routing`：
  新增 path 依赖 `zkc-routing-tfidf-rs`、`rust-anything.json` unit 记录（switch
  `RUST_ANYTHING_UNIT_ZKC_ROUTING_TFIDF`）与 glue stub。与之前五个单元一样，wire
  要求命令先出现在 `src/cli.rs::UNIT_COMMANDS` 与 front-door `commands` 里。
- wire **每次重写 `src/units/mod.rs` 并丢掉 `metrics_report`**：先备份到
  `/tmp/zkc-routing-wire-backup`，wire 后手写合并回 metrics + 五个 unit 路由，
  再追加 routing 路由；统一走原有 `unit_args` 协议，不用生成的 `(command, matches)` 签名。
- glue `src/units/zkc_routing_tfidf.rs` 手写填充 3 个函数；协议为
  `metrics-snapshot unit-routing <fn> '<json-array>'` → `{"ok":...}` / `{"error":...}`。
  参数保持 `Value` 端到端透传，键顺序由 crate 的 `serde_json` `preserve_order` 保证。
- spike-15 的 `pure_bridge.py` 只提供公开别名；`oracle.py` 按路径加载它，
  `RUST_ANYTHING_UNIT_ZKC_ROUTING_TFIDF=original` 时逐字委托原实现。

## 机械验证

| 检查 | 命令 / 口径 | 结果 |
|---|---|---|
| 单元黑盒对比 | `python3 rust/app/smoke_units.py`（stdout + exit code 逐字） | **43/43 matched**（既有 35 + routing 8） |
| kill switch | 前置假 `python3` 包装器，`RUST_ANYTHING_UNIT_ZKC_ROUTING_TFIDF=original` | 日志出现一次 `oracle.py routing tokenize [...]`；输出 `{"ok":["i","stanbul","strasse"]}` 与默认路径一致；关掉后不再调用 Python |
| 既有 app case | `rust-anything app replay --build rust/app/target/debug/metrics-snapshot` | **11/11 passed**，fallback **0.0%** |
| 单元 gate | `rust-anything gate rust/routing-tfidf-rs` | **Gate passed**（size 1.4x，behavior **25/25**，全项绿） |
| Rust 静态 | `cargo fmt --all -- --check` / `cargo clippy --all-targets -- -D warnings` / `cargo build` | 全过 |
| Python 全量 | `make test` | **671 OK** |
| 门禁 | `make mcp-gate` / `make invariant` / `scripts/zkc_authority_check.py` | **6/6** / **0 violations** / **0 leaks** |

## 纪律与边界

- **不是 lift**：六个 unit 都是新前门；metrics 路由与
  `RUST_ANYTHING_UNIT_METRICS_SNAPSHOT` kill switch 保留。43 个 smoke case 是人工选定
  输入，不是全输入空间证明。
- `app wire` 再次运行会重写 `units/mod.rs`，必须重新手工合并。本片未改 crate 源码，
  不涉及 `restore_lib_patch.py`；若之后 `refresh` 改动生成文件，需重新跑 gate。
- 只覆盖 3 个纯函数 × 25 录制输入；`route_text` / `LexicalRouter` / `DecisionRouter` /
  LLM / tuning gate / `lexical_corpus` 持久化留 Python。常量均为 recorded-literal；
  corpus-derived gate 未 promote 成 CALIBRATED；这不是路由放行或安全判定。
- `src/zkc/**` 零改动；`zkc` CLI 未新增命令。
