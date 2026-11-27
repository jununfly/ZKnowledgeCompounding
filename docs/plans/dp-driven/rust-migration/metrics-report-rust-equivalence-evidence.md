# metrics_report A 路径：Rust 黑盒等价证据

> 2026-11-27 · 过程态证据（**非 durable 权威**，closeout 时随 `docs/plans/` 删除）。
> 结论若需长期保留，须提炼进 ADR / 架构 / `docs/evidence/`。
> 回答问题：ticket 15 的「继续 A」是否拿到了 Rust 等价？

## 结论（一句话）

**CLI 黑盒层拿到了可证明的 Rust 等价**：`app replay --build` 对 2 个录制 case
**2/2 passed、fallback rate 0.0%**（front door 起点为 100%）。但这只覆盖
`metrics_snapshot.py --storage {pg,memory}` 这条 CLI 的**录制输出**，
**不等于** `metrics_report` 函数级等价，更不等于全仓 app lift 完成。口径见下「边界」。

## 做了什么（A 全链路）

1. **front door**：`rust-anything app front-door .` 在 `rust/app` 建 Rust binary，
   基线 replay 2/2、fallback 100%（所有命令跑原 Python）。
2. **手写 glue**（`rust/app/src/units/{mod.rs,metrics_report.rs,cli.rs}`）：
   - 修改生成的 CLI 解析：`--storage` 从 `Count` flag 改为带一个值的 option
     （原脚本 `--storage <kind>` 带值，默认生成不符）；
   - `mod.rs` 手写接线（**不用 `app wire`**：wire 会从 unit crate 的 `port.rs`
     重写 `mod.rs`，而本 glue 是完整的 PG 查询层 + 五度量实现，不是单个 port 薄封装）；
   - `metrics_report.rs` 实现 `load_metric_inputs` 的 5 表 PG 查询（sqlx，UUID cast 到 text
     避免 `uuid` feature）+ 五度量纯函数 + `build_report_dict` 的 Python `round(x,4)`
     与 dict key 顺序（靠 `serde_json` 的 `preserve_order`）；
   - kill switch `RUST_ANYTHING_UNIT_METRICS_SNAPSHOT=original`（双向实测：开 → 1 行
     fallback log 回退 Python；关 → 0 行，Rust 直答）。
3. **红→绿修了三处真实偏差**：
   - JSON key 顺序：默认 `serde_json::Map` 按字母排，不符 Python dict 插入序 → 启用 `preserve_order`；
   - clippy `question_mark`（`-D warnings`）：`match dsn { ... }` → `dsn?`；
   - `cli.rs` unused import `ArgAction` 删除。

## 验证读数

| 检查 | 结果 |
|---|---|
| `app replay --build`（Rust binary） | **2/2 passed, fallback 0.0%**, failures `[]` |
| 基线 `app replay`（原 Python） | 2/2 passed（前一轮，见 `metrics-report-app-record-evidence.md`） |
| pg case 五度量 | cd=0.75 / rr=1.0 / per=1.5 / mo=1 / dc=0.6667 / cf=0.6292（与原实现逐字节一致） |
| memory case | 六项全 0（逐字节一致） |
| kill switch | 开 = 1 fallback / 关 = 0 fallback（双向实测） |
| `cargo clippy -D warnings` | pass |
| `cargo fmt --check` | pass |
| `make test` | 671 OK |
| authority / invariant / mcp-gate | 0 leaks / 0 violations / 6 OK |

## 边界（必须同时读，否则会误报等价）

1. **录制输入集 = 2 个 case**（pg 固定 seed + memory 空库）。只证明这 2 个输入的输出一致；
   PG 查询层只走过 seed 覆盖的行，没有 fuzz、没有真实生产数据形态。
2. **`app replay` 比的是 CLI stdout/exit/DB effects，不是函数调用契约**。
   `metrics_report(store)` 的函数级行为不再有独立 oracle（Rust 侧没有相应的单元 diff/gate）；
   证明链是「CLI 黑盒」，粒度粗于「函数」。
3. **8 个 dataclass/Storage 函数并未迁移**：`metrics.py` 其余函数仍留 Python；
   本 glue 是在 CLI 边界重写了等价计算，不是把 `metrics_report` 函数 port 过桥。
   与 Q5=C 的定性一致——工具编码边界导致 unit bridge 不可证，A 只是在应用层绕开。
4. **不是 app lift**：全仓 front door 只覆盖了 `metrics-snapshot` 一个 CLI；
   `src/zkc` 的 domain/repository/adapters 未迁；tk8 整体仍未完成。
5. **常量来源**：四个权重 0.25、method target 10、ROT 0.9 均标 `recorded-literal`
   （1-26 CALIBRATED seed），本轮未改、未 promote。

## 结论对 ticket 15 / Q5 的影响

- A 路径**已实证可行且等价成本已付**（front door + glue + PG 查询层全打通）。
- 但这**不改变** Q5=C 对「unit bridge 不可编码 dataclass/Storage」的定性：
  A 证明的是「应用层可以绕开工具边界」，不是「unit 级可以 port」。
- ticket 15 可从「待拍板是否继续 A」更新为「A 已对 `metrics_report` CLI 走通」
  （见 DP 回灌）；8 函数是否要逐个在应用层重写，仍由 zj 按收益决定，不自动扩范围。
