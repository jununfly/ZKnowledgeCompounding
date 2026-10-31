# 架构 v1.2 逐条复核清单（三角对账 · 2026-10-31）

> 目的：把架构文档顶部那句笼统的「待 zj 复核」，拆成**可逐条签字**的清单，替代「zj 通读 700 行」。
> 对账三角：**A** = `docs/architecture/ZKC-architecture-v1.2.md`（404 行）· **B** = `spikes/spike-01…13b/` 14 份 README + 关键 test 文件计数 · **C** = `docs/prds/ZKnowledgeCompounding-PRD.md`（v0.2，208 行）。
> 用法：**zj 只需批 A 档（12 项）+ B 档（3 项）**；C 档（62 项）默认整批认可。批完后回填架构文档并关闭计划 §5 R9。
> 已由 zj 于 2026-10-31 拍板、**不在本清单内**的四项：交付形态（本地 web）／上线判定（单人 dogfood + ≥7 活跃日）／阈值治理（`zkc/tuning.py` + 来源标签）／已捕获单程票。

---

## A 档 · 需修订（12 项，每条已给可直接替换的新措辞）

| # | 位置 | 原文摘录 | 冲突对象 | 建议新措辞 |
|---|---|---|---|---|
| A1 | `ZKC-architecture-v1.2.md:374` | 「切片 B 统计赋值 16」（44 = 22+16） | 架构:24 / 架构:396 / `spike-09/test_spike_interval.py`(22) + `test_budget_estimator.py`(22) | `（**44 tests passed**：切片 A 三层规则 22 + 切片 B budget_per_day 统计赋值与 L3 闸门 22）`；同行的重复「切片 A切片 A：」改为「切片 A：」 |
| A2 | `PRD:196` | 「spike-09（22 tests passed）」 | 架构:24（44）/ `spike-09:3` | `④ …见 spikes/spike-09-review-interval/README.md（**44 tests passed**：切片 A 22 + 切片 B 22）` |
| A3 | `架构:339` | 「combine 复述率 0.56–0.72 → 0.155–0.171」 | `spike-10:10,45`（3 次采样：1.5B 中位 0.649/区间 0.553–0.689、overlap 0.656；4B 中位 0.10/0.075–0.103、overlap 0.057）；架构:243 自写 0.10 | `1.5B 的 combine 复述率 0.553–0.689（中位 0.649）、拼接复述 overlap 0.656；切到 Qwen3.5-4B 后降到 0.075–0.103（中位 0.10）/ 0.057（1.5B、4B 各 3 次采样，区间不重叠）。9B 无多次采样数据，不得与 4B 并列。`（PRD:174 同句同步改） |
| A4 | `架构:339` `架构:374` | 「所有臂跨源 claim 仅 0–1 条」 | `spike-10:45`（4B `n_cross` 中位 2、区间 1–2）；架构:25 自写「4B 仅 2/3 通过」 | `跨源 claim 绝对数：1.5B 0（0–1）、4B 中位 2（1–2）——4B 仍有 1/3 概率只产 1 条而踩 ≥2 门槛，故判不达标，非「各臂恒 0–1」`（架构:374 同改；PRD:174,196 同步） |
| A5 | `架构:242` | 「Ollama 0.40+（Apple silicon MLX）」 | `spike-02:127`、`spike-03:30`（实测 **Ollama 0.33.3** 全部通过） | `**Ollama（本机实测 0.33.3 全通过；Apple silicon 走 MLX）**` |
| A6 | `架构:121` | `embedding vector(1024)` | `spike-02:100`（nomic **768d**）、:101（qwen3 **4096d**）；`spike-06:48` k-NN 依赖该列 | `embedding vector(1024)  -- 维度为占位：需与最终选定编码器对齐（spike 02 实测 nomic 768d / qwen3-embedding 4096d，均 ≠1024；1024 仅由 spike-01 验证 DDL 可执行性）` |
| A7 | `架构:3` | 「Spike 12/13/13b …见 §9 项 6」 | 架构:374（§9 项 6 = DecisionRouter 7~14B 精度实测，与幻觉判定无关；§9 无 12/13/13b 条目） | `…见 §8「已定（spike 12/13/13b）」与 §10 项 1–5；§9 待补条目 ⑨ 幻觉判定闸门（spike-12/13/13b）` |
| A8 | `架构:229` | 「spike 06 已定，回填 §9 项 6」 | 架构:374（spike-06 = §9 子项 **②**；项 6 为 DecisionRouter） | `**context 成员关系（spike 06 已定，回填 §9 项 ②）**` |
| A9 | `架构:365⑤` | 「…已定，待 Spike 13b 实现」 | `spike-13b:3,7`（13b 实际是 **judge 执行模型 probe**，不含实现） | `⑤ Spike 13 接入设计（路由硬闸 + 注意力预算封顶 + claim 表增量 + LangGraph HITL + 人判自举校准语料）已定，**实现待另开 spike（Spike 13b 已改为 judge 执行模型 probe，不承担实现）**` |
| A10 | `架构:125–131` | `meta_claim` 表 5 列（无 faithfulness） | `spike-13:136–141`（claim 表增量 6 字段） | 在 §5 `meta_claim` 后追加：`-- D9（spike 13）：忠实度闸门状态（judge 不可用时全走 human_only）
ALTER TABLE meta_claim ADD COLUMN faithfulness_status text, ADD COLUMN judge_raw jsonb, ADD COLUMN judge_model text, ADD COLUMN faithfulness_route text, ADD COLUMN human_verdict text, ADD COLUMN human_verdict_at timestamptz;` |
| A11 | `PRD:85` | 「Context: scope(self-loop\|higher-dim), member_nodes[]」 | `架构:154–163` / `spike-06:38`（已改 `context_member` junction） | `- `Context`：scope(`self_loop` \| `higher_dim`)，成员关系走 **`context_member` junction 表**（每行带 `produced_by`+`weight`，架构 §5 D2；`member_nodes[]` 已弃用）`（PRD:113–121 mermaid 同步注明） |
| A12 | `PRD:3`、`PRD:194` | 「技术调研 + Spike 01–10 / Spike 01–05」 | 架构:3,26,365（已回填 spike-11/12/13/13b） | PRD:3 → `技术调研已完成（4 份 sealed 报告 + Spike 01–13b 全 passed）`；PRD §9 新增：`⑦ 跨源断言强制算子（已完成，spike-11，4B×3 稳定 3/3）；⑧ 幻觉判定闸门（spike-12/13/13b：机制可行 14 tests，本机 4B/9B 不可用，MVP 定案 HITL + 字面 rubric 预过滤）` |

