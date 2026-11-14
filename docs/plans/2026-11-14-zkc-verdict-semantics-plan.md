<!-- zj-roadmap-authority/v1
role: process-state
durable-citation: forbidden
promote-via: ADR|design|contract|runtime-evidence
-->

# ZKC 复审标注四档语义缺口收敛 · Plan（已批准归档）

> **本文件是过程态文档，不是权威源。** 它由 `zj-composer` 于 2026-11-14 产出、经 zj 批准，
> 是本次议题收敛后的**唯一留存**。按 ADR-0008 与项目护栏 #9：durable 代码与长期文档不得引用
> 本文件作为 proof / evidence；其中任何结论要成为长期事实，须提炼到 ADR / PRD / 架构 /
> risks / evidence。`docs/plans/` 于 2026-11-03 治理中已删除，2026-11-14 16:43 按 zj 指令
> 重新启用为过程态目录；同日 16:53 zj 再指令把本 Plan 编排成 roadmap，同目录下新增单份 carrier
> 与两份 CLI 生成的 md 视图（见 §口径变更记录），仅作本 Plan 的过程态投影，**不重建全局过程态
> 编排链路**。批准范围仍仅状态定案与归档，不启动 Step 2–7 能力链、不进入 Composer handoff、
> 不启动 TDD 执行链。

## 批准与终止记录

| 项 | 值 |
|---|---|
| 批准人 | zj（本人口述） |
| 批准时间 | 2026-11-14 16:40 GMT+8 |
| 批准原话 | 「批准 Plan，不继续按 composer skill 的流程往下执行。把 composer skill 的输出内容收敛为一份plan文档(后删除那些输出内容)」 |
| 目录口径 | 2026-11-14 16:43 zj 改定：「可以改为用 docs/plans/，但要记得它是过程态目录」；16:53 再改定：本 Plan 编排成 roadmap 后恢复单份 carrier + 两份视图，详见 §口径变更记录 |
| 批准范围 | 仅状态定案与归档 |
| 明确不执行 | 不启动 Step 2–7 能力链、不进入 Composer handoff、不启动 TDD 执行链 |
| status | `approved` |
| human_review | `approved` |
| plan_acceptance | `pending`（验收判据未被消费、Step 1–7 未执行；如实保留，不伪造通过） |
| 批准状态校验 | `validate_plan.py` 两次（默认快照 / 项目内副本）均 `valid=true, 0 error, 0 warning, 7 steps`；handoff `eligible=false`，唯一理由 `plan_acceptance_not_passed` |

批准后的 `approval_point` / `handoff` 等字段是 Composer 契约的历史记录，**不代表本次授权执行**。
`rejection_path` 为模板 rejected 分支的保留项，当前不适用。

## 口径变更记录（2026-11-14 补记）

> 本节只修订**目录与产物口径**的描述，使本文件与 `docs/plans/` 实物一致；不改任何裁决、规格、
> 验收判据、批准状态与执行边界。补记触发：zj 2026-11-14 18:57 指令「解决这些风险与偏差」。

| 项 | 值 |
|---|---|
| 触发指令 | zj 2026-11-14 16:53：「把 ZKnowledgeCompounding/docs/plans/2026-11-14-zkc-verdict-semantics-plan.md 编排成roadmap，保存到 ZKnowledgeCompounding/docs/plans/ 下」 |
| 被覆盖的旧表述 | 本文件头部、批准记录「目录口径」行、原附录 B 末条：`docs/plans/` 仅作单份计划归档，不恢复 `roadmap.json` carrier / `ROADMAP.md` 视图 / 过程编排链，目录下仅此一份文件 |
| 新口径 | `docs/plans/` 下新增本 Plan 的过程态 roadmap 投影：单份 carrier + 两份 CLI 生成视图；仅作该 Plan 的过程态投影，**不重建全局过程编排链路**，也不恢复已删除的 `docs/roadmap/` carrier 与视图 |
| **未被覆盖（逐字保留）** | `status=approved` 仅指状态定案与归档；`plan_acceptance=pending`；Step 1–7 能力链未执行、验收判据未消费；不进入 Composer handoff；不启动 TDD 执行链；`approval_point` / `handoff` / `rejection_path` 仍为 Composer 契约历史记录；§Intent / §Capability composition / §Human checkpoints / §Evidence / §Verification / §Failure 全部字段不动 |
| 新增产物 | `2026-11-14-zkc-verdict-semantics-roadmap.json`（carrier / 事实源）、`...-ROADMAP.md`（render 轻量视图）、`...-ROADMAP-full.md`（section --all 全量导出） |
| roadmap 状态口径 | 28 节点、零 `completed`、15 条 decisions、28 条 `blocks` 边（8 条 Step 级 + 20 条子工作继承）+ 1 条 `informs` 边；2026-11-14 19:21 起 `1-1` 为唯一 `in_progress`（其余 27 `pending`），`ready` 只剩根节点；已给裁决只以 decisions 落盘；节点完成状态不作 proof / evidence（ADR-0008 / 护栏 #9） |
| 门禁复跑 | `scripts/zkc_authority_check.py .` = 4 process targets / 254 durable / 0 unresolved leaks；skill `authority-check .` = clean；`make mcp-gate` / `make invariant` 均通过 |
| 留痕 | roadmap 根节点 7 条 decisions（scope / 口径改定 / 状态口径 / 命名落点 / 权威边界 / 状态门禁 / 继承边口径）+ `1-1` 六条裁决 decisions、`.workbuddy/memory/2026-11-14.md` |

