---
doc-kind: architecture-subsystem
authority: primary
authority-id: architecture.subsystem.data-storage
---

## Question

Data Storage 子系统负责什么状态、以什么结构持久化、对上层暴露什么接口、失败时如何自保？本页是这些问题的唯一 durable owner。

## Scope

- [implemented] 覆盖 PostgreSQL + pgvector 的物理存储、`repository` seam 的分层与门面、双时态版本链、双轨字段、decay/interval/embedding 字段的落点，以及从 `0001` 到 `0011` 的迁移契约。
- [implemented] 覆盖内存 fake（`memory.py`）作为无 DB 单测替身。
- [out of scope] 写入这些数据值的**业务时机与调用顺序**归 Data Flow 页；阈值常量取值理由归 §6.5 与 ADR；verdict 终局语义归 ADR-0011/0012。本页只讲「状态长什么样、怎么存、怎么读」，不讲「什么时候写」。

## Boundaries

- [implemented] 应用代码只依赖 `get_storage()` 返回的 `Storage` ABC，不认具体驱动；`pg.py` 是 raw SQL + psycopg，**无 ORM**。
- [implemented] 唯一允许 `docker exec psql` 的路径是 `migrate.py`；schema 变更只加列/改约束，不回改历史迁移文件（sha256 闸门会拒绝）。
- [implemented] `docs/plans/` 等过程态不参与本页任何事实来源；权威链为 code → schema → ADR/架构长期文档。
- [inference] transport（MCP）与 provider（LLM）、encoder 是同级的其他 seam，不属于本子系统，本页只在 Interface 说明它们如何通过 repository 门面取数。

## Responsibility

- [implemented] 持久化九个聚合：`Node`、`Claim`、`ModelingArtifact`、`Edge`、`Context`、`ReviewItem`、`AttentionObservation`、`LLMCallScore`、`TaskSpec/TaskItem`，外加 transform/context/budget 的编排读写。
- [implemented] 为静态事实提供双时态（valid + transaction time）版本链，为动态条目提供 decay / interval 状态位。
- [implemented] 维护 embedding 双列（`embedding` 768 维 + `embedding_4096` 4096 维）及 HNSW 索引，供相似度检索消费。
- [implemented] 提供注意力预算的唯一外生锚表 `attention_observation`，以及区间调整审计 `interval_adjustment`。

## Owned state

- [implemented] **`node` 表**（`0001_baseline_d1_d9.up.sql`）：`id`、`track`（static/dynamic/unrouted）、`routing_confidence`、`valid_from/valid_to`、`tx_from/tx_to`、`decay_score real CHECK[0,1]`、`review_interval`、`last_reviewed_at`、`attention_signal`、`created_at`、`embedding vector(768)`、`archived_at`、`baseline_interval`、`interval_source(auto|human)`。索引含 `node_track_decay_idx` 与 `node_embedding_idx`（HNSW, `vector_cosine_ops`）。
- [implemented] **双轨**：`node.track` 三值枚举。静态轨 `decay_score` 恒为 0（`decay.py` 的 `compute_decay_score` 对 `track=="static"` 直接返回 0.0），双时态只服务静态事实演进；动态轨才进入腐化与调度。
- [implemented] **双时态**：`valid_from/valid_to` 是业务时间，`tx_from/tx_to` 是事务时间；`node_history` 镜像 `node` 全列，主键 `(id, tx_from)`，外键 `ON DELETE CASCADE`。版本链采用 append-only 快照：`_locked_snapshot` 对当前行 `FOR UPDATE`，把旧像写入 `node_history`（`tx_to=clock_timestamp()`），再 `UPDATE` 主行并 `tx_from=clock_timestamp()`。`history()` 用显式列清单 `node_history UNION ALL node ORDER BY tx_from`——`0008` 之后禁止 `SELECT *`，因为 `embedding_4096` 不进历史。
- [implemented] **轻量派生更新不写历史**：`update_decay`、`set_embedding_column`、`mark_reviewed`、`archive` 只改派生状态，不 bump `tx_from`、不写 `node_history`；`tombstone/restore` 作为双时态事实变更走完整 `save` 版本链。
- [implemented] **embedding 双列**：`embedding vector(768)`（nomic，`EMBEDDING_DIM=768`）+ `0008` 新增 `embedding_4096 vector(4096)`（qwen3，`EMBEDDING_4096_DIM=4096`）。白名单 `EMBEDDING_COLUMNS={"embedding","embedding_4096"}` 防注入；相似度用 `<=>`，`sim=1-distance`。`embedding_4096` 明确不入历史（派生数据）。
- [implemented] **其他表**：`meta_claim`（`evidence_refs uuid[] NOT NULL` + `produced_by/revises/tx_from/tx_to` + D9 六字段）、`modeling_artifact`（唯一无 `version_seq`/OCC 的表）、`edge`、`context`/`context_member`、`citation`、`review_queue`、`interval_adjustment`（`kind ∈ baseline|budget|feedback`）、`attention_observation`、`llm_call_score`（`0007`）、`proposal_log`（`0004`+`0006`+`0005`）、`task_queue`（`0009`）、`node_deletion_audit` + `deleted_at`（`0011`）。
- [implemented] **OCC / 迁移**：`0003` 加 `version_seq` 列（node / node_history / meta_claim / context）；`schema_migration` 表 + sha256 留痕（`migrate.py`）。
- [unknown] `0001` 基线迁移是否曾被就地修改（sha256 闸门只约束「之后禁止改」，历史事实无独立证据）。

