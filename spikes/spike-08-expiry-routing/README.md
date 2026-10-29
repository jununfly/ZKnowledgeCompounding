# Spike 08 · 到期条目「蒸馏 vs 归档」分流规则（T5.x）

> 状态：**完成 · 9 tests passed**（PostgreSQL 16 + pgvector，`zkc-spike-pg:55433`，复用 spike-04 venv）
> 对应：架构 §10 剩余项 ⑤ / PRD §9 剩余项 ⑤

## 1. 问题

动态轨节点到达 `ROT_THRESHOLD=0.9`（Spike 01 定义）即「到期」。到期节点必须被处理（蒸馏或归档），否则按 PRD §7「衰减可控」指标从系统里静默流失。本 spike 给出**确定性、可解释**的分流规则，并强制「无法判定时交人审」，呼应 Spike 02 的 human-in-the-loop 立场（PRD §8：「宁少勿错」）。

## 2. 决策表（纯读侧规则）

| 信号 | 结论 | 含义 |
|---|---|---|
| 已捕获（节点是某 `meta_claim`/`modeling_artifact` 的 `evidence_refs`） | **ARCHIVE** | 价值已升入元认知层，原始记录直接归档 |
| 有连接（`edge` 触及）或在活跃 `context_member` 中，且未捕获 | **DISTILL** | 有复用迹象但价值未沉淀，提升到元认知层 |
| 同上，但 `attention_pressure ≥ 0.8` | **ABSTAIN** | 蒸馏要消耗人审注意力，预算满则延后 |
| 孤儿（无连接、无 context、未捕获） | **ABSTAIN** | 绝不静默丢弃，交人判定保留/蒸馏/归档 |

## 3. 关键发现（已记账，不得静默接受）

**无需新增任何信号列。** 规则用到的每一个信号都已存在于既有 schema：
- 到期判定：`node.track='dynamic' AND node.decay_score >= 0.9`
- 已捕获：`meta_claim.evidence_refs` / `modeling_artifact.evidence_refs` 包含该节点（Spike 07 已建 `citation` 表，但此处用 `evidence_refs` 方向即可）
- 连接度：`edge` 触及该节点的行数
- context：`context_member` 中该节点的行数

因此本 spike **只新增一张操作性表 `review_queue`**，让 ABSTAIN/DISTILL 结论可落地（人审网关），与 Spike 02/04 的 review gate 同构。这是一条**范围收敛（良性）偏差**：架构 §10 原预期可能需要 `review_status` 枚举或信号列，实测证明不需要。

## 4. 实现要点

- `route_expired(cur, node_id, attention_pressure)` → `{routable, action, reason, signals}`；非到期/已归档返回 `action=None`。
- `apply_archive(cur, node_id)` → 设置 `archived_at`（ARCHIVE 结局本地可执行）。
- `enqueue_review(cur, node_id, action, reason)` → 写入 `review_queue`（ABSTAIN 与 DISTILL 都入队；MVP **不做自动蒸馏**，由人/LLM 执行）。
- `route_and_apply(...)` → 路由并应用本地可落地部分（archive 立即执行；distill/abstain 入队）。
- 复用 Spike 01–07 同一 substrate，无新依赖。

## 5. 测试覆盖（9 tests passed）

到期+已连接+未捕获→DISTILL；到期+孤儿→ABSTAIN；到期+已捕获→ARCHIVE；注意力高压降级 DISTILL→ABSTAIN；非到期不可路由；apply_archive 写 `archived_at`；enqueue 持久化；批量 route_and_apply（d1→queue(distill)、d2→queue(abstain)、d3→archived）；rationale 回带底层信号。

## 6. 仍 open（P2，超出本 spike）

- `attention_pressure` 的**真实取值来源**未定义（需接 Spike 01 的注意力预算 `n/(0.6×interval)` 实时计算）。
- DISTILL 入队后的**实际蒸馏执行**（调 LLM/结合算子）属于 Spike 04/05 范畴，本 spike 只负责分流与入队。
- 孤儿 ABSTAIN 的**人审 SLA / 超时默认**（如 N 天不处理是否自动归档）未定。
- 规则阈值为**占位**（连接数≥1、压力≥0.8），需在真实数据上校准。
