# ADR-0013 · 节点墓碑软删除 + TTL 真删语义（DI-5「无物理删除」被推翻）

Status: accepted（2026-11-16，zj 于 16:10–16:24 逐条裁决 Q1–Q9；同轮明确推翻 DI-5）

## 边界声明（读前必读）

本 ADR 是**语义决策定案**记录，沉淀自 zj 2026-11-16 对「物理删除」真实需求的 9 轮 grilling（Q1–Q9）。它只定「要什么语义、推翻哪条旧约束」，**不定技术方案、不代表代码已改**。

- **实现状态 = 未设计、未实现、未授权落码**：墓碑标记 `is_delete`、全功能不可见谓词、TTL 月扫真删、引用检查、恢复入口、独立审计事件——均**尚未进入源码**。技术方案属本轮过程态 roadmap 的阶段二（in_progress），实施属阶段三（pending，待方案批准）；过程态路径不在此具名（ADR-0008 护栏，见 §验证证据）。任何「系统已支持物理删除」的表述均属误读。
  - **〔2026-11-16 阶段三末时点更新〕**：上句为方案批准前的历史状态陈述，保留原文；S1–S7 已落码（详见 §实施跟进）——代码能力已就绪，但**尚未对任何具体节点执行 mark/purge**（删除意图仍须 zj 逐条给）。两者不矛盾：上句记「决策当时未实现」，本注记记「阶段三末已实现能力、未施加意图」。
- **本 ADR 是决策定案，不是规格链、不是 TDD 证据**：无红绿输出、无 `make test` 增量、无真值回读对照。规格与测试须在阶段二/三另立。
- **权威依据**：所有裁决来自 zj 本人逐条拍板，逐字记录已沉淀至 `docs/evidence/physical-delete-decisions-2026-11-16.md`（原 roadmap carrier `1-1` 下 Q1–Q9 decisions 的过程态副本已随文档治理移除），原始工作日志 `.workbuddy/memory/2026-11-16.md`（16:10 / 16:24 段）。**逐字归档是历史记录、非权威 proof**（ADR-0008 / 护栏 #9）；本 ADR 才是持久权威。
- **不冒充 CALIBRATED、不污染 1-26 口径**：本 ADR 不改 `tuning.py` 任何阈值常量，不写回 `REGISTRY`。SURFACE=0.6 / ROT=0.9 / PRESSURE_DEFER=0.8 仍是 SIMULATION。
- **与历史 ADR 的关系**：DI-5「无物理删除」（ADR-0012 §9 DI-5，及 ADR-0011 定案语境、cutover §4/§7、risks.md R15 的对应陈述）在 2026-11-14 是当时的硬约束，**其历史原文一字不改**；本 ADR 记录 zj 2026-11-16 的显式推翻，旧文档仅追加 superseded 指针。

## 背景与触发

2026-11-16 每日循环中，两条 Obsidian vault 镜像目录索引节点（`a5de32cd…` BestPractices、`3f324c13…` ClaudeAPIDocs）进入待复审队列：content 均为 27 字占位「（目录索引 · 镜像自 Obsidian vault）」、`version_seq=60`（已被复审 60 次）、context/source 全空。zj 判「没有有效内容，可删除」，但系统 verdict 枚举无 delete、仓储只有 `archive`，由此展开 9 轮需求对齐。

关键事实调查（只读，均代码可核对）：

