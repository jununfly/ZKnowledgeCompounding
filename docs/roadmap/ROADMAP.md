<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

<!-- zj-roadmap-authority/v1
role: process-state
durable-citation: forbidden
promote-via: ADR|design|contract|runtime-evidence
-->

> 数据文件: `roadmap.json` | 最后更新: 2026-11-12 14:56:27

[~][X+] 1. ZKC MCP 集成执行路线图
    ├── [~][X+] 1-19. 风险册观察期终判组：R4/R5/R6/R10/R14 终判与阈值 source 升级
    ... 该层还有 25 个兄弟，1 个 in_progress ▸

### 当前施工：1-19. 风险册观察期终判组：R4/R5/R6/R10/R14 终判与阈值 source 升级

聚合理由：R4（预算不足终判）、R5（L3 依赖标注）、R6（校准值 open）、R10（外生锚样本）、R14（补全延迟触发率）共享同一个外生锚——真实多日埋点，故同一节点判定，避免 5 个节点互相等待。与 1-22 的分工：1-22 提供工程动作（建语料、跑 calibrate、落权重），本节点负责风险册状态判定与文档收口，共享 tuning.calibrate() 门禁但不重复实现。R18 已由 1-15(D3) 覆盖，R1/R8/R17 不依赖观察期、另立 1-20。

2026-11-06 Q1-Q4 终判执行（zj 拍板）：R4=缩动态集（落 ADR-0010，D2 归档 24 条退出调度回路为默认处置）；R5=每日复审队列已交付；R6=METRIC_W_* 已 SIMULATION 并打来源标签（CALIBRATED 升档挂 1-26 门禁）；R10=只留痕不勾销（待 1-17 由 zj 显式勾销并同步其滞后 notes，仍记 6/20）；R14=保持 open（判据不可执行：completion_fired 仅存运行时 report、无生产 run 落库、无聚合数据源，spike-11 旧样本与单测不得冒充真实触发率）。节点保持 in_progress 挂 1-26；risks.md 与 ADR-0010 已同步；未改 tuning.REGISTRY（只读）、未触 PRD §9、未代 zj 给 verdict。