**边界说明**：`docs/plans/` 整类仍是过程态目录，4 份文件均非权威源；任何结论进入代码或长期文档前须
提炼到 ADR / design / contract / runtime-evidence。本补记**不构成**对 Step 1–7 执行链的授权。

**2026-11-14 19:21 补记**：zj「开始 1-1」只把 roadmap 节点 `1-1` 置 `in_progress`（过程态单点开工），
**不等于**启动 `zj-grilling` 能力链，也不授权 Step 2–7 / TDD 执行链；授权范围以 roadmap 节点 `1-1`
的 decision「『开始 1-1』的授权范围怎么定？」为准。`1-1` 的四条 exit_criteria 经只读核对均已满足，
但节点 `completed` 仍受根节点门禁约束（须 zj 显式授权 + ADR / contract / runtime-evidence 独立证据），
当前语义裁决原文只落在过程态 Plan / roadmap decisions / 工作日志，尚未提炼到 ADR，故未打勾。

**2026-11-14 19:31 zj 选 A 定案**：保持 `1-1` 为 `in_progress`，等 Step 6 把语义矩阵 v2 提炼到 ADR 后再谈
`completed`；不立即打勾、不放宽门禁、不把过程态产物当独立证据。该 Human 决策已落在 roadmap 节点
`1-1` 的 decision「1-1 的 completed 门禁怎么处理？（zj 19:31 选 A）」中，并用 `1-6 → 1-1` 的
`informs` 边标注证据来源上下文（非调度、不改变 `[!]` / `ready`）。

## Identity

- **plan_id:** `zkc-verdict-semantics-2026-11-14`
- **title:** ZKC 复审标注四档语义缺口收敛
- **status:** `approved`
- **template_version:** `1`
- **generated_at:** 2026-11-14T06:22:54Z
- **composer_version:** zj-composer-v1
- **human_review:** `approved`

## Intent

- **goal:** 按 zj 2026-11-14 15:46 四项裁决、16:08 语义定案、16:25 a–d 结论与 16:33 覆盖分支裁决收敛复审标注：changed = 内容变了但仍有参考价值，走 nodes.save() 双时态新版本 + interval 重置为 L1 基线；stale = 内容腐坏基本无参考价值，两条分支并列纳入本批次 —— enrich / refresh 覆盖走 nodes.save() 双时态新版本 + interval 重置为 L1 基线，清除走 archive 软归档退出调度回路；两档均属 L3 终局动作、不再走 AIMD 乘因子，内容轴与节奏轴分列；changed 内容载荷与 stale 覆盖内容载荷均新增必填参数、只由 Human 逐条给、缺失即拒收，stale 的分支选择亦只由 Human 逐条给、不得自动判定或默认清除；审计 reason 须区分 changed / stale 覆盖 / stale 清除三者且均与 D2 区分；已写入的 3 条 changed 保留旧语义产物并记录口径切换点，不回填不重标记；不新增 too_early 档（人工通道维持单向收缩，记为已知取舍）；tuning.py:120-121 注释方向偏差另立独立 doc-only 切片
- **scope:** 仅限 ZKC 本仓库内复审标注语义的定案、规格、实现与长期文档收口；含 L3 终局动作（L1 基线重置 / archive 退出调度回路）与 stale 覆盖、清除两条分支的规格与实现；不含 too_early 档；不含物理删除节点（仓库无此接口，清除只映射 archive）；注释修订为独立 doc-only 切片、独立提交，不并入语义实现批次；本阶段只产出可评审 Plan 与证据，不进入源码改动
- **constraints:** verdict 只能由 Human 本人给出；changed 与 stale 覆盖的内容载荷只能由 Human 本人给出，不得自动填充或推测；stale 走覆盖还是清除只能由 Human 本人逐条给出，不得自动判定或默认清除；已写入的历史标注不得回填或重标记；不得静默改动阈值参数；过程结论须沉淀到 ADR 与风险册；E1 已并入 1-26 结案，meter 仪表只读，不作完成度证明；stale 不得再复用 too_late ×0.7 缩短 interval 的旧映射，changed 亦不得再走 AIMD 乘因子；清除只映射 archive 软归档且审计 reason 须与 D2 区分，不得引入节点物理删除；覆盖分支不得走 archive，清除分支不得写节点新版本；changed 与 stale 覆盖的 interval 均重置为 L1 基线，不继承旧内容的收缩结果；changed 与 stale 覆盖在系统动作上同构，两者的价值判定差别必须落在审计 reason 与用例断言，不得只拆名字
- **desired_output:** 一份通过校验、可逐项评审的分片 Plan，配套不可变能力目录快照与固定验收判据
- **exclusions:** 不触发 distill、不写 meta_claim、不改阈值参数、本 Plan 阶段不做 git 提交推送、不注册系统级调度、不安装或创建任何能力包
- **permission_boundary:** 禁止未经 Human 审批的 write / publish / install / modify / delete / network call 与凭证使用；本阶段仅允许生成 Plan 与快照两份证据文件，且须 Human 审批后才可进入消费链