## Interface

- [implemented] **注入点**：`get_storage(kind)` 读 `ZKC_STORAGE`（默认 `pg`；`memory` 走无 DB fake）；`get_dsn()` 读 `ZKC_PG_DSN`，默认 `postgresql://postgres:zkc@localhost:55433/zkc_dev`。
- [implemented] **门面**：`Storage` ABC 聚合九个仓库属性（`nodes/claims/artifacts/edges/contexts/review_queue/attention/scores/tasks`），并提供 `record_transform` / `load_schedulable` / `load_metric_inputs` / `assemble_context` / `revert_assembly` / `discover_higher_dim` / `purge_node` / `append_deletion_audit` 等编排方法。
- [implemented] **读接口**：`NodeRepository.search`（结构化：track/q/decay/order）、`search_by_embedding`（向量列可配）、`history`（双时态版本链）、`list_due_for_review`（`decay_score >= SURFACE_THRESHOLD AND (last_reviewed_at+review_interval) <= as_of AND archived_at IS NULL AND deleted_at IS NULL`）。
- [implemented] **写接口**：`save`、`update_decay`、`set_embedding_column`、`set_interval`、`set_baseline_interval`、`audit_interval`、`mark_reviewed`、`archive`、`tombstone/restore/hard_delete`、`record_transform`。
- [implemented] **检索列选择**：`web/browse.py` 的 `RETRIEVAL_COLUMN="embedding_4096"`；`search.search(column=)` 可配，编码器失败时降级为仅结构化结果。

## Failure behavior

- [implemented] **并发写**：`_locked_snapshot` 用 `FOR UPDATE` 行锁 + `version_seq+1` 做乐观并发；`clock_timestamp()` 而非 `now()` 保证提交顺序单调，避免同事务内时间戳相同导致版本链乱序。
- [implemented] **迁移失败**：`migrate.py` 单事务执行 + sha256 校验；历史迁移文件被改动会触发闸门拒绝，而不是静默漂移。
- [implemented] **无 DB 环境**：`memory.py` 提供同接口的纯内存 fake，供单测在无 PostgreSQL 时跑通；行为以接口等价为目标，不保证 PG 全部语义（如 HNSW、行锁）。
- [implemented] **嵌入列防注入**：`set_embedding_column` / `search_by_embedding` 对列名做白名单校验，非法列名直接拒绝。
- [inference] 若 `embedding_4096` 回填中断（进程被杀），`embed` 算子设计上幂等可重入，但「中断点的原子性」依赖两阶段写的具体提交边界，代码里有实现意图、`docs/evidence/` 无中断回放证据。

## Source map

- `../../src/zkc/repository/__init__.py` — 注入点 get_storage
- `../../src/zkc/repository/protocols.py` — Storage ABC 与九个仓库协议
- `../../src/zkc/repository/models.py` — Node/Claim/Track 等 dataclass
- `../../src/zkc/repository/connection.py` — DSN 与连接
- `../../src/zkc/repository/pg.py` — PgStorage / PgNodeRepository 全部 raw SQL
- `../../src/zkc/repository/memory.py` — 内存 fake
- `../../src/zkc/migrate.py` — 迁移器与 sha256 闸门
- `../../src/zkc/tuning.py` — SURFACE/ROT/EMBEDDING_DIM 阈值唯一真相源
- `../../src/zkc/decay.py` — 静态轨 decay 恒 0 与 compute_decay_score
- `../../src/zkc/web/browse.py` — RETRIEVAL_COLUMN=embedding_4096
- `../../src/zkc/embedding_backfill.py` — 4096 列回填算子
- `../../migrations/0001_baseline_d1_d9.up.sql`
- `../../migrations/0002_node_history.up.sql`
- `../../migrations/0008_node_embedding_4096.up.sql`
- `../../migrations/0011_node_tombstone.up.sql`

## Related authority

- [Data Flow](ta-data-flow.md) — 本子系统状态的写入时机与读取链路。
- [架构本体·数据模型（原 §5）](../evidence/architecture-v1.2-source-2026-11-19.md) / [架构本体·调度与预算（原 §6.5 interval 三层）](../evidence/architecture-v1.2-source-2026-11-19.md) — 设计论证与阈值校准来源；本页只记实现态，不复制论证。
- [ADR-0011 verdict 语义 v2](../zj-adr/0011-verdict-semantics-v2.md)（accepted）与 [ADR-0013 墓碑软删](../zj-adr/0013-node-tombstone-soft-delete.md)（accepted）— 解释 `archive`/`deleted_at` 的语义 decidability；ADR-0012 为 spec-frozen，仅作规格参考。
- [BOUNDARIES.md](../BOUNDARIES.md) — docs/code/roadmap 解耦约定。
