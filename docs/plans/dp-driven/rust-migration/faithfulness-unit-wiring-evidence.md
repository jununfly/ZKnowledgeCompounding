# Evidence · faithfulness rubric unit 接入 rust/app（ticket 24）

> 过程态证据，非持久权威。长期结论以 ADR/PRD/架构/代码为准。

## 结论

`rust/faithfulness-rubric-rs` 的 7 个字面 rubric 纯函数已作为新前门
`unit-faithfulness` 接入 `rust/app`。录制期 Python 原实现仍是唯一 oracle；
Rust 侧只做黑盒等价复刻，不是全仓 lift，也没有改 `src/zkc/**`。

DP：ticket 24（parent 8，blocks `24→8`）已完成，租约释放，`validate` 0 errors。

## 接线方式

- 真跑 `rust-anything app wire <repo> faithfulness-rubric-rs --command unit-faithfulness`：
  新增 path 依赖 `zkc-faithfulness-rubric-rs`、`rust-anything.json` unit 记录（switch
  `RUST_ANYTHING_UNIT_ZKC_FAITHFULNESS_RUBRIC`）与 glue stub。wire 要求命令先出现在
  `src/cli.rs::UNIT_COMMANDS` 与 front-door `commands` 里，故先手工补两处再执行。
- 与之前四个单元同样的工具约束：`wire` **每次重写 `src/units/mod.rs` 并丢掉
  `metrics_report`**。先把既有 `mod.rs` 备份到 `/tmp/zkc-faith-wire-backup`，wire 后
  手写合并：保留 metrics 路由 + transport/context/expiry/scheduling 路由，再追加
  faithfulness 路由；统一走原有的 `unit_args` 协议，不用 wire 生成的 `(command, matches)` 签名。
- glue `src/units/zkc_faithfulness_rubric.rs` 手写填充 7 个函数；协议为
  `metrics-snapshot unit-faithfulness <fn> '<json-array>'` → `{"ok":...}` / `{"error":...}`。
  参数保持 `Value` 端到端透传，错误文本由端口侧产生，不做二次编码。
  `ngrams` 在调用方省略 `n` 时补原实现的默认值 3。
- spike-10 的 `pure_bridge.py` 只规范 `set` → sorted list 这一个编码边界；`oracle.py`
  按路径加载该别名，`RUST_ANYTHING_UNIT_ZKC_FAITHFULNESS_RUBRIC=original` 时逐字委托原实现。

## 机械验证

| 检查 | 命令 / 口径 | 结果 |
|---|---|---|
| 单元黑盒对比 | `python3 rust/app/smoke_units.py`（stdout + exit code 逐字） | **35/35 matched**（既有 23 + faithfulness 12） |
| kill switch | 前置假 `python3` 包装器，`RUST_ANYTHING_UNIT_ZKC_FAITHFULNESS_RUBRIC=original` | 日志出现一次 `oracle.py faithfulness normalize [...]`；输出 `{"ok":"中文文本"}` 与默认路径一致；关掉后不再调用 Python |
| 既有 app case | `rust-anything app replay --build rust/app/target/debug/metrics-snapshot` | **11/11 passed**，fallback **0.0%** |
| 单元 gate | `rust-anything gate rust/faithfulness-rubric-rs` | **Gate passed**（size 2.6x，behavior **74/74**，全项绿） |
| Rust 静态 | `cargo fmt --all -- --check` / `cargo clippy --all-targets -- -D warnings` / `cargo build` | 全过（fmt 首轮报两处格式差，已修正后复验） |
| Python 全量 | `make test` | **671 OK** |
| 门禁 | `make mcp-gate` / `make invariant` / `scripts/zkc_authority_check.py` | **6/6** / **0 violations** / **0 leaks** |

## 纪律与边界

- **不是 lift**：五个 unit 都是新前门；metrics 路由与
  `RUST_ANYTHING_UNIT_METRICS_SNAPSHOT` kill switch 保留。35 个 smoke case 是人工选定
  输入，不是全输入空间证明。
- `app wire` 再次运行会重写 `units/mod.rs`，必须重新手工合并。本片未改 crate 源码，
  不涉及 `restore_lib_patch.py`；若之后 `refresh` 改动生成文件，需重新跑 gate。
- 只覆盖 7 个纯函数 × 74 录制输入；`AtomicFact` / `Judgment` / `Storage` / LLM /
  callable / datetime 路由留 Python。阈值 0.5 / 0.7 仍是 recorded-literal
  （`CALIB_OVERRIDE_AT` caveat 未消除）；`gate_new_claims` 仍仅 dogfood/测试，
  rubric flags 只作人审标注，不是放行决策。
- `src/zkc/**` 零改动；`zkc` CLI 未新增命令。