**决策：**
- Q: 为何 5 条风险聚成一个节点？ → R4/R5/R6/R10/R14 共享同一外生锚（真实多日埋点），拆成 5 个节点会互相等待且判定重复。R18 已由 D3 覆盖、R1/R8/R17 不依赖观察期，均排除在外。 (与 1-22 分工：本节点判状态，1-22 做工程动作)
- Q: 开始 1-19 的 scope gate 分类与开工真值基线？ → Product execution：本节点只做风险册状态判定与长期文档／ADR 收口；允许改 docs/risks.md、PRD §9（须 zj 拍板）、新增 ADR；代码、埋点、tuning.REGISTRY 与复审标注一律只读，不代 zj 给 verdict、不把 roadmap 完成状态当证据。工程动作（lexical 语料冷启动、calibrate 落权重）归 1-22／1-26，本节点不重复实现。真值（2026-11-06 20:47 GMT+8 只读）：zkc p64 累计 labeled_completed=20/20、7d rate=1.0（20/20）、all=true、观测 3 天；zkc meter 连续活跃日 3/7、标注率达标、budget 收敛 false（28d 估计 3.0、confidence=provisional、cv=0.0）、can_calibrate days_with_obs=3/14、saturated_days=1/3、ready=False；PG 只读 attention_observation 三行：11-04 3/3/queue27、11-05 3/3/queue0、11-06 14/14/queue0；node.last_reviewed_at 11-05 3 条、11-06 14 条，interval_adjustment 11-06 仅 3 条 feedback；llm_call_score=0、modeling_artifact=0。 (偏差留痕：1-17 notes 仍是 6/20、19:48 校准状态卡仍记 6/20 且称今日无快照行，与当前 20/20 实测不一致；11-06 单日 14 条且 queue_remaining=0，属单日脉冲且不计入饱和日，不能据此确认真实预算容量。开工机械验证：carrier validate Valid、stats 28 节点（completed 19／in_progress 3／pending 6）、focus=1-1、ready 含 1-19；HEAD 2c3f4f2、工作树仅 ?? tmp/。)
- Q: 5 条判据今日能否终判、1-19 能否 completed？ → 不能 completed。① R4 三选一：真实预算观测仅 3 天且 2 天清空队列、confidence=provisional；infeasible 证据来自占位常量与诊断语料，三选一须 zj 本人拍板，Agent 不代选。② R10：样本读数 20/20 与 rate 1.0 已真实达标，但 1-17 A 裁决明文要求达成后 PRD §9 TODO 与风险册状态由 zj 决定、勿自动勾销，故本轮只留痕不勾销。③ R14：completion_fired 只存在于运行时 report（cross_source.py 258 行附近），无生产 run 落库、无聚合证据，spike-11 旧样本与单测不得冒充真实触发率，判据不可执行。④ R5/R6：can_calibrate 门禁 3/14、1/3 未过，按判据④只能保持占位／SIMULATION 并显式留痕，CALIBRATED 归 1-26。⑤ risks.md 状态同步依赖上述裁决，暂不改。本轮动作限于开工、落盘真值与可判性、向 zj 提出 Q1-Q4；不改长期文档、不写 ADR、不动代码与埋点。 (硬约束：绝不伪造或批量灌入标注；verdict 必须 zj 本人给；SIMULATION／corpus-derived／诊断脚本读数不得冒充 CALIBRATED；过程状态不得当长期事实证据。)
- Q: Q1 R10 勾销口径？ → A：只留痕不勾销，保留给 1-17 由 zj 显式勾销并同步其滞后 notes。R10 样本口径已真实达标（zkc p64 累计 20/20、7d rate=1.0、all=true），但按 1-17 A 裁决，PRD §9 TODO 与风险册状态由 zj 在 1-17 显式勾销，本节点不代勾销。risks.md R10 状态保持「缓解中」，仅追加留痕日期戳。 (Q1=A 执行：risks.md R10 加 2026-11-06 留痕（不勾销），不改状态；不触 PRD §9。)
- Q: Q2 R4 三选一？ → B：缩动态集为默认处置。依据真实事实——D2 归档 = 退出整个调度回路（due/衰减扫描/higher_dim seeds），24 条归档后 due 归 0 但非恒久 0，动态集规模已被实际压缩，缓解「每日 51.6 条需求 vs 预算 1.0/天」的 infeasible 矛盾。真实预算确认（缺 ≥14d 真实埋点、confidence=provisional）与调 SURFACE_THRESHOLD（无数据支撑）均未采用。终判须落 ADR（exit_criteria[0]）。 (Q2=B 执行：R4 状态改「已终判·缩动态集」，risks.md + 降级链 + 新增 ADR 同步。)
- Q: Q3 R14 无生产 run？ → A：保持 open + 显式留痕「判据不可执行」。completion_fired 仅存在于运行时 report（cross_source.py 附近），无生产 run 落库、无聚合数据源；spike-11 旧样本与单测不得冒充真实触发率。挂真实 run 后再判，不补跑 dogfood 聚合（属工程动作越本节点 scope）。 (Q3=A 执行：R14 状态改「保持 open（判据不可执行）」，risks.md + 降级链留痕。)
- Q: Q4 R5/R6 与节点状态？ → A：按 EC④ 落地文档收口，顺手修 risks.md 过时描述（R5「依赖 P4.2」→ 每日复审队列已交付；R6「阈值全占位」→ METRIC_W_* 已 SIMULATION 并打来源标签）。节点保持 in_progress 挂 1-26（CALIBRATED 门禁未过）。R18 不在本组已由 D3 覆盖。 (Q4=A 执行：R5/R6 状态与描述更新；节点保持 in_progress；不改 tuning.REGISTRY（只读）。)
<!-- ROADMAP_SECTION_END -->
