# ZKnowledgeCompounding · 项目实施计划（骨架）

> 状态：**v0.6**（2026-10-31 按代码库对账后同步）
> - **已拍板并落地**：§0.1 六项 TODO + R2 六项（含 **③ 工期 = 4 h/周**）；架构三角审计 A 档 12 项已回填架构+PRD、B 档 3 项转 §5（R13/R14/R15）；**§3.2 裁剪方案 = S1 已生效**（执行顺序 P0→P1→P2→P4→P3→P5→P6）。
> - **P0 文档收口：完成**（R9 已解决）。P0 剩 P0.3「评审签字」待 zj 一次性签字。
> - **P1 存储地基：全部完成（7/7 节点）** —— P1.0（编码器定维，R16）/ P1.1（迁移 D1–D9，**11 tests passed**）/ P1.2（repository seam）/ P1.3（双时态+decay 线性实测）/ P1.4（阈值表 **17 tests** + 治理收口）/ P1.5（**R19 关闭=不回迁 Alembic**，guard 测试锁方向）均已完成。代码资产见 **§10**。
> - **⚠️ 全部改动未 commit**：`git status` 有 4 个 modified + 7 个 untracked（含 `zkc/`、`migrations/`、`tests/`、`spikes/spike-14-embedding-dim/`、`docs/zj-adr/`、`ZJ-CONTEXT.md`）。按 zj 约定 commit 需显式触发。
> - **⚠️ 4 h/周 的连带后果（见 §3.2）**：日历工期 **24–32 周（约 6–8 个月）**，与 P6「每天打开」不可共存 → **R10 降级判定默认启用**（上线判定 = 累计 ≥20 个带标注复审动作）。
> - **⚠️ 本次对账修正的过时结论（按 §0 铁律 2 留痕，见 §5 R19）**：`zkc/migrate.py` 的选型理由「pip 装不上包」**已被推翻**（走代理可装）——此为留痕，不再作为选型依据。R19 已于 **P1.5（2026-10-31 收口）正式关闭 = 不回迁 Alembic**：判定依据转为 R19 触发条件（P1.2 = raw SQL + repository seam，未引入 SQLAlchemy ORM → 触发未满足）+ 第一性不变量「依赖最少」+ 11 tests 跑通 + sha256 留痕/`verify` 闸门。锁方向 guard 测试见 `tests/test_r19_guard.py`。
> 目的：把 `PRD v0.2` + `架构 v1.2` + **15 个** spike 的**已验证决策**，转化为「开工 → 上线」的可执行计划。
> 本文件是**决策级 → 执行级**的桥接，不重复 PRD/架构内容，只引用与拆解。
>
> 引用文档（均为当前最新版）：
> - `docs/prds/ZKnowledgeCompounding-PRD.md`（v0.2）
> - `docs/architecture/ZKC-architecture-v1.2.md`（v1.2，顶部「待 zj 复核」→ **已复核**；逐条审计留痕见 §11 + `docs/plans/ZKC-architecture-v1.2-review-checklist.md`）
> - `docs/research/RESEARCH-TOPICS.md`（22 topic；**2026-10-31 已冻结为只读历史索引**，open 项已迁入本计划 §4/§5）
> - `spikes/spike-{01..13,13b,14}-*/README.md`（**15 个**，全 passed）
> - **代码资产**：`zkc/`（应用包 + 阈值表 + 迁移器）、`migrations/`（0001 D1–D9）、`tests/`（28 tests）——见 §10

---

## 0. 持续维护原则（本文件作为实施过程完整 context 的使用契约）

> 本文件不是「一次性写完后束之高阁」的交付物，而是**贯穿开工→上线的活 context**：任何执行者在任何时间切入，都应仅凭本文件 + 引用的 PRD/架构/spike 即可恢复完整上下文，不依赖口头传承或散落的聊天记录。

**维护铁律（每次推进都必须遵守）：**
1. **决策变更必回链**：§2 决策基线中任何一条被推翻/调整，必须回到对应 spike 复测，并在该决策行追加「变更日期 + 原因 + 新结论」，禁止静默改数。
2. **参数变更必留痕**：§2 / §4 / §6 中的任何阈值、默认值、模型选型改变，记录旧值→新值 + 触发条件，不得只改一处数字。
3. **open 项状态必流转**：§5 风险登记册的每条状态（open/已缓解/已解决）随实施推进更新；不得把「已缓解」误读为「已解决」，也不得把 spike 的「带限定结论」外推成「无条件成立」。
4. **坑位必登记**：实施中踩到的环境/硬件/工具约束（见 §8），无论是否预期，都回填 §8，使其滚雪球成为团队唯一可信的「踩坑备忘录」。
5. **进度回写**：每个 Phase 完成时，在对应 Phase 行追加实际工期、关键产出链接、偏离项；未完成的子任务保留 `[ ]` 并注明阻塞原因。
6. **禁止静默外推 spike 限定**：架构 §8 的「⚠️ Spike 10/02 限定条件」、各 spike 的 open 项，是本协议的最高风险红线；任何实现都不得假设「单次采样结论可信」「小模型自动判定可用」「阈值已校准」。
7. **渐进式暴露，避免臃肿**：本文件只保留实施所需的**必要信息**（决策/风险/里程碑/硬约束）；细节与证据一律**引用** PRD/架构/spike/调研报告，不在此复制。某节内容超过一屏即视为信号——将其外移为独立文档，本文件仅留「引用锚点 + 一句结论」，保持单一可维护 context 不膨胀。
8. **不依赖临时跟踪产物**：执行过程若借助临时路线图/进度跟踪文件（完成后即删），本文件**不得将其作为事实源或引用源**；其必要信息（执行顺序、关键决策）须**摄取**进本文件 §2/§3.2/§4 后方可删除该临时产物，使本文件自包含、可独立作为长期权威源。

**维护责任人**：zj（架构/决策）+ AI 搭档（执行中回写草稿，zj 复核签字）。每次 commit 前本文件应与代码同步更新（或显式标注「本提交未触及计划文件」）。

---

## 0.1 阅读指引与 TODO(zj) 汇总

**已全部拍板（zj，2026-10-31 全票通过推荐项）。** 下表即结论，后续不再回退；任何变更按 §0 铁律 1/2 留痕（旧值→新值 + 触发条件 + 变更日期）。

| # | TODO | 拍板结论 | 落地动作 | 状态 |
|---|---|---|---|---|
| ① | `上线`定义 | **本地 web 应用**（FastAPI + 服务端渲染极简页，`localhost:8000`）。交付 = 本机可启动 + README 启动脚本；**不做**打包/签名/对外分发/桌面壳/TUI | §1.2 已填；ADR-0001 | ✅ |
| ② | 架构「待 zj 复核」 | **AI 先做三角一致性审计**（架构 v1.2 vs 14 个 spike vs PRD v0.2），产出逐条清单；zj **只批 A/B 档异常项**，C 档整批认可 | 审计已交付：`docs/plans/ZKC-architecture-v1.2-review-checklist.md`——**A 档 12 项需修订 / B 档 3 项转 risk / C 档 62 项已验证**；**zj 已全批，A 档 12 项已回填架构（8 处）+ PRD（4 处）、B 档 3 项转 R13/R14/R15、C 档整批认可**，架构顶部已改「已复核」 | ✅ |
| ③ | Phase 工期估算 | **已定档：4 h/周** → 合计 **94–126 h = 24–32 周（6–8 个月）** + 观察期 | §3 / §3.1 已填；**连带启用 R10 降级判定**（§3.2） | ✅ |
| ④ | 占位阈值校准 | **冻结为 v1 常量表 + 来源标签 + 校准门禁**：建 `zkc/tuning.py`（`{value, source, calibrated_at}`）；budget 初值 **1.0/天**（原 1.2 无出处，弃）；AIMD **保留 1.5/0.7**；其余（α=0.3、±30%、×2、p25、oversubscribe×1.5、PRESSURE_DEFER 0.8）原样冻结；**顺带统一 5 处重复定义的 `ROT_THRESHOLD=0.9`** | §2 + P1.4 | ✅ |
| ⑤ | 已捕获规则统一 | **单程票**：已捕获 → 拉长观察 28d → 到期即 ARCHIVE，**永不回 DISTILL**。边界 1 = `produced_by` 级联撤销后按未捕获基线重算且写 D7 留痕；边界 2 = **self_loop 压过已捕获**（修 spike 09 内 L1/L2 顺序矛盾） | 架构 §6.5 / §8 已改；ADR-0002；P4.5 具体化 | ✅ |
| ⑥ | RESEARCH-TOPICS 收口 | **冻结为历史索引**（挂 spike 链接 + 标只读），open 项迁入架构 §9 + 计划 §5；**7 个无 spike 覆盖的 topic 转为显式待做**（T0.2/T0.3/T2.2/T6.1/X.1/X.2/X.3） | **P0.2 已完成（2026-10-31）**：顶部 🔒 只读声明 + §1 处置表 + §1.1 迁移表；T0.2→P2.1、T6.1→P5.1 已挂并计入工期；T0.3/T2.2 延后；**X.1 并入不变量 5 / X.2、X.3 转非目标（R2-5 拍板，见 §1.3）** | ✅ |

