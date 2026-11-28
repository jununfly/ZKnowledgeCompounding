# 证据 · ticket 10：app record + front-door 全量证明收口

日期：2026-11-28。task 4（app lift 与纯 Rust 收口）。

## 结论

**ticket 10 完成**：app 前门（`rust/app`，binary `metrics-snapshot`）的全部命令——
`metrics-snapshot` 主命令 11 个录制 case + 15 个 wired unit 命令 123 个录制 case——
已在 `rust-anything app replay --build` 下**134/134 passed、fallback 0.0%**。
lift 前置「replay passes with fallback rate 0」从「仅 metrics 主命令 11 case」
升级为「**全前门 134 case**」。

这补上了 `app-unit-wiring-evidence.md` 登记的缺口：
「unit CLI 协议没有 `app record` case；smoke case 是人工选定的代表性输入」——
现在 unit 命令有录制级 case，期望输出来自 Python oracle 的真实运行，不再是
手写对照脚本的私有资产。

## 做法

1. **录制输入**：从 `smoke_units.py` 的 123 个 case 机械生成 JSONL
   （`{"name": "unit-<unit>-<fn>[-n]", "args": ["unit-<unit>", "<fn>", "<json-array>"]}`），
   args 与 Rust 前门命令行完全同构。
2. **oracle.py 加 `unit-` 前缀别名**：`unit.startswith("unit-")` 则剥前缀再查表。
   除此零改动；无前缀调用（smoke_units.py 用法）不受影响。
3. **录制**：`rust-anything app record . --no-traps --inputs <jsonl> -- python3 rust/app/oracle.py`。
   oracle.py 是 wiring 证据里已定性的 process-only Python oracle（逐字委托原实现），
   即 unit 命令的 original。
4. **双 original 共存恢复**：record 会把 `rust-anything.json` 的 `run` 改写为
   oracle.py 并删除「不再录制」的 11 个 pg case。执行后用 `git checkout` 恢复
   `rust-anything.json` 与 pg case 文件（`run` 保持
   `python3 scripts/metrics_snapshot.py`、`effects` 的 db_reset/db_dump 保留），
   **只保留新增的 123 个 unit case 文件**。unit case 是 trycmd 文件，replay 只读
   文件不依赖 run 字段。
5. **噪声清理**：oracle.py docstring 被误抓成 3 个 `example-00*-embed` case，删除。

## 验证读数（2026-11-28）

| 检查 | 结果 |
|---|---|
| `app replay --build rust/app/target/debug/metrics-snapshot` | **134/134 passed，fallback 0.0%（0/134）** |
| case 构成 | 11 metrics（pg-* + memory-empty，含 DB effects 对照）+ 123 unit（15 个 wired unit 全覆盖） |
| `python3 rust/app/smoke_units.py` | 123/123 逐字一致（保留作独立平行对照，不因录制 case 而删） |
| `make test` | 671 tests OK |
| `make mcp-gate` / `make invariant` / `zkc_authority_check.py` | OK / 0 violations / 0 leaks |

fallback 0 的语义：134 个 case 全部由 Rust 前门应答，零 case 回落 Python original。

## 边界（诚实读法）

1. **unit case 期望输出的 oracle 身份**：来自 `oracle.py`（Python 原实现的进程级
   verbatim 委托），不是 `metrics_snapshot.py` 式的生产 CLI 包装。这与 kill-switch
   `RUST_ANYTHING_UNIT_*=original` 的 original 语义一致，wiring 证据已定性
   oracle.py 非生产代码。
2. **`app drift` 对 unit case 是假阳性**：drift 用 `rust-anything.json` 的 `run`
   （metrics_snapshot.py）重放全部 case，unit case 的 original 是 oracle.py，故
   drift 报「original changed」。**drift 只对 11 个 metrics case 有意义**；unit 的
   防漂移由可重跑的 `smoke_units.py`（Rust vs oracle 逐字对照）承担。若未来 lift
   后要 CI drift，须先解决双 original 结构（工具层限制，本仓不改工具）。
3. **录制协议**：unit 命令第三参是 JSON 数组字符串（与 smoke_units 的
   `json.dumps(args)` 一致）；args 顶层是 JSON object 时 Python 侧 `*args` 会
   解包成 key（协议规定数组包装，两侧行为一致，case 均为数组形态）。
4. **单目录双 original 是结构性妥协**：rust-anything 的 app-cases 绑定单一
   `run`；本方案以「恢复 run + 保留 case 文件」实现共存。后续对 metrics 主命令
   重新 `app record` 时必须显式给原 RUN，否则会再次改写 run 并删除 unit case。

## 对 lift（ticket 11）的影响

lift 前置两条已就绪一条：
- ✅ replay 100% + fallback 0：134/134（本 ticket）；
- ✅ 每 unit gate 通过：18 片 port 的 gate 已全过（各自 slice evidence）；
- ⏳ adapters（ticket 9，task 3）：在 zj-qwenwork-agent 手里（plan 3 租约）。

ticket 12（ADR/架构文档收口）等 lift。
