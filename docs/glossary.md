# ZKC 术语表（glossary）

> 边 grill / roadmap 边沉淀的精确词义。每条都是**可验证的代码现状**，不混入未拍板的决策。
> 新术语按字母序追加；词义漂移时改本条并留 `见 ADR-XXXX` 溯源。

---

## 预算 / budget_per_day

ZKC 里 "预算" 一词有 **三** 个互相独立、常被混用的含义。E1 退出判据③「budget 从初始值收敛到稳定值」
预设了第 3 义的存在，但运行时并未闭合——这是 2026-11-04 grill 发现的关键不一致。
**2026-11-04 zj 拍板取 A（无状态：含义②即预算，见 ADR-0006），故③已重述为「派生估计在 [7,14,21,28] 天窗口轨迹聚拢（CV≤10% 且 28d confidence=observed）」。**

| 含义 | 是什么 | 当前是否进运行时回路 |
| --- | --- | --- |
| ① 占位常量 `BUDGET_PER_DAY_DEFAULT = 1.0`（source=placeholder） | `zkc/tuning.py` 登记、标注「原 1.2 无出处，弃；1.0 偏保守」 | **否**。仅被诊断脚本 `scripts/r4_budget_check.py` 与 `tests/test_tuning.py` 读取；运行时 `review.py` / `scheduling` 的实际路径从不读它。属 `/tuning` 页面展示用的"文档化默认值"，不是活参数。 |
| ② 派生估计值 `estimate_budget_from(attention_observation)` | 纯函数，每次调用从 `attention_observation` 埋点重算：有饱和日取饱和日 completed 的 p25（钳 [0.1,500]），无饱和日取 lower_bound（永不下调）。 | **部分**。`review_queue_view`（/review 页面+API）调用它**仅用于展示**；不落库、不应用、不喂回 ③。 |
| ③ 有状态预算（设计意图） | 自举 `update_budget_from(current=None → estimate)` + EMA 阻尼（α=0.3, clamp=±30%）+ 应用 `fit_budget`（按优先级延后低优先条目、写审计、可整体回滚）。 | **否（闭环未闭合）**。`update_budget` / `fit_budget` 仅有定义 + 单测（`test_scheduling.py` / `test_scheduling_pg.py`），**运行时零调用点**。 |

**实测现状（2026-11-04，含本沙箱空库）：**
`estimate_budget_from([])` → `{'estimate': None, 'confidence': 'none', 'n_days': 0, ...}`
即 warm-up，L2 永远静止（不归一、不延后）。

**结论（事实）：** 当前**不存在一个活的、单一的 budget_per_day 标量**。系统以"无功能预算上限"运行——
L2 归一在观测出现前恒 passive，且即使观测出现，② 也从不驱动 ③。

**与 E1 的关系（2026-11-04 zj 拍板取 A，见 ADR-0006）：**
- **已定：A 无状态（含义②即预算）**。"初始值"是伪概念，③ 已改写为"派生估计在 [7,14,21,28] 天窗口轨迹上聚拢（CV≤10% 且 28d confidence=observed）"。`scripts/e1_calibration_progress.py` 的 `c3_budget_convergence` 即按此量，合规。
- **B 有状态（含义③）明确不接线**：`update_budget_from` / `fit_budget` 保留定义+单测待用，缺失的「每日收口 hook → update_budget → fit_budget」一段不在 1-1 范围；未来启用须先立 roadmap 节点（不得静默加装写入回路）。
- **`queue_remaining` 是负载-bearing 字段（2026-11-04 grill 纠正）**：它是「饱和日」的唯一输入——`estimate_budget_from` 的 `saturated = queue_remaining > 0`、`calibration_readiness` 的 `saturated_days` 同义。无 ≥3 饱和日则 E1-③ 永远拿不到 `confidence=observed`、`can_calibrate` 永远不 ready。**故收口必须真值、不可手工乱填**（fork 2 已落地 `/review/api/observe/auto` 服务端算真值）。`pushed` 则当前未被任何 E1 判据消费（纯遥测）。

---

## 活跃日（E1 口径）

`roadmap node 1-1` 退出判据①「连续 ≥7 活跃日」的计数单位（2026-11-04 落盘决策，**fork 3b / ADR-0007 重定**）：
**活跃日 = 当日真实复审发生**（`attention_observation.completed ≥ 1`，来自 `/review` 的 `decide` 标注）。
**空队列日豁免**：当日 `completed==0` 且 `queue_remaining==0`（队列本就空）→ 不破不断。
**仅「有 due 未复审」才断签**：当日 `completed==0` 且 `queue_remaining>0`（有到期项却没复审）→ 串归零。
**收口（`queue_remaining`）只影响 E1-③ 预算估计与 `can_calibrate` 门禁，不影响 E1-①**（见下「预算」条）。
由 `src/zkc/calibration.py` 的 `_evaluate_active_days` 量（**累计**活跃日 ≥7，不要求连续；2026-11-11 放宽）。