**R2 五项亦已全票通过（2026-10-31）并落地**（不属原六项，但由它们解锁）：
- ✅ **R2-0 审计异常项**：A 档 12 项全批、**已回填架构（8 处）+ PRD（4 处）**；B 档 3 项全转 risk（§5 R13/R14/R15）。C 档 62 项整批认可。**A6 引出的编码器未定问题 → 新增 R16**
- ✅ **R2-2 冷启动素材**：现有动态型素材 **≥60 条**（见 §1.2）
- ✅ **R2-3 预算分账**：蒸馏人审与复审**两套独立预算**（§2 / R11 已解决）
- ✅ **R2-4 溯源权威**：`evidence_refs` 唯一权威，`citation` 仅供度量（§2 / 架构 §5 已写入）
- ✅ **R2-5 度量 operationalize**：全部自动判定 + 复利系数等权 0.25 起步 + 每周复盘（§7）；X.1/X.2/X.3 去向已定（§1.3）
- ✅ **R2-1 每周可投入小时数**：**4 h/周**（zj 拍板 2026-10-31）→ §3 工期列已填死数字（24–32 周）；**因 4 h/周 与 P6「每天打开」不可共存，R10 降级判定改为默认启用**（见 §3.2 / §1.2 / §6）

---

## 1. 范围与上线定义

### 1.1 MVP 边界（引 PRD §3）
**目标（MVP 要证明的）**：
1. 原生双轨建模（静态/动态各自生命周期元数据）
2. 可运行的蒸馏路径（→ 元认知层 + topic 组织 + 反向连接）
3. 资源感知调度（基于生命周期/衰减的「该关注/可衰减」信号）
4. 复利可观测（基础度量说明复利正在发生）
5. **外生锚闭环**：每日复审队列 UI（两个自指闭环唯一外生锚；缺它 interval 停基线、budget 停 warm-up）

**非目标（MVP 不做）**：全自动蒸馏、复杂图谱可视化、跨设备同步、多人协同、权限体系、替代 OneNote/Obsidian 全部能力。

### 1.2 「上线」定义 ✅ 已拍板（zj，2026-10-31，ADR-0001）

- **交付形态**：**本地 web 应用** —— FastAPI + 服务端渲染极简页，浏览器开 `localhost:8000`。理由：MVP 有三处交互（每日复审队列 / 蒸馏 HITL 编辑结构化 claim / 5 度量面板），全是「列表 + 表单 + 编辑」；外生锚不可用的代价是**两个闭环全废**（架构 §6.5.1：没有这个界面，budget 估计器永远停在 `confidence='none'`、L3 闸门无样本）。
- **明确不做**：打包、签名、对外分发、桌面壳（Tauri/Electron）、TUI、CLI 为主形态 —— 一律延后到 P6 之后另议。
- **上线判定（P6）**：**单人 dogfood** —— zj 本人用**导入的真实历史素材**跑通 e2e 闭环。**⚠️ 判定口径已因 4 h/周 选档而变更**（2026-10-31）：原「≥7 个活跃日（每日队列非空）」要求**每天打开**，与「每周 1 次触碰、4 h/周」不可共存 → **默认启用 R10 降级判定**：
  - **现行判定 = 累计 ≥20 个带标注的复审动作**（不要求连续活跃日、不要求日历连续）；仍要求素材为**导入的真实历史素材**、标注率 ≥70%（§6）。
  - 「≥7 活跃日」降级为**可选加强档**：若某段时间确实能做到每天打开，可额外记录，但不作为上线必要条件。
  - **不要求第二人可独立安装**。
- **冷启动数据**：导入真实历史素材 —— **现有动态型素材**（工作项目随手记 / 待办 / 日志），**≥60 条**（zj 拍板 2026-10-31，R2-2）。硬约束来自 spike 09 的结构性极限：**条目太少时注意力容量不可观测**（oversubscribe 也抬不高供给），素材低于此量级 budget 估计器会长期停在 `lower_bound`、L2 永不归一化。具体来源目录待 P6 前确定（不阻塞开工）。
- **⚠️ 硬约束（已按降级口径改写，2026-10-31）**：判定不要求连续打开，但**必须真的产生 ≥20 个带标注的复审动作**；做不到则外生锚不产生、P6 判不了（budget 停在 warm-up、L3 无样本）。已登记 §5 R10。

### 1.3 不在范围内（引架构 §7 延后项）
图数据库(Kuzu/TerminusDB) · LiteLLM · Argilla · Langfuse · Electric/Automerge 多端同步 · XTDB（待带外验证）· Cordis/DeepSeek Harness（重述为**模式源**，不引入依赖）。

**由 RESEARCH-TOPICS 收口新增的非目标（zj 拍板 2026-10-31，R2-5）**：
- **X.1 隐私与安全** → **不单列 topic**：已由第一性不变量 5（默认本地/离线优先）覆盖，实现时按不变量遵守即可。
- **X.2 与 ZAgentic 复用边界** → **非目标**：MVP 不与 ZAgentic 共享代码或运行时，仅保留 provider/storage seam。
- **X.3 既有工具可取点** → **已由四份 sealed 调研关闭**（OneNote/Obsidian/llm-wiki/gbrain/OKF 只做 unit-capability 模式源，见架构 §6.4），不再作为独立工作项。
- **T0.3 多模态入口 / T2.2 topic 组织** → 延后到 P6 之后（不在 MVP 工期内）。

---

## 2. 决策基线（已验证，开工即锁定，禁止静默推翻）

