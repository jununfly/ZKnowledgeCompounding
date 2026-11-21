# 退役 ontology 派生视图 · 逐字归档（2026-11-21）
> 本文归档以下 6 份**派生视图**的逐字原文。它们在 2026-11-21 文档治理中退役删除（新 skill L4 判定为并行 ontology 体系，违反 one-home-per-fact）。
> 语义已由单一模型 `docs/ontology/model.json` 的实体/属性/关系/规则元素承载；架构设计论证的逐字原文另见 `architecture-v1.2-source-2026-11-19.md`。本归档仅作历史溯源，**不作产品语义来源**。

---

## 原文件：`docs/ontology/domain-ontology.md`

# ZKC 领域本体（domain ontology）

> doc-kind: reference（当前领域事实的 lookup surface）；authority: supporting（派生导航视图，不争夺 primary）。
> 本页把散落在 PRD / 架构 / ADR / 专题文档中的领域事实按本体四要素——**实体 / 属性 / 关系 / 规则**——归并重组。
> 每个实体只在这里出现一次；属性、关系、规则汇总其全部来源。本页**不新增产品语义**：每条都可溯源到「来源」列所指的权威页；冲突以来源页为准。
> 权威链（BOUNDARIES.md）：参数 → `tuning.REGISTRY`；事实 → 代码/schema/运行时；语义决策 → ADR；问题与目标 → PRD。过程态（roadmap/plan）不得作 proof。

## 0. 用法与边界

- **怎么读**：先按实体查定义 → 属性查取值 → 关系查耦合 → 规则查约束与状态；每个 rule 的「状态」列标明 已定 / 废弃 / 限定 / 保留观察 / 永久 caveat / 未实现，废弃项仅作溯源、不得当现行口径。
- **不在本页**：一次性取证读数（evidence surface）、过程态日志、单次 spike 采样数值——它们不是 durable 事实，见 docs/evidence/ 与各 spike README。
- **术语护栏**：双轨 ≠ 双时态；衰减 ≠ 衰减可控；归档 ≠ 墓碑。三者混用即架构偏移，见 §4 规则 G1/G2/G3。
- **口径标记**：`SIMULATION` = 设计口径/占位，非真实行为校准；`CALIBRATED` = 经真实埋点校准。凡标 SIMULATION 的数值不得当既成事实外推。

---

## 1. 实体（Entity）

### 1.1 核心领域实体

- **节点 node**：系统的第一性对象；单表存双轨 + 双时态 + 衰减 + interval + embedding 状态位。来源：`架构 §5·数据模型`；ta-data-storage.md。
- **轨道 track**：节点的类型+生命周期分类，`static` / `dynamic` / `unrouted` 三值枚举。来源：`架构 §5·数据模型`；ta-data-storage.md。
- **双轨 dual-track**：静态轨（事实型、长生命周期、decay 恒 0、不占预算）与动态轨（存活型、短生命周期、快速腐化、预算唯一消耗方）的分流法，核心语义是衰减率与注意力成本。来源：PRD §2.1；`架构 §2·基础与第一性`；ZJ-CONTEXT.md。
- **双时态 bitemporal**：`valid_time`（事实演进）+ `transaction_time`（溯源审计）的时态建模；只服务静态轨，不覆盖动态轨腐化。来源：`架构 §5·数据模型`；ZJ-CONTEXT.md。
- **元认知 claim（meta_claim）**：蒸馏产物，必须带 `evidence_refs` 才能存在（存储层 NOT NULL 强制）。来源：`架构 §5·数据模型`；PRD §4；ZJ-CONTEXT.md。
- **建模产物 modeling_artifact**：结合算子产物，唯一无 `version_seq`/OCC 的表。来源：ta-data-storage.md；`架构 §6.2·变换算子`。
- **边 edge**：节点间关系（derived_from 蒸馏溯源 / reverse_link 反向连接），带 weight。来源：PRD §4；`架构 §5·数据模型`。
- **引用 citation**：记录「后续条目复用某 claim」的行为事件，用于复用率；与 evidence_refs 方向相反。来源：`架构 §5·数据模型` 溯源权威声明。
- **上下文 context**：条目归属，`scope` 为 `self_loop`（自闭环）/ `higher_dim`（更高维）；成员走 context_member junction。来源：`架构 §5·数据模型` D1/D2；ZJ-CONTEXT.md。
- **孤儿 orphan**：无连接、无 context、未捕获的条目。来源：ZJ-CONTEXT.md；`架构 §6.5·调度与预算` L1。
- **已捕获 captured**：条目成为某 claim/产物的来源（`evidence_refs` 含它）；语义为「单程票」。来源：ADR-0002；ZJ-CONTEXT.md。
- **单程票 SingleTicket**：已捕获条目的命运——28d 观察 → 到期 ARCHIVE，永不回 DISTILL。来源：ADR-0002；`架构 §6.5·调度与预算`。

### 1.2 衰减与调度实体

- **衰减 decay**：线性时间函数 `min(1, elapsed / review_interval)`，衡量腐化程度；静态轨恒 0。来源：`架构 §6.3·调度与预算`；ADR-0003；ZJ-CONTEXT.md。
- **衰减可控 decay controllability**：到期条目在 ROT 前被处理（蒸馏或归档）的比例；复利系数四分量之一。来源：PRD §7；ZJ-CONTEXT.md。
- **行动窗口**：SURFACE_THRESHOLD(0.6) 到 ROT_THRESHOLD(0.9) 之间「还能救」的天数；interval=21d 时为 6.3 天。来源：`架构 §6.3·调度与预算`。
- **复审 review**：对到期前条目的重新确认，必须带显式结果标注。来源：`架构 §6.5·调度与预算`；ADR-0007。
- **复审间隔 review_interval**：「这条多久后腐化」的预测值，是双层量 = 个体基线 × 全局预算因子；L1 基线 / L2 预算归一 / L3 反馈三层。来源：`架构 §6.5·调度与预算`；ADR-0009。
- **活跃日 active day**：当日真实复审发生（`completed≥1`）；空队列日（`completed==0 且 queue_remaining==0`）豁免，仅有 due 未复审才断签。来源：ADR-0007；glossary.md。
- **饱和日 saturated day**：日末仍有积压（`queue_remaining>0`）的日子，是预算唯一可用的点估计样本。来源：`架构 §6.5.1·调度与预算`；ADR-0007。
- **删失观测 censored observation**：日末已清空时 `completed` 只是容量下界；与饱和日混平均会得错误预算。来源：`架构 §6.5.1·调度与预算`；ZJ-CONTEXT.md。
- **预算 budget_per_day**：每天可处理条目数上限，是容量、只能观测不能声明；三义中仅「无状态派生估计」生效。来源：ADR-0006；glossary.md。
- **外生锚 exogenous anchor**：来自系统之外、能证伪自证的 signal，仅两个——复审标注（A）/ 真实完成数（B）；自指闭环缺锚只会自证。来源：`架构 §6.5.1·调度与预算`；PRD §8。
- **注意力信号 attention_signal**：该关注程度（ZKC 自研）；现仅按 decay 排序。来源：`架构 §5·数据模型`/§6.3。

### 1.3 复审终局与生命周期实体

- **复审标注 verdict**：`zkc decide` 的人工四档结果 `still_valid` / `changed` / `stale` / `browse`（无 too_early）。来源：ADR-0011/0012。
- **终局动作**：替代 AIMD 乘因子的内容/价值生命周期动作（nodes.save 新版本 / set_baseline_interval / archive）。来源：ADR-0011。
- **审计 reason（REVIEW_REASON）**：五值互异集中常量——`still_valid` / `changed` / `stale_overwrite` / `stale_purged` / `browsed_without_label`。来源：ADR-0011/0012。
- **D2 归档**：退出整个调度回路（due / 衰减扫描 / higher_dim seeds），仍可查阅。来源：ADR-0010；risks.md。
- **墓碑 tombstone**：逻辑删除标记 `deleted_at`，全功能不可见、可恢复、TTL 后真删。来源：ADR-0013；`架构 §11·选型风险`。
- **真删 purge**：墓碑满 TTL 经引用闸门后物理删行及级联数据，仅留独立审计事件。来源：ADR-0013。
- **引用闸门**：真删前扫 `evidence_refs`（uuid[] 无 FK）+ `citation.citing_node_id`，有引用即拒删并写 `tombstone_purge_blocked`。来源：ADR-0013；`架构 §11·选型风险`。
- **独立审计事件**：真删后记录 id/title/时间/TTL/操作者、不记内容的删后真相源。来源：ADR-0013。

### 1.4 变换与度量实体

- **复利变换引擎**：蒸馏 / 结合 / 拓扑装配三类算子，人可干预（半自动）。来源：PRD §2.2/§5；`架构 §4·基础与第一性`。
- **蒸馏 distill**：条目 → 结构化抽取（Ollama 原生 /api/chat + format:json）→ 元认知 claim + topic 组织 + 反向连接。来源：`架构 §6.1·变换算子`。
- **结合 combine**：多条信息合成建模/方法论产物，复用 RCS 漏斗 + 双层合并，产物必带来源引用。来源：`架构 §6.2·变换算子`。
- **拓扑装配**：把条目装配进 context，含自闭环与更高维两方向。来源：`架构 §6.4·变换算子`。
- **跨源强制算子**：提示层硬约束（≥2 条跨源断言）+ 单次补全回路，把跨源综合从模型规模问题定位为算子层问题。来源：`架构 §8·选型风险`/§9⑧（Spike 11）。
- **忠实度闸门 faithfulness gate**：分解式 LLM-as-judge 机制可行但本机 4B/9B 不可用，MVP 定案 human-in-the-loop + 字面 rubric 预过滤。来源：`架构 §8·选型风险`（Spike 12/13/13b）。
- **复利系数**：连接密度 / 复用率 / 方法论产出 / 衰减可控四项等权（0.25×4）归一加权总指标，`method_target=10`。来源：PRD §7；`架构 §8·选型风险`；user-guide.md。
- **蒸馏质量度量**：漏检率（召回侧）/ 误蒸馏率（精确侧），zj 人工抽检定下，属系统外信号，与复利系数量度严格区分。来源：`架构 §8·选型风险` E8 锚2；rec-avoid-gate.md。

### 1.5 门禁 / 权威 / 边界实体

- **四项第一性特征**：双轨 / 衰减 / 双时态 / 注意力预算，即护城河。来源：`架构 §3·基础与第一性`；constraints.md。
- **caveat: moat-unverified-vs-mem0**：对外主张必带的护城河未验证声明（mem0 因编译限制未纳入对照），不得回退 3 项口径。来源：`架构 §3·基础与第一性`；constraints.md。
- **rec-avoid gate**：把护城河从口号落成机械可判定版本门（三件套：去模型化测试 + check_invariant.py + 图库主存储 EXCLUDED）。来源：ADR-0005；rec-avoid-gate.md。
- **去模型化测试**：去掉 LLM 后若 SilverBullet/logseq 可等价实现即稀释项，默认拒绝。来源：ADR-0005；rec-avoid-gate.md。
- **check_invariant.py**：CI 谓词，守 `evidence_refs NOT NULL`、无关闭 decay/attention 全局开关、归档退出调度。来源：ADR-0005；rec-avoid-gate.md。
- **权威边界 authority boundary**：产品行为/架构/发布/正确性必须由代码/测试/运行时/契约/design/ADR 建立；roadmap 只答过程状态。来源：ADR-0008；BOUNDARIES.md。
- **过程态 process material**：roadmap carrier / render 视图 / plan / 过程日志，只承载过程状态，不得作 proof/evidence。来源：ADR-0008；BOUNDARIES.md。
- **权威信封 zj-roadmap-authority/v1**：Markdown 视图开头 512B 内的结构签名，供检查器识别并跳过。来源：ADR-0008。
- **单一真相源**：参数 → tuning.REGISTRY + GET /tuning；进度 → PRD §9 / 运行时；决策 → ADR；实现 → 代码树。来源：BOUNDARIES.md。
- **seam**：storage / provider / encoder / transport 四道可替换边界。来源：`架构 §3·基础与第一性`/§6.4；ZJ-CONTEXT.md。
- **CALIBRATED / SIMULATION**：阈值与权重的溯源状态；`CALIB_OVERRIDE_AT` 是 R6 人工覆盖的永久 caveat 标记。来源：risks.md R6；`架构 §8·选型风险`。

### 1.6 接口 / 运行时实体

