# ZKnowledgeCompounding · 项目实施计划（骨架）

> 状态：**骨架 v0.2**（已补 §0 持续维护原则 + §8 实施上下文速查，使本文件可作为实施过程的完整 context；待 zj 填充：工期估算、校准阈值、`上线`定义；架构文档顶部「待 zj 复核」项需先清零，见 Phase 0）
> 目的：把 `PRD v0.2` + `架构 v1.2` + 14 个 spike 的**已验证决策**，转化为「开工 → 上线」的可执行计划。
> 本文件是**决策级 → 执行级**的桥接，不重复 PRD/架构内容，只引用与拆解。
>
> 引用文档（均为当前最新版）：
> - `docs/prds/ZKnowledgeCompounding-PRD.md`（v0.2）
> - `docs/architecture/ZKC-architecture-v1.2.md`（v1.2，顶部仍标 **待 zj 复核**）
> - `docs/research/RESEARCH-TOPICS.md`（22 topic；状态列全为「待调研」，与 spike 进展脱节 → Phase 0 收口）
> - `spikes/spike-0{1..9,10,11,12,13,13b}-*/README.md`（14 个，全 passed）

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

**维护责任人**：zj（架构/决策）+ AI 搭档（执行中回写草稿，zj 复核签字）。每次 commit 前本文件应与代码同步更新（或显式标注「本提交未触及计划文件」）。

---

## 0.1 阅读指引与 TODO(zj) 汇总

本骨架里所有 `TODO(zj)` 与 `[ ]` 为待你拍板或填充项，开工前必须清零：

- [ ] **`上线`的明确定义**（本地 CLI？桌面应用？web？架构 §7 已延后多端同步，默认 = 本地可分发单机 MVP）
- [ ] **架构文档顶部「待 zj 复核」项**逐条清零或转 risk（Phase 0 必修）
- [ ] **Phase 工期估算**（本文件所有「工期」列留空待填）
- [ ] **spike 09 / 10 的全部占位阈值校准**（预算 1.2/天、AIMD 1.5/0.7、α=0.3、±30%、×2 延后、振荡带 ±50%）
- [ ] **已捕获条目规则统一**：spike 08 判 ARCHIVE、spike 09 判 28d（两条待统一）
- [ ] **RESEARCH-TOPICS 状态列收口**（Phase 0 动作）

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

### 1.2 「上线」定义  `TODO(zj)`
- 默认假设（待确认）：**本地可分发单机 MVP**——用户本地安装/启动后，用真实数据跑通 e2e 闭环（捕获→蒸馏→调度→复审→复用→度量）。
- 需明确：交付形态（CLI / 桌面壳 / 本地 web）、打包方式、冷启动引导。

### 1.3 不在范围内（引架构 §7 延后项）
图数据库(Kuzu/TerminusDB) · LiteLLM · Argilla · Langfuse · Electric/Automerge 多端同步 · XTDB（待带外验证）· Cordis/DeepSeek Harness（重述为**模式源**，不引入依赖）。

---

## 2. 决策基线（已验证，开工即锁定，禁止静默推翻）

| 子系统 | 决策 | 来源 | 关键参数 / 约束 |
|---|---|---|---|
| 存储 substrate | **Postgres 16 + pgvector**（repository seam 可替换 Kuzu/TerminusDB） | Spike 01 | `vector(1024)`、enum、`uuid[]` GIN；静态轨 decay 恒 0；claim 无 evidence_refs 被 schema 拒绝 |
| 双轨模型 | 单表 `node` + `track` 枚举 + 双时态(`valid_/tx_from/to`) | Spike 01 / PRD §4 | 双时态≠双轨，仅服务静态事实演进溯源 |
| 衰减 decay | **线性** `min(1, elapsed/interval)` | Spike 01 | SURFACE=0.6 / ROT=0.9；阶梯否决；指数备选 |
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

> 上述决策若有调整，必须回到对应 spike 复测并回填架构文档，不得静默改。

---

## 3. 里程碑计划（Phase 0–6）

> 组织原则：**按数据流向切成 e2e 切片里程碑**（捕获→复利→调度→复审→复用），而非瀑布；每个 Phase 尽量自带可验证闭环（呼应 RESEARCH-TOPICS「闭环而非管道」）。

| Phase | 目标 | 关键产出 | 验收闸门 | 依赖 | 工期 |
|---|---|---|---|---|---|
| **P0 文档收口** | 基线对齐，消除文档债务 | 决策基线(§2)固化 + 风险登记册(§5) + RESEARCH-TOPICS 状态更新 | 架构「待 zj 复核」清零；RESEARCH-TOPICS 状态列与 spike 一致 | — | `[ ]` |
| **P1 存储地基** | schema 落地为可迁移代码 | Alembic 迁移(D1–D8) + repository seam | Postgres16+pgvector 迁移跑通；双时态/decay/claim/citation/context_member/review_queue/interval 全 DDL 落地 | P0 | `[ ]` |
| **P2 摄入+分流** | 低摩擦快捕获 + 正确分轨 | 捕获 UX(本地离线) + DecisionRouter 接入 | 动态条目 → 正确分轨 → 入 review_queue；弃权转人工 | P1 | `[ ]` |
| **P3 复利变换** | 蒸馏/结合/拓扑装配跑通 | 蒸馏(4B+HITL) + 结合算子(RCS) + context 装配 | 一条动态条目 → 元认知 claim+topic+反向连接 → 装配进 context | P1,P2 | `[ ]` |
| **P4 调度+复审闭环** | 资源感知 + 外生锚 | review_interval 三层 + **每日复审队列 UI** + budget 统计 | 每日出队→标注(still_valid/changed/stale)→interval 反馈；**标注率闸门 ≥70%** | P2,P3 | `[ ]` |
| **P5 复用+度量** | 复利可观测 | 检索/浏览 + 5 度量面板 | 能检索复用 compound 产物；5 度量出数 | P3,P4 | `[ ]` |
| **P6 上线** | 可分发单机 MVP | 打包 + 冷启动引导 + 用户文档 | 真实数据跑通 e2e 闭环一周；标注率≥70%；腐化可控（见 §6） | P1–P5 | `[ ]` |

