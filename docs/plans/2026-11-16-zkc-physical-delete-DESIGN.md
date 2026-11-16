<!-- zj-roadmap-authority/v1
role: process-state
durable-citation: forbidden
promote-via: ADR|design|contract|runtime-evidence
-->

# ZKC 节点墓碑软删除 + TTL 真删 · 技术方案 v1（阶段二产出）

> **状态：done，阶段三已全部实施落地（1-3-1~1-3-7 completed，commit 749af48「墓碑软删+TTL真删落地」）。** 本文件是过程态方案（见顶部信封），只做设计、不含红绿证据，不作 proof、不被持久文档具名引用。权威语义源 = ADR-0013；本文件只回答「怎么落地」。
> 事实基线日期：2026-11-16，全部代码位置为当日实读。

## 0. 设计输入（阶段一 9 条裁决，逐条映射到方案）

| 裁决 | 语义 | 方案落点 |
|---|---|---|
| Q1 | 墓碑 `is_delete=1` → 全功能不可见 → TTL 到期真删 | §1 数据模型、§2 可见性 |
| Q2/Q3 | ①防腐化污染 ②省复审注意力 ③明确无用+可接受重摄入+存储/运行时精简；删除语义 ≠ 归档 | §2、§4；三者由软删+真删分层承担 |
| Q5 | TTL 7d / 墓碑时刻起算 / 按月扫描；实际真删落在 7~37 天 | §5 月度门闩 |
| Q6 | 删前扫 `evidence_refs` + `citing_node_id`，有引用拒绝真删 | §4 引用闸门 |
| Q7 | `is_delete=0` 恢复，CLI+web，仅 zj，与 verdict 同级人环 | §3 人环入口 |
| Q8 | 独立审计事件（不引用已删 node）；明确推翻 DI-5 | §4 审计表；ADR-0013 已生效 |
| Q9 | 软删承担污染+复审；`is_delete` 谓词进**全部**读取路径 | §2 可见性矩阵 |

---

## 1. 数据模型与迁移（设计点 ①②）

### 1.1 字段选型：`deleted_at` 单字段承载墓碑态 + 起算点

zj 原话是 `is_delete=1`；但 Q5 要求「起算点 = 墓碑时刻」。用一个 `deleted_at timestamptz` 同时表达两件事，语义映射：

- `deleted_at IS NULL` ⟺ `is_delete=0`（未墓碑）
- `deleted_at = <t0>` ⟺ `is_delete=1`，且 t0 就是 TTL 起算时刻

**为什么不用 `is_delete boolean` + 独立 `deleted_at` 双字段**：双字段会允许「is_delete=1 但 deleted_at=NULL」这类非法组合，需要额外 CHECK 约束兜底；单字段让墓碑态与起算点原子一致，且 PG 部分索引可高效筛「未墓碑节点」。代价：查询谓词写 `deleted_at IS NULL` 而非 `is_delete=0`，对 zj 原话做了一层等价翻译——本方案明确记录这层翻译，请 zj 在批准时确认接受。

### 1.2 迁移 `0011_node_tombstone`（up/down 成对）

```sql
-- up
ALTER TABLE public.node ADD COLUMN deleted_at timestamptz;
CREATE INDEX node_deleted_idx ON public.node (deleted_at) WHERE deleted_at IS NOT NULL;
CREATE TABLE public.node_deletion_audit (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id       uuid NOT NULL,          -- 刻意无 FK：删 node 后审计行仍能独立存在
    title         text NOT NULL,          -- 删除时快照，不记 content
    tombstoned_at timestamptz NOT NULL,
    event_kind    text NOT NULL CHECK (event_kind IN ('tombstone','restore','purge')),
    deleted_at    timestamptz,            -- 仅 purge 事件填
    ttl_days      integer,                -- 仅 purge 事件填（快照 7）
    operator      text NOT NULL,          -- 人环操作者标识
    reason        text
);
CREATE INDEX nda_node_idx ON public.node_deletion_audit (node_id);
CREATE INDEX nda_kind_idx ON public.node_deletion_audit (event_kind, deleted_at DESC);
-- down: DROP TABLE node_deletion_audit; DROP INDEX node_deleted_idx; DROP COLUMN deleted_at;
```