- **ingest_with_routing**：主链路唯一写入闸，任何来源（CLI/MCP/Web）必须经其分流。来源：ta-data-flow.md。
- **DecisionRouter / LexicalRouter**：双轨分流器，前者本地 LLM 直接判定（主方案、编码器无关），后者 TF-IDF embedding-free（失败降级，保持 unrouted）。来源：`架构 §6·选型风险` 选型；ta-data-flow.md。
- **zkc CLI**：命令行入口——`daily` / `meter` / `decide` / `embed` / `capture` / `p64` / `migrate` / `tombstone`。来源：user-guide.md；ta-data-flow.md。
- **MCP server**：单边暴露的 stdio server，只调既有 repository/command API；第四 seam；五白名单 tool + `zkc://scheduler/due` resource；契约 zkc-mcp-contract/v1。来源：ADR-0004；user-guide.md。
- **CaptureProfile**：`zkc_capture` 的默认安全写集合（仅 `{node}`）；不写 interval、不触发 distill、不直写 claim。来源：ADR-0004。
- **Web 视图**：`/` 快捕获、`/review` 复审队列、`/metrics` 五度量面板、`/browse` 脱敏检索、`/review/api/*` 队列接口族。来源：user-guide.md。
- **每日驱动 daily_e1_driver.py**：E1 每日驱动，`ZKC_MODE=direct` 直写 PG；真值收口端点 `POST /review/api/observe/auto`。来源：ADR-0007；windows-install-and-run.md。
- **zj-zkc-daily skill**：canonical 在 `skills/zj-zkc-daily/SKILL.md` 的每日流程 skill。来源：ADR-0007；user-guide.md。

### 1.7 风险实体

- **R4**：注意力预算不足 → 腐化无解（rot=100%）；终判「缩动态集」，保留观察。来源：risks.md；ADR-0010。
- **R6**：budget/振荡带/ARCHIVE-vs-28d 规则未统一、阈值全占位；收口为永久 caveat。来源：risks.md。
- **R10**：外生锚供给风险；2026-11-07 实证收口（累计 ≥20 + 滚动率 ≥70%）。来源：risks.md；PRD §9。
- **R14**：completion 开启裁决；2026-11-12 收口为「确认安全·保持开启」。来源：risks.md。
- **R15**：verdict v2 语义落地不变量漂移；已落码守住（626 tests OK）。来源：risks.md；ADR-0012。
- **R16**：墓碑软删 + TTL 真删引入误删/悬空引用/月扫时序风险；已落码守住（667 tests OK）。来源：risks.md；ADR-0013。

---

## 2. 属性（Attribute）

| 实体 | 属性 | 取值 / 语义 | 来源 |
|---|---|---|---|
| node | track | static / dynamic / unrouted | `架构 §5·数据模型` |
| node | decay_score | real[0,1]；静态轨恒 0 | `架构 §5·数据模型`；ta-data-storage.md |
| node | review_interval / baseline_interval | 生效值 / 未污染 L1 基线 | `架构 §5·数据模型` D6 |
| node | interval_source | auto / human；human 豁免一切自动改写 | `架构 §5·数据模型` D6 |
| node | valid_from/to + tx_from/to | 业务时间 / 事务时间 | `架构 §5·数据模型` |
| node | archived_at / deleted_at | 归档标记 / 墓碑标记兼 TTL 起算 | `架构 §5·数据模型`/§11 |
| node | attention_signal / routing_confidence | 关注程度 / 分流置信度（弃权为 NULL） | `架构 §5·数据模型` |
| node | embedding / embedding_4096 | 768d nomic / 4096d qwen3；双列共存，4096 为 browse 召回列 | `架构 §6·选型风险`；ta-data-storage.md |
| node_history | 主键 | (id, tx_from)，ON DELETE CASCADE | ta-data-storage.md |
| meta_claim | evidence_refs | uuid[] NOT NULL，每条 claim ≥1 引用 | `架构 §5·数据模型` |
| meta_claim | faithfulness_status | supported / unsupported / contradicted / human_only | `架构 §5·数据模型` D9 |
| interval_adjustment | kind | baseline / budget / feedback | `架构 §5·数据模型` D7 |
| review_queue | action | classify（弃权入队）/ distill / archive / abstain | ta-data-flow.md；`架构 §5·数据模型` D5 |
| attention_observation | day / pushed / completed / queue_remaining / labeled_completed | 日主键 / 供给 / 完成 / 积压 / 带标注完成 | `架构 §5·数据模型` D8 |
| 衰减 | SURFACE_THRESHOLD / ROT_THRESHOLD | 0.6 进入注意力 / 0.9 已腐化 | `架构 §6.3·调度与预算` |
| 衰减 | 函数形态 | 线性（阶梯否决=窗口 0；指数触发过晚） | `架构 §6.3·调度与预算`；ADR-0003 |
| review_interval | MIN_INTERVAL_DAYS | 0.25（SIMULATION，非 CALIBRATED）；收缩链 1.0→0.7→0.49→0.343→0.25 | ADR-0009 |
| review_interval | L1 基线 | time_anchor clamp[0.25,180] / self_loop 3d / 已捕获 28d / 有连接 14d / 孤儿 7d / 静态 NULL | `架构 §6.5·调度与预算` |
| review_interval | L2 / L3 | 预算归一（×2 延后，MAX 180d）/ AIMD ×1.5 / ×0.7（v2 后不再由 verdict 驱动） | `架构 §6.5·调度与预算` |
| 预算估计 | 算法 | 删失感知 p25 + 单调护栏 + EMA(α=0.3,±30%) + 校准期 oversubscribe×1.5 | `架构 §6.5.1·调度与预算` |
| 预算估计 | confidence | none / lower_bound / provisional / observed | `架构 §6.5.1·调度与预算`；ADR-0010 |
| 标注率闸门 | 阈值 | ≥70%，窗口内完成 <10 不判定（v2 后仅审计读数，不改写 interval） | PRD §6 流C；`架构 §6.5·调度与预算` |
| verdict | VERDICTS | still_valid / changed / stale / browse（无 too_early） | ADR-0011 |
| 审计 reason | REVIEW_REASON | 五值互异、集中常量，不含 too_late/on_time | ADR-0012 |
| tombstone | is_delete / deleted_at | 1=墓碑（deleted_at 非 NULL，TTL 起算）/ 0=恢复（human-only） | ADR-0013；ZJ-CONTEXT.md |
| tombstone | TTL / 扫描 | 7d 起算、月扫（非 daily）、实际真删 7~37 天 | ADR-0013 |
| 复利系数 | 权重 / source | 四项等权各 0.25，method_target=10 / source=SIMULATION | `架构 §8·选型风险`；user-guide.md |
| 蒸馏调用 | ollama_chat 参数 | format:json / think:false / num_ctx=8192 / num_predict=1024 | ta-data-flow.md |
| MCP | 协议基线 / 契约 / transport | 2024-11-05 / zkc-mcp-contract/v1 / 默认 stdio | ADR-0004；user-guide.md |
| MCP | 量级上限 | 单会话 ≤1000（maxItems），超出拒绝分批 | ADR-0004 |
| 项目环境 | PG / 扩展 / 端口 / DSN | PG16 + pgvector 0.8.7 / 55433 / postgresql://postgres:zkc@localhost:55433/zkc_dev | constraints.md；windows-install-and-run.md |
| 定时任务 | FREQ | FREQ=DAILY;BYHOUR=23;BYMINUTE=50 | windows-install-and-run.md |

---

## 3. 关系（Relation）

方向记作 `主体 —[关系]→ 客体`。

### 3.1 摄入与分流

- 三入口（CLI / MCP capture / Web capture_note）—[必须经唯一写入闸]→ ingest_with_routing（ta-data-flow.md）。
- ingest_with_routing —[调用]→ route_text（DecisionRouter + LexicalRouter）（ta-data-flow.md）。
- route_text —[产出]→ track ∈ {static, dynamic, unrouted}（ta-data-flow.md）。
- DecisionRouter —[失败降级]→ LexicalRouter，保持 unrouted（ta-data-flow.md）。
- vague/unrouted —[入队]→ review_queue(action=classify)（ta-data-flow.md）。

### 3.2 存储与变换

- store.nodes.save —[写入]→ node + node_history 双时态版本链（ta-data-storage.md）。
- 蒸馏算子 —[产出]→ meta_claim（带 evidence_refs）+ LLMCallScore（ta-data-flow.md）。
- 结合算子 —[产出]→ modeling_artifact + context（ta-data-flow.md）。
- 元认知 claim —[反向连接]→ 源节点（reverse_link）；源节点 —[derived_from]→ claim（PRD §4）。
- context —[context_member 聚合]→ node（带 produced_by + weight，接入级联撤销）（`架构 §5·数据模型` D2）。
- citation —[记录复用]→ meta_claim（后续条目 → claim，与 evidence_refs 反向）（`架构 §5·数据模型`）。
- 所有变换产物 —[携带 produced_by]→ transform（可级联撤销）（`架构 §6.4·变换算子`）。

### 3.3 调度与终局

- refresh_decay —[刷新]→ node.decay_score → list_due_for_review（ta-data-flow.md）。
- expiry.route_expired —[三类终局]→ captured→ARCHIVE（单程票） / contextual→DISTILL / orphan→ABSTAIN（ta-data-flow.md；`架构 §5·数据模型` D5）。
- 每日复审队列 —[产出外生锚]→ 复审标注（A）+ 真实完成数（B）（`架构 §6.3·调度与预算`；PRD §6 流C）。
- queue_remaining —[喂给]→ estimate_budget_from / calibration_readiness → E1-③（ADR-0007）。
- estimate_budget_from —[估计]→ budget_per_day → 喂给 L2 预算归一（ta-data-flow.md）。
- L2 fit_budget —[写]→ set_interval + audit_interval(kind=budget)；L3 adapt_interval_math —[写]→ audit_interval(kind=feedback)（ta-data-flow.md）。
- L3 缩短 interval —[放大需求 Σ1/(0.6×Iᵢ)，被 L2 反向对冲]→ 预算归一化（ADR-0009）。
- changed / stale+cover —[nodes.save + 重置 L1，不退出调度]→ 新版本（ADR-0011）；stale+purge —[archive]→ 退出 due（ADR-0011）。
- decide_review —[外生锚归零：不调 adapt_interval]→ 仅 mark_reviewed + 标注埋点（ADR-0011 DI-1）。
- floor_hit（触及 0.25d）—[触发]→ archive + 审计 floor_hit_archive（ADR-0009）。

### 3.4 生命周期与治理

- tombstone(deleted_at 非 NULL) —[进入全功能不可见]→ 所有默认读取路径 + P4 静态守门（ADR-0013）。
- 墓碑满 7d —[经引用闸门]→ 真删；引用命中 —[拒删]→ tombstone_purge_blocked（ADR-0013）。
- 归档 —[退出]→ 整个调度回路（due / 衰减扫描 / higher_dim seeds）（ADR-0010）。
- 墓碑 —[区别于]→ 归档（前者全功能不可见且到期真删，后者仍可查阅）（ZJ-CONTEXT.md）。
- 去模型化测试 / check_invariant / 图库 EXCLUDED —[组合为]→ rec-avoid 版本门（ADR-0005）。
- rec-avoid gate —[守门]→ 任何新增功能 PR（rec-avoid-gate.md）。
- 四项第一性特征 —[对外必带]→ caveat: moat-unverified-vs-mem0（constraints.md）。
- code/docs —[禁止读取依赖]→ roadmap（BOUNDARIES.md）；code —[单向引用溯源]→ ADR id（BOUNDARIES.md）。
- 权威信封/结构签名 —[触发检查器跳过扫描]→ 过程态页面（ADR-0008）。

---

## 4. 规则（Rule）

状态：`已定` / `废弃`（仅溯源）/ `限定` / `保留观察` / `永久 caveat` / `未实现`。

### 4.1 第一性与术语护栏

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| G1 | 两类信息原生双轨建模，生命周期与操作语义分离 | 已定 | `架构 §3·基础与第一性` |
| G2 | 双轨 ≠ 双时态，双时态不覆盖动态轨腐化与注意力稀缺，禁互换 | 已定 | `架构 §2·基础与第一性`；PRD §2.0 |
| G3 | 衰减 ≠ 衰减可控；归档 ≠ 墓碑，混用即架构偏移 | 已定 | constraints.md；ZJ-CONTEXT.md |
| G4 | 四项核心语义对外必带 caveat: moat-unverified-vs-mem0，不得回退 3 项口径 | 已定 | `架构 §3·基础与第一性` |
| G5 | 存储是可替换 seam；变换语义与调度策略属 ZKC 自己 | 已定 | `架构 §3·基础与第一性` |
| G6 | 所有变换产物必须可溯源，否则无法复用、无法形成复利 | 已定 | `架构 §3·基础与第一性` |
| G7 | 本地/离线优先，云端仅作可切换 provider | 已定 | `架构 §3·基础与第一性` |

