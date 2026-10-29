# Spike 01 — 双轨 schema + decay

> 状态：**完成**（结论待 zj 采纳）
> 目标：验证「双轨 schema + decay 分数 + 计划重评估」能否真正防止动态信息腐化，并为 decay 函数选型提供证据。

## 假设（可证伪）

1. 动态轨若**不做**计划重评估，会在有限时间内大面积腐化（预期 rot_rate 接近 100%）。
2. 加上「decay 分数 + 每日注意力预算内的重评估」后，腐化可被控制在 **≤10%**。
3. 三种 decay 函数（线性 / 指数 / 阶梯）中，至少有一种不可用。

## 成功阈值（先于结果设定）

| 指标 | 阈值 |
|---|---|
| rot_rate（腐化率，decay ≥ 0.9 且未被复审） | ≤ 10% |
| 每日进入注意力的条目数 | ≤ 每日预算（5） |
| 静态轨 | decay 恒为 0（由双时态管辖，不受 decay 影响） |
| 元认知 claim | 无 `evidence_refs` 必须被拒绝 |

## 可丢弃边界

本 spike 为**模型验证**，不是生产代码。`decay_model.py` 的结论可被采纳后重写；Postgres schema 仅验证可执行性，未做迁移/回滚设计。

## 产出物

| 文件 | 说明 |
|---|---|
| `schema.sql` | Postgres 16 + pgvector DDL（node / meta_claim / edge / context） |
| `test_decay.py` | 18 个测试（TDD：先红后绿） |
| `decay_model.py` | 三种 decay 函数 + 调度器 + 模拟器 |
| `run_spike.py` | 对比实验 + Postgres 端到端验证 |

运行：
```bash
python3 -m unittest test_decay      # 18 passed
python3 run_spike.py                 # 对比表 + DB 验证
```

## 结果

### 1. 对比实验（50 条动态条目 / 60 天 / 每日预算 5 / interval 21 天）

| 函数 | 进入注意力 | 腐化 | **行动窗口** | rot_rate | 结论 |
|---|---|---|---|---|---|
| **linear** | 12.6 天 | 18.9 天 | **6.3 天** | **0%** | ✅ 推荐默认 |
| exponential | 27.8 天 | 69.8 天 | 42 天 | 0% | ⚠️ 可用但**过慢**（28 天才进入注意力，对"快速腐化"的动态信息太迟） |
| step | 21.0 天 | 21.0 天 | **0 天** | **100%** | ❌ **否决** |

### 2. 关键发现

1. **阶梯衰减（step）必须否决**：它在同一瞬间跨过「进入注意力」与「已腐化」两个阈值——条目被推送给你时**已经腐化**，行动窗口为 0。这不是调参问题，是函数形状问题。
2. **decay 机制确实起作用**：不加调度（预算=0）时 rot_rate = **100%**；加上调度后 linear/exponential 均降到 **0%**。证明「计划重评估」是防腐化的原因，而非时间本身。
3. **注意力预算必须覆盖需求，否则无解**：interval=7、预算=2 时（需求 7.14/天 > 预算 2），rot_rate = **100%**。
   → **有效复审节奏 = SURFACE_THRESHOLD × review_interval**，因此真实需求 = `条目数 / (0.6 × interval)`，不是 `条目数 / interval`。选型时必须按前者算。
4. **指数衰减窗口大但触发太晚**（27.8 天才进入注意力），与动态信息"快速腐化"的语义相悖；若采用需把 interval 调小。

### 3. Postgres 端到端验证（pgvector/pgvector:pg16）

- DDL 全部执行成功，含 `vector(1024)`、enum 类型、`uuid[]` 上的 GIN 索引。
- 50 条 dynamic 节点入库，`decay_score ≥ 0.6` 的调度查询按预算取前 5 条 ✅
- 静态轨插入后 `decay_score = 0` ✅（由双时态管辖，不受 decay 影响）
- 无 `evidence_refs` 的 claim 被 **拒绝** ✅（溯源在 schema 层强制）

## 结论与建议

- **decay 默认选 linear**（可预测、6.3 天行动窗口、触发时机合理）；exponential 作为可选（需调小 interval）；**step 否决**。
- **静态轨不参与 decay**——这点已在 schema 与代码两层验证。
- **调度容量是硬约束**：上线前必须按 `n_items / (SURFACE_THRESHOLD × interval)` 反推所需注意力预算，否则系统会静默失效。

## 未决（留给后续 spike）

- 真实 `review_interval` 如何按条目自动设定（当前为固定值）。
- `attention_signal` 的加权方式（当前仅用 decay 排序）。
- 到期条目「蒸馏」与「归档」两种处理路径如何分流。

## 环境说明

spike 用的 Postgres 跑在 Docker 容器 `zkc-spike-pg`（`pgvector/pgvector:pg16`）。
本机 `pg_ctl` 因残留 `postmaster.pid` 无法启动，故改用容器；另有 `zbrain-postgres-1-1` 属于他项目，未触碰。
停止容器：`docker stop zkc-spike-pg`。