对齐 `zkc.migrate` 的版本+sha256 机制（`src/zkc/migrate.py:45-120`）：新迁移编号 0011，up/down 同名成对，`make migrate` / `make verify` 照常覆盖。

### 1.3 Repository 接口增量（`src/zkc/repository/protocols.py`）

`Node` 模型加 `deleted_at: datetime | None = None`（`models.py:22-57`）；`NodeRepository` 加：

- `tombstone(node_id, at) -> None`：置 `deleted_at=at`，`version_seq+1`（走 history，见下）
- `restore(node_id) -> None`：清 `deleted_at=NULL`，`version_seq+1`
- `list_tombstones_before(cutoff) -> list[Node]`：月扫候选（`deleted_at IS NOT NULL AND deleted_at <= cutoff`）
- `hard_delete(node_id) -> None`：真删（内部先过引用闸门 §4，再由 PG CASCADE 清关联）

**版本链语义**：墓碑/恢复是否进 `node_history`？建议**进**（各写一行 snapshot，`archived_at` 路径已有 `version_seq+1` 先例 `pg.py:441-451`），这样墓碑期在双时态里可追溯；真删时这些历史随 `node_history` 的 FK CASCADE 一并清掉（Q6 已接受），但删除动作本身由独立审计表留痕。理由：审计表承载「谁在何时删了什么节点」，版本链承载「节点生前的状态演进」，两者不互相引用。

---

## 2. 「全功能不可见」谓词矩阵（设计点 ①，Q9 核心）

**统一原则**：默认读取一律加 `deleted_at IS NULL`；`include_archived=True` 只放开归档、**不放开墓碑**（墓碑语义强于归档，zj 原话「对所有功能不可见」）。恢复只能走 §3 人环入口。

| 路径 | 文件:行（实读） | 现状 | 改法 |
|---|---|---|---|
| 结构化检索 `search` | `pg.py:222-231` | `archived_at IS NULL`（include_archived 控制） | where 追加 `AND deleted_at IS NULL`（不受 include_archived 控制） |
| 向量检索 `search_by_embedding` | `pg.py:252-273` | `AND archived_at IS NULL` | 同上追加 |
| 到期复审 `list_due_for_review` | `pg.py:298-309` | `AND archived_at IS NULL` | 同上追加 |
| 调度快照 `load_schedulable` | `pg.py:1160` | `n.archived_at IS NULL` | 同上追加 |
| 高维近邻 `discover_higher_dim` | `pg.py:1255-1278` | **无 archived 谓词、无 decay 下限**（阶段一查实的漏洞） | 同时补 `archived_at IS NULL AND deleted_at IS NULL` |
| 其他 PG 聚合查询 | `pg.py:1146, 1185` | 投影 archived 标志 | 核对是否需同步过滤（实施切片 2 内逐条确认） |
| corpus 选节点 | `corpus.py:24` | `archived_at is not None` 跳过 | 加 `deleted_at is not None` 跳过 |
| memory 后端 search | `memory.py:110-119, 149-166` | include_archived 控制 | 同 PG 语义 |
| memory 到期/调度 | `memory.py:191, 587, 624` | archived 过滤 | 同 PG 语义 |
| web browse/search payload | `browse.py:160-242` | 传 include_archived | 无需直接改（走 repository），但 add 墓碑断言测试 |
| MCP 工具 | `mcp/handlers.py:78, 141` | 走 `search` / `list_due_for_review` | 间接覆盖，无需改 handler；加端到端断言 |

**机制**：在 `pg.py` / `memory.py` 各定义一个私有常量 `_VISIBLE_SQL = "archived_at IS NULL AND deleted_at IS NULL"`（memory 用等价 Python 判定），所有默认路径复用，避免漏改。