### 4.2 摄入 / 数据模型 / 衰减

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| I1 | 任何来源绕过 ingest_with_routing 直写 node 禁止 | 已定 | ta-data-flow.md |
| I2 | meta_claim 无 evidence_refs 在存储层被拒（NOT NULL） | 已定 | `架构 §5·数据模型` |
| I3 | 每条 claim ≥1 引用，失败不落库但仍记 LLMCallScore | 已定 | ta-data-flow.md |
| I4 | 静态轨 decay_score 恒 0 | 已定 | `架构 §5·数据模型`；ADR-0003 |
| I5 | update_decay 不写 node_history、不 bump tx_from，仅 UPDATE decay+version_seq | 已定 | ADR-0003 |
| I6 | set_interval 改真实调度事实，仍写 node_history 快照 | 已定 | ADR-0003 |
| I7 | schema 变更必须进 migrations/，禁手工建表；改历史迁移触发 sha256 闸门拒绝 | 已定 | constraints.md；ta-data-storage.md |
| I8 | 4096 为派生数据不入历史；history() 用显式列清单，禁 SELECT * UNION | 已定 | ta-data-storage.md |

### 4.3 分流 / 注意力预算

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| A1 | 单信号不可分，采用双信号弃权（相似度阈值 OR 信息量下限）；模糊/确定在真编码器下仍 OVERLAP | 已定 | `架构 §8·选型风险` Spike02/03 |
| A2 | 长模糊句单向误判为 dynamic（3/3，三编码器一致），长度仅弱代理、信息量门失效 | 已定（限定） | `架构 §8·选型风险` Spike02 |
| A3 | 注意力是硬预算，需求 = 动态条目数/(0.6×interval)；预算<需求时腐化无解（rot=100%） | 已定 | `架构 §6.3·调度与预算` |
| A4 | 预算不足诚实降级：infeasible + max_dynamic_items 显式报告，禁静默拉长 interval | 已定 | `架构 §6.5·调度与预算` |
| A5 | budget 是容量只能观测不能声明；删失感知，只有饱和日参与点估计（p25），无饱和日只报 lower_bound | 已定 | `架构 §6.5.1·调度与预算`；ADR-0006 |
| A6 | 单调护栏：非饱和日只抬升预算永不压低；饱和日才允许下调 | 已定 | `架构 §6.5.1·调度与预算` |
| A7 | 任何自指闭环需至少一个外生锚；缺锚闭环只自证 | 已定 | `架构 §6.5.1·调度与预算` |
| A8 | 唯一生效预算口径是无状态派生估计；BUDGET_PER_DAY_DEFAULT=1.0 仅占位 | 已定 | ADR-0006 |
| A9 | 有状态路径（update_budget_from/fit_budget）本阶段不接线，未来启用须先立 roadmap 节点 | 限定 | ADR-0006 |

### 4.4 interval 三层

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| V1 | L1 优先级：self_loop(3d) 压过已捕获(28d)（原表序相反已修） | 已定 | `架构 §6.5·调度与预算`；ADR-0002 |
| V2 | 已捕获=单程票：28d 观察 → 到期 ARCHIVE，永不回 DISTILL | 已定 | ADR-0002 |
| V3 | 撤销回退：produced_by 级联撤销后按未捕获基线重算（14d/7d），必须写 interval_adjustment，禁静默 | 已定 | ADR-0002 |
| V4 | interval_source='human' 全程豁免自动改写 | 已定 | `架构 §5·数据模型` D6 |
| V5 | MIN_INTERVAL_DAYS=0.25 是 SIMULATION 占位，禁止写成 CALIBRATED 或写回 REGISTRY | 已定 | ADR-0009 |
| V6 | <1d 仅数值语义不是日内复审能力；L1 解析器无小时级规则，<1d 只能由 L3 AIMD 收缩产生 | 已定 | ADR-0009 |
| V7 | L3 必须接显式复审标注，decay-only 反馈恒 no-op；收敛目标是 H/0.6 非真值 H | 已定 | `架构 §6.5·调度与预算`；ADR-0009 |
| V8 | 标注率 <70% 或样本 <10 → L3 停机（v2 后闸门读数仅审计，不改写 interval） | 已定 | PRD §6；`架构 §6.5·调度与预算` |
| V9 | floor_hit → archive，不再静默 no-op；human 节点提前返回 | 已定 | ADR-0009 |

### 4.5 verdict v2（ADR-0011/0012）

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| D1 | decide_review 对任何 outcome 都不得调 adapt_interval（spy 断言=0，DI-1 最硬） | 已定 | ADR-0012 |
| D2 | changed/stale+cover 走 nodes.save + set_baseline_interval + mark_reviewed，不退出；stale+purge 走 archive 必退出 | 已定 | ADR-0011；DI-2 |
| D3 | 覆盖=enrich/refresh 写节点双时态新版本（非蒸馏 claim）；清除仅映射 archive | 已定 | ADR-0011 S1b/S1c |
| D4 | changed 内容载荷与 stale 分支只能由 zj 逐条给；缺失即拒收（ValueError），绝不默认 purge | 已定 | ADR-0011/0012 DI-3 |
| D5 | REVIEW_REASON 五值集中常量两两不同，禁止字符串散落，与 D2 归档 reason 分开记 | 已定 | ADR-0012 DI-4 |
| D6 | 不改 tuning.py 任何常量、不写回 REGISTRY；adapt_interval 函数保留仅 decide_review 不调 | 已定 | ADR-0012 DI-6 |
| D7 | v2 只改新一次调用行为，无 retroactive 路径；历史 changed 不回填/不撤销 interval 调整 | 已定 | ADR-0012 DI-7 |
| D8 | changed/stale+cover 不产出 claim/produced_by 复利变换，纯 nodes.save 内容替换（不触发 distill） | 已定 | ADR-0012 DI-9 |
| D9 | 四档 verdict 仅 still_valid/changed/stale/browse，无 too_early；v1 OUTCOME_VERDICT 坍缩映射废弃 | 废弃(v1) / 已定(v2) | ADR-0011 |

### 4.6 生命周期（ADR-0013）

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| T1 | DI-5「无物理删除」被推翻，新增 tombstone 三态：active→tombstoned→purged | 已定（推翻 DI-5） | ADR-0013 |
| T2 | 墓碑对所有功能不可见（10 条读取路径 + P4 静态守门），且不受 include_archived 控制 | 已定 | ADR-0013；`架构 §11·选型风险` |
| T3 | 恢复 is_delete=0 仅 zj 本人，与 verdict 同级 human-only 门禁 | 已定 | ADR-0013 |
| T4 | 真删前扫 evidence_refs + citation.citing_node_id，有引用拒删不 CASCADE，无引用才 CASCADE | 已定 | ADR-0013 |
| T5 | 月扫 TTL 7d 起算、幂等、挂每日 automation 非侵入，不注册系统级调度；真删窗口 7~37 天 | 已定 | ADR-0013 |
| T6 | 真删后留独立审计事件（id/title/时间/TTL/操作者），不记内容、不引用已删 node | 已定 | ADR-0013 |
| T7 | 仅 2 条占位节点触发墓碑，不扩大到「一类节点治理」除非后续同类实证 | 限定 | ADR-0013 |

### 4.7 门禁 / 权威边界 / 解耦

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| P1 | roadmap 只答过程状态；产品行为/架构/发布/正确性必须由代码/测试/运行时/契约/design/ADR 建立 | 已定 | ADR-0008 PA-1 |
| P2 | 代码与长期文档不得引用过程编排稿作 proof/evidence，不得把「节点已完成」写成 proof | 已定 | ADR-0008 PA-2 |
| P3 | 权威判定靠结构签名（目录剪枝 + carrier 签名 + 512B 内信封完整匹配），不放宽；跳过清单逐条打印 | 已定 | ADR-0008 PA-3/4 |
| P4 | 去模型化判据：去 LLM 后可被等价实现即稀释项，默认拒绝（除非独立 moat 理由） | 已定 | ADR-0005；rec-avoid-gate.md |
| P5 | check_invariant 断言不可破；任何 feature 不得提供关闭 decay/attention 的全局开关 | 已定 | ADR-0005；rec-avoid-gate.md |
| P6 | 图库主存储 EXCLUDED，仅 Kuzu 只读投影 | 已定 | ADR-0005；`架构 §7·选型风险` |
| P7 | 新功能不得降低衰减+预算可观测性（rec-avoid 经验证伪闸） | 已定 | rec-avoid-gate.md |
| P8 | 解耦：roadmap label 不硬编码路径/迁移号/计数；code 可引 ADR id 但不读 docs/roadmap；单一真相源分落 REGISTRY/代码树/PRD§9/ADR | 已定 | BOUNDARIES.md |
| P9 | 首次接入须真实运行验证（验收 gate 每行须实测记录或标注「架构推演，待实测」，不得伪称已实测） | 已定 | rec-avoid-gate.md |

### 4.8 状态与风险口径

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| S1 | R4 终判=缩动态集（默认）；24 条 D2 归档后 due 归 0 但非恒久 0；余项保留观察 | 终判·保留观察 | ADR-0010；risks.md |
| S2 | R6 权重维持等权 0.25×4；CALIB_OVERRIDE_AT 永久保留；改权重须 zj 显式外生锚 | 永久 caveat | risks.md |
| S3 | R15 四类 reason 互异 + 阈值正交锁死（AIMD_UP/DOWN、MIN_INTERVAL_DAYS、METRIC_W_* 不动） | 已落码守住 | risks.md；ADR-0012 |
| S4 | R16 三层护栏：软删屏蔽+反悔窗口 / 引用闸门拒删告警 / 月度门闩+dry-run+审计 | 已落码守住 | risks.md；ADR-0013 |
| S5 | 复利系数 source=SIMULATION，升 CALIBRATED 需 ≥14d 埋点 + ≥3 饱和日 + zj 四分量价值排序；锚2 蒸馏质量抽检不构成其校准证据 | 已定 | `架构 §8·选型风险`；risks.md |
| S6 | spike 外推红线：单次采样不可信；比率须附绝对数量（≥2 跨源 claim）；强限定不得外推 | 已定 | constraints.md；`架构 §8·选型风险` |
| S7 | 被推翻处记为偏差、不得静默接受（`架构 §8·选型风险` 同款约定） | 已定 | PRD §9；[架构 §9·原文归档](../evidence/architecture-v1.2-source-2026-11-19.md) |

---

## 5. 来源与权威映射

| 权威域 | 权威页 | 本页对应实体/规则 |
|---|---|---|
| 问题 / 目标 / 非目标 | prds/knowledge-compounding-prd.md | §1.1、§1.2、§4.1 |
| 系统架构 / schema / 选型 | `ontology/zkc-arch/`（foundations / data-model / transforms / scheduling-budget / selection-risk 共 5 份，原 ZKC-architecture-v1.2 拆解）+ ta-data-flow.md + ta-data-storage.md | §1.1–1.4、§1.6、§4.2–4.4 |
| 长生命周期决策 | zj-adr/0001–0013 + cutover | §1.3、§1.5、§4.3–4.6 |
| 风险与降级链 | risks.md | §1.7、§4.8 |
| 技术约束 / 环境铁律 | constraints.md | §4.1、§4.8 |
| 产物边界 / 单一真相源 | BOUNDARIES.md | §1.5、§4.7 |
| 护城河守门 | rec-avoid-gate.md + ADR-0005 | §1.5、§4.7 |
| 术语精确定义 | glossary.md + ZJ-CONTEXT.md（root） | §1.1–1.4、§4.1 |
| 使用 / 安装 / 命令 | user-guide.md + setup/windows-install-and-run.md | §1.6、§2 |

> 一次性取证见 docs/evidence/（不作产品语义证明）；逐字决策归档仅作历史溯源。两者均非本页事实来源。

---

## 原文件：`docs/ontology/zkc-arch/data-model.md`

# 架构本体 · 数据模型（Data Model）

> doc-kind: reference；authority: supporting（架构域 ontology 视图，实体/属性/关系/规则四段式）。
> 覆盖原 `ZKC-architecture-v1.2.md` §5（数据模型草案 + 全部 SQL DDL + D1–D9 偏差回填 + 要点）。原文已拆解归档，本页与同目录 4 份共同承载其全部语义。
> 事实权威：schema 以 `migrations/` + 代码为准；语义决策以 ADR 为准。本页归并重组，不新增语义。
> 口径标记：`SIMULATION`=设计口径/占位，`CALIBRATED`=真实埋点校准。

## 0. 范围与读法

- 本页回答「有哪些表/列/类型/索引、约束是什么、双时态与衰减如何落在同一张表」。算子的行为语义见 `transforms.md`，interval/budget 的规则见 `scheduling-budget.md`。
- D1–D9 = 各 spike 对原 §5 草图的偏差回填编号；保持原编号便于溯源。

---

## 1. 实体（Entity）

