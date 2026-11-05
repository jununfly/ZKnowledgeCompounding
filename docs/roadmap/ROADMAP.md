<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

<!-- zj-roadmap-authority/v1
role: process-state
durable-citation: forbidden
promote-via: ADR|design|contract|runtime-evidence
-->

> 数据文件: `roadmap.json` | 最后更新: 2026-11-05 22:04:15

[~][X+] 1. ZKC MCP 集成执行路线图
    ├── [~][X+] 1-1. E1 校准闭环跑通：复审队列≥7活跃日且标注率≥70%
    ... 该层还有 23 个兄弟，0 个 in_progress ▸
<details><summary>阻塞链：1 个节点被阻塞</summary>

- 1-18. PRD §9 下版本决策收口：护城河锚 2 抽检 + 6 项 unknown 口径 + checkbox 勾销 ← e13: 1-8. E8 护城河实证化：复利度量口径回填与蒸馏抽检 [ ], e14: 1-9. E9 对外叙事对齐：caveat+4特征口径统一 [ ]

</details>


### 当前施工：1-1. E1 校准闭环跑通：复审队列≥7活跃日且标注率≥70%

**决策：**
- Q: 1-1 范围分类（scope gate）？ → Product execution（产品执行）：ZKC 自身路线图节点，操作/观测『已交付复审队列』校准闭环；目标代码保持只读除非发现 harness 缺口。本沙箱无 PG/Docker 无法跑实时回路，真实多日埋点须在 zj 本机（localhost:55433 + make serve）进行，严禁伪造数据。
- Q: 如何定义『活跃日』（退出判据1 计数口径）？ → SUPERSEDED 2026-11-04 (fork 3b / ADR-0007)：活跃日语义已改为『completed>=1 即活跃；空队列日(queue_remaining==0 且 completed==0)豁免；有 due 未复审(completed==0 且 queue_remaining>0)才断签』，且收口(queue_remaining) 只影响 E1-③ 不影响 E1-①。详见下方同问的新决策与 ADR-0007。 (superseded)
- Q: E1 三项退出判据怎么持续测量？ → 新增只读脚本 scripts/e1_calibration_progress.py：统一读 calibration_readiness / labeling_rate_from(7d) / estimate_budget_from(多窗口 7/14/21/28d 轨迹)。不写数据、不伪造；zj 本机 PG 起后每日跑一次看进度。已内存后端自测通过。
- Q: 『budget_per_day 收敛到稳定值』怎么判（退出判据3）？ → 临时定义：estimate 在 [7,14,21,28] 天窗口轨迹的变异系数 CV<=10% 且 28d confidence=observed。budget 不持久化、每次由 attention_observation 实时估计，故用多窗口聚拢作收敛信号。带宽(+-10%)待 zj 拍板可调。
- Q: 预算收敛判据采用哪种含义（A 无状态 / B 有状态）？ → A：无状态（含义②即预算）。estimate_budget_from 每次从 attention_observation 重算，无『持久化初始值』。E1-③ 重述为『派生估计在 [7,14,21,28] 天窗口轨迹聚拢（CV≤10% 且 28d confidence=observed）』。含义③有状态路径(update_budget/fit_budget)本阶段明确不接线，保留定义+单测待用——见 ADR-0006。带宽 ±10% 一并确认。
- Q: 如何定义『活跃日』（退出判据1 计数口径）？ →  (retracted:)
- Q: 如何定义『活跃日』（退出判据1 计数口径）？ → 活跃日 = 当日真实复审发生（attention_observation.completed>=1，来自 /review 的 decide 标注）。收口(queue_remaining) 只影响 E1-③ 预算估计与 can_calibrate 门禁，不影响 E1-①（2026-11-04 fork 3b 重定，见 ADR-0007）。空队列日(queue_remaining==0 且 completed==0) 豁免——不破不断；仅『有 due 未复审』(completed==0 且 queue_remaining>0) 断签。由 scripts/e1_calibration_progress.py 的 _evaluate_active_streak 量。
- Q: 每日运行机制（fork 1+2+3）？ → zj 拍板 fork 1+2+3 全选：(1) 新增服务端真值收口端点 POST /review/api/observe/auto（算 pushed=今日创建节点数、queue_remaining=当前到期数），由 scripts/daily_e1_driver.py 每日触发，修复『收口须真值不可手工乱填』的 harness gap；(2) 每日驱动仅自动化『真值收口 + 跑只读仪表』，复审标注(decide) 保持人工（不可自动化，否则伪造外生锚）；(3) 活跃日语义改『空队列日豁免、有 due 未复审才断签』(fork 3b)；(4) 跨平台调度：macOS launchd plist + Windows schtasks(.bat)。详见 ADR-0007。1-1 仍 product execution，新增端点属 harness gap 修复（非业务流改动）。
- Q: 解绑后 1-1 的状态与证据边界？ → 1-1 保持 in_progress，继续以真实 PG 埋点观察，三条退出判据不变（连续≥7 活跃日 / 标注率≥70% / budget 多窗口 CV≤10% 且 28d observed）。E2–E5 开工不产生任何 E1 数据；严禁把 MCP 实现产物当作 E1 达成证据，也不得回填或伪造 attention_observation。1-1 只在 zj 本机每日真值收口 + 人工 decide 标注后自然收敛。 (外生锚铁律：无标注复审禁止写 interval；人环 verdict 绝不自动化)
- Q: E2–E5 完成后 1-1 的判据复核结果（2026-11-05 收口）？ → 1-1 保持 in_progress，三条退出判据不变、不因 E 链落地而勾销。真实 PG 仪表复核（2026-11-05 13:25 UTC）：① 连续活跃日 1/7（60d 内 1 天，latest_ok=true）；② 标注率 gate=open（completed=3 < min_samples 10，rate=null）；③ budget 28d=3.0 provisional、cv=0.0 但 converged=false（can_calibrate=false：需 ≥14 天埋点 / ≥3 饱和日，现有 1/1）。all_exit_criteria_met=false，与开工前一致，未被本轮 523 条测试污染（days_with_observation 仍为 1）。**E2–E5 是 MCP 工程实现，不产生也不得回填 attention_observation；其完成不构成 E1 达成证据。**拓扑变化：e1 由 blocks 改 informs 后，critical-path 从 1-1→1-2→1-3→1-4→1-5 变为 1-8→1-18，E1 不再是 E 链的调度瓶颈，但仍是产品验收上的未闭合项，只能靠 zj 本机每日真值收口 + 人工 decide 标注自然收敛。 (下一步由 zj 决定：继续每日跑每日驱动累计活跃日，或先推进 E6–E9 / D 组独立节点；均不改写本节点状态)

### 下一步可开工（ready 前 3）

- 1-10. co-work(ZAgentic #234): E 链推进走 canonical reconcile+apply 路径，向 issue 回填真实一致性证据 [ ]
- 1-11. co-work(ZAgentic #235): 将本 roadmap.json 置为只读副本进 tmp/skills-outputs/ 供回放；另补 ZBrain/ZAgentic 两份样本 [ ]
- 1-12. co-work(ZAgentic #236): E6/E7/E8 复用共享 Work 入双 outline context 时，产出 reference Placement 真实用例供标记复核 [ ]
<!-- ROADMAP_SECTION_END -->
