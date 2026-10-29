# Spike 09 · `review_interval` 自动设定规则（架构 §9 剩余项 ④）

> 状态：**完成 · 44 tests passed**（PostgreSQL 16 + pgvector，`zkc-spike-pg:55433`，复用 spike-04 venv）
> 对应：架构 §9 剩余项 ④ / §10 未闭合项 4 / PRD §7 度量口径相关
> 切片：**A** 三层 interval 规则（22 tests） + **B** `budget_per_day` 统计赋值 + L3 标注率闸门（22 tests）

## 1. 问题

`review_interval` 此前是**固定值**（spike 01 用 7/21 天）。它的语义是「这条多久之后腐化」，所以自动设定它 = 预测每条动态信息的**腐化速率**。本 spike 给出确定性、可解释、可回滚的规则。

## 2. 核心判断：interval 是双层量，不是个体属性

最容易踩的坑是「按内容给每条算一个最优 interval」。这违反 spike 01 已证实的硬约束：

```
每日注意力需求 = Σ 1 / (0.6 × Iᵢ)          （均匀时退化为 spike 01 的 n/(0.6×I)）
```

**个体最优之和不保证集体可行**。因此规则必须是三层：

| 层 | 作用 | 输入 | 输出 |
|---|---|---|---|
| **L1 基线**（个体） | 这条信息自身暗示的腐化速率 | 显式时间锚 / context 归属 / 连接 / 是否已捕获 | `baseline_interval` |
| **L2 预算归一化**（全局） | 把个体基线压进注意力预算 | 全部动态条目 + `budget_per_day` | 生效 `review_interval` |
| **L3 反馈自适应**（闭环） | 先验不可靠，用真实复审结果修正 | 复审时条目实际状态 | `review_interval` × AIMD 因子 |

### L1 基线阶梯（先命中者胜）

| 顺序 | 信号 | interval | 理由 |
|---|---|---|---|
| 0 | 静态轨 / 已归档 | **NULL** | 静态轨不腐化，不该有 interval |
| 1 | 内容含显式时间锚（"下周三""3 天内""月底"…） | clamp(horizon, 1, 180) | 时间锚是腐化速率最强的证据，压过归属信号 |
| 2 | 已成为 claim/artifact 的 evidence（价值已沉淀） | 28d | 原始记录不必再频繁复审 |
| 3 | 属于 `self_loop` context（项目躬身入局） | 3d | 变化最快 |
| 4 | 有 edge 连接 / 在 `higher_dim` context | 14d | 中等 |
| 5 | 孤儿（无连接、无 context、未捕获） | 7d | 默认档 |

多个时间锚取**最早**的那个：复审太早只是浪费一点注意力，太晚则条目已经腐化（PRD §8「宁少勿错」）。

### L2 预算归一化（诚实降级契约）

- 需求 ≤ 预算：**一条都不动**。
- 需求 > 预算：按 `priority` 升序延后（有显式时间锚 3 > 项目 self_loop 2 > 有连接/共享 context 1 > 孤儿或已捕获 0），同优先级内**短 interval 先延后**（把 3 天砍一半的收益远大于把 28 天砍一半）。每步 ×2。
- **人工设定（`interval_source='human'`）永远不被自动改写**——不能被静默覆盖。
- 延后到 `MAX=180d` 仍超预算 → `infeasible=True` + `max_dynamic_items = budget × 0.6 × 180`。
  **不做无限延后**：interval 远超真实半衰期 = 决定让这条腐化，这个决定必须可见。唯一真解是**缩小动态集合**（回到 spike 08 的 DISTILL/ARCHIVE）。

### L3 反馈（AIMD，无 ML）

| 复审时实际状态 | 判定 | 动作 |
|---|---|---|
| 还很新鲜（decay < 0.3） | `too_early` | ×1.5（节奏比真实腐化快，骚扰过度） |
| 正好（0.3 ≤ decay < 0.9） | `on_time` | 不变 |
| 已经腐化（decay ≥ 0.9） | `too_late` | ×0.7（看的时候已经晚了） |

钳制在 `[1d, 180d]`。

## 3. 关键发现（已记账，不得静默接受）

### F1 · decay-only 反馈是**永久 no-op**（必须显式标注复审结果）

调度器严格按 `decay ≥ 0.6` 触发复审时，**复审瞬间的 decay 恒等于 0.6** → 判定永远是 `on_time` → interval 永不修正。仿真（`convergence.py`，真值 10 天腐化）：

```
labeled=False -> final=7.0d   (target 16.67d)  corrected=False   ← 永不纠错
labeled=True  -> final=15.75d (target 16.67d)  corrected=True, 2 步收敛
```