## Capability composition

### Step 1 — 语义裁决（Human 决策收敛）

- **skill_or_workflow:** zj-grilling
- **role:** 用多轮追问收敛四档语义的开放决策，产出 Human 逐项拍板记录
- **reason:** 需要先锁定验收判据：是否新增 too_early 档、changed 与 stale 是否拆分、changed 是否承载内容更新，否则后续规格没有稳定输入
- **inputs:** 本次只读核查结论（review.py:40 映射表、scheduling.py:220 因子分支、tuning.py:120-121 注释偏差）与本 Plan 的 Intent
- **outputs:** Human 逐项裁决记录（①–④ 已落盘）、16:08 语义定案 S0、16:25 a–d 结论 S1 与 16:33 覆盖分支裁决 S2，均作为语义矩阵 v2 的固定输入移交 Step 2
- **prerequisites:** 核查结论已落盘于 .workbuddy/memory/2026-11-14.md，且 Human 逐项裁决已给出
- **dependencies:** no dependencies
- **excluded_alternatives:** 不采纳 zj-discuss（发散讨论不产出可验收的拍板结论）与 zj-steelman（只替对立立场辩护，不收敛）

### Step 2 — 规格与验收判据

- **skill_or_workflow:** zj-to-spec
- **role:** 以已收口的 a / b / c / c2 / d 结论与 S2 为固定输入，把裁决与 16:08 语义定案转成可测规格与失败在先的验收断言，并定出 stale 分支选择参数的形态
- **reason:** TDD 红阶段需要明确的验收判据；a–d 与 S2 已由 Human 给出结论，必填内容载荷拒收、分支选择拒自动判定、L1 基线重置、archive 退出与三类审计 reason 区分必须写成稳定断言
- **inputs:** 裁决记录（①–④）、16:08 语义定案 S0、16:25 a–d 结论 S1、16:33 覆盖分支裁决 S2（stale 覆盖与清除两分支并列纳入）、src/zkc/cli.py 的 VERDICTS 常量、src/zkc/web/review.py 的 OUTCOME_VERDICT、src/zkc/expiry.py 的动作枚举、src/zkc/repository/protocols.py 的 NodeRepository 接口清单、tests/test_web_review.py:120-122 的映射断言
- **outputs:** 语义矩阵 v2 规格（内容轴与节奏轴分列、stale 两分支分列）、CLI verdict 与必填内容载荷及分支选择参数变更清单、OUTCOME_VERDICT 与终局动作两张表的断言更新清单、L1 基线重置与 archive 退出调度回路断言、changed / stale 覆盖 / stale 清除 / D2 四类审计 reason 口径、口径切换点记录格式、回归用例清单
- **prerequisites:** 上一环节已完成且每个决定项都有 Human 结论
- **dependencies:** Step 1
- **excluded_alternatives:** 不采纳 zj-to-tickets（拆任务票不写验收断言）与 zj-teach（面向讲解，不产出可测规格）

### Step 3 — 契约与设计评审

- **skill_or_workflow:** zj-tech-design-review
- **role:** 评审语义变更对外生锚 A、L3 AIMD、标注率闸门与埋点口径的连带影响，并锁定人工侧改走终局动作后 AIMD 自适应环路人工输入归零的架构级结论
- **reason:** 验收要求先证明改动不污染已结案的 1-26 CALIBRATED 口径，证据来自现有 ADR 与风险册
- **inputs:** 上一环节规格、docs/zj-adr/、docs/risks.md、src/zkc/scheduling.py:548-599
- **outputs:** 评审结论与必须锁定的不变量清单（含 AIMD 自适应环路退回 decay-only 恒 no-op 的架构级结论、L1 基线重置与 archive 退出的边界、覆盖分支不退出调度回路而清除分支必须退出的硬契约）
- **prerequisites:** 规格已成文且 Human 已确认决定项
- **dependencies:** Step 1, Step 2
- **excluded_alternatives:** 不采纳 zj-wait-what（只做质疑不落评审结论）与 zj-domain-modeling（面向领域建模，非本次边界复核）

