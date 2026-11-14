# ADR-0011 · 复审标注四档语义矩阵 v2 定案（changed/stale 拆分 + 终局动作替代 AIMD 乘因子）

Status: accepted（2026-11-14，zj 于 15:46 逐项裁决 ①–④、16:08 语义定案 S0、16:25 a–d 结论 S1、16:33 覆盖分支裁决 S2）

## 边界声明（读前必读）

本 ADR 是**语义决策定案**记录，沉淀自 `zkc decide` 人工复审标注的四档语义裁决。它只定「语义是什么」，**不定代码已改**。

- **实现状态 = 未做、未授权**：本仓库当前代码仍实现的是 v1 旧语义（`src/zkc/web/review.py:40-44` 的 `OUTCOME_VERDICT` 把 `changed`/`stale` 同映射为 `too_late`）。将本定案落到代码属于 Plan `2026-11-14-zkc-verdict-semantics-plan.md` 的 Step 2–5（TDD 执行链），**尚未启动、需 Human 单独授权**。
- **本 ADR 是 Step 1（语义裁决）产物的长期归档**，同时是 roadmap 节点 `1-1` 的 `completed` 证据源。Step 6 的完整交付（含规格/契约回归测试/风险册联动）依赖 Step 5 审查通过，本文件只覆盖其中「决策定案」这一项。
- **不冒充 CALIBRATED、不污染 1-26 口径**：本 ADR 不改任何阈值常量（`tuning.py` 的 `AIMD_UP`/`AIMD_DOWN`/`MIN_INTERVAL_DAYS`/`METRIC_W_*`），不写回 `tuning.REGISTRY`。1-26 校准的是 metric weights，与 verdict 反馈路径正交。
- **权威边界（ADR-0008 / 护栏 #9）**：决策溯源引用 Plan `2026-11-14-zkc-verdict-semantics-plan.md` 仅作**过程态溯源**，非权威 proof；本 ADR 的权威依据是所有裁决均来自 zj 本人逐项拍板（原始记录在 `.workbuddy/memory/2026-11-14.md` 工作日志与 roadmap carrier 的 `1-1` decisions），代码引用指向**当前可核对文件**。

## 背景与发现

现状代码（`review.py` 的 `decide_review`）把人工复审结果经 `OUTCOME_VERDICT` 转成 L3 节奏反馈：

```
OUTCOME_VERDICT = {"still_valid": "on_time", "changed": "too_late", "stale": "too_late"}
```

即 `changed` 与 `stale` 都坍缩为 `too_late`，触发 `scheduling._aimd_factor` 的 `AIMD_DOWN=0.7` 缩短 `review_interval`。两个结构性问题：

1. **语义混淆**：`changed`（内容变了、还有参考价值）与 `stale`（基本没参考价值）是**内容/价值生命周期动作**，却被当作**节奏信号**——两者都缩短 interval，导致「无价值条目反而更频繁地进入注意力」，与 zj「stale 基本没有参考价值」语义方向相反（Plan `generated_assertions` 已记录）。
2. **L3 空转隐患**：`browse`（仅浏览不标注）只复位时钟 + `completed++`、不触发 L3；而 `changed`/`stale` 走 AIMD 乘因子，使人工 verdict 成为 AIMD 自适应环路的唯一人工输入源（外生锚 A，见 `review.py:5-7` 注释）。一旦 verdict 不再走乘因子，该环路人工输入即归零。

约束事实（来自本仓库只读核查，均为代码可核对项）：
- `src/zkc/cli.py:47` `VERDICTS = ("still_valid", "changed", "stale", "browse")` —— 四档中**无 `too_early`**，且 `zkc decide` 只有 `--id`/`--verdict`，没有任何内容载荷参数。
- `src/zkc/scheduling.py:220-221` `_aimd_factor` = `{too_early: AIMD_UP, on_time: 1.0, too_late: AIMD_DOWN}`。
- `src/zkc/tuning.py:120-121` 注释方向**写反**：`AIMD_UP` 注释写「复审判 late → 缩短」、实际被 `too_early` 使用（应=拉长）；`AIMD_DOWN` 注释写「复审判 early → 拉长」、实际被 `too_late` 使用（应=缩短）。此即裁决④的注释漂移源。
- `src/zkc/expiry.py` 动作枚举仅 `distill`/`archive`/`abstain`，**无 `enrich`/`refresh`**；`repository/protocols.py` 的 `NodeRepository` 只有 `archive` 软归档、**无 delete 节点接口**。
- `nodes.save` 已走 OCC + 双时态历史快照（`repository/memory.py:52-88`），可做节点内容新版本，但 `decide_review` 当前完全未调用。