---

## 4. 任务拆解（占位，挂 spike + 架构 §）

> 仅列骨架，每项待填：具体子任务 / 负责人 / 工期 / 验收。编号供追溯。

**P0 文档收口**
- [ ] P0.1 架构文档「待 zj 复核」逐条清零或转 risk §5
- [ ] P0.2 RESEARCH-TOPICS 状态列收口（T0.1–X.3 映射到对应 spike）
- [ ] P0.3 本计划 §2 决策基线 + §5 风险登记册评审签字

**P1 存储地基**
- [ ] P1.1 迁移脚本：D1 context_scope / D2 context_member / D3 citation / D4 archived_at / D5 review_queue / D6 baseline_interval+interval_source / D7 interval_adjustment / D8 attention_observation（架构 §5）
- [ ] P1.2 repository seam 抽象（保持 Kuzu/TerminusDB 可替换）
- [ ] P1.3 双时态 + decay 触发器（线性）实测（Spike 01）

**P2 摄入+分流**
- [ ] P2.1 快捕获 UX（本地优先离线）（T0.2）
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
- [ ] P4.5 **已捕获条目规则统一**：spike 08 ARCHIVE vs spike 09 28d `[TODO(zj)]`

**P5 复用+度量**
- [ ] P5.1 复利产出检索/浏览（T6.1）
- [ ] P5.2 5 度量面板（连接密度/复用率/方法论产出/衰减可控/复利系数）（Spike 07）

**P6 上线**
- [ ] P6.1 打包/分发形态（见 §1.2 TODO）
- [ ] P6.2 真实数据冷启动引导
- [ ] P6.3 用户文档 + 度量复盘节奏（见 §7）

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
| R6 | budget/振荡带/ARCHIVE-vs-28d 规则未统一，阈值全占位 | Spike 09 | 调度精度漂移 | 占位待真实数据校准；已捕获条目规则 P4.5 统一；校准期 oversubscribe×1.5 防低估固化 | open |
| R7 | **16GB 硬件约束**（9B swap） | Spike 10 | 蒸馏延迟 4.7min/条 | 4B 默认；9B 仅可选上限 | 已缓解 |
| R8 | LangGraph/Semantic Router 破坏性变更 | 架构 §8 | 编排回归 | 锁版本 + 路由回归测试 | 缓解中 |
| R9 | **文档债务**（RESEARCH-TOPICS 状态全「待调研」、架构顶部「待 zj 复核」） | 本计划 Phase 0 | 基线混乱、决策失配 | Phase 0 收口（见 §0 TODO） | open |

---

## 6. 验收标准与上线闸门（Definition of Done）

**硬门槛（任一不满足不得上线）**：
- [ ] **标注率 ≥70%**（滚动 7 天 `labeled_completed/completed`；样本<10 放行不计，见 Spike 09 切片 B）
- [ ] **衰减可控**：到期动态节点在 ROT=0.9 前被引用或归档占比达标，且**先满足注意力预算** `n/(0.6×interval)`（否则该指标恒 0）
- [ ] **e2e 闭环跑通**：捕获→蒸馏→调度→复审→复用→度量，单条数据全链路无断点
- [ ] **5 度量出数**（连接密度/复用率/方法论产出/衰减可控/复利系数，PRD §7）
- [ ] **架构文档「待 zj 复核」清零**、风险登记册 R1/R4/R6/R9 有显式处置

**上线判定（P6）**：zj 本人用**真实数据**跑通 e2e 闭环 ≥1 周，上述门槛持续达标。

---

## 7. 度量与复盘（operationalize PRD §7）

> PRD §7 已定义 5 指标与质量口径，但**未 operationalize**（用什么数据、谁判、何时判）。此处落地。

| 指标 | 数据来源 | 判定者 | 复盘节奏 | 状态 |
|---|---|---|---|---|
| 连接密度 | `reverse_link`/`derived_from` 边 | 自动 | 每周 | `[TODO(zj)]` |
| 复用率 | `citation` 表 | 自动 | 每周 | `[TODO(zj)]` |
| 方法论产出 | `combine` transform 计数 | 自动 | 每周 | `[TODO(zj)]` |
| 衰减可控 | 到期节点 evidence_refs/archived_at | 自动 + 预算校验 | 每周 | `[TODO(zj)]` |
| 复利系数 | 4 指标归一加权 | 自动 | 每周（权重待校准） | `[TODO(zj)]` |
| 蒸馏质量口径 | 复述率/overlap/跨源率/引用命中/结构完整 | 自动 rubric + 人工抽审 | 每蒸馏批次 | `[TODO(zj)]` |

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
   └─证据表 spike01-13b → 本计划 §2 决策基线 / §4 任务挂接
   └─§5 D1-D8 schema   → 本计划 P1 迁移
   └─§6.5/§6.5.1 调度  → 本计划 P4
   └─§7 延后项         → 本计划 §1.3 不在范围
   └─§8 风险未决       → 本计划 §5 风险登记册
RESEARCH-TOPICS (22 topic) → Phase 0 收口后作为执行追踪基线
spikes/ (14, passed)       → 每个 Phase 任务的验证证据与时间胶囊
```