| 子系统 | 决策 | 来源 | 关键参数 / 约束 |
|---|---|---|---|
| 存储 substrate | **Postgres 16 + pgvector**（repository seam 可替换 Kuzu/TerminusDB） | Spike 01 | enum + GIN；静态轨 decay 恒 0；claim 无 evidence_refs 被 schema 拒绝。**⚠️ 2026-10-31 变更（铁律 2 留痕）：`vector(1024)` → `vector(768)`**。旧值 1024 = spike 01 验证 DDL 可执行性的占位，与真实编码器不符；新值 768 = spike 14 实测 `nomic-embed-text`。触发条件：迁移落地前必须定维（换维度 = 重建索引）。已落 `migrations/0001` |
| 双轨模型 | 单表 `node` + `track` 枚举 + 双时态(`valid_/tx_from/to`) | Spike 01 / PRD §4 | 双时态≠双轨，仅服务静态事实演进溯源 |
| 衰减 decay | **线性** `min(1, elapsed/interval)` | Spike 01 | SURFACE=0.6 / ROT=0.9（现集中于 `zkc/tuning.py`，`source=simulation`）；阶梯否决；指数备选；**c2（ADR-0003）：`decay_score` 是派生量，`update_decay` 不写 `node_history`、不 bump `tx_from`（刷新不污染双时态语义）** |
| 双轨分流 | **DecisionRouter 主方案** + 双信号弃权 + 人工兜底 | Spike 02/03 | 3-way 仅强编码器(qwen3)预过滤；`routing_confidence` 记录；周期重分类 |
| 蒸馏模型 | `qwen3.5:4b-mlx` 默认，9b 可选上限 | Spike 10 | 9B 在 16GB 常驻 10–12GB 触发 swap → 4B 默认 |
| 结合/建模 | **ZKC 自研程序**（RCS 漏斗 + 引用强制 + 级联撤销） | Spike 05 | 无候选产出建模产物 |
| LLM 编排 | Ollama + Instructor + LangGraph(checkpoint 落同库 PG) | T3.3 调研 | provider seam 保留切强模型 |
| 跨源综合 | **算子层硬约束**（≥2 跨源断言 + 单次补全回路） | Spike 11 | 4B×3 稳定 3/3；1.5B 无溢出收益 |
| 拓扑装配 | `context_member` junction + `produced_by` 级联撤销 | Spike 06 | `context.scope` 为 ENUM(context_scope) |
| 度量 | 5 指标：连接密度/复用率/方法论产出/衰减可控/复利系数 | Spike 07 | 权重与 `method_target` 待校准 |
| `review_interval` | **三层**(L1 基线/L2 预算归一/L3 AIMD 反馈) | Spike 09 | 双层量=个体基线×预算因子；`infeasible` 显式报告 |
| `budget_per_day` | 统计估计（删失感知+单调护栏+阻尼 EMA+校准期 oversubscribe） | Spike 09 切片 B | 阈值占位待真实数据校准 |
| 忠实度闸门 | **MVP = human-in-the-loop + 字面 rubric 预过滤** | Spike 12/13/13b | 自动 LLM judge 本机否决；`judge.py` 零改动可启用 |
| **交付形态** | **本地 web**（FastAPI + 服务端渲染，`localhost:8000`） | zj 拍板 2026-10-31 / ADR-0001 | 不做打包/签名/对外分发；桌面壳与 TUI 延后 |
| **上线判定** | **单人 dogfood + 导入真实历史素材 + 累计 ≥20 个带标注复审动作** | zj 拍板 2026-10-31（**2026-10-31 晚修订**：因 4 h/周 选档，R10 降级判定默认启用） | 原「≥7 活跃日（每天打开）」降为**可选加强档**——4 h/周 与"每天打开"不可共存；活跃日 ≠ 自然日（空队列日不计数，它正是 budget 估计最需要的删失样本）；第二人可装不属 MVP |
| **阈值治理** | **`zkc/tuning.py` 常量表 + `{value, source, calibrated_at}` + 校准门禁** | zj 拍板 2026-10-31 | budget 初值 **1.0/天**（原 1.2 无出处，弃）；AIMD **保留 1.5/0.7**；校准门禁 = 连续 14 天埋点且 ≥3 个饱和日后才允许置 `calibrated`；**5 处重复 `ROT_THRESHOLD=0.9` 统一到 tuning.py（P1.4）** |
| **已捕获条目** | **单程票**：已捕获 → 28d 拉长观察 → 到期即 ARCHIVE，**永不回 DISTILL** | zj 拍板 2026-10-31 / ADR-0002 | 边界 1：`produced_by` 级联撤销后按未捕获基线重算并写 D7 留痕（禁止静默变）；边界 2：**self_loop 压过已捕获**（修 spike 09 L1/L2 顺序矛盾） |
| **溯源权威** | **`meta_claim.evidence_refs` 唯一权威**（schema 级 NOT NULL，是 claim 存在的前提）；`citation` 只记「后续复用」的**行为事件**，仅用于复用率度量 | zj 拍板 2026-10-31（R2-4） | 已写入架构 §5 权威声明。**`citation` 不参与「是否已捕获」判定**——否则"被引用一次"会被等同于"价值已沉淀"，与单程票语义冲突 |
| **注意力预算分账** | **两套独立预算**：复审预算（`budget_per_day`，初值 1.0/天）与**蒸馏人审预算**分离计量 | zj 拍板 2026-10-31（R2-3） | 性质不同（维持 vs 生产）；`F_cap=20%` 只对蒸馏人审侧生效，不再把 0.2 条/天当上限 |
| **度量 operationalize** | 5 指标判定者**全部自动**；复利系数**等权 0.25 起步**（标占位）；复盘节奏**每周**（与 P6 的 7 活跃日对齐） | zj 拍板 2026-10-31（R2-5） | 见 §7；X.1 并入不变量 5 不单列；X.2/X.3 转非目标（见 §1.3） |
| **schema 迁移方式** | **自研零依赖迁移器** `zkc/migrate.py`（`docker exec psql` + `schema_migration` 版本表 + sha256 留痕）；**不用 Alembic** | P1.1（2026-10-31）/ **R19 关闭 2026-10-31** | 子命令 `status/upgrade/downgrade/verify`；单事务应用；`verify` 拦「改历史迁移」。**R19 已关闭 = 不回迁 Alembic**：「pip 装不上」理由已作废留痕，最终判定依 P1.2（raw SQL + repository seam，无 SQLAlchemy ORM → 回迁触发未满足）+ 依赖最少不变量；锁方向 guard 见 `tests/test_r19_guard.py` |
| **embedding 编码器** | **`nomic-embed-text:latest` → `vector(768)`** | Spike 14 实测 2026-10-31（R16 已解决） | 9.5ms/条、274MB（vs qwen3 4096d：183.2ms/条、4.7GB）。**硬约束：仅限检索召回/反向连接候选，严禁用于安全判定**（spike 03：nomic dangerous=3，该职责归 DecisionRouter）。可逆路径 = 加列 `embedding_strong vector(4096)` |

> 上述决策若有调整，必须回到对应 spike 复测并回填架构文档，不得静默改。

---

## 3. 里程碑计划（Phase 0–6）

> 组织原则：**按数据流向切成 e2e 切片里程碑**（捕获→复利→调度→复审→复用），而非瀑布；每个 Phase 尽量自带可验证闭环（呼应 RESEARCH-TOPICS「闭环而非管道」）。
>
> **⚠️ 执行顺序 ≠ 编号顺序（S1 已生效，zj 拍板 2026-10-31）**：编号保留原义供追溯，但**实际执行顺序为 P0 → P1 → P2 → P4 → P3 → P5 → P6**。
> 依据：P4（调度+复审闭环）**只依赖 P2 的分流结果**，不依赖 P3 的蒸馏产物；而 P4 的外生锚闭环与注意力调度信号是 ZKC 差异化**最早可感知**的产出。在 4 h/周（24–32 周跨度）下，这把「第一次看到系统替我省注意力」从第 14–22 周提前到**第 8–13 周**，总工时不变。

| Phase | 目标 | 关键产出 | 验收闸门 | 依赖 | 工期（按 4h/周 折算） |
|---|---|---|---|---|---|
| **P0 文档收口** | 基线对齐，消除文档债务 | 决策基线(§2)固化 + 风险登记册(§5) + RESEARCH-TOPICS 状态更新 | 架构「待 zj 复核」清零；RESEARCH-TOPICS 状态列与 spike 一致 | — | 2–4 h ≈ **0.5–1 周** · **实际：已完成 2026-10-31**（P0.1/P0.2/P0.4 ✅，剩 P0.3 签字） |
| **P1 存储地基** | schema 落地为可迁移代码 | 迁移(D1–**D9**) + repository seam | Postgres16+pgvector 迁移跑通；双时态/decay/claim/citation/context_member/review_queue/interval 全 DDL 落地 | P0 | 12–16 h ≈ **3–4 周** · **进行中 3/5**（✅ P1.0 编码器定维 / ✅ P1.1 迁移 0001 / ✅ P1.4 阈值表；剩 P1.2 seam、P1.3 decay 触发器） |
| **P2 摄入+分流** | 低摩擦快捕获 + 正确分轨 | 捕获 UX(本地离线) + DecisionRouter 接入 | 动态条目 → 正确分轨 → 入 review_queue；弃权转人工 | P1 | 16–20 h ≈ **4–5 周** |
| **P3 复利变换** | 蒸馏/结合/拓扑装配跑通 | 蒸馏(4B+HITL) + 结合算子(RCS) + context 装配 | 一条动态条目 → 元认知 claim+topic+反向连接 → 装配进 context | P1,P2 | 24–32 h ≈ **6–8 周**（**执行顺位 5**，S1 后移到 P4 之后） |
| **P4 调度+复审闭环** | 资源感知 + 外生锚 | review_interval 三层 + **每日复审队列 UI** + budget 统计 | 出队→标注(still_valid/changed/stale)→interval 反馈；**标注率闸门 ≥70%** | **P2**（S1 已生效：不再依赖 P3） | 20–26 h ≈ **5–6.5 周**（**执行顺位 4**） |
| **P5 复用+度量** | 复利可观测 | 检索/浏览 + 5 度量面板 | 能检索复用 compound 产物；5 度量出数 | P3,P4 | 12–16 h ≈ **3–4 周** |
| **P6 上线** | 本地 web 可启动 + 真实数据跑通（**不做打包/对外分发**） | 冷启动导入 ≥60 条 + 引导 + 用户文档 | **累计 ≥20 个带标注复审动作**（降级判定，见 §1.2）；标注率≥70%；腐化可控（见 §6） | P1–P5 | 8–12 h ≈ **2–3 周** + 观察期 |
| **合计** | | | | | **94–126 h ≈ 24–32 周（6–8 个月）** + 观察期 |