**不变式增量 P4**（`scripts/check_invariant.py`，现 P1/P3 两条）：静态扫描上述每个函数的源码切片，断言其查询体同时含 `archived_at` 与 `deleted_at` 的 IS NULL 谓词——把「全功能不可见」变成机械守门，而非靠人记。P1（evidence_refs NOT NULL）/ P3（归档退出调度）保持不动，只做加法。

---

## 3. 人环入口：墓碑标记 / 恢复（设计点 ⑦，Q7）

新增 CLI 子命令（与 `decide` 同级人环门禁）：

```
zkc tombstone mark   --id <uuid> [--reason ...]     # 置墓碑（= zj 对两条无内容节点说的「删除」）
zkc tombstone restore --id <uuid> [--reason ...]    # is_delete=0，仅 zj
zkc tombstone sweep  [--now ...] [--dry-run] --json # 月扫真删（§5），幂等
```

- **人环硬约束**：`mark` / `restore` 的调用即 zj 本人授权（与 `--verdict` 同口径：CLI 不替人编造意图）；不得由系统自动、批量脚本或定时任务默认调用——`sweep` 只做「已满 TTL 且无引用」的墓碑节点真删，不做标记/恢复。
- web 端：review 页加一对按钮（mark/restore），走同一 repository 方法，操作前二次确认，记 operator。
- 两条目标节点（`a5de32cd…` BestPractices、`3f324c13…` ClaudeAPIDocs）在阶段三实施后用 `mark` 落墓碑——**本阶段不动**。

---

## 4. 真删闸门与审计（设计点 ③④，Q6/Q8）

### 4.1 引用闸门（删前必过）

```sql
-- 任一命中即拒绝真删，报错并保留墓碑态；不 CASCADE
SELECT 1 FROM public.meta_claim       WHERE evidence_refs @> ARRAY[%(nid)s]::uuid[] LIMIT 1;
SELECT 1 FROM public.modeling_artifact WHERE evidence_refs @> ARRAY[%(nid)s]::uuid[] LIMIT 1;
SELECT 1 FROM public.citation          WHERE citing_node_id = %(nid)s LIMIT 1;  -- 真实表名
```

`evidence_refs` 是 `uuid[] NOT NULL` + GIN 索引（`migrations/0001:80,96,110,116`），**无 FK**——CASCADE 管不到，故必须手动扫 `@>`。`citing_node_id` 的真实表名是 `citation`（`0001:159-163`）。

> **需勘误的事实笔误（阶段一遗留）**：ADR-0013 §Q6 / 汇总矩阵写的是 `claim_evidence.citing_node_id`，但仓库里**没有 `claim_evidence` 表**，`claim_evidence_idx` 只是 `meta_claim.evidence_refs` 上的 GIN 索引名。真实引用方是 `citation.citing_node_id`。本方案按真实表名设计；建议阶段三实施时给 ADR-0013 加一条勘误注记（ADR 历史原文不涂改，仅追加），本阶段不改长期文档。

### 4.2 CASCADE 边界（Q6 已裁决「无引用才删」）

真删 `DELETE FROM node WHERE id=…` 后随 FK CASCADE 清除：`node_history`（该两条各 60 版本）、`edge(src,dst)`、`context_member(node_id)`、`citation(citing_node_id)`、`interval_adjustment(node_id)`、`proposal_log(seed_id)`、`review_queue(node_id)`。全部 `ON DELETE CASCADE`（实读 `0001:122-190`、`0005:11`、`0002:48`）。**不受 CASCADE 影响的**：`attention_observation`（按天聚合，已累计埋点不回退）、`node_deletion_audit`（§1.2，node_id 无 FK，刻意独立）。

### 4.3 独立审计事件（Q8）

`purge` 时写一行 `node_deletion_audit`：`node_id`（裸 uuid，无 FK）、`title` 快照、`tombstoned_at`、`deleted_at`、`ttl_days=7`、`operator`、`reason`。**不记 content、不建到 node 的 FK**——否则审计又成悬空引用或阻碍 CASCADE。墓碑/恢复各写一行（`event_kind` 区分），形成完整生命周期审计链。

### 4.4 引用闸门拒绝后的兜底（新发现风险，请 zj 拍板）