闭环**看起来在跑，实际不携带信息**。它只在两种情况下有信号：① 复审不是 decay 触发的（人主动打开、项目里程碑、预算饥饿导致延迟复审）；② 复审时**显式标注**结果（仍然有效 / 已变化 / 已过期）。
→ **MVP 必须把复审做成带结果标注的动作**（`adapt_interval(..., outcome=...)` 已支持显式覆盖），不能只依赖 decay 数值。这一点若漏掉，L3 会是一个纯装饰。

### F2 · 收敛目标不是「真值 H」而是「H / 0.6」

复审发生在 `elapsed = 0.6 × I`，要让复审正好落在真值 H 上，需要 `I* = H / 0.6 ≈ 1.67H`。AIMD 在显式标注 + ±20% 容忍带下 **2 步收敛并稳定**（15.75d vs 目标 16.67d）。这是 SURFACE=0.6 的定义所致，不是 bug；若要让复审发生在 H 之前，应调 `SURFACE_THRESHOLD` 而非改 AIMD 因子。

### F3 · 偏差 D6/D7：schema 增量

为让「双层结构」可审计、可回滚、人工覆盖不被改写：

- **D6**：`node.baseline_interval`（个体基线，未被预算缩放污染）+ `node.interval_source`（`auto`/`human`，人工设定豁免自动化）。
- **D7**：新增 `interval_adjustment` 表（append-only 审计，每行带 `kind`/`old_days`/`new_days`/`reason`/`produced_by→transform CASCADE`），使一次预算归一化批处理可整体回滚（`revert_transform`），落实架构 §6.4 C2「副作用可完全回滚」。

与 spike 04/05/06/07/08 同一 substrate，无新依赖。

## 4. 实现要点

- `interval_policy.baseline_interval(cur, node_id)` → `{days, reason, tier}`（纯读侧；静态/已归档返回 None）。
- `assign_baselines(cur, produced_by=None)` → 计算并持久化 L1，跳过人工覆盖。
- `fit_budget(cur, budget_per_day, transform_id=None)` → `{demand_before, demand_after, degraded[], infeasible, max_dynamic_items, transform_id}`。
- `adapt_interval(cur, node_id, decay_at_review, outcome=None)` → AIMD 修正，人工覆盖豁免。
- `revert_transform(cur, transform_id)` → 逆序恢复 `old_days`，再删 transform（CASCADE 清审计痕迹）。
- `convergence.simulate(...)` → L3 收敛性实验（F1/F2 的证据）。

## 5. 测试覆盖（22 tests passed）

L1：静态无 interval；时间锚压过 self_loop 归属；self_loop=3d；connected=14d；孤儿=7d；已捕获=28d；持久化 + 人工覆盖保留。
L2：预算充足零改动；预算不足按优先级延后且孤儿最先、人工豁免；不可行时报 `infeasible` 与 `max_dynamic_items`；需求公式与 spike 01 `n/(0.6×I)` 对齐。
L3：too_early ×1.5、too_late ×0.7、on_time no-op、钳制边界、人工豁免；**decay-only 永久 no-op（F1）**；**显式标注 2 步收敛并可从过长侧回落（F2）**。
审计/回滚：`revert_transform` 逐条恢复原值并清空痕迹；每次改动都带非空 reason。
解析器：多时间锚取最早、无锚返回 None、clamp 上界。

---

# 切片 B · `budget_per_day` 从使用习惯统计赋值

> zj 的方向：「通过一段时间，对我使用习惯的统计，做赋值更新」。已实现并仿真验证（16 tests）。

## B.1 为什么不能只是"统计一下平均复审条数"

因为这是一个**删失观测（censored observation）**问题，直接取平均会得到错的数：

| 日末队列 | 含义 | `completed` 的信息量 |
|---|---|---|
| **有积压**（`queue_remaining > 0`） | 供给超过容量，人做到上限就停 | **容量的确证**（capacity ≈ completed） |
| **已清空**（`queue_remaining = 0`） | 供给不足，人还能做更多 | **只是下界**（capacity ≥ completed） |

更麻烦的是这条链本身**自指**：`budget → L2 拉长 interval → 供给变少 → 观测到的复审变少 → budget 更低 → …`。把两类样本混在一起取平均，这条正反馈就会把预算一路拖到地上，而且每一步都有"数据支持"。

## B.2 三道防线

1. **删失感知估计**：只有饱和日参与点估计（取其 `completed` 的 **p25**，保守）；无饱和日时只报**下界** `max(completed)` 且 `confidence='lower_bound'`；无任何观测时 `confidence='none'`，**L2 完全不动**（warm-up）。埋点表 `attention_observation(day, pushed, completed, queue_remaining)`。
2. **单调护栏**：**非饱和日只能抬升预算，永不压低**（它只证明 capacity ≥ completed）。饱和日才允许下调。
3. **阻尼 EMA**：`α=0.3`，单次更新幅度钳在 ±30% 内。
4. **校准期过度供给**：估计未确认时 L2 拟合目标取 `budget × 1.5`（`OVERSUBSCRIBE_CALIBRATING`），确认后回到 1.0。理由见 B.3。