### 3.1 工期估算（**已定档：4 h/周**，zj 拍板 2026-10-31）

| Phase | 工时估算 | 说明 |
|---|---|---|
| P0 文档收口 | 2–4 h | ✅ **已完成**：审计清单交付（P0.1）+ RESEARCH-TOPICS 冻结（P0.2）+ ZJ-CONTEXT/ADR（P0.4） |
| P1 存储地基 | 12–16 h | D1–**D9** 迁移 ✅ + `tuning.py` 阈值表 ✅ + **编码器定死（R16）** ✅；剩 repository seam + decay 触发器 |
| P2 摄入+分流 | 16–20 h | 快捕获 UX（**T0.2**）+ DecisionRouter 接入 + 双信号弃权 |
| P3 复利变换 | 24–32 h | 蒸馏 + 跨源 + 结合 + context + 忠实度闸门（**最大块；HITL 人审是串行瓶颈**） |
| P4 调度+复审 | 20–26 h | interval 三层 + **复审队列 UI（web）** + budget 估计 + 标注率闸门 |
| P5 复用+度量 | 12–16 h | 检索浏览（**T6.1**）+ 5 度量面板 |
| P6 上线 | 8–12 h **+ 观察期** | 冷启动导入 ≥60 条 + 引导 + 文档；**观察期是日历时间，不可用工时压缩** |
| **合计** | **94–126 h** | 不含观察期 |

| 每周投入 | 日历工期（不含观察期） | 含观察期 | 备注 |
|---|---|---|---|
| **★ 4 h/周（已选）** | **24–32 周** | **25–33 周** | 每周约 1 次触碰 → **与 P6「每天打开」不可共存** ⇒ **R10 降级判定默认启用**；见 §3.2 现实性警示 |
| 6 h/周 | 16–21 周 | 17–22 周 | 约每周 3 次 × 2h |
| 10 h/周 | 10–13 周 | 11–14 周 | 需每周 5 次触碰，与原 P6 判定相容 |

**缩短工期的唯一真实杠杆**是砍 **P3**（24–32h，最大块且 HITL 串行）；P1/P4 是闭环的地基，砍不得。若想先把闭环跑起来，可把 P3 的「跨源强制 + context 装配」后置到 P5 之后（见 §3.2 裁剪方案）。

### 3.2 ⚠️ 4 h/周 选档的现实性警示与裁剪方案（新增 2026-10-31）

**事实**：4 h/周 ⇒ **24–32 周 ≈ 6–8 个月**，是对「个人工具 MVP」而言非常长的跨度。已登记 §5 **R17**（工期跨度风险）。三个具体失效模式：

1. **决策失忆**：6 个月后回看 §2 决策基线，容易忘记当初为何排除某方案；本文件虽是活 context，但**长期不触碰本身就是风险**。缓解：每次开工先读 §0 + §8（约 5 分钟）。
2. **动力衰减**：P3 是第 4 个 Phase（约第 14–22 周才进入），在此之前**看不到任何"复利"发生**。缓解：**考虑把 P4 提前到 P3 之前**（P4 的外生锚闭环 + 调度信号本身就是差异化的可感知产出，且不依赖 P3 的蒸馏产物——P4 只依赖 P2 的分流结果）。依赖表需相应调整：`P4 依赖 P2`（去掉 P3），`P5 依赖 P3,P4`。
3. **HITL 与低投入的叠加**：P3 的人审是串行瓶颈，每次开工 4h 内可能只推进 1–2 条蒸馏。缓解：P3 内部先做**批量离线蒸馏 + 集中人审**，不要"捕获一条→审一条"。

**裁剪方案（三档，供后续拍板，尚未生效）**：

| 方案 | 砍什么 | 砍后合计 | 折 4h/周 | 代价 | 状态 |
|---|---|---|---|---|---|
| **★ S1 顺序调整（零功能损失）** | 只把 **P4 提到 P3 之前**，其余不动 | 94–126 h（**不变**） | 24–32 周 | 仅改执行顺序；**但"提前看到复利"的收益极大** | ✅ **已生效（zj 拍板 2026-10-31）** |
| S2 后置跨源+装配 | S1 + P3.2 跨源强制、P3.4 context 装配 → 移到 P6 之后 | ≈ 83–111 h | 21–28 周 | 元认知产物缺跨源论证、无 context 装配（R2 降级回 Spike 10 状态） | 未采纳 |
| S3 最小闭环切片 | S1 + S2 + P5 检索降级为「最小列表」 | ≈ 71–95 h | 18–24 周 | P5 只剩度量面板，无法舒适浏览复用产物 | 未采纳 |
| 不裁剪 | 原顺序 P1→P2→P3→P4→P5→P6 | 94–126 h | 24–32 周 | 第 14–22 周才进入 P3 | 未采纳 |

**S1 生效后的执行顺序**：`P0 → P1 → P2 → P4 → P3 → P5 → P6`（编号保留原义供追溯）。
**S1 连带确认**：P4 的「已捕获单程票」（P4.5）**不依赖 P3 的蒸馏产物**——已捕获判定依据 `evidence_refs`（§2 溯源权威）与 `produced_by`，二者在 P1/P2 即可就绪；P3 延后只影响"新产物继续沉淀"，不影响 P4 闭环成立。
**S1 的新增风险**：P4 先于 P3 上线期间，动态条目到期只能走「ARCHIVE / 人工标注」，**蒸馏入口暂缺** → 此窗口内「衰减可控」指标会偏低，属**预期内**，不得据此判定失败（见 §7 衰减可控行）。

---

## 4. 任务拆解（占位，挂 spike + 架构 §）

> 仅列骨架，每项待填：具体子任务 / 负责人 / 工期 / 验收。编号供追溯。
>
> **⚠️ 执行顺序（S1 已生效）**：**P0 → P1 → P2 → P4 → P3 → P5 → P6**。下面清单的**书写顺序不等于执行顺序**（编号保留原义），按上方序列执行。

**P0 文档收口**
- [x] P0.1 架构文档「待 zj 复核」逐条清零或转 risk §5 ✅ **已完成 2026-10-31**：三角审计清单 `docs/plans/ZKC-architecture-v1.2-review-checklist.md`（A 档 12 / B 档 3 / C 档 62）；**zj 已全批 → A 档回填架构（8 处）+ PRD（4 处）、B 档转 R13/R14/R15、C 档整批认可**；架构顶部状态已改为「已复核」
- [x] P0.2 RESEARCH-TOPICS **冻结为历史索引** ✅ **已完成 2026-10-31**：顶部标「🔒 只读 · 已被取代」；§1 状态列改为「处置 + 证据」（已关闭 14 / 关闭带 open 2 / open 转待做 2 / 延后 2 / 转非目标 2）；新增 §1.1 迁移表（T0.2→P2.1、T6.1→P5.1、T2.1→R16、T4.2→R15、T0.3/T2.2 延后、X.1/X.2/X.3 转非目标）；§3 调研顺序标失效
- [x] P0.3 本计划 §2 决策基线 + §5 风险登记册评审签字 —— **P0 唯一剩余项（2026-10-31 已签字闭环）**：zj 通读 §2（22 行）+ §5（19 条：14 活跃 + 5 已解决）后一次性签字即可闭环 P0（✅ 签字；F1–F4 同步修订）
- [x] P0.4 建 `ZJ-CONTEXT.md` 术语表 + `docs/zj-adr/` ✅ **已完成 2026-10-31**：`ZJ-CONTEXT.md`（术语表：双轨/双时态/单程票/饱和日/删失观测/外生锚/活跃日）+ `docs/zj-adr/0001-mvp-delivery-form.md`（本地 web）+ `docs/zj-adr/0002-captured-single-way-ticket.md`（单程票）

