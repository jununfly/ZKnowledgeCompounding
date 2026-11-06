# ADR-0010 · R4 终判：以「缩动态集」为默认处置（D2 归档退出调度回路）

Status: accepted (2026-11-06, zj 拍板 1-19 Q2=B)

## 背景与问题

R4 = **注意力预算不足 → 腐化无解（rot=100%）**。Spike 01/09 + 1-8-6 实测已证实：

- 真实语料 61 条，L1 需求 **51.6 条/天** vs 默认预算 1.0/天（estimator warm-up 回退）；
- L2 延后 59 条后仍 **infeasible=True**，**58/61 条复审时 decay≥0.9（复审前必腐化）**；
- 诚实降级契约已生效：infeasible 显式报告、不静默拉长。

原终判挂观察期外生锚（真实 budget），届时三选一：**真实预算确认 / 缩动态集 / 调 SURFACE_THRESHOLD**（留痕）。2026-11-06 zj 在 1-19 拍板 **Q2=B**，选「缩动态集」为默认处置。

## 决策

1. **R4 终判 = 缩动态集（默认处置）**。依据真实已发生事实——D2 归档 = 退出整个调度回路
   （due / 衰减扫描 / higher_dim seeds），24 条归档后 due 归 0 但**非恒久 0**（未归档节点按
   interval 继续到期）。动态集规模已被实际压缩，缓解「每日 51.6 条需求 vs 预算 1.0/天」的
   infeasible 矛盾：退出回路的 24 条不再竞争注意力预算，把「全腐化无解」降级为
   「可控子集 + 退出回路项」。
2. **另两选项未采用**：
   - 真实预算确认——缺 ≥14d 真实埋点、`confidence=provisional`（28d 估计 3.0），门禁归 1-26，当前不可执行；
   - 调 SURFACE_THRESHOLD——无数据支撑，改表面阈值属掩盖而非解决，违反诚实降级契约。
3. **范围边界**：R4 是风险登记册条目，本 ADR 只定风险终判口径，不引入新代码。
   D2 归档机制已由 ADR-0009 Consequence 1（`floor_hit` → archive）+ 既有 corpus archive
   真实落地，无需新增实现；本节点 scope gate = 代码只读。

## Considered Options

- **缩动态集（采纳）**：以 D2 归档压缩动态集，真实已发生（24 条归档退出回路）。是缓解而非根治——
  未归档动态节点仍按 interval 到期，预算紧张本质未消除，但把「全腐化无解」降级为可管理的子集。
- **真实预算确认（拒绝）**：需 ≥14d 真实埋点、被删失样本干扰（清空队列日为删失），
  `confidence=provisional`，门禁归 1-26；当前数据不可辨识真实预算容量。
- **调 SURFACE_THRESHOLD（拒绝）**：无数据支撑，改表面阈值属掩盖而非解决，违反
  infeasible 显式报告的诚实降级契约。

## Consequences · 必须同时记住的边界

1. **risks.md R4 状态变更**：由「已校验·infeasible 已显式化（终判挂观察期）」改为
   「已终判·缩动态集（D2 归档 24 条退出调度回路为默认处置；真实预算确认/调 SURFACE_THRESHOLD 未采用）」；
   降级链条目注明 2026-11-06 终判（zj 拍板 Q2=B）。
2. **残余保留观察**：未归档动态节点仍受预算约束；若未来 D2 归档不足以覆盖，须回到
   真实预算确认或 SURFACE 调整，但必须以真实埋点为准，**不得伪造或批量灌入标注**。
3. **不冒充 CALIBRATED**：本终判基于已发生的 D2 归档事实，不是新校准；R4 闭环不写入
   `tuning.REGISTRY`，不写回任何 CALIBRATED 口径（沿用 EC④ 度量双轨护栏）。
4. **与 1-19 节点关系**：本 ADR 满足 `exit_criteria[0]`（R4 三选一终判落 ADR）；
   R4 判据完成，但 1-19 整体保持 in_progress（挂 1-26），因 R6 的 CALIBRATED 升档
   与 R14 触发率聚合仍需真实多日埋点（can_calibrate 门禁 3/14、1/3 未过）。
   注：R5 已于 2026-11-06 风险册清理中作为「已交付」归档（不在 CALIBRATED 升档路径），
   故此处仅保留 R6。

## 验证证据

- roadmap 1-19 决策「Q2 R4 三选一？」= B（缩动态集为默认处置），含 2026-11-06 20:47 真值基线。
- risks.md R4 行 + 降级链条目已同步（见本 ADR Consequence 1）。
- D2 归档机制真实落地：ADR-0009 Consequence 1（`floor_hit` → `store.nodes.archive` +
  写 `interval_adjustment` 审计 `kind='floor_hit_archive'`）；`attention_observation`
   生产只读复核 11-06 单日 14 条且 `queue_remaining=0`，24 条归档后 due 归 0（非恒久 0）。
- 硬约束自证：本 ADR 未引入任何标注灌入、未把过程状态当长期事实、未冒充 CALIBRATED。
