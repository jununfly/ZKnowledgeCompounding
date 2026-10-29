# Spike 07 · 复利度量口径（T7.1）+ 引用埋点（T6.2）

> 状态：**已完成（9 tests passed）** —— 校准候选，待 zj 复核并回填架构 §5。
> 上游：架构 §9 剩余项 ③ / PRD §7 度量；对应调研 Topic **T7.1（复利度量基础设施）** + **T6.2（复用率度量支撑 / 引用埋点）**。
> Substrate：Postgres + pgvector（`zkc` 库 @ :55433，复用 spike-01 base + spike-04 transform + spike-05 modeling_artifact + spike-04 venv）。

## 1. 目的

定义「复利可观测」的度量口径，使 ZKC 不再只有"管线跑通"这一粗糙信号，而能回答：**系统是否真的在产生复利**。覆盖 PRD §7 四类指标：连接密度 / 复用率 / 方法论产出 / 衰减可控，并合成单一复利系数。

## 2. 度量口径定义（T7.1）

| 指标 | 公式 | 含义 |
|---|---|---|
| 连接密度 `connection_density` | `含 reverse_link/derived_from 边的动态节点数 / 动态节点总数` | 动态信息是否被连回元认知层（防止"捕获即孤岛"） |
| 复用率 `reuse_rate` | `被 citation 引用的 claim 数 / claim 总数`；`citations_per_claim` = 引用总数 / claim 总数 | 元认知 claim 是否被后续条目复用（知识不被一次性消费） |
| 方法论产出 `methodology_output` | `由 combine transform 产出的 modeling_artifact 数` | 动静结合实际凝结出的建模/方法论条目数 |
| 衰减可控 `decay_controllability` | `到期动态节点中(被 evidence_refs 引用 或 已归档)的数量 / 到期动态节点数` | 腐化前是否被处理，而非静默丢失 |
| 复利系数 `compounding_factor` | 四项归一化后加权合成（默认等权） | 单一可追踪的"复利健康度" |

- 阈值沿用架构 §6.3：`ROT_THRESHOLD = 0.9` 界定"到期"；`method_target = 10`（methodology 产出达 10 记满分，待校准）。
- 所有指标对空库安全（除零返回 0，不抛异常）。

## 3. T6.2 引用埋点（关键设计决策）

**复用率无法仅用 `meta_claim.evidence_refs` 计算**。`evidence_refs` 指向"claim 自身的来源节点"，方向与"claim 被后续条目引用"相反。必须新增显式引用关系：

```sql
CREATE TABLE citation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  citing_node_id  uuid REFERENCES node(id)       ON DELETE CASCADE,  -- 复用方（后续条目）
  cited_claim_id  uuid REFERENCES meta_claim(id) ON DELETE CASCADE,  -- 被复用的 claim
  produced_by     uuid REFERENCES transform(id)  ON DELETE CASCADE,  -- 可级联撤销
  created_at      timestamptz NOT NULL DEFAULT now()
);
```

此外，`衰减可控` 的"已归档"分支需要在 `node` 上记录状态，故新增列：

```sql
ALTER TABLE node ADD COLUMN archived_at timestamptz;
```

两条埋点都与既有不变量同构（`produced_by` 级联撤销；与 spike-06 给 `context` 加列的手法一致）。

## 4. 对架构 §5 的偏差（必须回填，不得静默接受）

| # | 架构/PRD 现状 | spike 07 实测/结论 | 性质 |
|---|---|---|---|
| D3 | `meta_claim.evidence_refs` 单向，复用率无从计算 | 新增 **`citation` 表**（双向溯源） | 新增（功能性） |
| D4 | `node` 无"已归档"状态 | 新增 **`node.archived_at`** 列 | 新增（功能性） |

## 5. 算子 API（`metrics.py`）

- `connection_density(cur)` / `reuse_rate(cur)` → `(rate, per)` / `methodology_output(cur)` / `decay_controllability(cur, rot_threshold=0.9)`
- `compounding_factor(cur, weights, method_target)` / `report(cur)` → `CompoundingReport`

## 6. 测试结果（9 passed）

| 类 | 验证点 |
|---|---|
| TestCompoundingMetrics | 6 项口径在合成场景下的精确值（密度 .25 / 复用率 .5 / 方法论 1 / 衰减可控 .5 / 复利系数 .3375 / report 形状） |
| test_empty_db_safe | 空库不抛异常，全部归 0 |
| test_expired_referenced_counts_handled | 到期动态节点被 evidence_refs 引用即算"已处理"（不只是归档） |
| test_citation_cascade_undo | T6.2 citation 随 transform 删除级联撤销，不变量成立 |

## 7. 仍 open（超出本 spike）

- **复利系数权重/目标值未校准**：等权 + `method_target=10` 是占位，需按"什么是好的复利"主观校准。
- **自动采集时机未定**：metrics 现为查询时聚合，未定义采集频率/历史快照（趋势比单点更重要）。
- **复用语义偏窄**：当前只度量 claim 被引用；条目被检索复用、context 被复用等更宽复用未覆盖。
- **衰减可控的"处理"定义不完全**：只含蒸馏引用 + 归档，未含"用户已读/已 dismiss"等轻量处理信号。

## 8. 运行

```bash
cd spikes/spike-07-compounding-metrics
../spike-04-distill-loop/.venv/bin/python -m unittest test_spike_metrics -v
# 演示报告：
../spike-04-distill-loop/.venv/bin/python run_spike.py --demo
```