**P1 存储地基**
- [x] **P1.0 定死 embedding 编码器（R16 硬前置）** ✅ **已完成 2026-10-31**：`spikes/spike-14-embedding-dim/` 实测 → **`nomic-embed-text` → `vector(768)`**（9.5ms/条、274MB；vs qwen3 4096d 183.2ms/条、4.7GB）；两者均已 L2 归一化。**硬约束**：embedding 仅限检索召回/反向连接候选，**严禁用于安全判定**（spike 03 实测 nomic dangerous=3，该职责归 DecisionRouter）。R16 已解决，新增 R18（中文召回质量未实测）
- [x] **P1.4 阈值收敛（阈值表部分）** ✅ **已完成 2026-10-31**：新建 `zkc/tuning.py`（`Parameter{value, source, calibrated_at, history}`；`source ∈ {placeholder, simulation, calibrated}`）+ `tests/test_tuning.py`（**17 tests passed**）。**共 29 个参数**（16 `placeholder` / 11 `simulation` / 2 `calibrated`；增量 = P2.2 DecisionRouter 的 4 个 `ROUTING_*`，embedding 已在早期 25 内）：decay(3) / interval 基线(4+2 钳制) / L2 预算(3) / L3 AIMD(3) / 标注率闸门(3) / 校准门禁(2) / F_cap(1) / embedding(2)；`can_calibrate` 门禁（≥14 天埋点且 ≥3 饱和日）实测拒绝无数据改数并留痕。**⚠️ 澄清**：旧 spike 目录**不回改**（它们是时间胶囊式的验证证据），"统一 5 处 `ROT_THRESHOLD`"= 新代码统一走 `tuning.get()`，不是改 spike
- [x] **P1.1 迁移脚本 D1–D9** ✅ **已完成 2026-10-31**（`migrations/0001_baseline_d1_d9.up.sql` + `.down.sql` + `zkc/migrate.py` + `tests/test_migrate.py`，**11 tests passed**）
  - **⚠️ 实施偏差（按 §0 铁律 2 留痕）**：**Alembic → 自研零依赖迁移器**。旧值 = Alembic（原计划措辞）；新值 = `docker exec psql` + 版本表 `schema_migration` + sha256 留痕。**触发条件**：①架构不变量「依赖最少」；②迁移只需「按序执行 SQL + 记录版本」，不需要 ORM/autogenerate。**代价**：无 autogenerate，schema 靠手工维护（本阶段反而更可控，schema 源自 spike 证据）。已用 `verify` 子命令补上「改历史迁移必被抓到」的闸门。
  - **修正的三处 drift**（相对遗留 `zkc` 库）：① `node.embedding` **1024 → 768**（R16/spike 14）；② `meta_claim` **补 D9 六个 faithfulness 字段**；③ `context` **去掉已弃用的 `member_nodes uuid[]`**（D2 已由 `context_member` 取代）。
  - **验证**：upgrade / downgrade **完整重放通过**；幂等（重复 upgrade 为空操作）；schema 级不变量实测被拒（无 `evidence_refs` 的 claim、`decay_score` 越界、`labeled_completed > completed` 三者均报错）。
  - **产物库**：`zkc_dev`（已建并处于 `0001 applied`，`sha=824880c46260`）；实测 **12 张表**（11 张领域表 + `schema_migration`）、`node.embedding = vector(768)`；遗留库 `zkc` **原地保留**作 spike 时间胶囊、不回改。
  - **用法速查**：`python -m zkc.migrate {status|upgrade|downgrade|verify} [--db zkc_dev] [--to 0001]`
- [x] **P1.2 repository seam 抽象（保持 Kuzu/TerminusDB 可替换）** ✅ **已完成 2026-10-31**（roadmap 1-2-5）：`zkc/repository/`（`models`/`protocols`/`memory`/`pg`/`connection`/`__init__` 工厂 `get_storage`，`ZKC_STORAGE=pg|memory`）；`tests/test_repository.py` 用同一份行为契约同时跑内存 fake 与真实 PG（建 `zkc_repo_test` 库跑 0001），双实现一致；**前置已验证**：`psycopg[binary]` 可装（走代理）且已连通 `zkc_dev`
- [x] **P1.3 双时态 + decay 触发器（线性）实测（Spike 01）** ✅ **已完成 2026-10-31**：新建 `zkc/decay.py`（纯函数线性衰减模型 + `refresh_decay` 应用层维护扫描；阈值走 `tuning.get`）；`pg.list_due_for_review` 与 `memory.list_due_for_review` 的硬编码 `0.6` 改为 `tuning.get('SURFACE_THRESHOLD')`；`tests/test_decay.py`（9 纯单测）+ `tests/test_decay_pg.py`（3 真实 PG 集成实测：refresh 写回线性分 / append-only 双时态版本链不破 / 到期+超阈入选）；全仓 99 tests passed。双时态已在 0002 迁移 + `pg.save/_locked_snapshot` 落地
- [x] **P1.4 剩余（阈值治理收口）** ✅ **已完成 2026-10-31**：① 审计 zkc/ 全部业务代码，`pg/memory.list_due_for_review` 裸 `0.6` 已替换为 `tuning.get('SURFACE_THRESHOLD')`；`routing.py` 的 LLM/词法门槛早已走 `tuning.get`，无裸阈值残留；② `zkc/web/app.py` 新增 `GET /tuning` 端点，返回全部 29 个参数及 `source` 标签（`tuning.as_rows()`），UI/日志展示阈值须带来源铁律落地
- [x] **P1.5 决定是否回迁 Alembic（R19）** ✅ **已完成 2026-10-31（收口 = 不回迁）**：判定 = P1.2 走「raw SQL + repository seam」（psycopg 裸 SQL，**未引入 SQLAlchemy ORM 模型层**）→ R19 回迁触发条件**未满足**，维持自研 `zkc/migrate.py`。最终依据（替换已作废的「pip 装不上」理由）：① 触发条件未满足；② 第一性不变量「依赖最少」；③ 11 tests 跑通 + sha256 留痕 + `verify` 闸门拦「改历史迁移」。代价（无 autogenerate）本阶段可接受。**锁方向 guard 测试 = `tests/test_r19_guard.py`**（断言 zkc/ 无 SQLAlchemy/Alembic import、requirements 不含两者、迁移权威=zkc.migrate）；未来 P1.2 演进为 ORM 时该测试变红，自动触发 R19 重开。回迁窗口已关闭。

**P2 摄入+分流**
- [x] P2.1 快捕获 UX（本地优先离线）（T0.2）
- [ ] P2.2 DecisionRouter 接入 + 双信号弃权 + 人工兜底 + routing_confidence（Spike 02/03）
- [ ] P2.3 分流 → review_queue 写入联调

**P3 复利变换**
- [ ] P3.1 蒸馏算子：Ollama 4B + Instructor + LangGraph HITL + checkpoint 落 PG（Spike 04/10）
- [ ] P3.2 跨源强制算子（≥2 断言 + 补全回路）（Spike 11）
- [ ] P3.3 结合算子 RCS 漏斗 + 引用强制 + 级联撤销（Spike 05）
- [ ] P3.4 context 拓扑装配 + produced_by 级联撤销（Spike 06）
- [ ] P3.5 **忠实度闸门降级链第 2 级**：字面 rubric 预过滤 + 人工兜底（Spike 12/13/13b；自动 LLM judge 本机否决）

**P4 调度+复审闭环**
- [ ] P4.1 review_interval 三层(L1/L2/L3 AIMD)（Spike 09 §6.5）
- [ ] P4.2 每日复审队列 UI（MVP 必选，PRD §6 流 C / 目标 5）
- [ ] P4.3 budget_per_day 统计估计（删失感知+单调护栏+EMA+oversubscribe）（Spike 09 §6.5.1）
- [ ] P4.4 标注率闸门（滚动 7 天 ≥70% → 否则 L3 停机）（Spike 09 切片 B）
- [ ] P4.5 **已捕获条目「单程票」规则**（已拍板，见 §2 / ADR-0002）：① 已捕获 → `baseline_interval=28d` → 到期（`decay≥0.9`）直接 `ARCHIVE`、**永不进 DISTILL**；② **边界 1**——`produced_by` 级联撤销导致「已捕获」状态消失时，按未捕获基线重算（有连接 14d / 孤儿 7d）并**写 D7 `interval_adjustment` 留痕**，禁止静默变；③ **边界 2**——L1 顺序改为 `self_loop(3d)` 压过 `已捕获(28d)`（原 L1 表与 L2 优先级表顺序相反，已修）

**P5 复用+度量**
- [ ] P5.1 复利产出检索/浏览（**T6.1，原无 spike 覆盖，由 P0.2 收口转为显式待做**）
- [ ] P5.2 5 度量面板（连接密度/复用率/方法论产出/衰减可控/复利系数）（Spike 07）
- [ ] P5.3 **度量 operationalize**（§7 全 `[TODO(zj)]` → 待 R2-5 拍板判定者/节奏/复利系数权重）