### A 档的三条共性观察（不是新条目，供批阅时参考）
1. **数字漂移是主要失效模式**：A1/A2/A3/A4/A5 全是「架构里的数字没跟上 spike 最新采样」。根因是架构按「首次回填时的数字」写，spike 后补多次采样后没有回灌机制。→ 建议加一条维护铁律：**架构里出现的任何数字必须带 spike README 行号锚点，spike 更新数字时同步回灌**。
2. **A6（vector 维度 1024）是唯一可能反噬实现的条目**：spike 01 只验证了 DDL 可执行性，真实编码器是 768/4096 维。若不修，P1 迁移落地后要改维度 → **改维度 = 重建索引**，属上线后才发现的成本。建议**优先于其他 A 档项处理**。
3. **A10 是 schema 缺口而非措辞问题**：spike 13 定义了 6 个 faithfulness 字段，架构 §5 只回填到 D8。MVP 忠实度闸门走 HITL，这些字段是必须的（`human_verdict` 尤其）。→ 应作为 **D9** 进 P1 迁移清单。

---

## B 档 · 转 risk（3 项，文档层解决不了，需运行时/实测数据）

| # | 位置 | 问题 | 为什么文档改不了 |
|---|---|---|---|
| B1 | `架构:243`（9B 不可迭代） | `qwen3.5:9b` **GGUF 6.55GB + `num_ctx 8192` 的常驻**未实测（`spike-10:101,63`） | 只能上机实测；若常驻显著低于 mlx 8.9GB，「9B 在 16GB 不可用于迭代」的结论可能松动，纸面无法裁定 |
| B2 | `架构:374⑧`（补全回路 0/3 触发） | 补全回路在主生成不达标时 **+1× LLM 调用**的成本未计入 MVP 延迟预算（`spike-11:92`） | 需真实延迟分布；且「0/3 触发」只是 4B 样本，换语料后触发率未知 |
| B3 | `架构:156–166`（`context_member`） | junction 表在**高频重算下的写放大未压测**；是否改成「查询时计算」的动态视图未决（`spike-06:65`） | 需压测数据（条目规模 × 重算频率），文档只能记录而不能定 |

---

## C 档 · 已验证 · 建议整批认可（62 项）

