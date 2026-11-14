## ZJ Roadmap

<!-- zj-roadmap-authority/v1
role: process-state
durable-citation: forbidden
promote-via: ADR|design|contract|runtime-evidence
-->

> 数据文件: `2026-11-14-zkc-verdict-semantics-roadmap.json` | 最后更新: 2026-11-14 20:15:45


<!-- ROADMAP_TREE_START -->
<!-- 由 zj-roadmap-driven 自动生成，请勿手动编辑 -->
[ ][Y+] 1. ZKC 复审标注四档语义缺口收敛 · Plan 过程态 roadmap
├── [x][Y+] 1-1. Step 1 语义裁决：收敛四档语义的 Human 逐项拍板（zj-grilling）
├── [x][Y+] 1-2. Step 2 规格与验收判据：把 S0/S1/S2 转成可测断言（zj-to-spec）
│   ├── [ ][Y+] 1-2-1. 语义矩阵 v2 规格：内容轴与节奏轴分列、stale 两分支分列
│   ├── [ ][Y+] 1-2-2. CLI verdict 与必填内容载荷、stale 分支选择的参数变更清单
│   ├── [ ][Y+] 1-2-3. OUTCOME_VERDICT 与终局动作两张表的断言更新清单
│   ├── [ ][Y+] 1-2-4. L1 基线重置、archive 退出调度回路与四类审计 reason 的断言口径
│   └── [ ][Y+] 1-2-5. 口径切换点记录格式与回归用例清单
├── [ ][Y+] 1-3. Step 3 契约与设计评审：锁定外生锚 A 与不变量清单（zj-tech-design-review）
│   ├── [ ][Y+] 1-3-1. 复核外生锚 A、标注率闸门与埋点口径的连带影响
│   ├── [ ][Y+] 1-3-2. 锁定 AIMD 自适应环路人工输入归零的架构级结论
│   └── [ ][Y+] 1-3-3. 产出不变量清单：L1 基线重置与 archive 退出边界
├── [!][Y+] 1-4. Step 4 小切片实现：红绿重构语义矩阵 v2 与 CLI 契约（zj-tdd）
│   ├── [!][Y+] 1-4-1. 红阶段：逐条构造失败在先的语义断言
│   ├── [!][Y+] 1-4-2. 绿阶段：语义矩阵 v2 与 nodes.save 双时态新版本
│   ├── [!][Y+] 1-4-3. 绿阶段：L1 基线重置与 archive 软归档退出调度回路
│   ├── [!][Y+] 1-4-4. 绿阶段：分支选择人工门禁与四类审计 reason 区分
│   └── [!][Y+] 1-4-5. 绿阶段：CLI 契约、全量测试证据与口径切换点记录
├── [!][Y+] 1-5. Step 5 代码审查与证据复核：改动、测试与不变量三方对齐（zj-code-review）
│   ├── [!][Y+] 1-5-1. 复核改动范围、测试证据与不变量是否仍成立
│   └── [!][Y+] 1-5-2. zkc decide --list --json 真值回读与 choices 一致性核对
├── [!][Y+] 1-6. Step 6 长期文档收口：ADR、风险册与证据提炼（zj-doc-health）
│   ├── [!][Y+] 1-6-1. ADR：语义矩阵 v2、外生锚 A 改终局动作、AIMD 人工输入归零与已知取舍
│   ├── [!][Y+] 1-6-2. risks：标注率闸门与 archive 退出调度回路契约
│   └── [!][Y+] 1-6-3. evidence：真值回读证据、口径切换点与一致性检查记录
└── [!][Y+] 1-7. Step 7 注释方向偏差独立收口：tuning.py doc-only 切片（zj-doc-health）
    ├── [!][Y+] 1-7-1. 修订 tuning.py:120-121 的 AIMD_UP / AIMD_DOWN 中文注释方向
    └── [!][Y+] 1-7-2. 一致性检查与独立提交（不并入语义实现批次）
<!-- ROADMAP_TREE_END -->

### 阻塞链