### Step 4 — 小切片实现（TDD）

- **skill_or_workflow:** zj-tdd
- **role:** 以红绿重构实现语义矩阵 v2、changed 与 stale 覆盖的必填内容载荷及 nodes.save 双时态新版本、L1 基线重置、stale 清除归档退出、分支选择人工门禁、四类审计 reason 区分、以及 CLI 契约
- **reason:** 验收要求每条语义都有失败在先的测试证据，约束是不得静默改动阈值参数
- **inputs:** 规格、不变量清单、tests/test_web_review.py 与 tests/test_p1_review_fixes.py
- **outputs:** 新增与更新的用例、最小实现、全量测试输出证据、2026-11-14 语义口径切换点记录
- **prerequisites:** 规格与评审均已完成且 Human 审批已给
- **dependencies:** Step 2, Step 3
- **excluded_alternatives:** 不采纳 zj-prototype（原型不保证回归证据）与 zj-implement（不带红绿纪律）

### Step 5 — 代码审查与证据复核

- **skill_or_workflow:** zj-code-review
- **role:** 复核改动、测试证据与不变量是否仍成立
- **reason:** Plan acceptance 需要独立的证据复核，输入是上一环节的测试输出与改动清单
- **inputs:** 上一环节产物、zkc decide --list --json 真值回读、OUTCOME_VERDICT 与 CLI choices 一致性
- **outputs:** 审查结论（通过或退回）与证据清单
- **prerequisites:** 上一环节全量测试通过
- **dependencies:** Step 4
- **excluded_alternatives:** 不采纳 zj-review-findings（面向 findings 汇总，不复核改动）与 zj-neat-freak（只做整理）

### Step 6 — 长期文档收口（ADR 与风险册）

- **skill_or_workflow:** zj-doc-health
- **role:** 把语义矩阵 v2 定案、changed 与 stale 覆盖的内容更新通道、stale 两分支与 D2 的审计 reason 区分、外生锚 A 由乘因子改终局动作后的存续结论与已知取舍（不新增 too_early）沉淀到 ADR 与风险册
- **reason:** 项目护栏要求过程结论提炼到长期文档，验收要求语义定案与已结案 1-26 CALIBRATED 口径互不污染
- **inputs:** 裁决记录、规格、审查结论、docs/zj-adr/、docs/risks.md
- **outputs:** ADR 与风险册更新、语义口径切换点记录、一致性检查记录
- **prerequisites:** Step 5 审查结论为通过且 Human 已审批语义定案
- **dependencies:** Step 5
- **excluded_alternatives:** 不采纳 zj-docs-architecture（面向架构全图，非本次小范围收口）与 zj-edit-article（面向文章）

### Step 7 — 注释方向偏差独立收口（doc-only）

- **skill_or_workflow:** zj-doc-health
- **role:** 独立 doc-only 切片：只修订 src/zkc/tuning.py:120-121 的 AIMD_UP/AIMD_DOWN 中文注释方向，不改运行逻辑与阈值常量，单独提交
- **reason:** Human 裁决④要求注释偏差独立成片，验收要求注释与实现一致且不与语义实现混在同一变更批次
- **inputs:** src/zkc/tuning.py:119-121 注释、scheduling.py:220 的 _aimd_factor 因子分支、Step 5 审查结论
- **outputs:** doc-only 注释修订与一致性检查记录，独立提交，不并入语义实现批次
- **prerequisites:** Step 5 审查结论为通过，且 Human 已确认该切片独立提交
- **dependencies:** Step 5
- **excluded_alternatives:** 不采纳 zj-refactor（会触碰运行逻辑，越出 doc-only 边界）与 zj-neat-freak（只做整理，不校验注释与实现一致性）

## Gaps and suggestions

required skill：能把 ZKC 复审语义定案落成 ADR 与契约回归测试并在本项目内逐档校验 zkc decide 的证据协议
required skill：能隔离验证外生锚 A 与埋点口径并证明语义变更不污染已结案 CALIBRATED 门禁的审计能力
suggested capability：在 ZKC 仓库内增设绑定 zkc decide 真值回读的语义契约回归清单