## B.3 仿真结论（真值容量 3 条/天，60 条动态条目）

| 路径 | 初始 budget | 终值 | 结论 |
|---|---|---|---|
| A 乐观冷启动 | 10 | **3.001**（`observed`） | 收敛到真值 ✓ |
| B 悲观冷启动 | 1 | **2.999**（`observed`） | **也能爬上来** ✓ |
| D/E 供给稀缺（12 条、容量 3） | 10 | 3.001 | 有/无护栏差异只在头 5 天 |

**B 能爬升是 oversubscribe 的功劳**：关闭它时悲观冷启动会被锁死——因为供给恰好等于预算时队列天天清空，永远不产生饱和日，低估被永久固化。

**护栏对照（12 条、真值容量 8、供给始终 < 容量、关闭 oversubscribe）**：
- 护栏 ON → budget **保持 10 不动**（拒绝把"供给不足"读成"容量不足"）
- 护栏 OFF → budget 降到 **6**（错误地下调，并会连带无谓拉长 interval）

## B.4 ⚠️ 修正我自己的预判（必须记账）

我最初判断正反馈会导致「**无限塌陷到 0**」。**实测不是**：存在稳定不动点——供给由条目数与 interval 决定，budget 降到供给水平就停住。真实的失败形态是**错误的稳定均衡**：预算被固化在低于真实容量的水平（如 2 vs 真值 3），系统长期低利用率，且 interval 被无谓拉长。**是"固化"，不是"发散"**。这个区别影响对策：不需要紧急制动，需要的是持续探测（oversubscribe）。

**结构性极限**：当供给长期低于真实容量（条目太少），**容量不可观测**——oversubscribe 也抬不高供给（供给上限 = `条目数/(0.6×I)`）。此时唯一正确行为就是 L2 保持宽松（budget 停在 bootstrap 高值、不拉伸 interval），等条目积累；这也正是护栏的自然行为。

**更一般的结构性认识**：任何自指闭环都需要至少一个**外生锚**。decay 是我们自己定义的（拉长 interval 就等于"不腐化"）→ 需要 L3 的用户显式标注作外生锚（切片 A 的 F1）；budget 的观测（真实完成数）是另一个外生锚（切片 B）。两个闭环各自缺锚就会自证。

---

### B.5 L3 标注率闸门（zj 定：≥70% 起步）

「未标注的复审不得改写 interval」必须可执行，否则只是一句口号。故埋点加一列 `labeled_completed`（**D8**，带 `CHECK (labeled_completed <= completed)`）：

| 项 | 取值 |
|---|---|
| 口径 | 滚动 7 天窗口内 `labeled_completed / completed` |
| 门槛 | **≥ 70%** |
| 样本下限 | 窗口内完成复审 **< 10 次不判定**（样本不足，闸门放行） |
| 低于门槛 | **L3 停机**，interval 停在基线不动 |
| 人工显式 verdict | 不受闸门限制（人给的就是闸门要的信号） |

「样本不足不罚」是刻意的：否则 warm-up 期会把闭环冻死在起点。测试覆盖：率 40% → 闸门关闭且 `adapt_interval` 返回 `applied=False`；恰好 70% → 放行；3 个样本 0% → 放行；显式 `outcome` 绕过闸门；`labeled > completed` 被 schema 拒绝。

---

## 6. 仍 open（P2，超出本 spike）

- ~~`budget_per_day` 的真实取值来源~~ → **切片 B 已解决**：由 `attention_observation` 埋点统计估计（删失感知 + 单调护栏 + 阻尼 EMA + 校准期 oversubscribe），仿真验证可从 10 或 1 双向收敛到真值 3。仍 open 的是其**结构性极限**：条目太少导致供给长期低于容量时容量不可观测，只能等条目积累。
- **F1 的直接后果**：复审 UI/流程必须支持结果标注（`still_valid`/`changed`/`stale`），否则 L3 失效——这是产品侧动作，不是代码侧。
- **埋点前提**：`pushed/completed/queue_remaining` 需要真实 UI 每天写一次；MVP 若没有"每日复审队列"界面，这三列无从产生 → 切片 B 的估计器会永远停在 `confidence='none'`。**这是切片 B 的落地硬前提**。
- AIMD 因子 1.5/0.7 的振荡带约 ±50%；若要求更紧的收敛需换更温和因子（如 1.25/0.8）。
- L1 只用了文本时间锚 + 结构信号；LLM 判断「这条的腐化速率」未接（可走 DecisionRouter 同栈，待 §9 项 ⑥ 一并评估）。
- 已捕获条目本 spike 给 28d，但 spike 08 判定其应 ARCHIVE——两条规则需要统一（已捕获到底是「延长节奏」还是「直接归档」）。