- **track（enum）**：`static` / `dynamic` / `unrouted` 三值轨道类型。来源：原 §5 DDL。
- **node**：第一性对象；单表存双轨 + 双时态 + 衰减 + interval + embedding 状态位。来源：原 §5。
- **node_history**：node 的双时态版本链，主键 `(id, tx_from)`，`ON DELETE CASCADE`。来源：原 §5；ADR 墓碑增量。
- **meta_claim**：蒸馏产物；必须带 `evidence_refs`（NOT NULL）才能存在。来源：原 §5。
- **edge**：节点间关系，`kind` = derived_from（蒸馏溯源）/ reverse_link（反向连接），带 weight。来源：原 §5。
- **context + context_scope（enum）**：条目归属拓扑；`scope` = self_loop / higher_dim（D1：ENUM 比 text 严格）。来源：原 §5 D1。
- **context_member（junction）**：context 成员关系，替代废弃的 `member_nodes uuid[]` 数组列；每行带 produced_by + weight（D2）。来源：原 §5 D2。
- **citation**：记录「后续条目复用某 claim」的行为事件，与 `evidence_refs` 方向相反，仅用于复用率，不参与「是否已捕获」判定（D3）。来源：原 §5 D3；R2-4 拍板 2026-10-31。
- **review_queue**：到期分流人审网关（D5）；ABSTAIN/DISTILL 入队，action ∈ {distill, archive, abstain}。来源：原 §5 D5。
- **interval_adjustment**：`review_interval` 设定审计表（D7），append-only，kind ∈ {baseline, budget, feedback}，带 produced_by 可整体回滚。来源：原 §5 D7。
- **attention_observation**：注意力预算观测埋点（§6.5.1），日主键，含 pushed/completed/queue_remaining/labeled_completed。来源：原 §5 D8。
- **transform**：变换实例；`produced_by` 指向它，是所有变换产物的可撤销根（由 spike-04 ext schema 定义）。来源：原 §5 / §6.4。
- **archived_at / deleted_at**：归档标记（D4，退出调度但可查阅）/ 墓碑标记（ADR-0013，全功能不可见、TTL 后真删）。来源：原 §5 D4；§11 墓碑增量。

---

## 2. 属性（Attribute）

### 2.1 node 列

| 列 | 取值 / 语义 | 来源 |
|---|---|---|
| id | uuid PK | 原 §5 |
| track | track NOT NULL | 原 §5 |
| routing_confidence | real；分流置信度，弃权/未校准为 NULL | 原 §5 |
| title / content | text | 原 §5 |
| valid_from / valid_to | timestamptz；业务时间（静态轨事实演进） | 原 §5 |
| tx_from / tx_to | tx_from 非 NULL；事务时间（溯源审计） | 原 §5 |
| decay_score | real[0,1]；越大越腐化；静态轨恒 0 | 原 §5；ADR-0003 |
| review_interval | interval；**生效**周期 = baseline × 预算因子 | 原 §5；§6.5 |
| baseline_interval | interval；未污染 L1 基线（审计用，D6） | 原 §5 D6 |
| interval_source | auto / human；human 豁免一切自动改写（D6） | 原 §5 D6 |
| last_reviewed_at | timestamptz | 原 §5 |
| archived_at | timestamptz；已归档（衰减可控信号，D4） | 原 §5 D4 |
| attention_signal | real；该关注程度（ZKC 自研） | 原 §5 |
| embedding | vector(768)；nomic-embed-text（spike14 已定）；双列共存另加 `embedding_4096 vector(4096)` qwen3 | 原 §5；原 §6 选型；spike14 |
| deleted_at | timestamptz；墓碑标记兼 TTL 起算（ADR-0013） | §11 墓碑增量 |

### 2.2 其他表关键列

| 实体 | 列 | 取值 / 语义 | 来源 |
|---|---|---|---|
| meta_claim | evidence_refs | uuid[] NOT NULL；每条 claim ≥1 来源 node id | 原 §5 |
| meta_claim | level | 元 / 方法 / 事实 | 原 §5 |
| meta_claim | faithfulness_status | supported / unsupported / contradicted / human_only（D9） | 原 §5 D9 |
| meta_claim | judge_raw / judge_model / faithfulness_route / human_verdict | 分解式判定原始输出 / 模型 / auto_pass·human_required / 人工判决 | 原 §5 D9 |
| context | scope | context_scope enum：self_loop / higher_dim（D1） | 原 §5 D1 |
| context | member_nodes | uuid[]；**保留但弃用**（D2，改 context_member） | 原 §5 D2 |
| context_member | produced_by / weight / added_at | 装配来源（NULL=人审添加）/ 软归属 1.0 / 时间 | 原 §5 D2 |
| citation | citing_node_id / cited_claim_id / produced_by | 复用方 / 被复用 claim / 产生引用的变换（均 FK CASCADE） | 原 §5 D3 |
| review_queue | action / reason / resolved | distill·archive·abstain / 原因 / 默认 false | 原 §5 D5 |
| interval_adjustment | kind / old_days / new_days / reason / produced_by | baseline·budget·feedback / 前值(NULL=无) / 新值 / 必填解释 / NULL=人审或反馈 | 原 §5 D7 |
| attention_observation | day / pushed / completed / queue_remaining / labeled_completed | 日 PK / 供给 / 完成 / 积压(>0 饱和) / 带标注完成(D8) | 原 §5 D8 |
| node_history | 主键 + DDL | (id, tx_from)，ON DELETE CASCADE；墓碑增量双列 deleted_at | 原 §5；§11 |

### 2.3 值与口径

| 项 | 取值 / 语义 | 来源 |
|---|---|---|
| SURFACE_THRESHOLD / ROT_THRESHOLD | 0.6 进入注意力 / 0.9 已腐化（spike01 已定） | 原 §5 要点；§6.3 |
| 有效复审节奏 | SURFACE × review_interval（非 interval 本身）；需求 = 动态条目数/(0.6×interval) | 原 §5 要点 |
| embedding 用途约束 | 仅限检索召回 / 反向连接候选；**严禁安全判定**（spike03 实测 nomic dangerous=3） | 原 §5；spike14 |
| 已实装向量 | PG16 + pgvector 0.8.7；HNSW；embedding(768) + embedding_4096(4096) 双列共存（R18） | 原 §5；constraints.md |

---

## 3. 关系（Relation）

### 3.1 存储与溯源

- store.nodes.save —[写入]→ node + node_history 双时态版本链。来源：原 §5。
- node —[历史版本]→ node_history（按 tx_from 链；墓碑增量双列同步）。来源：原 §5；§11。
- meta_claim.evidence_refs —[唯一权威来源]→ node（claim 存在前提，NOT NULL）。来源：原 §5 R2-4 声明。
- citation.cited_claim_id —[记录复用]→ meta_claim；citing_node_id ←[复用方] node；与 evidence_refs **方向相反**。来源：原 §5 D3。
- edge —[kind=derived_from]→ 蒸馏溯源；edge —[kind=reverse_link]→ 反向连接。来源：原 §5。

### 3.2 context 与可撤销

- context —[context_scope]→ self_loop / higher_dim。来源：原 §5 D1。
- context —[context_member junction]→ node（带 produced_by + weight）。来源：原 §5 D2。
- context —[produced_by]→ transform；一次装配（一个 transform → 一个 context + 成员）可整体级联撤销。来源：原 §5；§6.4。
- 所有变换产物（claim / 反向连接 / context 边 / citation）—[携带]→ produced_by → transform → 级联撤销。来源：原 §5；§6.4。

### 3.3 标记正交与级联

- archived_at（归档）—[区别于]→ deleted_at（墓碑）：前者退出调度仍可查阅，后者全功能不可见且到期真删；二者**正交**。来源：原 §5 D4；§11。
- 真删 —[PG FK ON DELETE CASCADE]→ node_history / edge / context_member / citation / interval_adjustment / proposal_log / review_queue；attention_observation 按天聚合不回退。来源：§11。

---

## 4. 规则（Rule）

状态：`已定` / `废弃` / `限定` / `保留观察` / `永久 caveat` / `未实现`。

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| M1 | 静态轨主要用 valid/ tx 表达事实演进与溯源；动态轨主要用 decay_score 表达腐化；同表但语义分离、互不替代 | 已定 | 原 §5 要点 |
| M2 | 图遍历先用递归 CTE / 邻接表，不引入图数据库（保持 repository seam 可切 Kuzu / TerminusDB） | 已定 | 原 §5 要点；ADR-0005 |
| M3 | decay 线性；阶梯否决（窗口 0）；静态轨 decay 恒 0 | 已定 | 原 §5 要点；ADR-0003 |
| M4 | schema 已在 PG16 + pgvector 实测通过：vector(768)（原写 1024 为占位已改）、enum、uuid[] GIN 索引 | 已定 | 原 §5 要点 |
| M5 | meta_claim 缺 evidence_refs 被 schema 拒绝（溯源存储层强制） | 已定 | 原 §5 要点 |
| I1 | 任何来源绕过 ingest_with_routing 直写 node 禁止 | 已定 | ta-data-flow.md |
| D1 | context.scope 实际为 ENUM context_scope（比草图 text 严格） | 已定（偏差回填） | 原 §5 D1；spike06 |
| D2 | member_nodes 数组保留但弃用；成员关系改 context_member junction（带 produced_by + weight） | 已定（偏差回填） | 原 §5 D2；spike06 |
| D3 | 新增 citation 表构成双向溯源；复用率不能仅用 evidence_refs 算（方向相反） | 已定（偏差回填） | 原 §5 D3；spike07 |
| D4 | 新增 node.archived_at（衰减可控「已归档」分支） | 已定（偏差回填） | 原 §5 D4；spike07 |
| D5 | 到期分流规则无需新信号列，仅新增 review_queue 操作表（良性范围收敛） | 已定（偏差回填） | 原 §5 D5；spike08 |
| D6 | 新增 node.baseline_interval + interval_source，保护人工设定不被自动化改写 | 已定（偏差回填） | 原 §5 D6；spike09 |
| D7 | 新增 interval_adjustment append-only 审计表，带 produced_by 可整体回滚 | 已定（偏差回填） | 原 §5 D7；spike09 |
| D8 | 新增 attention_observation.labeled_completed（L3 标注率闸门埋点） | 已定（偏差回填） | 原 §5 D8；spike09 |
| D9 | meta_claim 忠实度闸门字段（judge 不可用全走 human_only） | 已定（偏差回填） | 原 §5 D9；spike13 |
| DDL | 4096 为派生数据不入历史；history() 用显式列清单，禁 SELECT * UNION | 已定 | ta-data-storage.md |
| TOMB | 墓碑增量：node + node_history 双列 deleted_at；部分索引 WHERE deleted_at IS NOT NULL；审计表 node_deletion_audit 无 FK 不记 content | 已定（推翻 DI-5） | §11；ADR-0013 |

---

## 5. 来源与权威映射

| 本页实体/规则 | 原文档章节 | 事实权威 | 备注 |
|---|---|---|---|
| §1–2 全部表/列/DDL | 原 §5 数据模型草案 | `migrations/` + 代码 schema | DDL 权威在迁移文件，本页为语义视图 |
| D1–D9 偏差回填 | 原 §5 各 D 标注 | 对应 spike README + ADR | 保留原编号便于溯源 |
| M3 / decay 恒 0 | 原 §5 要点 | ADR-0003 | — |
| M2 / 图库 EXCLUDED | 原 §5 要点 + §7 | ADR-0005 + rec-avoid-gate.md | — |
| embedding 双列 / R18 | 原 §5 + §6 选型 | spike14 + `scripts/r18_recall_eval.py` | — |
| TOMB 墓碑增量 | §11 | ADR-0013 | 语义权威在 ADR |
| §3.1 摄入闸门 | ta-data-flow.md | ta-data-flow.md | 写入时机归 flow 页 |

> 原文档 §5 逐字 DDL 与长注见归档 `docs/evidence/architecture-v1.2-source-2026-11-19.md`。本页保留全部列/约束语义；完整可执行的建表语句以 `migrations/` 为准。

---

## 原文件：`docs/ontology/zkc-arch/foundations.md`

# 架构本体 · 基础与第一性（Foundations）

> doc-kind: reference；authority: supporting（架构域 ontology 视图，实体/属性/关系/规则四段式）。
> 覆盖原 `ZKC-architecture-v1.2.md` §1（Know Why）/ §2（术语约定）/ §3（第一性不变量）/ §4（总体架构）。原文已拆解归档，本页与同目录 4 份共同承载其全部语义。
> 事实权威仍以代码/schema/ADR 为准（见 §5）；本页只做归并重组，不新增语义。冲突以 ADR / 代码为准。
> 术语护栏：双轨 ≠ 双时态；衰减 ≠ 衰减可控；归档 ≠ 墓碑。口径标记：`SIMULATION`=设计口径/占位，`CALIBRATED`=真实埋点校准。

## 0. 范围与读法

- 本页回答「系统为何这样设计、有哪几条不可动摇的公理、总体分几层」。具体 schema 见 `data-model.md`，算子见 `transforms.md`，调度/预算见 `scheduling-budget.md`，选型/风险/生命周期见 `selection-risk.md`。
- 读法：§1 实体查定义 → §2 属性查取值 → §3 关系查耦合 → §4 规则查不变量与状态。

---

## 1. 实体（Entity）

### 1.1 问题空间

