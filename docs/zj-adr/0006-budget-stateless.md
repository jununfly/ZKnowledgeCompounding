# 预算语义定标：采用无状态估计（含义②）为唯一预算口径

Status: accepted (2026-11-04, zj 拍板，经 zj-grill-with-docs 对「现在的预算是什么」的质疑收敛)

## 背景与问题

ZKC 中 "budget_per_day" 一词在代码里有三个互不相同的含义（见 docs/glossary.md）：

- ① 占位常量 `BUDGET_PER_DAY_DEFAULT = 1.0`：仅被诊断脚本与测试读取，运行时回路不读。
- ② 派生估计 `estimate_budget_from(attention_observation)`：纯函数，每次从 `attention_observation` 重算，仅用于 `/review` 页面展示，不落库、不驱动调度。
- ③ 有状态预算（设计意图）：`update_budget_from`（自举+EMA 阻尼）+ `fit_budget`（按优先级延后）闭环——**运行时零调用点，闭环未闭合**。

grill 暴露的不一致：E1 退出判据③原文「budget 从初始值收敛到稳定值」预设了③（有状态、会自举）的存在，但③在运行时根本没接上。若据此去量「从不存在的初始值收敛」，是建在流沙上。

## 决策

**采用 A：无状态预算（含义②）为唯一生效的 budget_per_day 口径。**

- `estimate_budget_from(obs)` 即预算。它每次从原始 `attention_observation` 埋点重算，没有也不需要有「持久化的初始值」。
- E1 退出判据③重述为：**budget_per_day 派生估计在 [7,14,21,28] 天窗口轨迹上聚拢（变异系数 CV ≤ 10%）且 28d 窗口 confidence = observed**。
- 含义③的有状态路径（`update_budget_from` / `fit_budget`）**本阶段明确不接线**，保留其定义与单测（`test_scheduling.py` / `test_scheduling_pg.py`）作为未来可选扩展；缺失的「每日收口 hook → update_budget → fit_budget」一段不在本 ADR 范围内。

## Considered Options

- **A 无状态（采纳）**：估计即预算，每次重算。优点：与现有运行时现状完全一致，无新接线、无新增风险；E1-③ 立即可测（`scripts/e1_calibration_progress.py` 已按此量）。代价：失去 EMA 阻尼/有状态自举带来的平滑与「从初始值收敛」叙事——但后者在纯观测产品执行节点里本就非必需。
- **B 有状态（拒绝）**：补一段每日收口 hook 调 `update_budget` + `fit_budget`，把估计值持久化并真正去延后低优先条目。优点：实现设计意图、L2 归一/延后真正生效。代价：属实现缺口而非纯观测，超出 E1「产品执行/代码只读」scope gate；引入新写入路径与回滚复杂度，在真实多日埋点尚未累积前收益不明确。留待后续独立 roadmap 节点评估。

## Consequences

- `scripts/e1_calibration_progress.py` 的 `c3_budget_convergence`（多窗口 CV≤10% + 28d observed）**即为 E1-③ 的合规测量**，无需改逻辑。
- E1 `exit_criteria[2]` 由「budget_per_day 从初始值收敛到稳定值」改为上述 A 重述。
- docs/glossary.md「预算」条标注 2026-11-04 zj 拍板取 A，并在「与 E1 的关系」处留 `见 ADR-0006` 溯源。
- 含义③函数保留但标记为「未接线、待用」；任何未来启用 B 路径的 PR 须先在 roadmap 立节点并经决策，不得静默加装写入回路。