## 决策（语义矩阵 v2 定案）

### ①–④ 四项裁决（zj 2026-11-14 15:46 逐项拍板）

- **① 否**：不新增 `too_early` 档。人工复审通道维持**单向收缩**（只有 still_valid 维持、changed/stale 收敛退出），记为已知取舍（见 Consequences §已知取舍）。
- **② 拆**：`changed` 与 `stale` 拆成**不同信号**——二者系统动作可同构，区分必须落在**审计 reason 与用例断言**（否则等于只拆名字）。
- **③ 承载**：`changed` 承载**内容更新动作**（写节点双时态新版本）。
- **④ 独立**：`tuning.py:120-121` 的 `AIMD_UP`/`AIMD_DOWN` 注释方向偏差，单独成 **doc-only 切片**、独立提交，不与语义实现混在同一变更批次（Plan Step 7）。

### S0 · 语义定案（zj 2026-11-14 16:08，须逐字保留）

- `changed` = **内容变了，但还有参考价值**
- `stale` = **内容腐坏了，基本没有参考价值，要么被 enrich / refresh 覆盖，要么被清除**

据此两档都是**内容/价值生命周期动作**，不是节奏信号；原建议 b（`stale` 保留 `too_late ×0.7`）与 zj 语义冲突，已作废。

### S1 · a–d 结论（zj 2026-11-14 16:25 原话「a–d 同意推荐」，须逐字保留）

- **a.** `changed` / `stale` 走 **L3 终局动作**、**不走 AIMD 乘因子** —— `changed` 更新内容（`nodes.save` 双时态新版本）且 interval **重置为 L1 基线**；`stale` 走 `archive` **退出调度回路**；既不硬绑节奏轴，也不让 L3 空转。
- **b.** 「enrich / refresh 覆盖」= 节点双时态新版本（`nodes.save`），**不是蒸馏产出 claim**（后者属复利变换，会撞上「不触发 distill」硬约束）。
- **c.** 「清除」只映射 `archive` 软归档，审计 `reason` 须与 D2「价值已升元认知层」**分开记**。
- **c2.** `changed` 内容载荷新增**必填参数**，只由 zj 本人逐条给，缺失即拒收，绝不自动填充或推测。
- **d.** 今日已写入的 **3 条 `changed` 保留旧语义产物** + 标注口径切换点，不回填、不重标记、不撤销 interval 调整。

### S2 · 覆盖分支裁决（zj 2026-11-14 16:33 原话「stale 覆盖分支纳入」，须逐字保留）

S0 中 `stale` 的 enrich / refresh 覆盖分支与清除分支**并列纳入本批次**；S1-a 中对 `stale` 的单条 `archive` 描述据此细化为两分支（属补充而非推翻）。

### 由 S2 与既有外生锚铁律推导的规格约束（非新增裁决，Human 可否决）

- `stale` 走覆盖还是清除**只能由 zj 本人逐条给出**，不得自动判定或默认清除。
- 覆盖的内容载荷同样**必填且只由 zj 给**。
- 覆盖按 a 的 **L1 基线同构**处理，不继承旧内容收缩结果。
- **覆盖分支不退出调度回路，清除分支必须退出**（硬契约）。
- `changed` / `stale 覆盖` / `stale 清除` / `D2` **四类审计 `reason` 互不相同**。

### 外生锚 A 架构级结论（须由 Plan Step 3 锁不变量并写本 ADR）

