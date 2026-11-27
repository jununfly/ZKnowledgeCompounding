# 证据 · decay 首切片 bridge → record → diff → gate（2026-11-27）

## 命令与结果（原样读数，未手填 SHA）
- `rust-anything bridge . src/zkc/decay.py --out rust/decay-rs --name zkc-decay-rs` → 导出 8 个函数；原 Python 源码未被修改。
- `rust-anything record rust/decay-rs --count 60` → **544 cases（108 threw）**，逐函数：decay_linear 77 / decay_exponential 77 / decay_step 78 / elapsed_days 63 / compute_decay_score 63 / surface 60 / review_reset 63 / refresh_decay 63。
- `rust-anything diff rust/decay-rs --json` → 首轮 539/544（5 个 `surface` 输入为 str/dict 时桥接器拒绝）；把 `items` 签名从 `Vec<Value>` 改为 `Value` 并 `refresh`  bindings 后 → **544/544，failed=0**。
- `rust-anything gate rust/decay-rs` → **Gate passed**（fmt / clippy / cargo test / unsafe 0 / lockfile / ported / literals / tests / error cases / panics / build / api / behavior 全 pass）。
- `cargo test` → 7 passed（5 个 port 单测 + 2 个生成测试）；`make test` → **671 tests OK**；`zkc_authority_check` → 0 leaks；`make invariant` → 0 violations；`make mcp-gate` → 6/6 OK。
- `git status`：`M docs/architecture/ta-data-flow.md`（11-27 已有未提交校订，未触碰）、`?? docs/plans/`、`?? rust/`。未 commit/push。

## 覆盖边界（不得夸大）
`datetime` 无法穿过 JSON bridge，录制的 `now`/`node`/`repo` 全是标量/列表/字典；`elapsed_days` 的 datetime 分支、`refresh_decay` 的仓库迭代分支在录制中不可达。因此这次 gate 只证明「录制到的输入」等价，真实日期语义靠从 `tests/test_decay.py` 翻译的 Rust 单测（Q3 修正口径）。**不能写成「decay 模块生产等价」。**

## 产物
- `rust/decay-rs/src/port.rs`（Rust 实现 + 单测），`rust/decay-rs/cases.jsonl`（录制 case），`rust/decay-rs/recorded-from.json`（源文件指纹）。
- `rust/decay-rs/.rust-anything/tests.json`（gate 保存的测试基线）；后续若减少测试/断言会被 gate 拒绝。