- 全库 SQL 直连 68 节点 / 38 未归档，含占位文本恰好 2 条 = 本次两条（**个案，非一类**）。
- 节点进入 Human-review 共两类入口：到期复审队列 `list_due_for_review`（pg.py:298，decay≥0.6 + interval 到期 + 未归档）与 `review_queue` 入队（`classify`/`distill`/`abstain`/`archive`，当前 open=0）。这两条走前者，60 次复审即 60 次到期回队。
- `meta_claim.evidence_refs` / `modeling_artifact.evidence_refs` 是 `uuid[]` **无外键**（仅 GIN 索引，migrations/0001:80,96,110,116）；其余 7 处引用 node 的 FK 均 `ON DELETE CASCADE`。故真删 node 时 CASCADE 清不掉 `evidence_refs` 数组里的 UUID → 悬空引用；P1 静态检查（`check_invariant.py:27,115`）只验 `uuid[] NOT NULL`，**查不出悬空**。
- 运行时污染入口是 `discover_higher_dim`（pg.py:1255-1278）的 kNN 近邻召回 **无 `archived_at` 谓词、无 decay 下限**，其结果喂给 `context.propose_higher_dim`（context.py:173）生成高维装配提议。其余路径（search / browse / list_due / load_schedulable / corpus）默认已排除 archived。

## 决策（Q1–Q9，zj 原话逐字保留）

### Q1 · 终局语义 = 墓碑软删除 + 全功能不可见 + TTL 真删（语义 D）

zj 原话：「软删除，类似于 db 表里标 `is_delete=1` 但不真实删除，对所有功能不可见；持续一段时间不标 `is_delete=0` 就真删除。」

结论：既非 A 永久归档、也非立即 C 真删，而是 **D = 墓碑标记（is_delete=1）→ 全功能不可见 → TTL 到期未恢复则真删**。明确提出「真删除」，与 DI-5 正面冲突（见 Q8 裁决）。

### Q2 · 触发动机（两者都要，逐字保留）

zj 原话：「两者都要。完整考虑如下：1、防止已经腐化的节点被误用，污染各种运行时上下文的知识有效性和可信度；2、节约复审注意力；3、删除对应的是『已经明确无用了，真要用到能接受一次重新摄入的成本』，归档对应的是『日常用不到，但很小概率需要查阅时它还在』。以删除的方式精简掉，既有运行时的效率收益，也有存储空间的节约。」

结论：三条动机并列采纳。第 1 点由 Q9 裁决的解法承担，第 2 点由墓碑承担，第 3 点是删除语义的独立理由。

### Q3 · 归档为何不够

由 Q2 第 3 点回答：归档与删除是不同语义。zj 要的删除 = 明确无用、小概率查阅不值得保留、可接受一次重摄入成本；归档的「它还在」在此需求里不是收益而是负担（运行时效率 + 存储空间）。

### Q4 · 是否推翻 DI-5

由 Q8 裁决承担（Q4 在 Q1 展开时已被覆盖；其决策记录为事后归档，原话逐字在 Q8）。结论：接受推翻。

### Q5 · TTL 时长 / 起算点 / 扫描周期

zj 原话：「TTL 时长 = 7 天；起算点 = 墓碑时刻；定期跑扫描，但 daily 的周期太短，软删除已经可以保证 动机 1（污染）+ 2（复审注意力），可以设置按月扫描。」

结论：TTL = 7d，从置 `is_delete=1` 时刻起算；扫描按月（非 daily）。**已记并接受的副作用**：7d TTL + 月扫 → 实际真删发生在墓碑后第 7~37 天，非精确第 7 天（因软删除已即时屏蔽污染与复审，此延迟可接受）。每日入口仍负责软删除可见性，月度扫描只做「墓碑满 7d → 真删」批量清理；不注册系统级调度。

### Q6 · 真删范围（级联与悬空引用）

zj 原话：「Q6 同意推荐」（推荐 = 删前扫 `evidence_refs` + `citing_node_id`，有引用就拒绝真删并报错）。

结论：真删前检查引用——`meta_claim` / `modeling_artifact` 的 `evidence_refs` 数组 + `claim_evidence.citing_node_id`，任一存在对该节点的引用 → **拒绝真删并报错，不 CASCADE**；无引用才允许删。目的：避免悬空引用破坏知识链完整性（P1 静态检查查不出 `uuid[]` 悬空，必须由删除路径自己守）。无外部引用时，`node_history` 与 edge / context_member / interval_adjustment / proposal_log.seed 随行 CASCADE 清除可接受。

### Q7 · 墓碑期恢复

