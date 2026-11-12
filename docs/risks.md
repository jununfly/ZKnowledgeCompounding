# 风险登记册与降级链（长期沉淀）

> 沉淀来源：原 `docs/plans/ZKC-implementation-plan.md` §5（2026-11-02 文档治理中沉淀至本长期文档；原件已归档至 `docs/archive/plans/ZKC-implementation-plan.md`）。
> 本文件是 ZKC 风险的**长期单一真相源**。状态变更请直接在此维护；open / 缓解的细节原文见归档原件与架构「证据来源」表。
> 2026-11-06 清理：已闭合风险（已缓解 / 已关停 / 已交付 / 已解决）已从本表移除并归档至 `docs/archive/plans/`，本表仅保留仍活跃或挂观察期项（R4 / R6）。R10（外生锚供给风险）已于 2026-11-07 由 1-17 显式收口（实证达成），已归档至 `docs/archive/plans/ZKC-risk-R10-closed.md` 并从本表移除。**R14 已于 2026-11-12 由 1-27-2 真实 10 run 裁决收口为「确认安全·保持 completion 开启」，已归档至 `docs/archive/plans/ZKC-risk-R14-closed.md` 并从本表移除**。

## 风险登记册

| ID | 风险 | 来源 | 影响 | 降级预案 | 状态 |
|---|---|---|---|---|---|
| R4 | **注意力预算不足 → 腐化无解**（rot=100%） | Spike 01/09 + 1-8-6 实测 | 到期条目全腐化 | **已校验（2026-11-01，1-8-6）**：`scripts/r4_budget_check.py` 对真实语料（61 条）跑数——L1 需求 **51.6 条/天** vs 默认预算 1.0/天（estimator warm-up 回退）→ L2 延后 59 条后仍 **infeasible=True**，**58/61 条复审时 decay≥0.9（复审前必腐化）**→ 当前预算下「衰减可控」恒 0，预警定量证实。诚实降级契约生效：infeasible 显式报告、不静默拉长。**终判挂 1-7-4 观察期外生锚**（真实 budget），届时三选一：真实预算确认 / 缩动态集 / 调 SURFACE_THRESHOLD（留痕）。**2026-11-06 终判（zj 拍板 Q2=B）**：选**缩动态集**为默认处置——D2 归档 = 退出整个调度回路（due/衰减扫描/higher_dim seeds），24 条归档后 due 归 0 但非恒久 0，动态集规模已被实际压缩，缓解「每日 51.6 条需求 vs 预算 1.0/天」的 infeasible 矛盾；真实预算确认（缺 ≥14d 真实埋点、confidence=provisional）与调 SURFACE_THRESHOLD（无数据支撑）均未采用。残余：未归档动态节点仍按 interval 到期，预算紧张本质未消除，保留观察 | 已终判·缩动态集（D2 归档 24 条退出调度回路为默认处置；真实预算确认/调 SURFACE_THRESHOLD 未采用） |
| R6 | budget/振荡带/ARCHIVE-vs-28d 规则未统一，阈值全占位 | Spike 09 | 调度精度漂移 | **规则已统一（P4.5 单程票，2026-10-31 拍板）；阈值已冻结进 `zkc/tuning.py` + 来源标签（P1.4）**；校准门禁 = 连续 14 天埋点且 ≥3 饱和日；校准期 oversubscribe×1.5 防低估固化。**2026-11-06 复核（Q4=A）**：原「阈值全占位」已过时——`METRIC_W_*` 等已置 SIMULATION 并打来源标签，非全占位；CALIBRATED 升档归 1-26（**2026-11-11 zj 显式覆盖自动门禁结案**：METRIC_W_* + MIN_INTERVAL_DAYS 在 tuning.py seed 直接标 CALIBRATED，数值维持 SIMULATION 等权结论，非经 calibrate() 门禁） | 缓解（规则已统一；阈值已冻结 tuning.py + 来源标签；1-26 于 2026-11-11 由 zj 显式覆盖门禁结案，METRIC_W_* 等标 CALIBRATED） |

## 关键降级链与观察期锚

- **R4（注意力预算不足 → 腐化无解）**：已校验 infeasible 已显式化（2026-11-01，1-8-6）；**2026-11-06 终判（zj 拍板 Q2=B）= 缩动态集**——D2 归档 24 条退出调度回路为默认处置；真实预算确认/调 SURFACE_THRESHOLD 未采用。详见 ADR-0010。