**P6 上线**
- [ ] P6.1 **明确不做**打包/签名/对外分发（ADR-0001，§1.2）；只保证「本机可启动」+ README 启动脚本
- [ ] P6.2 真实数据冷启动引导（导入 ≥60 条动态型素材）
- [ ] P6.3 用户文档 + 度量复盘节奏（见 §7）
- [ ] P6.4 达成 **累计 ≥20 个带标注复审动作**（R10 降级判定口径）+ 标注率 ≥70%

---

## 5. 风险登记册与降级链

> 来源：架构 §8 风险与未决 + 各 spike 的 open/限定项。**不得静默当成已解决**；每条带降级预案。

| ID | 风险 | 来源 | 影响 | 降级预案 | 状态 |
|---|---|---|---|---|---|
| R1 | 忠实度/幻觉**自动判定本机不可用**（4B/9B 速度+格式死） | Spike 12/13/13b | 自动质量闸门失效 | **MVP = human-in-the-loop + 字面 rubric 预过滤**；`judge.py`/`run_spike12.py` 零改动可启用（待可用判定模型）；真实危险漏检率/阈值校准 open | open |
| R2 | 跨源综合薄弱（原 Spike 10 缺口） | Spike 10/11 | 元认知产物缺跨源论证 | **算子层硬约束**已解（4B×3 稳定 3/3）；1.5B 无溢出→4B 默认；≥2 跨源断言强制 | 已缓解 |
| R3 | 分流**单向偏差污染生命周期**（错判一律沉动态轨→decay→耗注意力） | Spike 02 限定 | 噪声累积、注意力被吞 | DecisionRouter + 双信号弃权 + `routing_confidence` + 周期重分类（真编码器复核确认必要） | 已缓解 |
| R4 | **注意力预算不足 → 腐化无解**（rot=100%） | Spike 01/09 | 到期条目全腐化 | 上线前按 `n/(0.6×interval)` 反推校验；不足则调大 interval 或减动态集；`infeasible` 显式报告，不静默拉长 | open(需上线前校验) |
| R5 | **L3 必须接复审结果标注**，否则 decay-only 反馈恒 no-op | Spike 09 限定 | interval 永不修正 | **每日复审队列 UI 是硬前提**（PRD 目标 5）；未标注复审禁止写 interval 调整 | 依赖 P4.2 |
| R6 | budget/振荡带/ARCHIVE-vs-28d 规则未统一，阈值全占位 | Spike 09 | 调度精度漂移 | **规则已统一（P4.5 单程票，2026-10-31 拍板）；阈值已冻结进 `zkc/tuning.py` + 来源标签（P1.4）**；校准门禁 = 连续 14 天埋点且 ≥3 饱和日；校准期 oversubscribe×1.5 防低估固化 | 缓解中（校准值仍 open） |
| R7 | **16GB 硬件约束**（9B swap） | Spike 10 | 蒸馏延迟 4.7min/条 | 4B 默认；9B 仅可选上限 | 已缓解 |
| R8 | LangGraph/Semantic Router 破坏性变更 | 架构 §8 | 编排回归 | 锁版本 + 路由回归测试 | 缓解中 |
| R9 | ~~**文档债务**~~（RESEARCH-TOPICS 状态全「待调研」、架构顶部「待 zj 复核」） | 本计划 Phase 0 | ~~基线混乱、决策失配~~ | **P0.1 已完成**：架构转逐条复核清单，A 档 12 项已回填架构+PRD、B 档 3 项转 R13/R14/R15、C 档 62 项整批认可。**P0.2 已完成（2026-10-31）**：RESEARCH-TOPICS 冻结为只读索引 + open 项迁入本计划（见 §1.1 迁移表） | 已解决 |
| R10 | **外生锚供给风险**：P6 上线判定原要求 zj 连续 ≥7 个活跃日每天使用，做不到则 budget 停在 warm-up、L3 无样本，P6 永远判不了 | 本次拍板（§1.2） | MVP 核心命题（复利可观测）无法被证明 | **降级判定已定为该风险的默认处置（2026-10-31，因 4 h/周 选档，不再等触发条件）**：上线判定 = **累计 ≥20 个带标注的复审动作**（不要求连续活跃日 / 不要求日历连续），标注率 ≥70% 仍为硬门槛；「≥7 活跃日」降为可选加强档。**残余风险**：若连 20 个动作都攒不出来，则外生锚仍不产生 → 需再降级到「人工显式 verdict 驱动 L3」（标注率闸门不受此限） | 缓解中（判定口径已改；样本产出仍待观察） |
| R17 | **工期跨度风险**：4 h/周 ⇒ 24–32 周（6–8 个月）才到 P6 | zj 选档 2026-10-31（§3.1） | 决策失忆（长期不触碰本文件）、动力衰减（第 14–22 周才进入 P3，此前看不到复利）、HITL 与低投入叠加（4h 可能只推进 1–2 条蒸馏） | 三条缓解：① 每次开工先读 §0 + §8（约 5 min）；② **建议 P4 提前到 P3 之前**（P4 只依赖 P2，其外生锚闭环+调度信号本身即可感知，见 §3.2 S1）；③ P3 内部改为**批量离线蒸馏 + 集中人审**，不做「一条一审」。**进一步裁剪方案 S2/S3 见 §3.2（尚未生效，待拍）** | open |
| R11 | ~~蒸馏 HITL 人审预算与复审预算冲突~~ —— **已定：两套独立预算** | zj 拍板 2026-10-31（R2-3） | ~~蒸馏人审被封死~~ | **蒸馏人审与复审预算分离计量**（性质不同：维持 vs 生产），各有独立埋点与封顶，不互相挤压；`F_cap` 只对蒸馏人审侧生效 | 已解决 |
| R13 | **9B 可用性结论未实测完整**：`qwen3.5:9b` 的 **GGUF 6.55GB + `num_ctx 8192` 常驻**未实测（架构:243 / spike-10:101,63） | 审计 B1 | 若常驻显著低于 mlx 8.9GB，「9B 在 16GB 不可用于迭代」的结论可能松动 → 选型可能无需那么保守 | P3 前上机实测一次（不阻塞：4B 已是默认，9B 仅可选上限） | open |
| R14 | **补全回路的延迟成本未入预算**：跨源补全在主生成不达标时 **+1× LLM 调用**（spike-11:92） | 审计 B2 | MVP 延迟预算失真；「0/3 触发」只是 4B 样本，换语料后触发率未知 | P3 实现时埋点记录**补全触发率与额外延迟**；超预算则关闭补全回路（退回主生成质量） | open |
| R15 | **`context_member` 写放大未压测**：junction 表在高频重算下的写入成本未知（spike-06:65） | 审计 B3 | 装配频繁时写放大可能成为瓶颈 | **先按「查询时计算」的动态视图实现**（规避写放大），压测后再决定是否物化为 junction 表 | open |
| R16 | ~~**embedding 编码器未最终确定**~~ | 审计 A6 | ~~换编码器 = 重建索引~~ | **已定死（2026-10-31，spike 14 实测）**：**`nomic-embed-text` → `vector(768)`**。实测 768d / 9.5ms/条 / 274MB vs qwen3 4096d / 183.2ms/条 / 4.7GB（延迟 19.3×、体积 17×）；两者均已 L2 归一化。**硬约束**：embedding **仅限检索召回/反向连接候选，严禁用于安全判定**（spike 03 实测 nomic 在相似度阈值判定下 dangerous=3，该职责归 DecisionRouter）。**可逆路径**：加列 `embedding_strong vector(4096)` 属增量，不重建 768d 索引 | 已解决 |
| R18 | **中文检索召回质量未实测**：spike 14 只测维度/延迟/归一化，**未评估召回质量**；nomic 中文语义弱于 qwen3 是合理预期但无证据 | spike 14 限定 | P5 检索/反向连接候选不准 → 反向连接发现率下降 | P5 用**真实语料**验证召回；不合格则走 R16 的可逆路径（加列 `embedding_strong vector(4096)`）；MVP 检索以结构化查询（track/decay/topic/context）为主，embedding 只做候选召回 + 人确认，降低对该风险的暴露 | open |
| R12 | ~~7 个无 spike 覆盖的 topic 转为待做~~（T0.2/T0.3/T2.2/T6.1/X.1/X.2/X.3），原计划工期未计入 | P0.2 收口 | ~~工期被低估~~ | T0.2→P2.1、T6.1→P5.1 已挂并计入工期；T0.3/T2.2 延后到 P6 之后；**X.1 并入不变量 5 不单列、X.2/X.3 转非目标**（均已写入 §1.3，R2-5 拍板） | 已解决 |
| R19 | ~~**迁移器选型理由部分作废，是否回迁 Alembic 重新 open**~~：`zkc/migrate.py` 当时的首要理由「本机 pip 装不上 alembic/psycopg（沙箱网络）」**已于 2026-10-31 被推翻**留痕（走 Clash 代理后 `instructor 1.17.0`、`psycopg[binary]` 均可装，见 §8.3）——此为过时理由留痕，**不再是选型依据** | P1.5 收口（2026-10-31） | 若日后 schema 演进频繁，缺 autogenerate 会让 schema 维护成本上升（`verify` 只能拦「改历史迁移」，不能自动 diff 模型） | **最终处置（2026-10-31 收口）：不回迁 Alembic，维持自研 `zkc/migrate.py`**。判定依据 = R19 触发条件：P1.2 走「raw SQL + repository seam」（psycopg 裸 SQL，**未引入 SQLAlchemy ORM 模型层**）→ 回迁触发条件**未满足**；叠加第一性不变量「依赖最少」+ 11 tests 跑通 + sha256 留痕 + `verify` 闸门。**锁方向 guard 测试 = `tests/test_r19_guard.py`**（断言 zkc/ 无 SQLAlchemy/Alembic import、requirements 不含两者、迁移权威 = zkc.migrate）；日后 P1.2 演进为 ORM 时该测试变红 → 自动触发 R19 重开。若未来确需 SQLAlchemy ORM，则重新 open 并同步回迁 | 已解决 |