zj 原话：「Q7 同意推荐」（推荐 = CLI + web、仅 zj 本人、与 verdict 同级人环门禁）。

结论：墓碑期可恢复，`is_delete=0` 反向操作要做；入口 CLI + web，仅 zj 本人触发，与 verdict 同级 human-only 门禁（不得由系统自动或批量脚本默认恢复）。墓碑期 = 置 `is_delete=1` 起至真删前（TTL 7d，月扫，实际窗口 7~37 天）。

### Q8 · 审计事件 + 明确推翻 DI-5

zj 原话：「Q8 保留审计事件，明确确认推翻 ADR-0011/0012 的 DI-5『无物理删除』。」

结论：① 真删后留**独立审计事件**（记 id/title/删除时间/TTL/操作者，不记内容）；该审计事件本身不引用已删 node 行（否则又成新悬空），须独立于 `evidence_refs` 体系。② **zj 明确裁决推翻 DI-5**——ADR-0011/0012 + cutover 三处「无物理删除」硬约束就此失效，引入节点真删除语义。

### Q9 · 运行时污染的解法（软删除承担，删除不作纵深防御）

zj 原话（Q5 内）：「软删除已经可以保证 动机 1（污染）+ 2（复审注意力）。」

结论：接受由墓碑软删除（`is_delete=1` + 全功能不可见）承担运行时污染与复审注意力，不再要求删除作为这两点的纵深防御。**推论（必做项，非旁路）**：既然 `is_delete` 要「对所有功能不可见」，所有读取路径（含 `discover_higher_dim`）都必须认 `is_delete` 谓词——这是软删除语义自身的落地要求。真删在 zj 语义里独立承担动机 3（存储 / 运行时精简），按月扫描执行。

## 决策汇总（规格输入，供阶段二消费）

| 维度 | 裁决 |
|---|---|
| 终局语义 | 墓碑 `is_delete=1` → 全功能不可见 → TTL 真删（语义 D，非 A 归档非立即 C） |
| 动机 | ①防运行时污染 ②省复审注意力 ③明确无用+可接受重摄入+存储/运行时精简（三者并列） |
| 污染解法 | 软删除承担；`is_delete` 谓词进**全部**读取路径（含 discover 漏洞） |
| TTL | 7d / 墓碑时刻起算 / 月扫（实际真删落在 7~37 天） |
| 级联 | 删前扫 `evidence_refs`（无 FK）+ `citing_node_id`，有引用拒绝真删；无引用才 CASCADE |
| 恢复 | `is_delete=0`，CLI + web，仅 zj 本人，与 verdict 同级人环门禁 |
| 审计 | 独立审计事件（不引用已删 node，不记内容）；明确推翻 DI-5 |
| 扫描调度 | 挂现有入口，按月触发；不注册系统级调度 |

## Considered Options

- **A 永久归档（拒绝）**：`stale purge` 已存在，但无 TTL 真删、不满足动机 3（存储/运行时精简），且现存 `archive` 不等于运行时不可见（discover 漏洞）。
- **C 立即物理删（拒绝）**：无墓碑期、不可逆、无反悔窗口；且直接 CASCADE 会留下 `evidence_refs` 悬空。
- **D 墓碑软删 + TTL 真删（采纳）**：先软删即时屏蔽污染/复审，给 7 天反悔窗口，月扫批量真删，删前引用检查护知识链。代价：推翻 DI-5、新增 migration/读取谓词/月扫/审计事件/恢复入口，须阶段二设计 + 阶段三 TDD 实施。

## Consequences · 必须同时记住的边界