- **两类异构信息**：静态（事实型 / 长生命周期 / 可演进）与动态（存活型 / 短生命周期 / 快速腐化 / 占注意力）。来源：原 §1。
- **硬约束**：长期时间精力有限 + 短期注意力有限 → 系统必须自决「此刻该关注什么、什么可安全衰减」。来源：原 §1。
- **复利变换层**：价值发生在变换而非存储——结合→建模/方法论、蒸馏→元认知+topic+反向连接、拓扑装配→自闭环↔更高维 context。来源：原 §1。

### 1.2 术语对象

- **双轨 dual-track**：信息类型 + 生命周期分类（静态 / 动态），核心语义是**衰减率与注意力成本**。来源：原 §2；glossary.md。
- **双时态 bitemporal**：时态建模机制（valid time + transaction time），核心语义是**事实演进与溯源审计**；只覆盖静态轨，不覆盖动态轨腐化与注意力稀缺。来源：原 §2。
- **caveat: moat-unverified-vs-mem0**：对外主张四项核心语义时必须附带的护城河未验证声明（mem0 因编译限制未纳入对照）。来源：原 §3。

### 1.3 分层架构

- **摄入层 ingest**：多源捕获 → 双轨分流（双信号弃权 + 转人工）。来源：原 §4。
- **存储层 store**：Postgres + pgvector；节点表（静态/动态轨）、双时态列、decay 分数、元认知 claim + 反向连接边、context 拓扑、向量列 + HNSW。来源：原 §4。
- **复利变换引擎 transform**：蒸馏（JSON 结构化抽取 + 校验重试）/ 结合建模（RCS 漏斗 + 双层合并）/ 拓扑装配（自闭环 ↔ 更高维）。来源：原 §4。
- **资源感知调度层 schedule**：decay 驱动 → 注意力信号 → 「该关注 / 可衰减」清单，并回灌摄入与变换。来源：原 §4。
- **LLM 运行时 llm**：Ollama 本地推理 + provider seam（LLM callable 注入）+ 复审队列 HITL（review_queue + /review UI）。来源：原 §4。
- **seam（可替换边界）**：storage / provider / encoder / transport 四道；存储是可替换基础设施，不是架构中心。来源：原 §3/§4；ZJ-CONTEXT.md。

---

## 2. 属性（Attribute）

| 实体 | 属性 | 取值 / 语义 | 来源 |
|---|---|---|---|
| 双轨 | 轨类型 | static / dynamic（+ 未决 unrouted 由分流产生） | 原 §2 |
| 双轨 | 核心语义 | 衰减率 + 注意力成本 | 原 §2 |
| 双时态 | 时间轴 | valid_time（事实演进） + transaction_time（溯源审计） | 原 §2 |
| 双时态 | 覆盖范围 | 仅静态轨；不覆盖动态轨腐化 / 注意力稀缺 | 原 §2 |
| 双轨 vs 双时态 | 等价性 | 不等价；引入双时态 ≠ 解决双轨问题 | 原 §2 |
| 四项核心语义 | 构成 | 双轨标签定义 / decay 衰减模型 / 双时态溯源 / 稀缺注意力调度 | 原 §3 |
| 四项核心语义 | 对外口径 | 必带 `caveat: moat-unverified-vs-mem0`，不得回退 3 项口径 | 原 §3；constraints.md §8.1 |
| 存储层 | substrate | Postgres + pgvector（本地/自托管） | 原 §4；原 §6 选型表 |
| LLM 运行时 | 默认栈 | Ollama 本地推理（Apple silicon 走 MLX） | 原 §4；原 §6 选型表 |
| 人审 | 载体 | review_queue + /review 复审队列 UI（非 LangGraph interrupt） | 原 §4；MVP 实装修订 2026-11-03 |

---

## 3. 关系（Relation）

方向记作 `主体 —[关系]→ 客体`。

### 3.1 五层主链路（原 §4 mermaid）

- 多源捕获 —[进入]→ 双轨分流（双信号弃权 + 转人工）。
- 双轨分流 —[不确定]→ 人工判定。
- 双轨分流 & 人工判定 —[汇入]→ 存储层。
- 存储层 —[供数]→ 复利变换引擎。
- 复利变换引擎 —[回写]→ 存储层。
- 存储层 —[供数]→ 资源感知调度层。
- 资源感知调度层 —[回灌]→ 摄入层 / 复利变换引擎。
- 复利变换引擎 —[送审]→ 复审队列 HITL → LLM 运行时 → provider seam。

### 3.2 语义耦合

- 双轨 —[区分于]→ 双时态（前者是分类+成本，后者是时态建模，禁互换）。来源：原 §2。
- 四类第一性不变量 —[对外必带]→ caveat: moat-unverified-vs-mem0。来源：原 §3。
- 存储 —[是]→ 可替换 seam；变换语义与调度策略 —[归属]→ ZKC 自己。来源：原 §3。
- 所有变换产物 —[必须]→ 可溯源（否则无法复用、无法形成复利）。来源：原 §3。
- 本地/离线 —[优先于]→ 云端 provider。来源：原 §3。

---

## 4. 规则（Rule）

状态：`已定` / `废弃`（仅溯源）/ `限定` / `保留观察` / `永久 caveat` / `未实现`。

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| G1 | 两类信息原生双轨建模，生命周期与操作语义分离，不在同一张「笔记表」混同 | 已定 | 原 §3 不变量 1 |
| G2 | 四项核心语义自建：双轨标签 / decay / 双时态 / 注意力调度；对外必带 caveat，不得回退 3 项 | 已定 | 原 §3 不变量 2 |
| G3 | 存储是可替换 seam，不是架构中心；变换语义与调度策略属 ZKC 自己 | 已定 | 原 §3 不变量 3 |
| G4 | 所有变换产物必须可溯源（回溯来源条目），否则无法复用/无复利 | 已定 | 原 §3 不变量 4 |
| G5 | 默认本地/离线优先（个人数据+隐私），云端仅作可切换 provider | 已定 | 原 §3 不变量 5 |
| G6 | 双轨 ≠ 双时态；文档中禁止互换；引入双时态 ≠ 解决双轨问题 | 已定 | 原 §2 |
| G7 | 复利发生在变换层而非存储层：结合→建模、蒸馏→元认知+topic+反向连接、拓扑装配→自闭环↔更高维 | 已定 | 原 §1 |
| G8 | 长期时间/短期注意力均有限 → 系统必须自决关注与可衰减对象 | 已定 | 原 §1 |
| G9 | 现有工具（OneNote/Obsidian/llm-wiki/gbrain/OKF）各只优化单一维度，无一能一站式承担 | 已定（问题陈述） | 原 §1 |

---

## 5. 来源与权威映射

| 本页实体/规则 | 原文档章节 | 事实权威 | 备注 |
|---|---|---|---|
| §1 问题空间、G7/G8/G9 | 原 §1 Know Why | PRD §1–2 | 问题与目标归 PRD |
| §1.2 双轨/双时态、G6 | 原 §2 术语约定 | glossary.md + ZJ-CONTEXT.md + PRD §2.0 | 术语精确定义归 glossary |
| §1.3 四项核心语义、G2 | 原 §3 不变量 2 | 架构 + constraints.md §8.1 + rec-avoid-gate.md | 对外口径三处同步 |
| §1.3 seam、G1/G3/G4/G5 | 原 §3 不变量 1/3/4/5 | 代码 / schema / ADR-0005 | — |
| §1.3 五层、§3.1 主链路 | 原 §4 总体架构 mermaid | 本页（重组视图）+ ta-data-flow.md（实现态） | 总图为架构视图，实现细节归 flow |
| caveat 声明 | 原 §3 + constraints | constraints.md + 架构 §3 原文（归档） | 唯一性未经 mem0 复核 |

> 原文档 §1–4 逐字正文见归档 `docs/evidence/architecture-v1.2-source-2026-11-19.md`。本页为去重重组，不复制论证长文。

---

## 原文件：`docs/ontology/zkc-arch/scheduling-budget.md`

# 架构本体 · 调度与预算（Scheduling & Budget）

> doc-kind: reference；authority: supporting（架构域 ontology 视图，实体/属性/关系/规则四段式）。
> 覆盖原 `ZKC-architecture-v1.2.md` §6.3（资源感知调度）/ §6.5（review_interval 三层）/ §6.5.1（budget_per_day 统计估计）+ §6 选型表中衰减/注意力/分流行 + §8 相关已定/未决条目。原文已拆解归档，本页与同目录 4 份共同承载其全部语义。
> 事实权威：阈值参数以 `tuning.REGISTRY` 为准；语义决策以 ADR（0002/0003/0006/0007/0009/0011/0012）为准；实现以代码为准。本页归并重组，不新增语义。
> 口径标记：`SIMULATION`=设计口径/占位（禁外推为 CALIBRATED）；`CALIBRATED`=真实埋点校准。

## 0. 范围与读法

- 本页回答「decay 怎么算、interval 三层怎么定、budget 怎么估、外生锚为何必需、verdict v2 如何改变反馈」。算子语义见 `transforms.md`，观测表结构见 `data-model.md`。
- 关键护栏：双轨 ≠ 双时态；衰减 ≠ 衰减可控；`decay-only` 反馈恒 no-op；收敛目标 `H/0.6` 非真值 H。

---

## 1. 实体（Entity）

- **decay 衰减**：线性函数 `min(1, elapsed / review_interval)`，衡量腐化程度；静态轨恒 0。来源：原 §6.3；ADR-0003。
- **行动窗口**：SURFACE(0.6) 到 ROT(0.9) 之间「还能救」的天数；interval=21d 时为 6.3 天。来源：原 §6.3。
- **注意力预算 attention budget**：硬约束；需求 = `动态条目数 / (0.6 × interval)`，预算 < 需求时腐化无解（rot=100%）。来源：原 §6.3。
- **review_interval**：「这条多久后腐化」的预测值；**双层量** = 个体基线 × 全局预算因子；分 L1/L2/L3 三层。来源：原 §6.5。
- **L1 基线**：条目自身暗示的腐化速率（个体）。来源：原 §6.5。
- **L2 预算归一化**：压进注意力预算（全局）。来源：原 §6.5。
- **L3 反馈**：用真实结果修正先验（闭环）。来源：原 §6.5。
- **标注率闸门**：L3 只认显式结果标注，不认 decay 数值；口径 = 滚动 7 天 `labeled_completed / completed`。来源：原 §6.5。
- **外生锚**：能证伪自证的外部 signal——复审结果标注（A）/ 真实完成数（B）。来源：原 §6.5.1；PRD §8。
- **budget_per_day**：每天容量上限，只能观测不能声明；删失感知统计估计。来源：原 §6.5.1；ADR-0006。
- **删失观测 censored observation**：日末有积压（饱和日）completed 是容量确证；日末清空 completed 只是下界。来源：原 §6.5.1。
- **活跃日 / 饱和日**：活跃日=真实复审发生（ADR-0007）；饱和日=日末有积压，预算唯一可用点估计样本。来源：原 §6.5.1；ADR-0007。
- **DecisionRouter / 双信号弃权**：分流器；前者本地 LLM 直接判轨（主方案、编码器无关），后者相似度阈值 OR 信息量下限（失败降级）；单信号不可分模糊/确定。来源：原 §6 选型；原 §8 Spike02/03；ta-data-flow.md。
- **诚实降级 infeasible**：预算不足时显式报告 `infeasible` + `max_dynamic_items`，禁静默拉长 interval。来源：原 §6.5。
- **复审队列（每日）**：调度层产品面；decay≥0.6 清单 + 结果标注 + 收口埋点；两个闭环唯一外生锚载体。来源：原 §6.3 末；PRD §6 流C。

---

## 2. 属性（Attribute）