- 1-4. Step 4 小切片实现：红绿重构语义矩阵 v2 与 CLI 契约（zj-tdd） ← e5: 1-3. Step 3 契约与设计评审：锁定外生锚 A 与不变量清单（zj-tech-design-review） [ ]
- 1-4-1. 红阶段：逐条构造失败在先的语义断言 ← e17: 1-3. Step 3 契约与设计评审：锁定外生锚 A 与不变量清单（zj-tech-design-review） [ ]
- 1-4-2. 绿阶段：语义矩阵 v2 与 nodes.save 双时态新版本 ← e18: 1-3. Step 3 契约与设计评审：锁定外生锚 A 与不变量清单（zj-tech-design-review） [ ]
- 1-4-3. 绿阶段：L1 基线重置与 archive 软归档退出调度回路 ← e19: 1-3. Step 3 契约与设计评审：锁定外生锚 A 与不变量清单（zj-tech-design-review） [ ]
- 1-4-4. 绿阶段：分支选择人工门禁与四类审计 reason 区分 ← e20: 1-3. Step 3 契约与设计评审：锁定外生锚 A 与不变量清单（zj-tech-design-review） [ ]
- ... 另有 11 个节点被阻塞未列出

### 决策历史

| 节点 | 问题 | 答案 | 备注 |
|------|------|------|------|
| 1 | 把已批准 Plan 编排成 roadmap 属于什么 scope？ | 过程态编排（类比 Acceptance/evaluation）：仅写 docs/plans/ 下 carrier 与 Markdown 视图；目标项目源码、阈值、长期文档保持只读；不启动 Step 2–7 能力链、不进入 Composer handoff、不启动 TDD 执行链、不改任何 verdict 或内容载荷；不把任何节点置 in_progress 或 completed。 | zj 2026-11-14 16:53 指令「把 ...plan.md 编排成roadmap，保存到 docs/plans/ 下」；Scope gate 分类声明。 |
| 1 | 与 16:40/16:43 归档口径「不恢复 carrier / 视图 / 过程编排链」冲突怎么处理？ | 按 zj 更晚的显式指令执行：本次恢复单份 carrier + 单份轻量 md 视图 + 一份全量导出，但仅作该 Plan 的过程态投影，不重建全局过程编排链。2026-11-14 18:57 zj 指令「解决这些风险与偏差」后，原 Plan 已补记 §口径变更记录：把过时的「不恢复 carrier / 视图 / 目录下仅此一份文件」改为真实口径，并显式列出未被覆盖的批准状态、plan_acceptance=pending、Step 1–7 未执行、不进 handoff、不启动 TDD 执行链。口径冲突已收口，不再是待确认项。 | zj 口述 > workspace 实物；偏差以补记方式留痕，不静默改写已批准归档的裁决/规格/验收字段。 |
| 1 | Step 节点的状态怎么定？ | 全部 pending。Plan 明载 plan_acceptance=pending、Step 1–7 能力链未执行，不得把节点 completed 当作 proof / evidence；已由 zj 给出的裁决只以 decisions 形式落盘，不改状态。 | ADR-0008 与项目护栏 #9：节点完成状态不是长期事实的证明。 |
| 1 | carrier 与视图的命名/落点怎么定？ | carrier = 2026-11-14-zkc-verdict-semantics-roadmap.json；轻量视图 = 2026-11-14-zkc-verdict-semantics-ROADMAP.md（render 生成）；全量导出 = 2026-11-14-zkc-verdict-semantics-ROADMAP-full.md（section --all 生成）。三者都在 docs/plans/，与 Plan 同目录、同日期前缀一一对应。 | 带日期前缀而非通用 roadmap.json / ROADMAP.md，避免被误读为重开全局过程编排链；全量导出是 CLI 显式导出视图，供 Human 审阅全量决策表，不是手工编辑的 md section。 |
| 1 | 权威边界与结论提炼路径？ | process-state only：本 roadmap 回答接下来执行什么，不回答产品行为、架构、发布状态或正确性。语义矩阵 v2 与外生锚 A 由乘因子改终局动作、AIMD 自适应环路人工输入归零 → ADR；标注率闸门与 archive 退出契约 → risks；zkc decide --list --json 真值回读 → evidence。未完成提炼前只作决策脉络溯源。 | durable 代码与长期文档不得引用 docs/plans/ 下文件作 proof / evidence。 |
| 1 | 零 completed 与 ready 读数怎么约束执行授权？ | 零 completed 是刻意口径，不是遗漏：Plan 明载 plan_acceptance=pending、Step 1–7 能力链未执行，未获 zj 显式授权前任何节点不得置 in_progress 或 completed；节点 completed 须同时具备 zj 显式授权与该 Step 的独立证据（ADR / contract / runtime-evidence），不得用节点完成状态当 proof / evidence。ready 是 CLI 按 blocks 边派生的「图上无未完成前驱」读数，不等于执行授权；子节点通过上游继承 blocks 边继承父 Step 的硬依赖，避免被误读为可开工。根节点作为分组节点仍会出现在 ready，属 CLI 已知口径。 | 收口上一轮「状态诚实」与「ready 派生噪声」两条偏差；对应 Plan §口径变更记录 与 ADR-0008 / 护栏 #9。 |
| 1 | 子工作为什么继承上游 Step 的 blocks 边？ | 纯机械修正，不是新增 Human 裁决：原图只有 Step 级 blocks 边，CLI 的 ready 把无前驱的 20 个子节点列为可开工，与「执行链未授权」的真实状态不符。给每个子节点补一条来自其父 Step 最近上游 Step 的 blocks 边后，ready 只剩根节点（分组节点，CLI 已知口径）与 1-1。边来源全是 Step 级外部节点，不依赖子节点完成状态，不引入父等子/子等父死锁；Plan §Capability composition 的 Step 级 dependencies 语义不变。 | 20 条继承边（e9–e28）；由 zj「解决这些风险与偏差」指令派生，Human 可否决。 |
| 1-1 | ①–④ 四项语义裁决怎么定？ | zj 2026-11-14 15:46 原话「① 否；② 拆；③ 承载；④独立」：①不新增 too_early 档（人工通道维持单向收缩，记为已知取舍）；②changed 与 stale 拆成不同信号；③changed 承载内容更新动作；④tuning.py:120-121 注释方向偏差独立成 doc-only 切片、独立提交。 | Plan §Human checkpoints.decisions_needed；原话逐字保留。 |
| 1-1 | changed / stale 的语义定案（S0）是什么？ | zj 2026-11-14 16:08 原话（须逐字保留）：changed = 内容变了，但还有参考价值；stale = 内容腐坏了，基本没有参考价值，要么被 enrich / refresh 覆盖，要么被清除。 | 两档都属内容/价值生命周期轴，不是节奏轴；原建议 b（stale 保留 too_late ×0.7）据此作废。 |
| 1-1 | a–d 规格衍生决策怎么定？（S1） | zj 2026-11-14 16:25 原话「a–d 同意推荐」：a. changed / stale 走 L3 终局动作、不走 AIMD 乘因子 —— changed 更新内容（nodes.save 双时态新版本）且 interval 重置为 L1 基线，stale 走 archive 退出调度回路；b. 「enrich / refresh 覆盖」= 节点双时态新版本，不是蒸馏产出 claim；c. 「清除」只映射 archive 软归档，审计 reason 须与 D2「价值已升元认知层」分开记；c2. changed 内容载荷新增必填参数，只由 zj 本人逐条给，缺失即拒收，绝不自动填充或推测；d. 今日已写入的 3 条 changed 保留旧语义产物 + 标注口径切换点，不回填、不重标记、不撤销 interval 调整。 | 规格输入 S1，须逐字保留；不触发 distill 是硬约束。 |
| 1-1 | stale 覆盖分支是否纳入本批次？（S2） | zj 2026-11-14 16:33 原话「stale 覆盖分支纳入」：S0 中 stale 的 enrich / refresh 覆盖分支与清除分支并列纳入本批次，S1-a 中对 stale 的单条 archive 描述据此细化为两分支，属补充而非推翻。覆盖 → nodes.save() 双时态新版本 + interval 重置 L1 基线、不退出调度回路；清除 → archive 软归档、退出 due 队列，审计 reason 与 D2 区分。 | 规格输入 S2，须逐字保留。 |
| 1-1 | 由 S2 + 外生锚铁律推导出的规格约束？ | ①stale 走覆盖还是清除只能由 zj 本人逐条给，不得自动判定或默认清除；②覆盖的内容载荷同样必填且只由 zj 给；③覆盖按 a 的 L1 基线同构重置，不继承旧内容收缩结果；④覆盖分支不退出调度回路、清除分支必须退出；⑤changed / stale 覆盖 / stale 清除 / D2 四类审计 reason 互不相同。 | agent 推导并明确标注：非 Human 新增裁决，Human 可否决。 |
| 1-1 | 两处不因裁决收口而消失的结构性问题？ | ①changed 与 stale 覆盖在系统动作上同构（都是双时态新版本 + L1 基线重置），②「拆」的价值判定差别必须落在审计 reason 与用例断言，否则等于只拆名字；②终局动作让 L3 不空转，但 AIMD ×1.5 / ×0.7 自适应环路的人工输入仍归零，退回 decay-only 恒 no-op，须由 Step 3 锁不变量并进 ADR，不因 a 已裁决而视为解决。 | Plan §Human checkpoints 结构性提醒；不得静默归为已解决。 |
| 1-1 | 「开始 1-1」的授权范围怎么定？ | zj 2026-11-14 19:21 指令「开始 1-1」= 仅对节点 1-1 的定点开工授权，构成对根节点门禁「未获 zj 显式授权前任何节点不得置 in_progress」的例外，只此一节点，不扩及 1-2–1-7。Scope gate 分类：Acceptance/evaluation 类比的过程态节点操作 —— 本 roadmap 是已批准 Plan 的过程态投影，项目不继续完成/发布；允许按请求更新 roadmap 元数据（状态 + 决策 + 视图），目标项目代码 / 依赖 / 产品文档保持只读。不启动 zj-grilling 重做裁决（①–④、S0、S1、S2 已于 15:46–16:33 由 zj 本人逐项给出并逐字落盘，重跑会重复劳动且可能扰动已定案裁决）；不进入 Composer handoff；不启动 Step 2–7 / TDD 执行链；不把 1-1 标 completed。 | 节点开工 ≠ 能力链启动。completed 仍受根节点门禁约束：须 zj 显式授权 + 该 Step 的独立证据（ADR / contract / runtime-evidence）；当前裁决原文只落在过程态 Plan / roadmap decisions，尚未提炼到 ADR，故不自动打勾。 |
| 1-1 | 1-1 的 completed 门禁怎么处理？（zj 19:31 选 A） | zj 2026-11-14 19:31 原话「A」：保持 1-1 为 `in_progress`，等 Step 6（长期文档收口）把语义矩阵 v2 定案提炼到 ADR 后，再谈 1-1 的 `completed`。不立即打勾、不放宽根节点门禁（`completed` 须 zj 显式授权 + ADR / contract / runtime-evidence 独立证据）、不把过程态 Plan / roadmap decisions / 工作日志当作独立证据。四条 exit_criteria 虽已满足，但判据满足不等于可 completed。 | 决策由 zj 本人给出，agent 只转录、不代拍。用 1-6 → 1-1 的 informs 边（非调度、不引入 blocks 环）标注「Step 6 的 ADR 是 1-1 completed 的证据来源」这一上下文。 |
| 1-1 | ADR-0011 提炼完成，1-1 是否转 completed？ | 是；依 zj 19:31 选项 A（等 Step 6 把语义矩阵 v2 提炼到 ADR 后再谈 completed），ADR-0011 已于 19:57 落盘，1-1 在此转 completed | 语义裁决（Step 1）产物已沉淀为长期 ADR；代码实现（Step 2-5）仍 pending、未授权；completed 只表 Step 1 决策定案收口，不作下游执行授权 |
| 1-2 | 「A 授权落码(Step 2 规格链)」的授权范围怎么定？ | A = 执行 Step 2 规格链（zj-to-spec）：产出可测规格与验收断言（ADR-0012），不含源码/测试实现；落码本体在 Step 4（zj-tdd）。B = 联动 docs/risks.md（新增 R15 硬不变量）。C = commit+push 作 batch checkpoint。 | Step 2 spec 已落 ADR-0012 为 completed 证据；源码/阈值/测试零改动；1-2 completed 不等同授权 Step 3-5 执行链 |


