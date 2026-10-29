# Spike 04 · 蒸馏闭环（Instructor + Ollama + LangGraph interrupt/resume 落 PG）

**目标**：验证蒸馏全链路无外部 API 可跑通，并把架构 §6.4 的两条约束作为验收条件：

- **C1（双时态 append-only）**：历史行内容永不改写，只闭合 `tx_to`；修订 = 新行 + `revises` 血缘。
- **C2（produced_by 级联撤销）**：每个蒸馏产物（claim、反向连接边）带 `produced_by → transform(id) ON DELETE CASCADE`，撤销变换即撤销全部副作用。

**结果**：**9 tests passed（OK）**，两条约束均被测试强制验证。

## 文件

| 文件 | 作用 |
|---|---|
| `schema_ext.sql` | 在 spike-01 schema 之上扩展：`transform` 表、`meta_claim` 版本化列（`revises`/`tx_from`/`tx_to`/`produced_by`）、`edge.produced_by` |
| `store.py` | 存储层：`persist_distill`（产物+溯源）、`revise_claim`（append-only 修订）、`discard_transform`（级联撤销） |
| `models.py` | `ClaimDraft`（Pydantic）：蒸馏输出契约 = 元认知 claim，非摘要 |
| `distill_graph.py` | LangGraph 图：`extract`（Instructor+Ollama 结构化抽取）→ `review`（`interrupt()` 人审）→ `persist`（落 PG）；checkpointer = **PostgresSaver，与领域 schema 同库** |
| `test_spike04.py` | 9 个测试（三类见下） |
| `run_spike04.py` | 端到端演示：extract → interrupt → 带编辑 resume → 落库 → 级联撤销 |

## 测试矩阵（9 passed）

**C1 append-only（2）**
- `test_claim_revision_is_append_only`：修订前快照 vs 修订后——历史行 statement/level/confidence 逐字段不变、仅 `tx_to` 闭合；新行 `revises` 指向旧行。
- `test_only_one_current_version`：三级修订链后 `tx_to IS NULL` 的行恰 1 条、全血缘 3 条保留。

**C2 级联撤销（2）**
- `test_cascade_reverts_all_products`：删 transform → 其 claim 与 edge 全消失；**人工手写的 claim/edge（produced_by NULL）存活**。
- `test_claim_requires_evidence`：无 `evidence_refs` 的 claim 仍被 schema 拒绝（spike-01 语义保持）。

**图回路（5，需 Ollama qwen2.5-coder:1.5b）**
- `test_interrupt_pauses_and_nothing_is_written`：图停在 interrupt，DB 零写入。
- `test_approve_persists_with_provenance`：approve 后 claim 落库，`produced_by` 非空、`evidence_refs` == 源节点 id。
- `test_resume_with_human_edit_wins`：resume 时人工编辑覆盖草稿陈述。
- `test_rejection_persists_nothing`：拒绝 → 零写入。
- `test_checkpoint_survives_new_connection`：**第一个连接发起 interrupt、关闭，再用全新 PostgresSaver 连接 resume 成功**——checkpoint 真住在 PG 而非进程内存。

## 环境说明

- Postgres：Docker 容器 `zkc-spike-pg`（`pgvector/pgvector:pg16`），**重建时补发布端口 `-p 55433:5432`**（spike-01 原容器无端口映射，只支持 docker exec；LangGraph 的 PostgresSaver 需要 TCP）。原 spike 数据可由 `run_spike.py` 再生。
- 依赖安装曾被沙箱「临时文件删除策略」卡死（`No usable temporary directory`），`langgraph` 单独装成功后，其余三个包（`langgraph-checkpoint-postgres` / `psycopg[binary]` / `instructor`）由 zj 在本机终端手动装——与 spike-02 的 FastEmbed 坑同源，已记入环境坑清单。

## 观察与结论

1. **两条 §6.4 约束可直接作为 schema 级验收**：append-only 用「修订=闭行+插行」实现，级联撤销用 FK `ON DELETE CASCADE` 实现——都不需要应用层补偿逻辑，**撤销正确性由数据库保证**。
2. **PG checkpoint 同库成立**：LangGraph checkpoint 表与 ZKC 领域表共存于 `zkc` 库，无第二个存储；跨连接 resume 实测通过，进程崩溃后人工可续跑（印证架构复核「durable execution 缺口对人工驱动蒸馏非 blocker」）。
3. **⚠️ 1.5B 模型蒸馏质量不足（已预期）**：演示中 qwen2.5-coder:1.5b 的「蒸馏」产物基本是**复述**（「批量导入时先删索引再重建…」），未上升到元认知。这印证架构 §8 风险「本地小模型蒸馏质量可能不足」——**架构对策不变**：Instructor/LangGraph 侧已验证的是管线与约束，蒸馏语义质量靠 provider seam 切强模型（本地大参数或云端）解决，属后续工作。
4. **人审语义完整**：approve/edit/reject 三路径行为均符合预期，interrupt 载荷含草稿全文供审。

## 未决（留给后续）

- `produced_by` 撤销目前是**硬删**（级联）；是否需要「软撤销」（标记 discarded，保留审计痕迹）待定——Cordis 模式的 append-only 事件流更倾向软撤销。
- 蒸馏质量评估：需要更强模型（≥7B）复测「产物是否真为元认知」。
- 结合算子（T3.2）的多源漏斗未进入本 spike；`transform.kind` 已预留 `'combine'`。
