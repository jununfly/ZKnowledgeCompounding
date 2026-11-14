# 风险登记册与降级链（长期沉淀）

> 沉淀来源：原 `docs/plans/ZKC-implementation-plan.md` §5（2026-11-02 文档治理中沉淀至本长期文档；原件已退役删除）。
> 本文件是 ZKC 风险的**长期单一真相源**。状态变更请直接在此维护；open / 缓解的细节原文见归档原件与架构「证据来源」表。
> 2026-11-06 清理：已闭合风险（已缓解 / 已关停 / 已交付 / 已解决）已从本表移除（归档副本已退役删除），本表仅保留仍活跃或挂观察期项（R4 / R6）。R10（外生锚供给风险）已于 2026-11-07 由观察期收口（实证达成），收口证据见观察期收口决策记录，归档副本已退役删除。**R14 已于 2026-11-12 由 R14 真实 10 run 裁决收口为「确认安全·保持 completion 开启」，收口证据见 `data/r14_telemetry.jsonl` + `scripts/r14_status.py`（R14 真实 run 为过程态记录），归档副本已退役删除**。

## 风险登记册

| ID | 风险 | 来源 | 影响 | 降级预案 | 状态 |
|---|---|---|---|---|---|
| R4 | **注意力预算不足 → 腐化无解**（rot=100%） | Spike 01/09 + 注意力预算维度实测 | 到期条目全腐化 | **已校验（2026-11-01，注意力预算维度）**：`scripts/r4_budget_check.py` 对真实语料（61 条）跑数——L1 需求 **51.6 条/天** vs 默认预算 1.0/天（estimator warm-up 回退）→ L2 延后 59 条后仍 **infeasible=True**，**58/61 条复审时 decay≥0.9（复审前必腐化）**→ 当前预算下「衰减可控」恒 0，预警定量证实。诚实降级契约生效：infeasible 显式报告、不静默拉长。**终判挂 R10 观察期外生锚**（真实 budget），届时三选一：真实预算确认 / 缩动态集 / 调 SURFACE_THRESHOLD（留痕）。**2026-11-06 终判（zj 拍板 Q2=B）**：选**缩动态集**为默认处置——D2 归档 = 退出整个调度回路（due/衰减扫描/higher_dim seeds），24 条归档后 due 归 0 但非恒久 0，动态集规模已被实际压缩，缓解「每日 51.6 条需求 vs 预算 1.0/天」的 infeasible 矛盾；真实预算确认（缺 ≥14d 真实埋点、confidence=provisional）与调 SURFACE_THRESHOLD（无数据支撑）均未采用。残余：未归档动态节点仍按 interval 到期，预算紧张本质未消除，保留观察 | 已终判·缩动态集（D2 归档 24 条退出调度回路为默认处置；真实预算确认/调 SURFACE_THRESHOLD 未采用） |
| R6 | budget/振荡带/ARCHIVE-vs-28d 规则未统一，阈值全占位 | Spike 09 | 调度精度漂移 | **规则已统一（P4.5 单程票，2026-10-31 拍板）；阈值已冻结进 `zkc/tuning.py` + 来源标签（P1.4）**；校准门禁 = 连续 14 天埋点且 ≥3 饱和日；校准期 oversubscribe×1.5 防低估固化。**2026-11-06 复核（Q4=A）**：原「阈值全占位」已过时——`METRIC_W_*` 等已置 SIMULATION 并打来源标签，非全占位；CALIBRATED 升档归人工覆盖校准（**2026-11-11 zj 显式覆盖自动门禁结案**：METRIC_W_* + MIN_INTERVAL_DAYS 在 tuning.py seed 直接标 CALIBRATED，数值维持 SIMULATION 等权结论，非经 calibrate() 门禁）。**2026-11-12 经后续收口（A+(a)）**：正式自动校准门禁在真实数据上判定不可达（真实四分量 cd/rr/mo 结构性为 0、dc=1.0 为归档假象，权重不可辨识）；zj 拍板保留 CALIB_OVERRIDE_AT 作为**永久 caveat**，权重维持等权 0.25×4（均匀先验 Bayes 最优默认）。未来若真实四分量可辨识，须由 zj 显式给出价值排序外生锚后方可改权重（参考先验 cd .35/rr .30/mo .20/dc .15 仅作提案、未应用、未归因 zj） | 缓解·永久 caveat（规则已统一；阈值已冻结 tuning.py + 来源标签；2026-11-11 由 zj 显式覆盖门禁结案，METRIC_W_* 等标 CALIBRATED；2026-11-12 经后续确认：CALIB_OVERRIDE_AT 保留为永久 caveat，calibrate() 门禁机制未失效、仍作真实性护栏） |
| R15 | **复审标注四档语义 v2 落地不变量漂移**（外生锚 A 人工输入归零 / 覆盖不退出·清除退出硬契约 / 四类审计 reason 互异 / 不污染 1-26 CALIBRATED） | ADR-0011 + ADR-0012（Plan `2026-11-14-zkc-verdict-semantics-plan.md` Step 2 规格链） | verdict 语义 v2 落地若重新引入 AIMD 乘因子或错配调度回路，将污染 decay-only 复审恒 no-op 架构结论、使无价值 `stale` 更频繁进入注意力 | **以失败在先断言锁死（ADR-0012 §5）**：A3 `decide_review` 对 `changed`/`stale` 不调用 `adapt_interval`（外生锚 A 人工输入归零）、B2/C2 `changed`/`stale 覆盖` 写双时态新版本且**不退出**调度回路、D2 `stale 清除` 走 `archive` 且**退出** due 队列、F1 `changed`/`stale_overwrite`/`stale_purged`/`browsed_without_label` 四类 reason 互异；CLI 门禁 C1–C4 拒缺内容载荷/缺 stale 分支；阈值常量（`tuning.py` 的 `AIMD_UP`/`AIMD_DOWN`/`MIN_INTERVAL_DAYS`/`METRIC_W_*`）**不动**、不写回 `REGISTRY`；清除只映射 `archive` 软归档、**无物理删除** | 缓解·待 Step 4 测试守卫（spec ADR-0012 已冻结 2026-11-14；落码未启动，不变量待红绿实现守住） |

## 关键降级链与观察期锚

- **R4（注意力预算不足 → 腐化无解）**：已校验 infeasible 已显式化（2026-11-01，注意力预算维度）；**2026-11-06 终判（zj 拍板 Q2=B）= 缩动态集**——D2 归档 24 条退出调度回路为默认处置；真实预算确认/调 SURFACE_THRESHOLD 未采用。详见 ADR-0010。