来源：2026-11-14 对 src/zkc/web/review.py、src/zkc/scheduling.py、src/zkc/tuning.py 的只读核查，以及 tests/test_web_review.py:120-122 已固化的映射断言。
适配保留：以上形状均未在已安装目录内出现，属未来能力而非现成能力，不得当作已安装或已授权。
未知项：ZKC 仓库内尚无绑定本项目 CLI 真值回读的验收能力包，其证据格式与落地位置尚未定。
边界：本 Plan 只记录缺口与建议，不创建、不安装、不授予执行权。

## Human checkpoints

- **approval_point:** Human 审批点：本 Plan 交付后由 zj 逐项审阅并显式批准；四项语义裁决、16:08 语义定案、16:25 a–d 结论与 16:33 覆盖分支裁决均不等于 Plan 整体批准，未批准前任何步骤不得启动
- **decisions_needed:** ①–④ 已由 zj 本人于 2026-11-14 15:46 逐项裁决：①否（不新增 too_early 档，人工通道维持单向收缩，记为已知取舍）；②拆（changed 与 stale 拆成不同信号）；③承载（changed 承载内容更新动作）；④独立（tuning.py:120-121 注释偏差单独成 doc-only 切片，独立提交）。2026-11-14 16:08 zj 给出 ②③ 的语义定案（规格输入 S0，须逐字保留）：changed = 内容变了，但还有参考价值；stale = 内容腐坏了，基本没有参考价值，要么被 enrich / refresh 覆盖，要么被清除。据此两档都是内容/价值生命周期动作，不是节奏信号；原建议 b（stale 保留 too_late ×0.7）与 zj 语义冲突，已作废。2026-11-14 16:25 zj 原话「a–d 同意推荐」，规格阶段衍生决策全部收口（规格输入 S1，须逐字保留）：a. changed / stale 走 L3 终局动作、不走 AIMD 乘因子 —— changed 更新内容（nodes.save 双时态新版本）且 interval 重置为 L1 基线，stale 走 archive 退出调度回路；既不硬绑节奏轴，也不让 L3 空转；b. 「enrich / refresh 覆盖」= 节点双时态新版本，不是蒸馏产出 claim（后者属复利变换，会撞上不触发 distill 的硬约束）；c. 「清除」只映射 archive 软归档，审计 reason 须与 D2「价值已升元认知层」分开记；c2. changed 内容载荷新增必填参数，只由 zj 本人逐条给，缺失即拒收，绝不自动填充或推测；d. 今日已写入的 3 条 changed 保留旧语义产物 + 标注口径切换点，不回填、不重标记、不撤销 interval 调整。2026-11-14 16:33 zj 原话「stale 覆盖分支纳入」（规格输入 S2，须逐字保留）：S0 中 stale 的 enrich / refresh 覆盖分支与清除分支并列纳入本批次，S1-a 中对 stale 的单条 archive 描述据此细化为两分支，属补充而非推翻。由 S2 与既有外生锚铁律推导出的规格约束（非新增裁决，Human 可否决）：stale 走覆盖还是清除只能由 zj 本人逐条给出，不得自动判定或默认清除；覆盖的内容载荷同样必填且只由 zj 给；覆盖按 a 的 L1 基线同构处理，不继承旧内容收缩结果；覆盖分支不退出调度回路，清除分支必须退出；changed / stale 覆盖 / stale 清除 / D2 四类审计 reason 互不相同。结构性提醒：changed 与 stale 覆盖在系统动作上同构，②拆的价值判定差别必须落在审计 reason 与用例断言，否则等于只拆名字；终局动作不等于 AIMD 自适应环路仍有人工输入，该架构级结论由 Step 3 锁不变量并进 ADR，不因 a 已裁决而视为解决
- **rejection_path:** 保留本 Plan 并记录原因 because 需 Human 复审后另行裁决，不进入执行
- **side_effect_authorization:** 源码改动、阈值改写、git 提交推送与独立 doc-only 切片提交均须 Human 单独授权；changed 与 stale 覆盖的内容载荷及 stale 分支选择须由 Human 本人逐条给出；本 Plan 自身仅生成 Plan 与快照两份证据文件

## Evidence and provenance

