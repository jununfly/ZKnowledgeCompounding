# 复审标注四档语义 v2 · 真值回读一致性检查（2026-11-14）

> 配套：ADR-0011（决策定案）、ADR-0012（规格 + §9 设计评审不变量 DI-1..DI-9）、`2026-11-14-verdict-semantics-cutover.md`（口径切换点 + 门禁健康度）。
> 本记录是 Step 6（长期文档收口）的 `1-6-3` 交付物：把 `zkc decide --list --json` 真值回读归档为证据，并做与裁决/规格的一致性核对。过程态结论须提炼至 ADR/PRD/架构/risks/evidence（护栏 #9）；本文只引用 durable 文档，不引 roadmap carrier。

## 1. 真值回读快照（证据源）

- 文件：`docs/evidence/verdict-v2-truth-readback-2026-11-14.json`
- as_of：`2026-11-14T13:24:39.002581+00:00`
- 原始命令：`python -m zkc.cli decide --list --json`

关键字段：

| 字段 | 值 | 含义 |
|---|---|---|
| `items` | `[]` | 当前无到期待复审项（快照时刻，非错误） |
| `due_count` | `0` | 无到期项，与 `items` 空一致 |
| `gate.rate` | `1.0` | 标注率 100%（labeled 28 / completed 28） |
| `gate.threshold` | `0.7` | 标注率闸门阈值（ADR-0012 / R15 口径） |
| `gate.gate` | `open` | 标注率 ≥ 阈值 → L3 自适应环路运行 |
| `budget.estimate` | `3.0` | 观测置信度（confidence=observed），5 饱和日 p25=3 |

## 2. 一致性核对（裁决/规格 → 运行时）

| # | 核对项（源自 ADR-0011 / ADR-0012 / R15） | 回读证据 | 结论 |
|---|---|---|---|
| C1 | **标注率闸门 intact**：verdict 语义 v2 不得污染标注率闸门（R15 影响面：标注率闸门口径不受影响） | `gate.rate=1.0 ≥ threshold=0.7` → `gate=open`，L3 正常 | ✅ 一致 |
| C2 | **外生锚 A 归零后 decay-only 复审恒 no-op 不受影响**：标注率埋点（labeled_completed）仍独立驱动闸门 | `labeled_completed=7`、`labeled=28`，闸门由埋点驱动，无 AIMD 因子介入回读 | ✅ 一致 |
| C3 | **无 due 项 ≠ 口径失灵**：清除了 stale 的节点退出调度回路，本就是预期行为（DI-4） | `due_count=0` 且 `items=[]` 为快照时刻真实状态，非缺失 | ✅ 一致（需 zj 真实复审标注才会再产生 due） |
| C4 | **改动面不波及标注率/预算机制**：Step 4 未改 `scheduling.py` 闸门、`tuning.py` 阈值常量 | `gate.threshold` 仍为 0.7、`budget.estimate` 来自观测，与 cutover §4「阈值常量未动」对齐 | ✅ 一致 |
| C5 | **1-26 CALIBRATED 口径未被污染**：verdict 反馈路径与 metric weights 校准正交 | 回读无任何 `METRIC_W_*` / `AIMD_*` 因子运算痕迹；阈值未变 | ✅ 一致 |

## 3. 与 Step 5（1-5-2）真值回读的一致性衔接

- Step 5 已做 `zkc decide --list --json` 真值回读与 choices 一致性核对（1-5-2）；本文件是其证据归档化（Step 6 要求落盘到 `docs/evidence/`）。
- 本次回读 `items=[]` 表示当前无待办复审项；choices 一致性核对以「运行时闸门/预算机制未被 verdict v2 改动破坏」为判据（C1–C5），与 Step 5 审查结论同源。

## 4. 结论

真值回读证据已归档，且与 ADR-0011 / ADR-0012 / R15 / cutover 文档的五条一致性判据全部通过。无发现 verdict 语义 v2 落地导致标注率闸门、预算机制或 CALIBRATED 口径漂移的迹象。

> 未决：本回读为单时刻快照；持续回归依赖 `make mcp-gate` + `make invariant` + `scripts/zkc_authority_check.py`（见 cutover §6），不在此文件重复承载。