1. **本 ADR 只定语义，代码未改**：`is_delete` / TTL / 引用检查 / 审计事件均未在源码实现，阶段二方案未出、阶段三未授权。任何「已支持物理删除」表述属误读。
2. **DI-5 推翻的生效范围**：仅推翻「不得引入节点物理删除」这一条约束；ADR-0012 其余不变量（DI-1 外生锚 A 归零、DI-2 终局动作分发、DI-3 Human-only 门禁、DI-4 reason 互异、DI-6 阈值正交、DI-7 历史不回填、DI-8 签名兼容、DI-9 不触发 distill）**继续有效**，不受本次推翻影响。
3. **软删除的可见性契约**：`is_delete=1` 必须对所有功能不可见——这是 zj 原话的硬要求，落地时需逐路径核对（search / browse / discover / due / schedulable / corpus / MCP 对外接口），漏一处即语义不成立。
4. **悬空引用是真实风险**：`evidence_refs` 无 FK、P1 静态检查查不出悬空；删除路径必须自己做引用检查，否则静默破坏知识链。
5. **月扫延迟已接受**：7d TTL + 月扫 = 实际 7~37 天真删窗口；因软删除已屏蔽污染/复审，此延迟不是缺陷。
6. **个案非一类**：本次仅 2 条占位节点触发，全库无第三例；不因此扩大到「一类节点治理」，除非后续出现同类实证。

## 验证证据

- **决策溯源（历史记录，非权威 proof）**：本轮 Q1–Q9 共 9 条 zj 原话的逐字副本已沉淀至 `docs/evidence/physical-delete-decisions-2026-11-16.md`（原 roadmap carrier 三阶段过程态副本已随文档治理移除）；工作日志 2026-11-16 日（14:55 建图 / 15:03 Q1 / 15:48 Q2-Q3 / 16:10 Q5-Q9 / 16:24 收口）。二者仅作溯源，不作 proof。
- **代码现状（可核对）**：`pg.py:298` 到期判定、`pg.py:1255-1278` discover 无归档过滤、`pg.py:252-273` search_by_embedding 有归档过滤、migrations/0001 的 `evidence_refs uuid[]` 无 FK、`check_invariant.py:27,115` 的 P1 口径——均为本仓库当前事实。
- **TDD 证据 = N/A**：实现未启动，无红绿输出、无门禁增量。本 ADR 不声称任何运行时验证。
- **门禁**：本轮为 doc-only 变更，未触碰源码/阈值/迁移；`make mcp-gate` / `make invariant` / authority check 的复跑留待阶段三落码后。

## 实施跟进

> 2026-11-16 阶段三 S1–S7 已落码；本节只追加实施状态与证据指针，**不涂改上文决策正文**。过程态路径按 ADR-0008 不具名。

### 实施状态（2026-11-16，S1–S7 全部完成）

语义已落地为代码，但**尚未由 zj 对两条目标节点执行 `mark`（墓碑）**——代码能力就绪 ≠ 已对具体节点施加删除意图（verdict/mark 仍须 zj 本人逐条给）。

> **〔2026-11-16 17:20 时点更新〕** 上句为 S1–S7 实施末的时点陈述，按历史原文保留。17:20 经 zj 显式授权逐条执行 `mark`，两条占位节点已落墓碑；详见本节末「运行时施加」。

| 切片 | 能力 | 落点 |
|---|---|---|
| S1 | 数据模型 + 迁移 | `migrations/0011_node_tombstone`（node + node_history 双列 `deleted_at`、部分索引、审计表）；`Node.deleted_at`；`NodeRepository.tombstone/restore/list_tombstones_before/hard_delete` 双后端 |
| S2 | 全功能不可见 | 10 条读取路径加 `deleted_at IS NULL`（含 `discover_higher_dim` 补归档+墓碑双过滤）；`check_invariant.py` P4 静态守门（P1/P2/P3 不动） |
| S3 | 人环入口 | `zkc tombstone mark/restore`（operator 必填）+ web review 墓碑区；`store.append_deletion_audit` / `list_deletion_audit` |
| S4 | 引用闸门 | `zkc/purge_gate.py`：扫 `meta_claim/modeling_artifact.evidence_refs` + `citation.citing_node_id`，命中拒删并写 task_queue `tombstone_purge_blocked` |
| S5 | 真删 + 审计 | `zkc/purge.py`：闸门 + TTL 检查后真删；PG FK CASCADE 清关联；purge 审计 node_id 无 FK、不记 content；attention 观测不回退 |
| S6 | 月扫幂等 | `zkc/sweep.py`：月度门闩 + TTL 7d + dry-run；`zkc tombstone sweep` + `zkc daily` 末尾非侵入挂载；不注册系统级调度 |