- **skill_index_snapshot:** `catalog-v1-b397a22bfb436db13ae2787e202126a0e13940edf1b1e5565a022d45eec9d884`
- **catalog_revision_or_digest:** `b397a22bfb436db13ae2787e202126a0e13940edf1b1e5565a022d45eec9d884`
- **source_references:** selected=[zj-grilling -> zj-grilling/SKILL.md|zj-to-spec -> zj-to-spec/SKILL.md|zj-tech-design-review -> zj-tech-design-review/SKILL.md|zj-tdd -> zj-tdd/SKILL.md|zj-code-review -> zj-code-review/SKILL.md|zj-doc-health -> zj-doc-health/SKILL.md]; excluded=[Step 1 -> ZKC:src/zkc/web/review.py|Step 2 -> ZKC:tests/test_web_review.py|Step 3 -> ZKC:docs/risks.md|Step 4 -> ZKC:Makefile|Step 5 -> ZKC:src/zkc/scheduling.py|Step 6 -> ZKC:src/zkc/tuning.py|Step 7 -> ZKC:src/zkc/tuning.py]; gap=[required skill：能把 ZKC 复审语义定案落成 ADR 与契约回归测试并在本项目内逐档校验 zkc decide 的证据协议 -> ZKC:docs/zj-adr/|required skill：能隔离验证外生锚 A 与埋点口径并证明语义变更不污染已结案 CALIBRATED 门禁的审计能力 -> ZKC:docs/risks.md]; suggested=[suggested capability：在 ZKC 仓库内增设绑定 zkc decide 真值回读的语义契约回归清单 -> 本次会话只读核查 ZKC:src/zkc/web/review.py]
- **evidence_requirements:** Human 逐项裁决记录（①–④）、16:08 语义定案 S0 原文、16:25 a–d 结论 S1 原文、16:33 覆盖分支裁决 S2 原文；changed 与 stale 覆盖的内容载荷缺失时不得自动填充的失败断言；stale 分支选择缺失或被自动判定的拒收断言；changed / stale 覆盖的 interval 重置为 L1 基线而非 ×0.7 的失败断言；stale 清除走 archive 且退出 due 队列、覆盖写双时态新版本且不退出调度回路的失败断言；changed / stale 覆盖 / stale 清除 / D2 四类审计 reason 互异的失败断言；新增用例先失败后通过的两次输出；make test 全量结果（基线 574）；zkc decide --list --json 回读；ADR 与风险册更新记录；2026-11-14 口径切换点记录；注释一致性检查
- **generated_assertions:** 已安装目录 69 个能力包且元数据告警为 0；原 OUTCOME_VERDICT 把 changed 与 stale 同映射为 too_late；四档中无 too_early 且裁决①确认不新增；AIMD_UP 仅由 classify_review 自动触发，人工侧单向收缩为已知取舍；browse 使 labeled 不增；tests/test_web_review.py:120-122 已固化三条映射，语义变更后必须同步更新；现有 zkc decide 只有 --id 与 --verdict，没有任何内容载荷参数，changed 承载内容更新需新增输入通道；2026-11-14 已写入 3 条 changed 属旧语义产物；expiry.py:35-37 动作枚举只有 distill / archive / abstain，没有 enrich 或 refresh；PRD §2.2 的 enrich 指蒸馏产出 claim 去繁升维，不是覆盖节点内容；NodeRepository 协议无 delete 节点接口，只有 archive 软归档（protocols.py:103），delete 只存在于 claim / artifact / edge / member 仓储；nodes.save 走 OCC + 双时态历史快照（memory.py:52-88），可做节点内容新版本但当前 decide_review 完全未调用；stale 若沿用 too_late ×0.7 会缩短 interval 让无价值条目更频繁地进入注意力，与 zj「基本没有参考价值」语义方向相反；S1-a 已定：changed / stale 走 L3 终局动作、不走 AIMD 乘因子，changed 更新内容且 interval 重置为 L1 基线，stale 走 archive 退出调度回路；S1-b 已定：enrich / refresh 覆盖 = 节点双时态新版本（nodes.save），不是蒸馏产出 claim；S1-c 已定：清除只映射 archive 软归档，审计 reason 与 D2 区分；S1-c2 已定：内容载荷新增必填参数，只由 zj 逐条给，缺失即拒收；S1-d 已定：历史 3 条 changed 保留旧语义产物与口径切换点，不回填、不重标记、不撤销 interval 调整；S2 已定：stale 覆盖分支与清除分支并列纳入本批次，S1-a 中 stale 的单条 archive 描述细化为两分支；S2 推导约束：stale 分支选择只由 Human 给、覆盖内容载荷必填且只由 Human 给、覆盖按 L1 基线同构重置、覆盖不退出调度回路而清除必须退出、四类审计 reason 互异；changed 与 stale 覆盖系统动作同构，②拆的区分必须落在审计 reason 与用例；终局动作使 L3 不空转，但 AIMD ×1.5 / ×0.7 自适应环路的人工输入仍归零，须由 Step 3 锁不变量并写 ADR
- **unknowns:** a / b / c / c2 / d 已由 Human 于 16:25 收口、stale 覆盖分支是否纳入已由 Human 于 16:33 收口，均不再是未决项；stale 分支选择的具体参数名与取值形态尚未定，由 Step 2 定；changed 与 stale 覆盖必填内容载荷的具体参数名与落库字段名尚未定，由 Step 2 定；L1 基线重置的实现落点（复用 adapt_interval 还是新路径）尚未定；覆盖分支成功后 decay 时钟的复位口径尚未定；四类审计 reason 的具体枚举值尚未定；口径切换点记录格式尚未定；注释偏差已裁决独立成片但尚未定独立提交时点