---

## 6. 验收标准与上线闸门（Definition of Done）

**硬门槛（任一不满足不得上线）**：
- [ ] **标注率 ≥70%**（滚动 7 天 `labeled_completed/completed`；样本<10 放行不计，见 Spike 09 切片 B）
- [ ] **衰减可控**：到期动态节点在 ROT=0.9 前被引用或归档占比达标，且**先满足注意力预算** `n/(0.6×interval)`（否则该指标恒 0）
- [ ] **e2e 闭环跑通**：捕获→蒸馏→调度→复审→复用→度量，单条数据全链路无断点
- [ ] **5 度量出数**（连接密度/复用率/方法论产出/衰减可控/复利系数，PRD §7）
- [ ] **架构文档「待 zj 复核」清零** ✅（复核清单 A/B 档批完并回填）、风险登记册 **R1/R4/R6/R9/R10/R12/R13/R14/R15/R16/R17/R18/R19** 有显式处置（**R19 已于 P1.5 收口 = 不回迁，对应 guard 测试 `tests/test_r19_guard.py` 锁方向**）；**上线前仍 open 且需关掉的**：R1（自动判定）、R4（预算校验）、R13、R14、R15、R18

**上线判定（P6）**：zj 本人用**导入的真实历史素材**跑通 e2e 闭环，达成 **累计 ≥20 个带标注的复审动作**（**R10 降级判定已默认启用**，2026-10-31；原「≥7 个活跃日」降为可选加强档，见 §1.2），上述门槛持续达标。**不要求第二人可安装**（对外分发不属 MVP，见 §1.2）。

---

## 7. 度量与复盘（operationalize PRD §7）

> PRD §7 已定义 5 指标与质量口径，但**未 operationalize**（用什么数据、谁判、何时判）。此处落地。

| 指标 | 数据来源 | 判定者 | 复盘节奏 | 状态 |
|---|---|---|---|---|
| 连接密度 | `reverse_link`/`derived_from` 边 | **自动** | 每周 | ✅ 已定（等权合成，无独立目标值） |
| 复用率 | `citation` 表（**不参与「已捕获」判定**，见 §2 溯源权威） | **自动** | 每周 | ✅ 已定 |
| 方法论产出 | `combine` transform 计数 | **自动** | 每周 | ✅ 已定；`method_target` 标占位待校准 |
| 衰减可控 | 到期节点 `evidence_refs`/`archived_at` | **自动 + 预算校验** | 每周 | ✅ 已定；恒 0 时先查预算 `n/(0.6×interval)` 而非查指标 |
| 复利系数 | 4 指标归一加权 | **自动** | 每周 | ✅ 已定：**等权 0.25 起步，标 `source=placeholder`**（真实数据后可校准） |
| 蒸馏质量口径 | 复述率/overlap/跨源率/引用命中/结构完整 | **自动 rubric**（字面层）+ **人工抽审**（忠实度，HITL） | 每蒸馏批次 | ✅ 已定；**抽审比例受蒸馏人审独立预算封顶**（§2，R11） |

复盘节奏建议：每周一次，输入 = 5 度量 + 标注率 + 腐化率；输出 = 阈值校准提案 + 风险登记册更新。

---

## 8. 实施上下文速查（极易 miss 的硬约束）

> 这一节是「实施时最容易漏掉、却会直接决定成败」的底层约束合集。它不是决策，而是决策的**承重墙**。每次开工前扫一遍。

### 8.1 第一性不变量（任何变更的判定基准，引架构 §3）
1. **两类信息原生双轨建模**：生命周期与操作语义分离，不在同一张"笔记表"混同。
2. **ZKC 拥有三项核心语义**（任何候选都不提供，必须自建）：双轨标签定义、decay 衰减模型、稀缺注意力调度。
3. **存储是可替换 seam**：不是架构中心；变换语义与调度策略属于 ZKC 自己。
4. **所有变换产物必须可溯源**（回溯到来源条目），否则无法复用、无法复利。
5. **默认本地/离线优先**：个人数据 + 隐私；云端只作可切换 provider。

### 8.2 术语护栏（防混用，错用即架构偏移）
- **双轨(dual-track) ≠ 双时态(bitemporal)**：双轨 = 静态/动态类型 + 生命周期分流（衰减率与注意力成本）；双时态 = valid time + transaction time 的溯源建模（事实演进 + 审计）。Utopia 的 bitemporal 只覆盖 ZKC「静态轨事实可更新」一半，**完全不覆盖动态轨腐化与注意力稀缺**——这是 ZKC 的差异化核心，引入 bitemporal 不等于解决了双轨。
- **衰减 ≠ 衰减可控**：前者是时间函数；后者是「到期前被处理（蒸馏/归档）」的可观测度量。

### 8.3 环境与硬件约束（本机 16GB，极易 miss）
- **Postgres 不是本机裸装，是 docker 容器**：容器名 **`zkc-spike-pg`**，镜像 `pgvector/pgvector:pg16`，宿主端口 **55433** → 5432。实测 PostgreSQL **16.15**、pgvector **0.8.7**。
  - 连接沿用 spike 01 的口径，不要新造：`docker exec -i zkc-spike-pg psql -U postgres -d zkc -v ON_ERROR_STOP=1 -tA -f -`
  - **应用代码 DSN**（spike 09 口径）：`postgresql://postgres:zkc@localhost:55433/zkc_dev`（密码 `zkc`）。已实测 psycopg 连通。
  - **⚠️ `zkc/migrate.py` 不读 DSN，读三个环境变量**（对账 2026-10-31 修正：此前误记为 `ZKC_PG_DSN`，**该变量不存在**）：`ZKC_PG_CONTAINER`（默认 `zkc-spike-pg`）、`ZKC_PG_USER`（默认 `postgres`）、`ZKC_PG_DB`（默认 `zkc_dev`）。它经 `docker exec psql` 执行，**不需要 Python DB 驱动**。
  - 遗留库 `zkc` = 14 个 spike 累积的**手工 schema**（15 表，`node` 0 行）→ **保留作时间胶囊，不回改**；新库 **`zkc_dev`** 由 `zkc/migrate.py` 从零建（实测 12 表 / `0001 applied` / 可 up+down 重放）。
  - ⚠️ 容器状态可被 docker 重启丢掉 → **任何 schema 变更必须进 `migrations/`，禁止手工建表**。