`changed`/`stale` 改走终局动作后，**AIMD 自适应环路的人工输入归零**：`decide_review` 不再调用 `S.adapt_interval`（AIMD 乘因子），只保留 decay 时钟复位（`mark_reviewed`）+ 标注率埋点（`attention_observation`）。即外生锚 A 由「乘因子反馈」退化为「仅时钟复位 + 埋点」，与 spike-09 F1 的 decay-only 复审恒 no-op 同源。该架构级结论**不抵消** a 已裁决的「终局动作替代乘因子」——它只是陈述采纳 a 后的连带事实，须在 Step 3 作为不变量锁定、实现时以测试守住。

## 语义矩阵 v2（规格输入，供 Step 2 消费）

| 档 | 内容/价值语义（S0） | 系统终局动作（S1-a/b/c） | 调度回路 | interval | 内容载荷 | 审计 reason |
|---|---|---|---|---|---|---|
| `still_valid` | 仍有效 | 仅复位时钟（维持） | 维持 | 维持（L1/L2/L3 现状） | 无 | `still_valid` |
| `changed` | 内容变了，还有参考价值（③承载） | `nodes.save` 双时态新版本 | 维持（不退出） | **重置为 L1 基线** | **必填，只由 zj 给** | `changed`（与另三类互异） |
| `stale` → 覆盖 | 内容腐坏，被 enrich/refresh 覆盖 | `nodes.save` 双时态新版本（≠蒸馏 claim） | **维持（不退出）** | **重置为 L1 基线**（同构，不继承收缩） | **必填，只由 zj 给** | `stale_overwrite`（与另三类互异） |
| `stale` → 清除 | 内容腐坏，无保留价值 | `archive` 软归档 | **退出**（due 队列消失） | —（已退出） | 无（仅分支选择必填且只由 zj 给） | `stale_purged`（与 D2 分开记） |
| `browse` | 仅浏览不标注 | 复位时钟 + `completed++` | 维持 | 维持 | 无 | `browsed_without_label` |

> `too_early` 不在表中（裁决①）；`D2`（价值已升元认知层）单列审计 reason，不与 `stale_purged` 混同（S1-c）。

## Considered Options

- **保持 v1 坍缩映射（拒绝）**：`changed`/`stale` 同走 `too_late ×0.7`，使无价值 `stale` 条目更频繁进入注意力，与 zj 语义方向相反；且 L3 把内容生命周期当节奏信号，语义混乱。
- **新增 `too_early` 档（拒绝，裁决①）**：人工通道维持单向收缩为已知取舍；新增档会引入「拉长 interval」的正反馈，与当前 AIMD 环路及 ADR-0009 的 0.25d 下界语义耦合过深，超出本次切片。
- **②拆 + 终局动作替代乘因子（采纳）**：`changed`/`stale` 拆信号、各自走终局动作、`interval` 重置 L1 基线、`stale` 清除退出回路。代价：需 Step 2–5 实现（必填载荷通道、`nodes.save` 新版本接入、`archive` 退出、`reason` 四分类、CLI 契约），且 AIMD 自适应环路人工输入归零（须以测试守住不变量）。

## Consequences · 必须同时记住的边界

