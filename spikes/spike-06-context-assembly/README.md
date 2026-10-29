# Spike 06 · Context 拓扑装配（T4.1 发现 + T4.2 成员维护）

> 状态：**已完成（10 tests passed）** —— 校准候选，待 zj 复核并回填架构 §5。
> 上游：架构文档 §10 剩余项 ②；对应调研 Topic T4.1 / T4.2（均为 P2）。
> Substrate：Postgres + pgvector（`zkc` 库 @ :55433，复用 spike-01 基础 schema + spike-04 `transform` 表 + spike-04 venv）。

## 1. 目的

验证「context 拓扑装配」两个未决点：

- **T4.1 自闭环 vs 更高维 context 自动发现**：给定种子节点，如何提议一个更高维 context。
- **T4.2 context membership 维护模型**：成员关系用哪种结构表达（架构 §5 草图写的是 `context.member_nodes uuid[]`）。

## 2. 关键设计决策（spike 验证结论）

**membership 用 junction 表 `context_member`，不用 `uuid[]` 数组。**

理由：spike 04/05 已固化一条不变量——**所有变换产物必须可溯源、可级联撤销**（`produced_by` 引用 `transform(id) ON DELETE CASCADE`）。`uuid[]` 数组列**无法**为单个成员携带 `produced_by`，因此无法参与级联撤销。junction 表每行带 `produced_by` + `weight`（软归属），正好接入同一套撤销机制。

```sql
CREATE TABLE context_member (
  context_id  uuid REFERENCES context(id) ON DELETE CASCADE,
  node_id     uuid REFERENCES node(id)    ON DELETE CASCADE,
  produced_by uuid REFERENCES transform(id) ON DELETE CASCADE,  -- NULL = 人审添加
  weight      real NOT NULL DEFAULT 1.0,
  added_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (context_id, node_id)
);
```

一次「装配」= 一个 transform → 一个 context + 其若干 member 行；撤销 transform 时 context 与成员**级联消失**（FK CASCADE）。

## 3. 与架构 §5 的两处偏差（必须回填，不得静默接受）

| # | 架构 §5 草图 | spike 06 实测/结论 | 性质 |
|---|---|---|---|
| D1 | `context.scope text` | 基础 schema 实际是 **ENUM `context_scope`**（`self_loop` \| `higher_dim`），比 `text` 更严格 | 收紧（良性） |
| D2 | `context.member_nodes uuid[]` | 改为 **`context_member` junction 表**（`produced_by` + `weight`），数组列保留但弃用 | 修正（功能性） |

两处均为**收紧/修正**，且都更贴合既有的「可溯源 / 可级联撤销」不变量。应回填进架构 §5 数据模型与证据表。

## 4. 算子 API（`context_assembly.py`）

- `create_context(cur, scope, title, produced_by=None)`
- `assemble(cur, scope, node_ids, title, weight=1.0)` → `(context_id, transform_id)`
- `add_member_human / remove_member_human`（produced_by=NULL，可单独删，受 transform 行保护隔离）
- `contexts_of(node_id)` / `members_of(context_id)`（双向查询，member 按 weight 降序）
- `discover_higher_dim(cur, seed_node_id, k=5)` → k 近邻（pgvector 余弦 `<=>`）

## 5. 测试结果（10 passed）

| 类 | 验证点 |
|---|---|
| TestScopeEnforced | D1：非法 scope 被 enum 拒绝 |
| TestCreate | self_loop / higher_dim 两类 context 可建 |
| TestAssemble | 装配后每行 member 带 produced_by；双向查询正确 |
| TestCascadeUndo | 撤销 transform 级联删 context+members，人审 context 不受影响；self_loop 与 higher_dim 互相独立 |
| TestHumanMembership | 人审成员可单独删；transform 产成员不可被人审路径误删 |
| TestDiscovery | T4.1：同簇节点（sim≈1.0）先于跨簇（sim≈0）返回，余弦距离有序 |
| TestWeighting | member 按 weight 降序 |

## 6. 仍 open（超出本 spike，P2）

- **T4.1 启发式过朴**：当前仅 pgvector k-NN，未融合 topic / 项目邻近 / 时间信号；也未自动命名更高维 context（需 LLM 命名，复用 spike 03 的 DecisionRouter/Ollama 栈）。
- **membership 维护成本**：junction 表在高频重算下的写放大未压测；是否引入「查询时计算」的动态视图未决。
- **自动触发策略**：何时自动提议/创建 higher_dim context（阈值、频率、人审闸门）未定。

## 7. 运行

```bash
cd spikes/spike-06-context-assembly
../spike-04-distill-loop/.venv/bin/python -m unittest test_spike_context -v
```