| 实体 | 属性 | 取值 / 语义 | 来源 |
|---|---|---|---|
| decay | 函数形态 | 线性 min(1, elapsed/review_interval)；阶梯否决（窗口 0，rot=100%）；指数触发过晚（interval=21d 时 27.8d 才进注意力） | 原 §6.3；ADR-0003 |
| decay | 阈值 | SURFACE_THRESHOLD=0.6 / ROT_THRESHOLD=0.9；行动窗口 interval=21d→6.3d | 原 §6.3 |
| decay | 静态轨 | decay_score 恒 0 | 原 §6.5 L1；ADR-0003 |
| 注意力预算 | 需求公式 | 动态条目数 / (0.6 × interval)；按 interval 直接算低估约 40% | 原 §6.3 / §5 要点 |
| L1 基线 | 优先级序列 | 时间锚 clamp(horizon,0.25,180) > self_loop 3d > 已捕获 28d > 有 edge/higher_dim 14d > 孤儿 7d > 静态 NULL；多锚取最早；顺序即优先级 | 原 §6.5；ADR-0002 |
| L1 基线 | 下界 | MIN_INTERVAL_DAYS=0.25d（**SIMULATION 占位，非 CALIBRATED**；原 spike09 为 1d） | 原 §6.5 下界修订；ADR-0009 |
| L2 预算归一 | 规则 | 需求≤预算不动；否则按优先级升序延后（时间锚3>self_loop2>有连接1>孤儿/已捕获0），同级短 interval 先延后，每步 ×2；MAX=180d 仍超→infeasible + max_dynamic_items=budget×0.6×180 | 原 §6.5 |
| L3 反馈 | AIMD 机制 | decay<0.3→×1.5；0.3–0.9→不变；≥0.9→×0.7；钳制[0.25d,180d]；**v2 后不再由 verdict 触发（保留数学机制）** | 原 §6.5；ADR-0011/0012 |
| 标注率闸门 | 阈值 | ≥70%；窗口内完成 <10 不判定（放行避免 warm-up 冻结）；v2 后仅审计读数不改写 interval | 原 §6.5；PRD §6 流C |
| 预算估计 | 三道防线 | ①删失感知 p25 + 单调护栏（非饱和日只抬不压）+ 阻尼 EMA(α=0.3,±30%) + 校准期 oversubscribe×1.5；②护栏；③EMA | 原 §6.5.1 |
| 预算估计 | confidence | none / lower_bound / provisional / observed；无饱和日只报下界 max(completed)；无观测 L2 完全不动(warm-up) | 原 §6.5.1；ADR-0010 |
| 预算估计 | 仿真结论 | 真值 3/天 60 条：乐观 10→3.001、悲观 1→2.999（双向收敛）；护栏 ON 保持 10 不动，OFF 降到 6 | 原 §6.5.1 |
| 外生锚 | 两类 | A=复审结果标注（修 interval）/ B=每日真实完成数（修 budget）；缺锚闭环只自证 | 原 §6.5.1；PRD §8 |
| 分流 | DecisionRouter | 本地 LLM 直接判轨；编码器无关；F1（模糊误提交0）/F2（长模糊对抗句0进dynamic）完美、覆盖100%；主方案 | 原 §6 选型；spike03 |
| 分流 | 双信号弃权 | 相似度阈值 OR 信息量下限；模糊/确定在真编码器下仍 OVERLAP（nomic 模糊 max 0.894>明确 min 0.563） | 原 §8 Spike02 限定 |
| 收口埋点 | 字段 | pushed / completed / queue_remaining / labeled_completed | 原 §6.5.1；ta-data-flow.md |

---

## 3. 关系（Relation）

### 3.1 调度主链

- refresh_decay —[刷新]→ node.decay_score → list_due_for_review。来源：ta-data-flow.md。
- decay ≥ 0.6 —[触发]→ 进入注意力 / 复审队列；decay ≥ 0.9 → 判已腐化。来源：原 §6.3。
- 每日复审队列 —[产出外生锚]→ 复审标注（A）+ 真实完成数（B）。来源：原 §6.3 末；PRD §6 流C。
- queue_remaining —[喂给]→ estimate_budget_from / calibration_readiness → E1-③。来源：ADR-0007。
- estimate_budget_from —[估计]→ budget_per_day → 喂给 L2 预算归一。来源：原 §6.5.1；ta-data-flow.md。
- L2 fit_budget —[写]→ set_interval + audit_interval(kind=budget)；L3 adapt_interval_math —[写]→ audit_interval(kind=feedback)。来源：ta-data-flow.md。

### 3.2 三层耦合与对冲

- L1 基线 —[×]→ L2 预算因子 → 生效 review_interval。来源：原 §6.5。
- L3 缩短 interval —[放大需求 Σ1/(0.6×Iᵢ)，被 L2 反向对冲]→ 预算归一化。来源：原 §6.5；ADR-0009。
- 复审标注 —[v2 后终局动作（非 AIMD 乘因子）]→ nodes.save / set_baseline_interval / archive；decide_review **不调 adapt_interval**（DI-1 最硬）。来源：ADR-0011/0012。
- floor_hit（触及 0.25d）—[触发]→ archive + 审计 floor_hit_archive；human 节点提前返回。来源：ADR-0009。

### 3.3 自指闭环与外生锚

- budget → L2 拉长 interval → 供给变少 → 观测复审变少 → budget 更低（**自指链，每步都有数据支持**）。来源：原 §6.5.1。
- decay 是自己定义的（拉长 interval=不腐化）→ 需 L3 用户显式标注作外生锚；budget 的真实完成数是另一外生锚。来源：原 §6.5.1。
- decisionRouter —[失败降级]→ LexicalRouter 保持 unrouted → 入 review_queue(classify)。来源：ta-data-flow.md。

---

## 4. 规则（Rule）

状态：`已定` / `废弃` / `限定` / `保留观察` / `永久 caveat` / `未实现`。

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| S1 | decay 选线性；阶梯否决（窗口0）；指数备选；静态轨恒 0 | 已定 | 原 §6.3；ADR-0003 |
| S2 | 注意力是硬预算，需求=动态数/(0.6×interval)；预算<需求腐化无解（rot=100%），上线前必须反推校验 | 已定 | 原 §6.3；原 §8 |
| S3 | 保守起步宁少勿错——错误推送比不推送更伤注意力 | 已定 | 原 §6.3 |
| S4 | 已捕获=单程票：拉长观察(28d)→到期 ARCHIVE，永不回 DISTILL | 已定 | 原 §6.5；ADR-0002 |
| S5 | 撤销回退：produced_by 级联撤销后按未捕获基线重算（14d/7d），必须写 D7 留痕，禁静默 | 已定 | 原 §6.5；ADR-0002 |
| S6 | self_loop(3d) 压过已捕获(28d)（原 L1 表与 L2 优先级表顺序相反已修） | 已定 | 原 §6.5；ADR-0002 |
| S7 | interval_source='human' 全程豁免自动改写 | 已定 | 原 §6.5；原 §5 D6 |
| S8 | MIN_INTERVAL_DAYS=0.25d 是 SIMULATION 占位，禁写成 CALIBRATED 或写回 REGISTRY；<1d 只数值语义非日内复审能力 | 已定 | 原 §6.5 下界修订；ADR-0009 |
| S9 | L3 必须接显式复审标注，decay-only 反馈恒 no-op；收敛目标 H/0.6 非真值 H | 已定 | 原 §6.5；ADR-0009 |
| S10 | 标注率 <70% 或样本 <10 → L3 停机（v2 后闸门仅审计，不改写 interval） | 已定 | 原 §6.5；PRD §6 |
| S11 | 诚实降级：预算不足用 infeasible + max_dynamic_items 显式报告，禁静默拉长 interval | 已定 | 原 §6.5 |
| S12 | budget 是容量只能观测不能声明；删失感知，只有饱和日参与点估计(p25)，无饱和日只报 lower_bound | 已定 | 原 §6.5.1；ADR-0006 |
| S13 | 单调护栏：非饱和日只抬升预算永不压低；饱和日才允许下调 | 已定 | 原 §6.5.1 |
| S14 | 阻尼 EMA(α=0.3,±30%) + 校准期 oversubscribe×1.5，防低估固化 | 已定 | 原 §6.5.1 |
| S15 | 任何自指闭环需至少一个外生锚；缺锚闭环只自证 | 已定 | 原 §6.5.1；PRD §8 |
| S16 | 真实失败形态是错误的稳定均衡（固化）非发散；容量长期不可观测时唯一正确行为是 L2 保持宽松等积累 | 已定（记账） | 原 §6.5.1 预判修正 |
| S17 | 单信号不可分模糊/确定，采双信号弃权；长模糊句单向误判 dynamic（3/3 三编码器一致），长度仅弱代理、信息量门失效 | 已定（限定） | 原 §8 Spike02/03 |
| S18 | DecisionRouter 作主方案（编码器无关），3-way 路由仅强编码器(qwen3≥4096d)下安全，降级为候选预过滤 | 已定 | 原 §6 选型；spike03 |
| S19 | decide_review 对任何 outcome 都不得调 adapt_interval（DI-1 最硬）；changed/stale+cover 走终局动作，stale+purge 走 archive | 已定 | ADR-0011/0012；DI-1/DI-2 |
| S20 | 每日复审队列界面是 MVP 必选：无它则 interval 停基线、budget 停 warm-up，两闭环皆装饰 | 已定 | 原 §6.3 末；PRD §6 流C |
| S21 | L2 与 L3 方向对冲，calibrating/观测不足时可能互相抵消污染 budget 估计；真实取值须 ≥14d 埋点 + ≥3 饱和日门禁 | 已定 | 原 §6.5 边界3；原 §8 |
| S22 | 阈值全为占位（AIMD 1.5/0.7、×2 延后、±容忍带、p25、α=0.3、±30%、×1.5），振荡带约 ±50%，需真实数据校准 | 限定 | 原 §8 未决(3)；原 §6.5.1 |

---

## 5. 来源与权威映射

| 本页实体/规则 | 原文档章节 | 事实权威 | 备注 |
|---|---|---|---|
| §1–3 decay / interval 三层 / budget、S1–S18 | 原 §6.3 / §6.5 / §6.5.1 | 代码 + ADR（0002/0003/0006/0007/0009）+ tuning.REGISTRY | 阈值参数归 REGISTRY；本页为语义视图 |
| S4/S5/S6 单程票 | 原 §6.5 | ADR-0002 | 语义权威在 ADR |
| S8 下界 0.25d | 原 §6.5 下界修订 | ADR-0009 | SIMULATION 永久 caveat |
| S19 verdict v2 | ADR-0011/0012 | ADR-0011/0012 | v2 取代原 AIMD 反馈语义 |
| S12–S16 budget | 原 §6.5.1 | ADR-0006/0010 + 代码 | — |
| S17/S18 分流 | 原 §8 / §6 选型 | spike02/03 + ta-data-flow.md | — |
| 观测表字段 | 原 §5 D8 | data-model.md + 代码 | 结构归 data-model |
| 收口埋点端点 | 原 §6.3 末 | ADR-0007 + windows-install-and-run.md | POST /review/api/observe/auto |

> 原文档 §6.3/§6.5/§6.5.1 逐字正文（含四条边界、两条 spike 实测发现、下界修订全文）见归档 `docs/evidence/architecture-v1.2-source-2026-11-19.md`。本页保留全部规则语义与关键数值。

---

## 原文件：`docs/ontology/zkc-arch/selection-risk.md`

# 架构本体 · 选型·风险·生命周期（Selection, Risk & Lifecycle）

> doc-kind: reference；authority: supporting（架构域 ontology 视图，实体/属性/关系/规则四段式）。
> 覆盖原 `ZKC-architecture-v1.2.md` §6（核心子系统与选型表）/ §7（被拒绝/延后选项）/ §8（风险与未决）/ §11（墓碑软删 + TTL 真删）。原文已拆解归档，本页与同目录 4 份共同承载其全部语义。
> 事实权威：选型以代码 + ADR 为准；风险状态以 risks.md 为准；墓碑语义以 ADR-0013 为准。本页归并重组，不新增语义。
> 口径标记：`SIMULATION`=设计口径/占位，`CALIBRATED`=真实埋点校准。复利系数 source=SIMULATION，升 CALIBRATED 仍 open。

## 0. 范围与读法

- 本页回答「各子系统选了什么/拒绝什么、有哪些风险与降级、节点墓碑生命周期怎么处理」。具体 schema 见 `data-model.md`，复利度量算法口径见本页 §4，调度阈值见 `scheduling-budget.md`。
- §9（spike 清单）/ §10（PRD 校准 ledger）是过程态，按契约不进 ontology，随原文归档。

---

## 1. 实体（Entity）

### 1.1 选型对象

- **存储 substrate**：Postgres + pgvector（本地/自托管）；seam 可切 Kuzu（图变核心）/ TerminusDB（需原生版本控制）。来源：原 §6 选型表。
- **向量索引**：pgvector HNSW，与元数据同库可 JOIN。来源：原 §6 选型表。
- **embedding 编码器**：nomic-embed-text → vector(768)（已定 2026-10-31）；双列共存 embedding_4096（qwen3 4096d）为生产召回列。来源：原 §6 选型；spike14。
- **本地推理运行时**：Ollama（0.33.3 实测；Apple silicon MLX）；seam=任意 OpenAI 兼容端点。来源：原 §6 选型表。
- **蒸馏/结合模型**：qwen3.5:4b-mlx（迭代默认）/ 9b-mlx（可选上限）。来源：原 §6 选型表。
- **跨源综合**：由 Spike11 强制算子解决，与模型选型解耦。来源：原 §6 选型表；spike11。
- **复利度量**：五项——连接密度 / 复用率 / 方法论产出 / 衰减可控 / 复利系数；设计口径 source=SIMULATION。来源：原 §6 选型；原 §8；spike07。

### 1.2 风险与守门对象