## Verification

- **step_checks:** Step 1 检查裁决记录逐项有 Human 结论、16:08 语义定案 S0、16:25 a–d 结论 S1 与 16:33 覆盖分支裁决 S2 原文均已落盘；Step 2 检查规格含每条语义的可测断言、内容轴与节奏轴分列、a / b / c / c2 / d 与 S2 逐条映射为断言，stale 两分支分列且分支选择须由 Human 给出，四类审计 reason 互异；Step 3 检查不变量清单覆盖外生锚 A、标注率闸门、覆盖不退出与清除必须退出调度回路的硬契约、以及 AIMD 自适应环路人工输入归零的架构级结论；Step 4 检查红绿两阶段输出、必填内容载荷拒收、分支选择拒自动判定、L1 基线重置与 make test 全绿；Step 5 检查证据清单与真值回读一致；Step 6 检查 ADR 与语义口径切换点记录；Step 7 检查注释一致性且提交范围仅含 doc-only 改动
- **scenario_oracle:** 固定可观察判据：python -m unittest discover -s tests 全绿（基线 574）；新增用例对 OUTCOME_VERDICT 逐档断言且与语义矩阵 v2 一致，changed 与 stale 的映射不再相等且 stale 不再复用 ×0.7 缩短；changed 与 stale 覆盖必须带内容载荷、缺失时拒收且不得自动填充或推测；stale 分支选择缺失或由非 Human 来源给出即拒收，不得默认清除；changed 与 stale 覆盖的 interval 重置为 L1 基线而非沿用旧内容的收缩结果；stale 覆盖写 nodes.save 双时态新版本且节点仍在 list_due_for_review，stale 清除走 archive 且节点退出 list_due_for_review 与 due_count；changed / stale 覆盖 / stale 清除 / D2 四类审计 reason 互不相同；zkc decide --list --json 回读 due_count 与 today_observation 保持真值；tests/test_web_review.py:120-122 的断言随定案同步更新；历史标注不回填、不重标记、不撤销 interval 调整
- **plan_acceptance:** `pending`

## Failure and rollback

- **failure_exits:** 任一决定项无 Human 结论即停；stale 分支选择非 Human 本人给出、缺失被默认清除或被自动判定即停；内容载荷来源非 zj 本人或缺失被自动填充即停；changed 或 stale 覆盖仍走 AIMD 乘因子、或 L1 基线重置被静默改成乘因子即停；覆盖分支走 archive 或清除分支写节点新版本即停；覆盖未重置 L1 基线即停；发现任何物理删除节点的实现即停；四类审计 reason 混同、或清除后仍出现在 due 队列、或覆盖后节点从 due 队列消失即停；红阶段无法构造失败断言即停；全量测试未绿即停；真值回读与埋点不一致即停；审查退回即停；注释切片混入非 doc-only 改动即停
- **safe_stop:** 停在 Human 审批前，本 Plan 阶段不产生任何源码改动
- **rollback:** 本 Plan 阶段无源码改动，回退即丢弃 Plan 与快照两份产物；执行链的回退由消费链按分支恢复，不改写已推历史
- **undeclared_side_effect_response:** stop, preserve evidence, and escalate for Human review.

## Handoff

- **consuming_execution_chain:** ZKC 本项目内的 TDD 执行链（zj-tdd 与 zj-code-review），由 Human 审批后在本仓库启动；不新建第二条运行时
- **handoff_preconditions:** Human approval, complete provenance, and passing verification checks.
- **authority_statement:** Composer 仅提议与记录，无执行权；审批后的动作由消费链承担

## 附录 A · Composer 输出收敛与证据

| 原产物（workspace 内） | 去向 |
|---|---|
| `skills-outputs/zj-composer/2026-11-14-zkc-verdict-semantics.md` | 全文收敛入本文件（§Identity 至 §Handoff，字段逐字保留）；原件已删除 |
| `skills-outputs/zj-composer/catalog-snapshots/catalog-v1-b397a22b….json` | 关键元数据收敛入本附录；原件已删除 |