### §5 数据模型（11 项）
- 双轨 ENUM + 双时态列 + decay 列 + `transform/produced_by` 级联撤销 ← `spike-01:29,60` / `spike-04:6,45`
- 静态轨 decay 恒 0；无 `evidence_refs` 的 claim 被 schema 拒 ← `spike-01:62,63`
- D1 `context.scope` 收紧为 ENUM `context_scope` ← `spike-06:37`
- D2 `member_nodes uuid[]` 弃用、改 `context_member`（`produced_by`+`weight`）← `spike-06:38,18`（**PRD:85 未同步，见 A11**）
- D3 新增 `citation` 表构成双向溯源（复用率可算）← `spike-07:26,50`
- D4 `node.archived_at`（衰减可控的「已归档」分支）← `spike-07:41,51`
- D5 仅新增 `review_queue`（规则无需新信号列，良性收敛）← `spike-08:27,33`
- D6 `baseline_interval` + `interval_source`（人工豁免）← `spike-09:80`
- D7 `interval_adjustment` append-only + `produced_by` 整体回滚 ← `spike-09:81`
- D8 `attention_observation.labeled_completed` ← `spike-09:152`
- 三态分流（已捕获→ARCHIVE／有连接未捕获→DISTILL／孤儿或预算高压→ABSTAIN）← `spike-08:14–17,39`

### §6 选型表（9 项）
- 存储 Postgres+pgvector（PG16 实测）← `spike-01:58–60`
- 向量 pgvector 余弦 k-NN 可行（T4.1）← `spike-06:48,59`
- 双轨分流 DecisionRouter 主方案（编码器无关、F1=0、F2 0/3、覆盖 100%）← `spike-03:46,63–66`
- 3-way 仅 qwen3 级（≥4096d）安全；nomic 768d 有 1 误提交 + 2 互混 ← `spike-03:52,67`
- 结构化抽取 Instructor（校验重试）← `spike-04:17` / `spike-05:38`
- 编排 LangGraph + PostgresSaver 同库同 schema、跨连接 resume ← `spike-04:36,46`
- 蒸馏/结合模型 `qwen3.5:4b-mlx` 默认、9B 可选上限（16GB swap 实测）← `spike-10:13,71–74`
- decay 线性、阶梯否决（窗口 0）、指数过慢（27.8d）← `spike-01:46–48,52–56`
- 注意力需求 `n/(0.6×interval)`、预算不足 rot=100% ← `spike-01:54,55`

### §6.1–§6.4（7 项）
- §6.1 蒸馏契约 = 元认知 claim（非摘要）+ interrupt/resume 人审 ← `spike-04:16,33–36`
- §6.2 RCS 漏斗 + 双层合并 + 引用强制（幻觉引用剔除／零引用删除／全失效抛错）← `spike-05:24–26`
- §6.2 跨源硬约束（≥2 跨源断言）+ bounded 单次补全回路；schema 未动 ← `spike-11:37–46,68–72`
- §6.3 decay 线性 `min(1, elapsed/review_interval)`、阈值 0.6/0.9、窗口 6.3 天 ← `spike-01:44–46`
- §6.4 C1 append-only（闭行 + 插行，历史行逐字段不变）← `spike-04:24,25`
- §6.4 C2 `produced_by` CASCADE 撤销、人工产物（`produced_by` NULL）存活 ← `spike-04:28` / `spike-05:26`
- §6.4 Cordis 仅作模式源、不作依赖 ← 架构侧论证（无 spike 证据，按架构自述认可）

### §6.5 / §6.5.1（14 项）
- L1 五档基线（NULL／时间锚 clamp(1,180)／已捕获 28d／self_loop 3d／edge 或 higher_dim 14d／孤儿 7d，多锚取最早）← `spike-09:31–38`
- L2 优先级升序延后、同优先级短 interval 先延后、每步 ×2、`human` 豁免、`MAX=180d` ← `spike-09:43–44`
- L2 `infeasible=True` + `max_dynamic_items = budget×0.6×180`（不做无限延后）← `spike-09:45–46`
- L3 AIMD ×1.5 / ×0.7、钳制 `[1d,180d]` ← `spike-09:52–56`
- L3 标注率闸门 ≥70%、滚动 7 天、<10 次不判定、低于则停机 ← `spike-09:157–160`
- 发现① decay-only 反馈永久 no-op（复审瞬间 decay 恒 0.6），需显式标注，2 步收敛 15.75d ← `spike-09:62–69`
- 发现② 收敛目标 `H/0.6 ≈ 1.67H`（SURFACE=0.6 定义所致，非 bug）← `spike-09:74`
- §6.5.1 删失感知估计（饱和日取 `completed` p25；无饱和日 `lower_bound`；无观测 `none`）← `spike-09:121`
- §6.5.1 单调护栏（非饱和日只抬不压）+ 阻尼 EMA α=0.3、±30% + 校准期 ×1.5 oversubscribe ← `spike-09:122–124`
- §6.5.1 仿真双向收敛（10→3.001 / 1→2.999）；护栏 ON 保持 10 vs OFF 降 6 ← `spike-09:128–138`
- §6.5.1 预判修正：是「错误稳定均衡／固化」而非「发散到 0」；条目太少时容量不可观测 ← `spike-09:142,144`
- §6.5.1 外生锚硬前提（每日队列 UI 未交付则 estimate 恒 `none`、L3 无样本）← `spike-09:170`