- **rec-avoid 机械闸**：把护城河从口号落成版本门；三件套（去模型化测试 + check_invariant.py + 图库主存储 EXCLUDED）。来源：原 §7；ADR-0005；rec-avoid-gate.md。
- **去模型化测试**：去掉 LLM 后若 SilverBullet/logseq 可等价实现即稀释项，默认拒绝。来源：原 §7；ADR-0005。
- **check_invariant.py**：CI 谓词，守 evidence_refs NOT NULL、无关闭 decay/attention 全局开关、归档退出调度。来源：原 §7；rec-avoid-gate.md。
- **蒸馏质量度量（E8 锚2）**：漏检率（召回侧）/ 误蒸馏率（精确侧），zj 人工抽检；属系统外信号，与复利系数度量严格区分。来源：原 §8 E8 锚2；rec-avoid-gate.md。
- **复利系数度量（spike07）**：系统自算四项等权；source=SIMULATION，升 CALIBRATED open。来源：原 §8 已定条目。
- **忠实度闸门**：见 transforms.md；风险面为幻觉/危险漏检率。来源：原 §8。
- **provider seam**：常规抽取本地，元认知步骤可切强模型（应对本地小模型质量不足）。来源：原 §8。

### 1.3 生命周期对象

- **墓碑 tombstone**：node.deleted_at 非 NULL；全功能不可见、可恢复、TTL 后真删。来源：原 §11；ADR-0013。
- **三态模型**：active → tombstoned → purged；与 archived_at 正交。来源：原 §11。
- **引用闸门**：真删前扫 meta_claim.evidence_refs / modeling_artifact.evidence_refs（uuid[] 无 FK 手扫 @>）+ citation.citing_node_id；命中拒删 + 告警。来源：原 §11；ADR-0013。
- **真删 purge**：PG FK ON DELETE CASCADE 清级联数据；独立审计事件 node_deletion_audit（无 FK、不记 content）。来源：原 §11。
- **月扫**：TTL 7d 起算，月度门闩幂等，挂每日 automation 非侵入调用，不注册系统级调度；实际真删窗口 7~37 天。来源：原 §11。

---

## 2. 属性（Attribute）

### 2.1 选型取值

| 子系统 | 选型 | 依据 | 可替换 seam |
|---|---|---|---|
| 存储 | Postgres + pgvector | 依赖最少、可离线、事务/PITR 成熟 | Kuzu / TerminusDB |
| 向量 | pgvector HNSW | 与元数据同库可 JOIN | — |
| embedding | nomic 768d；embedding_4096(qwen3) 生产召回 | spike14：768d/9.5ms/274MB vs 4096d/183.2ms/4.7GB；R18 Recall@10=1.000/MRR=0.853 | encoder seam，双列共存 |
| 双轨分流 | DecisionRouter 主 + Semantic Router 候选预过滤 | spike03：编码器无关、F1/F2 完美、覆盖100% | Semantic Router / Outlines / DSPy |
| 本地推理 | Ollama 0.33.3 | 唯一原生本地/离线运行时 | 任意 OpenAI 兼容端点 |
| 蒸馏/结合模型 | qwen3.5:4b-mlx；9b 可选上限 | spike10：4B 复述率中位 0.10；9B 16GB swap | 云端强模型(provider seam) |
| 结构化抽取 | Ollama 原生 /api/chat + format:json | /v1 + response_format 对 qwen3.5-mlx 永久挂死 | Outlines |
| 编排/人审 | 自研确定性程序 + review_queue HITL | 蒸馏为确定性工作流，无需图编排 | 最小状态机(已采用) |
| 蒸馏语义 | ZKC 自研 | 无候选提供「去繁→元认知+topic+反向连接」 | — |
| 结合/建模 | ZKC 自研程序（RCS 漏斗+双层合并） | 无候选产出建模/方法论产物 | DSPy 编程模型 |
| 衰减 decay | ZKC 自研 · 线性 | 候选均无原生 TTL/腐化语义；线性 rot=0%、窗口6.3d | 指数(触发过晚) |
| 注意力调度 | ZKC 自研 | 所有候选均不覆盖 | — |

### 2.2 风险/度量取值

| 实体 | 属性 | 取值 / 语义 | 来源 |
|---|---|---|---|
| 复利系数 | 权重 / source | 四项等权 0.25×4，METRIC_METHOD_TARGET=10 / source=SIMULATION | 原 §8；tuning.py |
| 复利系数 | 真实快照 | cd=rr=mo=0、dc=1.0（归档假象）→ 三权重不可辨识；等权为 Dirichlet(1,1,1,1) 先验下 MSE 最小 | 原 §8 已定；scripts/metric_weights_sim.py |
| 升 CALIBRATED 门禁 | 条件 | ≥14d 埋点 + ≥3 饱和日 + zj 四分量价值排序；缺一不可 | 原 §8 仍 open；tuning.can_calibrate |
| 蒸馏质量度量 | 两率 / 样本 | 漏检率 / 误蒸馏率；9 gold / 17 claim，两率均 0%；证据弱（极小合成样本、同文档锚定偏倚） | 原 §8 E8 锚2 |
| E8 锚2 结论 | 限定 | 仅限蒸馏环节；0% 不能证伪蒸馏质量；不替代 spike12/13 HITL 定案；待真实长文档复测 | 原 §8 E8 锚2；risks.md |
| 图库主存储 | 决定 | EXCLUDED（显式拒绝），仅 Kuzu 只读投影 | 原 §7；ADR-0005 |
| 16GB 硬件 | 约束 | 9B 常驻 10–12GB、swap 用满 17–21GB；迭代默认 4B | 原 §8 Spike10 限定⑥ |

### 2.3 墓碑取值

| 实体 | 属性 | 取值 / 语义 | 来源 |
|---|---|---|---|
| 墓碑 | is_delete / deleted_at | 1=墓碑（deleted_at 非 NULL，TTL 起算）/ 0=恢复（human-only） | 原 §11；ADR-0013 |
| 墓碑 | TTL / 扫描 | 7d 起算、月扫（非 daily）、真删窗口 7~37 天 | 原 §11；ADR-0013 |
| 墓碑 | 可见性 | 所有默认读取路径加 deleted_at IS NULL，不受 include_archived 控制；P4 静态守门 | 原 §11 |
| 墓碑 | 实现落点 | migrations/0011_node_tombstone；zkc/tombstone.py、purge_gate.py、purge.py、sweep.py | 原 §11 |
| 审计 | node_deletion_audit | 记 id/title/时间/TTL/操作者，不记 content、node_id 无 FK | 原 §11；ADR-0013 |

---

## 3. 关系（Relation）

### 3.1 选型与拒绝

- 存储 —[选型]→ Postgres + pgvector；Kuzu —[仅只读投影]→ 存储（不得当主存储）。来源：原 §6/§7；ADR-0005。
- 图数据库(Kuzu/TerminusDB) —[EXCLUDED]→ 主存储（递归 CTE 足够，保持 seam 可切）。来源：原 §7；ADR-0005。
- 换世代(1.5B→Qwen3.5) —[显著降复述率]→ 蒸馏/结合质量；跨源综合 —[由]→ Spike11 算子解决。来源：原 §6 选型；原 §8。
- 本地小模型质量不足 —[缓解]→ provider seam 切强模型。来源：原 §8。
- 复利度量 —[严格区分于]→ 蒸馏质量度量（E8 锚2）；锚2 抽检 —[不构成]→ spike07 权重校准证据。来源：原 §8 E8 锚2。

### 3.2 rec-avoid 守门

- 去模型化测试 + check_invariant.py + 图库 EXCLUDED —[组合为]→ rec-avoid 版本门。来源：原 §7；ADR-0005。
- rec-avoid gate —[守门]→ 任何新增功能 PR（须附去模型化测试结论）。来源：rec-avoid-gate.md。
- 四项第一性特征 —[对外必带]→ caveat: moat-unverified-vs-mem0。来源：原 §3（归档 foundations.md）；constraints.md。
- 图库主存储「延后」—[改为]→「EXCLUDED」+ 拒绝理由行（ADR-0005 驱动）。来源：原 §7。

### 3.3 墓碑生命周期

- active —[tombstone mark（operator 必填，与 verdict 同级门禁）]→ tombstoned。来源：原 §11；ADR-0013。
- tombstoned —[全功能不可见]→ 所有默认读取路径 + P4 静态守门（不受 include_archived 控制）。来源：原 §11。
- tombstoned —[restore（is_delete=0，仅 zj 本人）]→ active。来源：原 §11；ADR-0013。
- 墓碑满 7d —[经引用闸门]→ 真删；引用命中 —[拒删]→ tombstone_purge_blocked + 告警。来源：原 §11。
- 真删 —[CASCADE]→ node_history / edge / context_member / citation / interval_adjustment / proposal_log / review_queue；—[留]→ 独立审计事件。来源：原 §11。
- 归档(archived_at) —[区别于]→ 墓碑(deleted_at)：前者退出调度仍可查阅，后者不可见且真删；二者正交。来源：原 §11；ZJ-CONTEXT.md。

---

## 4. 规则（Rule）

状态：`已定` / `废弃` / `限定` / `保留观察` / `永久 caveat` / `未实现`。

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| L1 | 四项第一性特征对外必带 caveat: moat-unverified-vs-mem0，不得回退 3 项口径 | 已定 | 原 §3/§7；constraints.md |
| L2 | 整体采纳开源知识应用拒绝，只做 unit-capability 复用 | 已定 | 原 §7 |
| L3 | Utopia/OpenWiki 重述为模式源，非待验证候选 | 已定 | 原 §7 |
| L4 | 图数据库作主存储 EXCLUDED，仅 Kuzu 只读投影 | 已定 | 原 §7；ADR-0005 |
| L5 | LiteLLM / Argilla / Langfuse / Electric·Automerge 延后（MVP 单人单机） | 已定（延后） | 原 §7 |
| L6 | XTDB 待带外验证（pinned 编译器无法解析 submodule 树） | 限定 | 原 §7 |
| L7 | Cordis/dsh 拒为编排层依赖，重述为模式源 | 已定 | 原 §7；ADR-0005 |
| C1 | rec-avoid 三件套守门：去模型化测试 + check_invariant + 图库 EXCLUDED；新功能 PR 须附去模型化结论 | 已定 | 原 §7；ADR-0005 |
| C2 | check_invariant 不可破：evidence_refs NOT NULL、无关闭 decay/attention 全局开关、归档退出调度 | 已定 | 原 §7；ADR-0005 |
| C3 | 复利系数 source=SIMULATION，四项等权 0.25×4；升 CALIBRATED 需 ≥14d 埋点 + ≥3 饱和日 + zj 价值排序，缺禁写 CALIBRATED/伪造标注 | 已定 | 原 §8；risks.md S2 |
| C4 | 锚2 蒸馏质量抽检 vs spike07 复利系数是两套度量，严格区分，互不充当校准证据 | 已定 | 原 §8 E8 锚2；risks.md |
| C5 | 单次采样不可信，结论须基于多次采样分布；比率须附绝对数量（≥2 跨源 claim）；强限定不得外推 | 已定 | 原 §8 Spike10 限定；constraints.md |
| C6 | 被推翻处记为偏差，不得静默接受 | 已定 | 原 §8 末；PRD §9 |
| C7 | 质量口径已可自动计算（复述率/overlap/跨源率/引用命中/结构完整），采样噪声可翻转单次结论 | 已定 | 原 §8 已定 |
| T1 | DI-5「无物理删除」被推翻，新增三态 active→tombstoned→purged | 已定（推翻 DI-5） | 原 §11；ADR-0013 |
| T2 | 墓碑对所有功能不可见（10 读取路径 + P4 静态守门），不受 include_archived 控制 | 已定 | 原 §11；ADR-0013 |
| T3 | restore 仅 zj 本人，与 verdict 同级 human-only 门禁 | 已定 | 原 §11；ADR-0013 |
| T4 | 真删前扫 evidence_refs + citation.citing_node_id，有引用拒删不 CASCADE，无引用才 CASCADE | 已定 | 原 §11；ADR-0013 |
| T5 | 月扫 TTL 7d 起算、幂等、挂每日 automation 非侵入，不注册系统级调度；真删窗口 7~37 天 | 已定 | 原 §11；ADR-0013 |
| T6 | 真删后留独立审计事件，不记内容、不引用已删 node | 已定 | 原 §11；ADR-0013 |
| T7 | P1/P2/P3 不变式保持不动，新增 P4（墓碑对所有读取路径不可见）；阈值常量未改，与墓碑可见性解耦 | 已定 | 原 §11 |
| T8 | 仅 2 条占位节点触发墓碑，不扩大到「一类节点治理」除非后续同类实证 | 限定 | ADR-0013 |

---

## 5. 来源与权威映射

| 本页实体/规则 | 原文档章节 | 事实权威 | 备注 |
|---|---|---|---|
| §1.1/§2.1 选型表 | 原 §6 选型表 | 代码 + ADR + spike README | 选型语义归 ADR，实现归代码 |
| §1.2/§2.2 风险与度量、C3–C7 | 原 §8 | risks.md + ADR-0010/0011/0012 + tuning.py | 风险状态归 risks.md |
| §1.3/§2.3/§3.3 墓碑、T1–T8 | 原 §11 | ADR-0013 | 语义权威在 ADR |
| §3.1 图库 EXCLUDED、L4/C1 | 原 §7 | ADR-0005 + rec-avoid-gate.md | — |
| 蒸馏质量度量 E8 锚2 | 原 §8 E8 锚2 | docs/evidence/e8-anchor2-sampling-kit.md + rec-avoid-gate.md | 证据弱、待真实复测 |
| 复利系数设计口径 | 原 §8 已定 | scripts/metric_weights_sim.py + tuning.py | source=SIMULATION |
| §9/§10 过程态 | 原 §9/§10 | 不进 ontology | 随原文归档 |