- **快照**：schema `zj-composer/catalog-snapshot/v1`；snapshot_id 与 `source.content_digest` 同为 `b397a22bfb436db13ae2787e202126a0e13940edf1b1e5565a022d45eec9d884`；generated_at `2026-11-14T06:26:28Z`；skills_root `/Users/bilibili/.workbuddy/skills`；layout `installed-flat`；69 个文件 / 69 个能力包 / 0 元数据告警。
- **模板 v1 绑定**：`plan-template.md` 的 sha256 与 `template-versions.json` registry pin 同为 `b099ee5de513477da3f1217e6c862c00c17b0eff52c8987510f5e058f396def3`。
- **selected 6 能力的 SKILL.md sha256**：

| 能力 | 路径 | sha256 |
|---|---|---|
| zj-grilling | `zj-grilling/SKILL.md` | `337182c422281d1eeed98df953e406806a5c737f51a8b60b377fd6e4e48ebfb2` |
| zj-to-spec | `zj-to-spec/SKILL.md` | `0864090db46256deeae09e87f13b4f6e2e55bffb3215bf107fc7a1464b7f4aee` |
| zj-tech-design-review | `zj-tech-design-review/SKILL.md` | `bf3e3a69b35354cbd90e065bc55b4ee9c080b9f8f919f37e5e0c4515432259d3` |
| zj-tdd | `zj-tdd/SKILL.md` | `e9b7e9d9d9f9251312fed1217f92c7733c2886bf3268317e2fd8829a8c47ab65` |
| zj-code-review | `zj-code-review/SKILL.md` | `1d2736795f01220327d181e44f122d89c4e8af08c7460a490d730e00d40fb203` |
| zj-doc-health | `zj-doc-health/SKILL.md` | `b7cd82afc305d60dfa0b18e67ba991be31bef3d50d1edffe50c3a11ae00e1647` |

- **校验记录**：批准前 `status=planned` 时 `validate_plan.py` 多次复验均 `valid=true, 0 error, 0 warning, 7 steps`；批准状态改动后复验两次（默认快照 / 项目内副本）仍为 `valid=true, 0 error, 0 warning, 7 steps`，handoff 唯一理由 `plan_acceptance_not_passed`。
- **不可复跑说明**：原始 catalog snapshot JSON 的完整 manifest 未随本文件保留，仅内嵌上述可核对的 id / digest / 统计 / selected sha。`validate_plan.py` 在本仓库内因此**不再可复跑**；上述校验结果是本次归档所依据的历史证据记录，不是当前可重放的门禁。
- **全局副本**：`~/.workbuddy/skills/skills-outputs/zj-composer/catalog-snapshots/` 下由脚本自动生成的同名快照原件未删除，属用户级 skill 安装目录的注册表状态，不是本仓库交付物。

## 附录 B · 过程态边界与门禁

- `scripts/zkc_authority_check.py` 把 `PROCESS_DIR_PARTS = ("docs", "plans")` 认定为过程产物目录：该目录下文件计入 `process_targets`，遍历 durable 候选时整类剪枝；`docs/roadmap/` **不是** process target，2026-11-13 治理后也已无该目录。
- 本文件位于 `docs/plans/`，因此生效的是**目录剪枝**。文件头仍保留 `zj-roadmap-authority/v1` 权威信封（`role: process-state` / `durable-citation: forbidden` / `promote-via: ADR|design|contract|runtime-evidence`）作为防御性声明：若日后被移出过程态目录，门禁仍按结构签名识别并跳过扫描。
- 门禁历史读数：收敛前 `0 process target(s)` / `scanned 256 durable source(s)` / `0 unresolved leaks`；16:46 收敛后 `1 process target(s)` / `254 durable` / `0 leaks`；**2026-11-14 17:10 编排成 roadmap 后复跑 `python scripts/zkc_authority_check.py .`：`4 process target(s)` / `scanned 254 durable source(s)` / `0 unresolved leaks`**（3 份新增产物同在 `docs/plans/`，受目录剪枝保护）。
- **权威边界**（ADR-0008 / 护栏 #9）：本文件是过程态计划，**不得作为权威源引用**；durable 代码与长期文档不得引用它作 proof / evidence，不得把其结论直接写成完成度证明。结论提炼路径固定为：语义矩阵 v2 与外生锚 A 由乘因子改终局动作、AIMD 自适应环路人工输入归零 → ADR；标注率闸门与归档退出契约 → risks；`zkc decide --list --json` 真值回读 → evidence。未完成提炼前，本文件只作决策脉络溯源。
- 已删除的 `docs/roadmap/roadmap.json` carrier 与 `ROADMAP.md` 视图**仍不恢复**；按 zj 16:53 指令，`docs/plans/` 下新增的是本 Plan 的过程态 roadmap 投影（单份 carrier + 两份 CLI 生成视图），连同本文件共 4 份，均带 `zj-roadmap-authority/v1` 信封。**不重建全局过程编排链路，也不授权执行 Step 1–7**（见 §口径变更记录）。