Q6 裁决「有引用就拒绝并报错」，但没定义**之后怎么办**：若墓碑节点永久被 `evidence_refs` 引用，它会永远卡在墓碑态、真删不了。建议：拒绝时同时写一条 `task_queue` 待办（`tombstone_purge_blocked`），提示 zj 人工决定「改 claim 的 evidence_refs / 放弃真删」。否则静默挂起违背第一性——需要人知道删除为何没发生。本方案按此设计，列入 §7 批准清单。

---

## 5. 月扫触发与幂等（设计点 ③，Q5）

### 5.1 触发点（不注册系统级调度）

本任务已有的每日触发入口（`automation` 每日调 `zkc daily`）作为**唯一触发源**；在其后追加一次非侵入调用 `zkc tombstone sweep`。**不改 `zkc daily` 的输出语义**，sweep 内部用月度门闩判定，未到月份直接 no-op。不新增 launchd / schtasks。

### 5.2 月度门闩（幂等）

```python
# 伪码：本月是否已跑过 sweep
last = audit_repo.last_event("purge")            # 查 node_deletion_audit 最近 purge 时间
if last and same_month(last, now): return no_op   # 月度门闩
cutoff = now - timedelta(days=TTL_DAYS)           # TTL_DAYS=7，走 tuning 常量（禁止裸数字）
candidates = nodes.list_tombstones_before(cutoff)
for node in candidates:
    if reference_gate(node.id):                   # §4.1，有引用 → 跳过 + task_queue 待办
        continue
    nodes.hard_delete(node.id)                    # §4.2 CASCADE
    audit_repo.append_purge(node, now, operator)  # §4.3 独立审计
```

- **幂等**：同一月重复调用，门闩命中即 no-op；`hard_delete` 对已删节点是空操作。
- **TTL 边界**：7d 从 `deleted_at` 起算；月度门 → 实际真删在墓碑后 7~37 天（Q5 已接受此延迟）。
- `--dry-run`：只读列候选与闸门结果，不写任何数据（供人工预演，对齐现有 `zkc embed --dry-run` 口径）。
- **月扫不做墓碑标记/恢复**：只处理已满 TTL 的既有墓碑，杜绝自动标记（人环不可被定时任务代理）。

---

## 6. 持久权威改写清单（设计点 ⑤，Q8 提炼）

阶段三实施时随代码一并落（本阶段只列清单、不改）：

| 文档 | 改写 | 状态 |
|---|---|---|
| ADR-0013 | 加勘误注记（`claim_evidence` → `citation`）+ 实施状态从「未设计未实现」更新为「方案 v1 已定（过程态不具名）、实施进行中」，附 TDD/门禁证据 | 待阶段三 |
| PRD §生命周期 | 新增墓碑软删 + TTL 真删章节，引用 ADR-0013（不引用本方案文件） | 待阶段三 |
| architecture | §数据生命周期 addendum：三态（active/tombstoned/purged）+ 谓词分层 + 审计独立 | 待阶段三 |
| ZJ-CONTEXT | 4 词条已补（上一轮完成） | ✅ 已完成 |
| risks.md | 新增 R16：墓碑误删 / 悬空 evidence_refs / 月扫时序风险（缓解=§4 闸门 + §2 P4 + §5 幂等） | 待阶段三 |

---

## 7. TDD 实施切片（阶段三，按序；每片独立红→绿）