> 原文档 §6 选型表 / §7 / §8 / §11 逐字正文（含 Spike10 六条限定、Spike02 四条限定、各已定/未决条目全文）见归档 `docs/evidence/architecture-v1.2-source-2026-11-19.md`。本页保留全部选型取值、风险状态与生命周期规则。

---

## 原文件：`docs/ontology/zkc-arch/transforms.md`

# 架构本体 · 复利变换算子（Transforms）

> doc-kind: reference；authority: supporting（架构域 ontology 视图，实体/属性/关系/规则四段式）。
> 覆盖原 `ZKC-architecture-v1.2.md` §6.1（蒸馏）/ §6.2（结合建模）/ §6.4（Cordis/DeepSeek Harness 模式借鉴）+ §6 选型表中蒸馏/结合/编排相关行。原文已拆解归档，本页与同目录 4 份共同承载其全部语义。
> 事实权威：算子实现以 `src/zkc/` 代码为准；语义决策以 ADR / spike README 为准。本页归并重组，不新增语义。
> MVP 实装修订（2026-11-03）：Instructor / LangGraph **未进入 MVP 实装**；LLM 调用为 Ollama 原生 `/api/chat` + `format:json` + 手写校验重试（`src/zkc/llm.py`，零编排依赖），HITL 为 review_queue + /review 复审队列。spike 期选型记录保留作决策历史。

## 0. 范围与读法

- 本页回答「三类变换算子各自做什么、用什么模式、产出什么、有哪些不变量」。调度/预算见 `scheduling-budget.md`，数据模型见 `data-model.md`。
- 三类算子：蒸馏 / 结合 / 拓扑装配；对外统称复利变换引擎（半自动、人可干预）。

---

## 1. 实体（Entity）

- **蒸馏算子 distill**：条目 → 结构化抽取 → 确定性程序 → 入 review_queue → /review UI 人工确认/修改 → 写入 meta_claim（带 evidence_refs）。来源：原 §6.1。
- **结合/建模算子 combine**：多条信息合成建模/方法论产物，显式 Python 程序（`src/zkc/cross_source.py`，无编排框架）。来源：原 §6.2。
- **拓扑装配 assembly**：把条目装配进 context，含自闭环 ↔ 更高维两方向。来源：原 §4；原 §6.4。
- **RCS 漏斗**：源自 PaperQA2；top-k 检索 → 每源一条 query 条件下上下文摘要 → LLM 重排打分 → 来源数上限 → 单次生成。来源：原 §6.2。
- **双层合并**：源自 LightRAG；local（实体级细节）+ global（关系链 / 更高维）。来源：原 §6.2。
- **层级汇总思路**：源自 GraphRAG，**仅借鉴模式、不引入依赖**（项目维护模式）。来源：原 §6.2。
- **跨源强制算子 CrossSourceCombineOperator**：提示层硬约束（≥2 条跨源综合断言）+ bounded 单次补全回路；spike11 实证跨源综合是算子层问题、非模型规模。来源：原 §8/§9⑧；spike11。
- **忠实度闸门 faithfulness gate**：分解式 LLM-as-judge（机制可行）但本机 4B/9B 不可用；MVP 定案 human-in-the-loop + 字面 rubric 预过滤。来源：原 §8 Spike12/13/13b。
- **Cordis / DeepSeek Harness（dsh）**：**非依赖、仅模式源**；三点可迁移模式。来源：原 §6.4；原 §7。
- **produced_by（级联撤销根）**：变换实例 id；所有变换产物携带它，删除变换时副作用随之撤走。来源：原 §6.4；原 §5。
- **review_queue HITL**：蒸馏/人审的载体（原设计 LangGraph interrupt/resume，MVP 落为复审队列）。来源：原 §6.1；原 §6 修订注。

---

## 2. 属性（Attribute）

| 实体 | 属性 | 取值 / 语义 | 来源 |
|---|---|---|---|
| 蒸馏算子 | 抽取方式 | Ollama 原生 `/api/chat` + `format:json` + 校验失败手写重试（原 Instructor 走 /v1 对 qwen3.5-mlx 永久挂死，否决） | 原 §6 选型；spike04；MVP 修订 |
| 蒸馏算子 | 语义契约 | 结果必须是元认知 claim + topic + 反向连接，**不是摘要** | 原 §6.1 |
| 蒸馏算子 | ollama_chat 参数 | format:json / think:false / num_ctx=8192 / num_predict=1024 | ta-data-flow.md |
| 结合算子 | 实现 | 显式 Python（`src/zkc/cross_source.py`），无编排框架（原写 DSPy/LangGraph，实装未引入） | 原 §6.2；MVP 修订 |
| 结合算子 | 产出约束 | 带来源引用的结构化建模产物；evidence_refs NOT NULL + 手写 JSON 校验，非自由文本 | 原 §6.2 |
| 跨源强制算子 | 硬约束 | ≥2 条跨源综合断言；补全回路 bounded 单次，全崩保留主产物 | 原 §9⑧；spike11 |
| 跨源强制算子 | 实证结论 | 4B ×3 稳定 3/3、ncross 1–2→2–3、补全 0 触发；1.5B 无溢出（0/3） | 原 §9⑧；spike11 |
| 忠实度闸门 | 机制 | 拆原子事实→逐条 supported/unsupported/contradicted→确定性推导 overall，不信任模型自总结（14 tests） | 原 §8；spike12 |
| 忠实度闸门 | 本机可用性 | 4B ~110-130s/条不产 JSON；9B ~6min/条 JSON 不合规（吐 Label/Evidence/Overall）→ 判定能力对，死因是速度与格式 | 原 §8；spike13/13b |
| 忠实度闸门 | MVP 定案 | human-in-the-loop + 字面 rubric 预过滤（Spike13 降级链第 2 级）；自动 LLM 预过滤层本机推迟 | 原 §8 已定 |
| 蒸馏/结合模型 | 迭代默认 / 上限 | qwen3.5:4b-mlx / 9b-mlx 可选（9B 在 16GB 触发 swap，单次 4.7 分钟） | 原 §6 选型；spike10 |
| LLM 运行时 | 栈 | Ollama（0.33.3 实测全通过；Apple silicon 走 MLX） | 原 §6 选型 |
| 结构化抽取 | seam | ~~Instructor~~ → Ollama 原生；可替换 Outlines | 原 §6 选型 |
| 编排/人审 | seam | ~~LangGraph~~ → 自研确定性程序 + review_queue HITL；可替换最小状态机（已采用） | 原 §6 选型 |

---

## 3. 关系（Relation）

- 条目 —[进入]→ 蒸馏算子 → 产出 meta_claim（带 evidence_refs）+ LLMCallScore。来源：原 §6.1；ta-data-flow.md。
- 蒸馏算子 —[入队]→ review_queue → /review UI 人工确认/修改 → 写入 meta_claim。来源：原 §6.1。
- 多源条目 —[进入]→ 结合算子 → 产出 modeling_artifact + context。来源：原 §6.2；ta-data-flow.md。
- 结合算子 —[复用]→ RCS 漏斗 + 双层合并 + 层级汇总思路。来源：原 §6.2。
- 跨源强制算子 —[作用于]→ 结合算子的提示层（≥2 跨源断言 + 补全回路），schema 未动。来源：原 §9⑧；spike11。
- 忠实度闸门 —[预过滤]→ 字面 rubric（verbatim/overlap/citation_hit）→ HITL 兜底。来源：原 §8。
- 元认知 claim —[反向连接]→ 源节点（reverse_link）；源节点 —[derived_from]→ claim。来源：原 §5；PRD §4。
- 所有变换产物 —[携带]→ produced_by → transform（可级联撤销）。来源：原 §6.4。
- 变换 —[送审]→ 复审队列 HITL → LLM 运行时（E1→E2 provider seam）。来源：原 §4；原 §6.1。

### 3.1 Cordis / dsh 模式迁移（原 §6.4）

- append-only 事件流 = SSOT，context 从流投影 —[同构于]→ ZKC 双时态（transaction_time↔追加记录，valid_time↔当前视图）；**背书非新依赖**，写入保持 append-only（闭合 valid_to/tx_to，不改写历史行）。
- spatiotemporal composability（副作用可完全回滚）→ 变换产物须可追溯、可撤销（统一 produced_by 级联）。
- 「一切皆插件」的可替换边界 → 印证 storage / encoder / provider seam；算子保持可替换，编排层不渗透领域语义。
- Cordis/dsh —[拒绝为依赖，重述为模式源]→ 双栈分裂（Python 领域 + TS harness）、session 自有事件流无法落 PG 同库、HITL 仅轨迹级、把 decay_score/evidence_refs 塞进事件流丢 schema 校验。

---

## 4. 规则（Rule）

状态：`已定` / `废弃` / `限定` / `保留观察` / `永久 caveat` / `未实现`。

| 规则 | 内容 | 状态 | 来源 |
|---|---|---|---|
| X1 | 蒸馏结果必须是元认知 claim + topic + 反向连接，不是摘要 | 已定 | 原 §6.1 |
| X2 | 结合产物必须带来源引用的结构化产物（evidence_refs NOT NULL），非自由文本 | 已定 | 原 §6.2 |
| X3 | 层级汇总仅借鉴 GraphRAG 模式，不引入依赖 | 已定 | 原 §6.2 |
| X4 | 所有变换产物带 produced_by，可级联撤销；删除变换副作用随之撤走 | 已定 | 原 §6.4；原 §5 |
| X5 | 变换产物统一 append-only 双时态写入（闭合 valid_to/tx_to，不改写历史行） | 已定 | 原 §6.4 模式1 |
| X6 | 跨源综合缺口在算子/提示层可解（≥2 硬约束 + 单次补全），与模型规模解耦；但能力下限由模型结构化能力决定（1.5B 不可用） | 已定（限定） | 原 §9⑧；spike11 |
| X7 | 忠实度闸门 = HITL + 字面 rubric 预过滤；自动 LLM 预过滤本机推迟（更快硬件/离盒/云端可零改动启用 judge.py） | 已定 | 原 §8；spike12/13/13b |
| X8 | 分解式判定不信任模型自总结，逐原子事实确定性推导 overall | 已定 | 原 §8；spike12 |
| X9 | 结构化抽取走 Ollama 原生 /api/chat + format:json；禁 /v1 + response_format（对 qwen3.5-mlx 永久挂死） | 已定 | 原 §6 选型；Ollama 铁律 |
| X10 | think:false + num_ctx=8192；num_predict 给足 | 已定 | ta-data-flow.md；Ollama 铁律 |
| X11 | 蒸馏为确定性领域工作流，不引入 LangGraph；人审走 review_queue | 已定（MVP 修订） | 原 §6 选型修订注 |
| X12 | Cordis/dsh 不作 ZKC 依赖，仅作模式源；引入造成双栈分裂且丢 schema 校验 | 已定 | 原 §7；原 §6.4 边界警示 |
| X13 | 1.5B 产物为摘要堆砌（模型规模问题，记账）；语义质量走 provider seam 切强模型，选型不推翻 | 已定（限定） | 原 §9 项4/项5；spike04/05 |
| X14 | 幻觉判定 / 阈值校准 / golden 规模（现 13 例）仍 open | 未实现 | 原 §8 已定⑥ |

---

## 5. 来源与权威映射

| 本页实体/规则 | 原文档章节 | 事实权威 | 备注 |
|---|---|---|---|
| §1–2 蒸馏/结合/跨源/忠实度 | 原 §6.1 / §6.2 / §8 / §9⑧ | `src/zkc/llm.py` + `cross_source.py` + spike README | 实现归代码，语义归 ADR/spike |
| §3.1 Cordis 模式 | 原 §6.4 / §7 | 原文档归档 + ADR-0005 | 跨项目研究非本仓权威 |
| X9/X10 Ollama 铁律 | 原 §6 选型 + ta-data-flow | 代码 + ta-data-flow.md | 原生 /api/chat 禁 /v1 |
| X7 忠实度闸门 | 原 §8 Spike12/13/13b | spike README + ADR | — |
| produced_by 级联 | 原 §6.4 + §5 | 代码 schema + ADR-0002 | 撤销回退归 ADR-0002 |
| 蒸馏语义契约 | 原 §6.1 | PRD §4 + 代码 | — |

> 原文档 §6.1/§6.2/§6.4 逐字正文见归档 `docs/evidence/architecture-v1.2-source-2026-11-19.md`。本页为去重重组。