- **⚠️ pip 必须走 Clash 代理，否则「装不上」是假象**：`python -m pip install --proxy http://127.0.0.1:7890 <pkg>`。不走代理时报 `from versions: none / No matching distribution found`，**看起来像「这个包不存在/沙箱禁网」，实为没配代理**。已实测装上 `instructor 1.17.0`、`psycopg[binary]`。**更正**：此前「semantic-router 装不上（沙箱网络）」以及据此写进 `zkc/migrate.py` docstring 的「本机 pip 无法访问 PyPI」**均已过时**——那是没走代理，不是装不上（连带影响见 §5 R19）。
- **蒸馏模型默认 `qwen3.5:4b-mlx`**（3.97GB）；`9b-mlx` 仅可选上限——9B 在 16GB 常驻 10–12GB、触发 swap、单次蒸馏 ~4.7min，不可用做日常迭代。
- **Ollama 代理**：直连 registry 会 DNS 超时；需 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7890`（Clash）。本地 `localhost:11434` 必须 `NO_PROXY=localhost,127.0.0.1` 绕过，否则 httpx 把本地也走代理 → 无限挂起。
- **`num_ctx` 必须显式限制**：未限制时 9B GGUF 常驻 15GB、swap 用满 20GB+；限 `8192` 后空闲 9%→69%。控制上下文是 16GB 跑 9B 的前提。
- **忠实度自动判定本机否决**：4B 经 Ollama 不输出 JSON（~110–130s/条且格式错）；9B ~6min/条且同样不合规。→ MVP 忠实度闸门 = human-in-the-loop + 字面 rubric 预过滤；`judge.py`/`run_spike12.py` 零改动可启用（待更快硬件/离盒/云端 opt-in）。

### 8.4 工具与 git 铁律（本环境特有，踩过多次）
- **git 提交后必跑 `git ls-tree -r HEAD --name-only | wc -l` 校验树文件数**（应≈全仓 tracked 数）；异常立即用「删 index/index.lock → 同命令内 `git add <完整路径>` + `git commit`」重暂存（拆分命令会导致空树塌缩）。feat/docs 分离提交在本环境不可行，只能单提交保全树。
- **safe-delete shim 会执行 `rm -rf` 致 git 损坏**；涉及 workspace 文件落盘/备份/还原一律用 Read/Edit/Write，勿用 Bash `cp/git checkout/stash` 来回倒。
- **Bash 默认超时 120s**：长命令（全量测试/安装/构建）显式给 timeout 或拆多条；被 SIGTERM(137) 看似失败实为超时。
- **zsh 单词分割坑**：`for n in $VAR` 不按空格分词（bash 才分）；批量多目标用 Python 或 zsh 数组 `${=VAR}`。
- **sandbox-center 拦截 `VAR=value &&` 链式赋值**与向 workspace 写文件；遇阻用 `env` 前缀或 Python 脚本。
- **Grep 工具静默跳过隐藏目录**（`.github/`/`.claude/` 等）；「全仓零命中」类否定结论必须换工具链（`git ls-files`/Read）交叉验证。

### 8.5 spike 限定外推红线（禁止静默当成已解决）
- **单次采样结论不可信**：同一臂两次跑跨源率可 0.0↔1.0；任何质量对比须基于多次采样分布。
- **比率指标可被「少发 claim」刷高**：rubric 必须同时要求绝对数量（≥2 条跨源 claim）。
- **幻觉/忠实度无法用字面方法测**：抽象 claim 本就该用源文本没有的词，字面重叠无法区分「好抽象」与「无据编造」。
- **跨源综合原不达标（Spike 10）**：已由 Spike 11 算子层解（4B×3 稳定 3/3），但 1.5B 无溢出收益 → 能力下限由模型结构化能力决定。
- **L3 复审反馈必须接显式结果标注**：decay-only 反馈恒为 no-op，永不修正基线（Spike 09 实测）。

---

## 9. 与现有文档的衔接图（文字版）

```
PRD v0.2 (做什么)
   └─§3 目标/非目标 → 本计划 §1 范围
   └─§7 成功度量   → 本计划 §6 闸门 / §7 度量
架构 v1.2 (怎么做/选型)
   └─证据表 spike01-14 → 本计划 §2 决策基线 / §4 任务挂接
   └─§5 D1-D9 schema   → 本计划 P1 迁移 / migrations/0001（已落地）
   └─§6.5/§6.5.1 调度  → 本计划 P4
   └─§7 延后项         → 本计划 §1.3 不在范围
   └─§8 风险未决       → 本计划 §5 风险登记册
RESEARCH-TOPICS (22 topic) → 冻结为只读索引，open 项迁入架构 §9 + 本计划 §5
spikes/ (15, passed)       → 每个 Phase 任务的验证证据与时间胶囊
代码资产 (zkc/ migrations/ tests/) → 本计划 §10
```

---

## 10. 代码资产现状（对账 2026-10-31）

> 本节回答「**代码现在到哪了、怎么跑**」。每次推进后同步；与文档不一致时**以代码为准并回写本节**。

### 10.1 目录与文件

| 路径 | 作用 | 状态 |
|---|---|---|
| `zkc/__init__.py` | 应用包入口（声明 MVP 形态 + 阈值唯一来源） | ✅ |
| `zkc/tuning.py` | **阈值唯一权威来源**：29 个参数 × `{value, source, calibrated_at, history}`；`can_calibrate()` 门禁；`Parameter.set()` 强制留痕 | ✅ 17 tests |
| `zkc/decay.py` | **衰减模型（P1.3）**：纯函数线性衰减 `decay_linear` + `compute_decay_score`（静态轨恒 0）+ `surface` + `refresh_decay` 应用层维护扫描；阈值全走 `tuning.get` | ✅ 9 纯单测 + 3 PG 集成 |
| `zkc/migrate.py` | 零依赖 schema 迁移器：`status / upgrade / downgrade / verify`；单事务 + sha256 留痕 | ✅ 11 tests |
| `zkc/web/app.py` | FastAPI 本地捕获层；新增 `GET /tuning` 端点（P1.4 ②：展示全部参数及 `source` 标签） | ✅ |
| `migrations/0001_baseline_d1_d9.up.sql` | 基线全量 DDL：11 张领域表 + 枚举 + 索引 + FK（D1–D9） | ✅ applied |
| `migrations/0001_baseline_d1_d9.down.sql` | 逆序回滚 | ✅ |
| `tests/test_tuning.py` | 阈值表单测（17） | ✅ |
| `tests/test_migrate.py` | 迁移集成测试，**打真实 docker 容器**（11） | ✅ |
| `spikes/spike-14-embedding-dim/` | `probe_dim.py` + `probe_result.json` + README（R16 实测证据） | ✅ |
| `ZJ-CONTEXT.md` / `docs/zj-adr/0001` `/0002` | 术语表 + 两份 ADR | ✅ |

### 10.2 常用命令

```bash
# 全量测试（28 tests）
python -m unittest discover -s tests

# 迁移
python -m zkc.migrate status    --db zkc_dev
python -m zkc.migrate upgrade   --db zkc_dev
python -m zkc.migrate downgrade --db zkc_dev --to 0001
python -m zkc.migrate verify    --db zkc_dev   # 拦「改历史迁移」

# 阈值表（业务代码禁止裸数字）
python -c "from zkc import tuning; print(tuning.get('ROT_THRESHOLD'))"
```

### 10.3 已知缺口（代码侧）

1. **无 pyproject / 无 venv / 无依赖清单**：依赖靠本机全局 Python + 走代理 `pip install`。P1.2 引入 seam 时应补一份最小 `requirements.txt`（目前只有 `psycopg[binary]`、`instructor` 是必须显式装的）。
2. **`zkc_dev` 无种子数据**：11 张领域表全空；P6 前需导入 ≥60 条真实动态型素材（§1.2）。
3. **repository seam 尚未建立**：目前唯一访问路径是 `zkc/migrate.py` 的 `docker exec psql`，业务代码还没有数据访问层（P1.2）。
4. **`migrate.py` docstring 含一条已作废的理由**（「pip 无法访问 PyPI」），保留仅为留痕，实际选型理由见 §2「schema 迁移方式」与 §5 R19。

---

## 11. 架构 v1.2 逐条复核清单（外移文档）

> 按 §0 铁律 7（内容超一屏即外移），清单本体不在本文件，见：
> **`docs/plans/ZKC-architecture-v1.2-review-checklist.md`**
>
> 口径：三角对账（架构 v1.2 全文 / 14 个 spike README / PRD v0.2），逐条带行号证据。
> **A 档 12 项 = 需修订**（已给可直接替换的新措辞）；**B 档 3 项 = 转 risk**；**C 档 62 项 = 已验证·建议整批认可**。
> **状态（2026-10-31 更新）：zj 已全批 A + B 档，C 档整批认可。A 档 12 项已回填架构（8 处）与 PRD（4 处）；B 档 3 项已转 §5 R13/R14/R15。本清单转为只读审计留痕。**