### 勘误注记（ADR 历史原文不涂改，仅追加）

- **Q6 段的 `claim_evidence.citing_node_id` 是笔误**：仓库中**没有 `claim_evidence` 表**，`claim_evidence_idx` 只是 `meta_claim.evidence_refs` 上的 GIN 索引名。真实引用方表是 **`public.citation.citing_node_id`**（`migrations/0001_baseline_d1_d9.up.sql:159-163`）。S4 闸门按真实表名 `citation` 实现。上文 Q6 / 汇总矩阵 / Consequences 的 `claim_evidence` 字样保留为历史原文，以本注记为准。
- **字段语义等价翻译**：zj 原话 `is_delete=1` 落地为单字段 `deleted_at`（NULL=未墓碑，非 NULL=墓碑时刻兼 TTL 起算点），单字段保证墓碑态与起算点原子一致——此翻译已经 zj 在阶段二批准清单确认。

### 验证证据（TDD 红→绿）

- 新增测试：`test_tombstone_repo.py`（双后端契约）、`test_tombstone_visibility.py`（双后端 18 路径）、`test_tombstone_human.py`（人环 6 项）、`test_purge_gate.py`（闸门 6 项）、`test_purge_execution.py`（含 PG 真库 CASCADE）、`test_tombstone_sweep.py`（幂等 5 项）。
- 全量门禁：`make test` 667 tests OK（阶段三末）；`check_invariant.py` 0 violations（P1/P2/P3/P4）；`make mcp-gate` 6 OK；authority check 0 leak。
- 未触碰 `tuning.py` 阈值 / REGISTRY；未触发 distill；未写 meta_claim；未对任何具体节点执行 mark/purge。

### 运行时施加（2026-11-16 17:20，时点更新）

上文「尚未由 zj 对两条目标节点执行 `mark`」与「未对任何具体节点执行 mark/purge」均为 **S1–S7 阶段末的时点陈述**，按历史原文保留、不涂改。17:20 之后状态如下（**截至 2026-11-16 17:37 的只读快照**）：

- **已施加**：zj 显式授权「逐条执行」后，`zkc tombstone mark --operator zj --json` 分别作用于 `a5de32cd-a53b-4b8b-88e0-6aa0dccfd76e`（BestPractices）与 `3f324c13-105d-4798-a054-e9ce28641ae5`（ClaudeAPIDocs），各一次 applied=true；审计链按 `tombstone → restore → tombstone` 追加（时区校正所致），不涂改历史。未填 reason（不伪造外生锚）。
- **时区校正**：S3 遗留的 `datetime.now()` naive 默认值使首标时刻未来化 8h；独立 TDD 切片已改为 `datetime.now(timezone.utc)`（3 条新测试），两条墓碑经 restore→re-mark 把 `deleted_at` 校正为真实 UTC。证据：`docs/evidence/tombstone-timezone-fix-2026-11-16.md`。
- **当前态**：两条仍处墓碑态、未 purge。只读 `zkc tombstone sweep --dry-run --json` 读数（17:37）：`scanned=2 / eligible=0 / purged=0 / blocked=0 / ttl_days=7`。满 7d 后由月扫自动真删；若引用闸门命中则拒删并写 `task_queue` 的 `tombstone_purge_blocked`，需 zj 人工裁决。
- **边界不变**：`mark` 仍是 zj 逐条人环授权、非系统自动；本注记不改语义、不改阈值、不写 REGISTRY，`corpus-derived ≠ CALIBRATED` 口径不动。TDD 证据段（667 tests OK）记的是 S1–S7 阶段末，17:20 后的修复证据见上述 evidence 文件与工作日志（过程态，非 proof）。