1. **本 ADR 只定决策，代码未改**：当前 `OUTCOME_VERDICT` 仍是 `{"still_valid":"on_time","changed":"too_late","stale":"too_late"}`，`zkc decide` 仍无内容载荷参数。任何「代码已按 v2 实现」的表述均属误读。落码属 Plan Step 2–5，未授权。
2. **外生锚 A 行为变更待实现**：「AIMD 自适应环路人工输入归零」在落码前不成立；当前 `decide_review` 仍调 `adapt_interval`。实现时须用测试锁死「verdict 不再触发乘因子、只复位时钟 + 埋点」，并与 ADR-0009 的 `floor_hit`→`archive` 机制区分（后者是 interval 触底后的自动归档，与人工 `stale` 清除是两回事）。
3. **与 ADR-0007 / ADR-0009 的关系不变项**：ADR-0007 fork1「人工 `decide` 不可自动化」继续成立（内容载荷仍须 zj 逐条给）；ADR-0009 的 `MIN_INTERVAL_DAYS=0.25` 下界与 `floor_hit`→archive 机制不变，但人工 verdict 不再作为 AIMD 乘因子的输入（post-implementation）。
4. **已知取舍（裁决①）**：不新增 `too_early` 档，人工复审通道单向收缩；若未来出现「节奏比真实腐化快、应拉长」的真实外生锚，再单独立项，不静默回填本 ADR。
5. **注释漂移（裁决④）独立处理**：`tuning.py:120-121` 的 `AIMD_UP`/`AIMD_DOWN` 注释方向写反，由 Plan Step 7 的 doc-only 切片单独修订、独立提交，不并入语义实现批次。
6. **历史 3 条 `changed` 不回填**：S1-d 定，今日已写入的 3 条 `changed` 保留旧语义产物与口径切换点，落码时不得回填、重标记或撤销其 interval 调整。

## 验证证据

- **决策溯源（过程态，非权威 proof）**：Plan `2026-11-14-zkc-verdict-semantics-plan.md` §Human checkpoints 逐字收录 ①–④ / S0 / S1 / S2；原始拍板在工作日志 `.workbuddy/memory/2026-11-14.md`（15:46 / 16:08 / 16:25 / 16:33 段）；roadmap carrier `1-1` decisions 同步落盘。
- **代码现状（可核对）**：`web/review.py:40-44`、`cli.py:47`、`scheduling.py:220-221`、`tuning.py:120-121`、`expiry.py` 动作枚举、`repository/protocols.py` NodeRepository 接口，均为本仓库当前事实。
- **TDD 证据 = N/A**：实现（Step 2–5）未启动，无红绿输出、`make test` 增量、`zkc decide --list --json` 真值回读对照。本 ADR 不声称任何运行时验证。
- **roadmap 联动**：节点 `1-1`（Step 1 语义裁决）依 zj 2026-11-14 19:31 选项 A（「保持 in_progress，等 Step 6 把语义矩阵 v2 提炼到 ADR 后再谈 completed」），在本 ADR 落盘后转为 `completed`；下游 `1-2`–`1-7` 仍 `pending`，受 `blocks` 边阻塞，未授权执行。

## 实现跟进（2026-11-14 Step 4 落码后）

> 本 ADR 决策已于 2026-11-14 Step 4（TDD 落码，zj 20:49 授权）实现。上方「实现状态 = 未做、未授权」「本 ADR 只定决策，代码未改」「下游 1-2–1-7 仍 pending」均为**定案时刻（19:57）状态描述，现已过时**，以 `2026-11-14-verdict-semantics-cutover.md` 为准。

- **代码已实现**：`src/zkc/web/review.py` 重写为终局动作分支 + `REVIEW_REASON` 常量（替代 `OUTCOME_VERDICT`）；`src/zkc/cli.py` 新增 `--content`/`--stale-branch`（choices=cover/purge），`ValueError`→`exit 2`；新增 `tests/test_verdict_v2.py`（12 项）+ 改写 `tests/test_web_review.py`（22 项）。
- **门禁与健康度**（见 cutover §6）：全量 **626 tests OK**（基线 613，+13）、authority 0 leaks、mcp-gate 6 OK、invariant 0 violations。
- **不变量已落实**：外生锚 A 人工输入归零（DI-1，A3）、覆盖不退出·清除退出（DI-4，B2/D2）、四类 reason 互异（DI-2，F1）均被测试守住。
- **口径未污染**：阈值常量（`AIMD_UP`/`AIMD_DOWN`/`MIN_INTERVAL_DAYS`/`METRIC_W_*`）未动、不写回 `REGISTRY`，与 1-26 CALIBRATED 正交（DI-6）。
- **本文档定位不变**：仍是 Step 1 语义裁决的长期归档；上方决策正文（①–④ / S0 / S1 / S2 / 外生锚 A 结论 / 语义矩阵 v2）一字未改，仅补充实现跟进，不涂改原决策。