### §7 延后项（2 项）
- 图数据库延后（递归 CTE 足够，保持 Kuzu/TerminusDB seam）← 架构自述（spike-06 用 pgvector，无图库实证）
- Cordis/dsh 拒绝为依赖（双栈分裂、HITL 仅轨迹级、丢 schema 级校验）← 架构自述

### §8 风险与未决（15 项）
- spike 10 五维 rubric（复述率／overlap／跨源率／引用命中／结构完整）← `spike-10:9,84`
- 采样噪声足以翻转单次结论（0.678 vs 0.105；跨源 0.0 vs 1.0）← `spike-10:36,45`
- 比率可被「少发 claim」刷高 → 加绝对数门槛 ≥2 ← `spike-10:38,82`
- 幻觉/忠实度字面不可测（抄的 1.0/1.0 vs 好抽象 0.18/0.12）→ 需 LLM judge ← `spike-10:80`
- LCS 抓不住拼接复述 → 并列 `overlap` 门槛 ← `spike-10:81`
- 修重试非瓶颈（1.5B + 新重试仍 0/3）← `spike-10:12,51`
- 16GB 硬约束（9B 常驻 10–12GB、空闲 9–10%、swap 17–21GB、单次蒸馏 4.7min）← `spike-10:71–74`
- spike 02 相似度不可分（模糊 0.164 vs 明确 0.292；真编码器仍 OVERLAP）← `spike-02:56,100–101`
- 长模糊 3/3 单向误判为 dynamic（三编码器一致）← `spike-02:71,110`
- 「0% 错判不可外推」获佐证（nomic routed 准确率降 80%）；原「词法限定」撤销 ← `spike-02:111–113`
- 分解式 LLM-as-judge 机制可行（**14 tests passed**，已核 `test_judge.py` 恰 14 个 test 方法；oracle 满分、坏 judge 暴露漏检）← `spike-12:80–85`
- 4B 本机不可用（~110–130s/条 + 不产 JSON，instructor 流式卡死），但判定能力对 ← `spike-12:91–98`
- 9B 本机否决（364.5s/条、吐 `Label/Evidence/Overall`、g6 矛盾识别正确）← `spike-13b:47–54,60–64`
- MVP 忠实度闸门 = HITL + 字面 rubric 预过滤（降级链第 2 级）；`judge.py` 零改动可启用 ← `spike-13:41,56,66–67`
- 路由硬闸（空分解／矛盾 100% 强制人审）+ `F_cap=0.2` 预算封顶 + 人判自举扩 golden ← `spike-13:96–99,117,166`

### §9 / §10（4 项）
- ① spike-01 18 tests；② spike-02 9；③ spike-03 9（1 expectedFailure）；④ spike-04 9；⑤ spike-05 9 ← 各 README:36/35/35/8/8
- spike-06 10 tests；spike-07 9；spike-08 9；spike-09 44（代码 22+22 复核）；spike-10 8；spike-11 9 ← 各 README:3
- ⑦ 每日复审队列 UI 为两闭环唯一外生锚载体（MVP 必选）← `spike-09:170` / PRD:67,197
- §10 ledger 7 行对账（§2.0/§2.3/§4/§5/§6-7/§8/§9）与 PRD v0.2 逐项一致 ← PRD:30–34,56,78,88,152,168–172,196

---

## D. 审计覆盖说明

- **已读全文**：架构 v1.2（404 行，含被截断的 374 行分段补全）、PRD v0.2（208 行）、`spikes/spike-01…13b` 全部 14 份 README.md。
- **额外读（为核数）**：`spike-12/test_judge.py`（计得 14 个 `def test_`，坐实「14 tests passed」）、`spike-09/test_spike_interval.py`(22) 与 `test_budget_estimator.py`(22)，坐实 44 = 22+22 → 故 A1 的「16」判为错值、A2 的「22」判为遗漏。
- **跳过**：各 spike 的 `.py` 实现与 `report_*.json` / `multisample*.json`（仅 grep 校验数值）；`docs/research/*` 5 份 sealed 报告（不在三角内）；`docs/plans/ZKC-implementation-plan.md`（未纳入）。
- **读不到的**：无。
- **遗留提示（非本档结论）**：`spike-12:3` 状态仍写「进行中」，与架构按「已完成 / 14 tests」引用口径不符，属 spike 侧文档待更新，建议一并回填。