| # | 切片 | 红（先写失败测试） | 绿（最小实现） | 门禁 |
|---|---|---|---|---|
| 1 | schema + model + repo 读写 | migration up/down roundtrip、`deleted_at` 存取、`version_seq` 自增 | `0011` 迁移 + `Node.deleted_at` + `tombstone`/`restore`/`list_tombstones_before`/`hard_delete` | `make migrate verify`、invariant |
| 2 | 全功能不可见 | §2 矩阵每个路径一条「墓碑节点不可见」测试（含 `include_archived=True` 仍不可见墓碑、discover 漏洞回归） | 统一 `_VISIBLE_SQL` 谓词逐点接入 + P4 静态守门 | `make test`、`make invariant` |
| 3 | 人环入口 | CLI mark/restore 参数校验、operator 记录、不得自动调用断言 | CLI 子命令 + web 按钮 + 二次确认 | `make test`、mcp-gate |
| 4 | 引用闸门 | 有 `evidence_refs` / `citation` 引用 → 拒删；无引用 → 放行；P1 不破 | §4.1 三条 SQL + 拒绝报告 + task_queue 待办 | `make test`、`make invariant` |
| 5 | 真删 + 审计 | 删后 node_history/edge/… 清空、审计行保留且 node_id 无 FK、audit 不记 content | §4.2 CASCADE + §4.3 审计写入 | `make test`、`make invariant` |
| 6 | 月扫幂等 | 同月重复 no-op、跨月触发、TTL 7d 边界、`--dry-run` 零写入、不自动标记 | §5 月度门闩 + sweep CLI | `make test` |
| 7 | 权威同步 + 全量门禁 | §6 文档改写完成、ADR-0013 状态更新 | 文档 + 勘误 | authority 0 leak / invariant 0 / mcp-gate 6 / `make test` 全绿 |

**切片顺序依赖**：1 → 2 → 3（软删可见性闭环）→ 4 → 5 → 6（真删闭环）→ 7（文档）。每片提交独立、可回滚；不改阈值常量、不碰 1-26 CALIBRATED、不触发 distill、不写 meta_claim。

---

## 8. 风险与 trade-off

| 决策点 | 推荐 | 理由 / 代价 |
|---|---|---|
| 字段：`deleted_at` vs `is_delete`+时间戳 | 单字段 `deleted_at` | 原子一致、部分索引高效；代价=对 zj 原话做等价翻译（§1.1），需批准 |
| `include_archived=True` 是否放开墓碑 | 不放开 | 墓碑「全功能不可见」强于归档；恢复只走人环 |
| 墓碑/恢复是否进版本链 | 进（各 1 行 snapshot） | 可追溯；真删时随 CASCADE 清，审计表独立留痕 |
| 引用闸门拒绝后 | 写 task_queue 待办 | 避免静默永久挂墓碑（§4.4，待 zj 拍板） |
| 月扫触发 | 挂现有每日 automation + 月度门闩 | 不注册系统级调度（硬约束）；代价=真删延迟 7~37 天（Q5 已接受） |
| 真删级联 | 接受 CASCADE（Q6 已裁决） | 60 版本历史随删；独立审计表保住「删了什么」的痕迹 |
| 腐化阈值 | 不动（SURFACE 0.6 / ROT 0.9 仍 SIMULATION） | 可见性谓词与 decay 解耦；软删屏蔽污染不依赖阈值校准 |

**残余风险**：
- 墓碑节点若被 `evidence_refs` 引用 → 永久卡墓碑态（§4.4 缓解：待办告警）。
- `discover_higher_dim` 补过滤后，高维装配提议的种子集合会变小——这是修复，但需确认不破坏现有高维工作流（切片 2 加回归测试）。
- 审计表 `node_id` 无 FK 是有意设计（删后仍存在）；需防止有人「好心」补 FK 导致真删被阻碍——写入 ADR-0013 边界声明。

---

## 9. 批准清单（请 zj 一次性拍板）

1. **字段翻译**：接受用 `deleted_at` 单字段承载 `is_delete` 语义 + TTL 起算点（§1.1）。
2. **不可见强度**：`include_archived=True` 也不放开墓碑，恢复只走人环（§2）。
3. **引用闸门兜底**：拒绝真删时写 task_queue 待办告警，而非静默挂起（§4.4）。
4. **月扫口径**：挂现有每日 automation + 月度门闩，不注册系统级调度；接受 7~37 天真删延迟（§5）。
5. **ADR-0013 勘误**：阶段三追加 `claim_evidence → citation` 表名勘误注记（§4.1）。

批准任一项若有调整，指出即可；全部同意则回复「批准阶段二」，我按 §7 切片进阶段三（仍按纪律：先红后绿、小切片、逐片验证，commit/push 由 zj 显式触发）。
