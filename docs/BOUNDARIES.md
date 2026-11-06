# 产物边界约定 · docs / code / roadmap 解耦

> 生效：2026-11-02（zj 拍板「内容解耦，不动目录」）
> 配套：roadmap 根节点 1 的 decide「解耦原则」。
> **roadmap 驱动跟踪已于 2026-11-03 结束**：`docs/plans/roadmap.json` + `ROADMAP.md` 已删除（节点 1-7-4 为唯一未结项，其观察期目标已迁入 PRD §9 TODO 续跟）；ADR 0010 的「roadmap.json 留在 docs/plans/」条款随之失效。本文件保留为**通用解耦约定**，code 注释中的 roadmap 节点 id 溯源锚仍有效（见规则 2）。

## 为什么需要这份约定

验证发现 roadmap 与代码存在**易失效的硬耦合**，会在代码演进后悄然失真：

- roadmap 节点 label 写死代码文件路径 `zkc/tuning.py`，而 1-9 已把 `zkc/` 平铺改为
  `src/zkc/`，路径引用当场失效；
- 同一 label 硬编码实时计数 `REGISTRY 49`，而该计数在 29 → 48 → 49 之间反复漂移
  （历史 decide 留痕可见），roadmap 成了代码状态的失真镜像；
- `task_queue.py` / `review.py` 仍引用**已删除**的 `TODO.md`（1-9 Q4 已删），属 dead reference；
- `UI-BRIEF.md`（已于 2026-11-02 文档治理中删除，系 1-9 临时 intake brief）此前同样引用已删除的 `TODO.md`。

解耦目标：**三类产物各自拥有清晰的真相域，互引只走稳定标识符，不把对方当实时镜像。**

## 三类产物的归属与职责

| 产物 | 位置 | 拥有（真相源） | 不拥有 |
|---|---|---|---|
| **code** | `src/` `tests/` `migrations/` `scripts/` | 实现；参数/路径/计数/迁移编号的**实时真相** | 进度状态、决策依据 |
| **docs** | `docs/`（PRD / 架构 / 研究 / user-guide / ADR） | what / why；概念、架构决策、使用方式 | 实时参数、节点进度 |
| **roadmap** | （已结束 · 2026-11-03 文件已移除） | plan / status / intent；节点进度与决策留痕（现为历史快照） | 代码内部细节的实时值 |

## 解耦规则（强制）

1. **roadmap 节点 label / notes 只描述意图、能力、状态，不硬编码代码内部细节。**
   - 禁止：文件路径（`zkc/tuning.py`）、把迁移编号当真理、参数 / 测试 / 节点**实时计数**。
   - 允许：引用**能力名**（「阈值表（tuning 模块）」）、引用**稳定标识符**（ADR id、roadmap 节点 id）、
     指向**运行态真相**（「以 `/tuning` 实时为准」）。
   - 历史快照若要保留，放进 `decide`（审计留痕），**不在 label 当当前真理**。
2. **code 注释可引 roadmap 节点 id / ADR id 作溯源锚**，但**不得读取或依赖** `docs/` / roadmap 文件，
   不得把文档当配置或数据源（单向引用）。
3. **docs 不复述代码内部路径 / 计数**；架构文档引用模块能力或 ADR，不引易变文件路径。
4. **互引只走稳定标识符**：roadmap ↔ code 经「节点 id / 能力名」；doc 经「ADR / 节点 id」。
   禁止双向硬绑（code 读 roadmap 文件、roadmap 当代码镜像）。
5. **单一真相源**：
   - 参数 → `tuning.REGISTRY` + `GET /tuning`
   - 代码路径 / 结构 → 代码树本身
   - 进度状态 → （roadmap 已结束）现以 PRD §9 TODO / 代码运行时为准
   - 决策依据 → ADR / decision

## 编辑工作流

- **roadmap**：（已结束 · 2026-11-03 文件已移除）原只走 `roadmap_cli.py`（`update` / `decide` / `render`）；本项目的 roadmap 驱动跟踪已收尾，文件不再维护。code 注释中保留的 roadmap 节点 id 仍作溯源锚，不依赖文件存在。
- **docs**：正常编辑；新架构决策先落 ADR，不在 roadmap 复述细节。
- **code**：TDD；改路径 / 计数自动反映到运行时，**不回写** roadmap label 的计数或路径。

## 本次已清理的耦合

- 节点 `1-2-3` label：去掉失效路径 `zkc/tuning.py`（已随 1-9 迁 `src/zkc`）+ 去掉硬编码 `REGISTRY 49`，
  改为「阈值表（tuning 模块；参数数以 `/tuning` 实时为准）」。历史计数（29/48/49）仍保留在 decision 留痕。
- code：移除 `src/zkc/task_queue.py` 与 `src/zkc/web/review.py` 对已删除 `TODO.md` 的引用。
- `UI-BRIEF.md`：已于 2026-11-02 文档治理中**删除**（临时 intake brief，信息已无残留引用）。

## 仍需关注的残留（建议，本次未自动改）

- `docs/archive/plans/ZKC-implementation-plan.md`（原 ≈59KB，2026-11-02 已归档）→
  风险表 R1–R19：已闭合项（R1/R2/R3/R5/R7/R8/R9/R11/R12/R13/R15/R16/R17/R18/R19）已归档至 `docs/archive/plans/`，活跃/挂观察期项（R4/R6/R10/R14）在 `docs/risks.md`；§8 硬约束在 `docs/constraints.md`；本文件不再持续维护，与 roadmap 双头真相已解除。
- 大量 `decide` 记录含历史代码路径 / 计数（29/48/49、391/403/407/409、commit hash） →
  这些是**审计留痕**，保留；理解时以代码 / 运行时为准，不以其中数字为当前真理。
- `tuning` 多数参数仍为 `PLACEHOLDER`（校准门禁），属设计内，待 PRD §9 观察期目标（原 `1-7-4`）攒够埋点后 `calibrate()`。
