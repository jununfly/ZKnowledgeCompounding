# ADR-0009 · L3 AIMD 下界由 1d 降为 0.25d（不做日内调度）

Status: accepted (2026-11-06, zj 拍板：新下界 `0.25d`；每日驱动保持每天一次)

## 背景与发现

架构 §6.5 / spike 09 把 `review_interval` 定为三层规则（L1 个体基线 / L2 预算归一化 /
L3 复审反馈 AIMD），L3 钳制区间写作 `[1d,180d]`。真实运行暴露一个**静默失效**：

- `src/zkc/tuning.py` 的 `MIN_INTERVAL_DAYS=1.0`；`src/zkc/scheduling.py` 的
  `clamp_days` 把 `1.0 × AIMD_DOWN(0.7) = 0.7` 夹回 1.0，`adapt_interval_math`
  因此 `applied=False`；`adapt_interval` 在 `applied=False` 时不写
  `interval_adjustment`（锚 A 噪声治理的既有设计，避免 7→7 无信息量行）。
- 后果：`review_interval=1d` 的节点无论人给什么显式 verdict，节奏都不变、也不留审计。
  L3 的「复审标注作外生锚 → 修正节奏」在这批节点上是装饰，不是闭环。
- 2026-11-06 生产 PG 只读复核（仅 SELECT，未刷新 decay、未写任何数据）：
  动态轨 1d 节点共 27 条（24 条已按既有清理归档、3 条仍活跃）；
  `interval_adjustment` 61 行全部为 `kind='baseline'`，`feedback` 行 **0** ——
  生产库中 L3 从未产生过一次有效 interval 变更。
- 下界来源核查：1.0 是 spike 09 仿真定下的 `SIMULATION` 阈值，**不是硬不变量**；
  架构 §6.5 与 spike 09 README 的 `[1d,180d]` 是研究时点结论，仓库内并无任何 ADR
  声明 1d 不可变。真正的反向约束来自 ADR-0007：每日驱动每天只做一次真值收口 +
  人工 `decide`，故 1d 实际是调度的最小粒度。

## 决策

1. `MIN_INTERVAL_DAYS: 1.0 → 0.25`（`src/zkc/tuning.py`），`source` 保持
   `SIMULATION`，note 写明依据与「非 CALIBRATED」。`clamp_days` 实现与三层规则不变。
   取 0.25d 的依据：`AIMD_DOWN=0.7` 时 1.0d 可走四步
   `1.0 → 0.7 → 0.49 → 0.343 → 0.25`，让触底节点的反馈重新携带信息。
2. **每日驱动不改**：ADR-0007 的 launchd / schtasks 仍每天一次，不做日内多次扫描。
   `<1d` 仅是 `review_interval` 的数值语义，**不是日内复审能力**；
   `list_due_for_review` 与收口仍按天发生，0.7d 的节点在下一次日扫描时到期。
3. L1 时间锚解析器不加小时级规则：当前没有文本锚能产生 `<1d` 基线，
   `<1d` 只能由 L3 AIMD 收缩产生。
4. 架构 §6.5 与 spike 09 README 标注为「2026-11-06 后续修订」；
   `spikes/spike-09-review-interval/` 的代码常量与既有 44 tests 口径保持原样，
   不静默覆盖研究时点结论。生产口径以本 ADR 与架构 §6.5 为准。

## Considered Options

- **保持 1d 并如实承认 L3 对触底节点失效**（Agent 建议，未采纳）：改动最小、风险最低，
  但保留 no-op；zj 选择让反馈真正能改写节奏。
- **允许 <1d 且同步改成日内多次扫描**（未采纳）：需改调度器、每日驱动、埋点口径与
  活跃日语义，范围过大；当前也没有真实外生锚证明需要日内复审。
- **触底节点改走其它反馈路径**（未采纳）：如触底后转归档 / 蒸馏 / 一次性 HITL 裁决，
  语义最干净，但要改架构 §6.5 的 L3 定义并新增契约与测试，超出本次切片。

## Consequences · 必须同时记住的边界

1. **触底已被真正消除（2026-11-06 续 修订）**：收敛到 0.25d 后仍 `too_late` 时，
   `adapt_interval_math` 标记 `floor_hit=True`，`adapt_interval` 不再静默 no-op，
   而是复用 D2 归档范式把节点移出调度回路（`store.nodes.archive`）+ 写
   `interval_adjustment` 审计（`kind='floor_hit_archive'`）。语义：到下限仍跟不上腐化，
   应退出回路而非无限 no-op。human 节点（`interval_source='human'`）在 floor 判定前已
   提前返回，不受影响。`test_sub_day_lower_bound_flags_floor_hit` 与
   `test_1d_feedback_converges_then_floor_hit_archives` 锁住这一行为。
   原「触底没消失，只是下移」表述作废（见下方修订记录）。
2. **L2 与 L3 方向对冲**：L3 缩短 `I` 使需求 `Σ1/(0.6×Iᵢ)` 放大，L2 预算归一化会
   反向拉长 `I`；两者在 calibrating / 观测不足时可能互相抵消并污染 `budget_per_day`
   估计。`test_l2_l3_directions_oppose_within_sub_day_band` 锁住方向。
3. **0.25d 是 SIMULATION 占位，不是 CALIBRATED**：真实阈值须走 ≥14d 埋点 + ≥3 饱和日
   校准门禁（`tuning.CALIB_MIN_DAYS` / `CALIB_MIN_SATURATED_DAYS`）与真实可辨识的
   四分量价值排序外生锚。禁止把本次改值写成校准完成，也不得写回 REGISTRY 的
   CALIBRATED 口径。
4. **生产数据已按 zj 裁决变更（2026-11-06 续）**：原「全程只读」仅限本 ADR 初次落地；
   后续 zj 裁决归档 3 条残留 1d 导入语料（活跃 40→37，仅写 `archived_at`，
   `attention_observation` 的 labeled_sum=6 / completed_sum=6 不变），并将 11-04/11-05
   共 6 条标注定为有效外生锚（override 1-7 corpus.py / ADR-0006 默认伪标注假设，
   仅本批次 6 条，不静默改写既有默认口径）。详见 roadmap 1-13 / 1-1 / 1-17 决策。
5. **E1 三判据与 P6.4 观察期口径不变**：本决策只改调度阈值语义，不改验收口径。

## 修订记录（2026-11-06 续，zj 裁决）

初次落地时 Consequence 1 写「触底没有消失，只是下移」、Consequence 4 写「全程只读」。
同日 zj 就 1-13 的待裁决项拍板，推翻上述两条默认口径，记录如下：

- **触底真正消除（选项 c）**：zj 裁决不再把 floor no-op 当永久限制。实施 =
  `adapt_interval_math` 增加 `floor_hit` 标志（verdict=too_late 且 new==old 于
  `MIN_INTERVAL_DAYS`）；`adapt_interval` 在 `floor_hit` 时走 **归档终局**（复用 D2
  归档范式 `store.nodes.archive` + 写 `interval_adjustment` 审计 `kind='floor_hit_archive'`），
  返回 `resolution='archived'`，不再静默 no-op。蒸馏 / HITL 为可选替代终局，当前默认归档。
- **3 条残留 1d 导入语料已归档**：按 id 精确归档（不走 `zkc corpus archive`，因其
  corpus 选择器不匹配这 3 条——它们 decay=0.0067 / last_reviewed=11-05，已被 11-06
  verdict 改动）。活跃 40→37，`attention_observation` 不变。
- **6 条标注定为有效外生锚**：11-04 / 11-05 共 6 条标注，zj 显式 override 1-7
  corpus.py / ADR-0006 的「导入语料 verdict 属伪标注」默认假设（仅本批次 6 条），
  E1 活跃日=2、标注率=100%、P6.4 累计=6/20 读数有效。
- **0.25d 的 CALIBRATED 归属**：扩至 1-26（与 METRIC_W_* 共享 `can_calibrate` 门禁），
  见 1-26 notes / EC。

## 验证证据

- **TDD 红 → 绿**（`tests/test_scheduling.py`，ADR-0009 初次落地新增 5 条：纯函数 3 +
  内存编排层 2；续修订再增 1 条 `test_adapt_math_floor_hit_only_on_too_late_at_floor`，
  并把 `test_sub_day_lower_bound_still_bottoms_out` 改写为
  `test_sub_day_lower_bound_flags_floor_hit`、`test_1d_feedback_converges_to_lower_bound_then_noops`
  改写为 `test_1d_feedback_converges_then_floor_hit_archives`）：
  红态（下界 1.0）3 红 2 绿 —— `MIN_INTERVAL_DAYS<1.0` 断言失败、
  `adapt_interval` 返回 `applied=False`、`kind='feedback'` 审计行缺失；
  绿态（下界 0.25）全部通过，该文件 43 tests OK。
- **覆盖点**：`clamp_days(0.7)==0.7`、1.0d 的 `too_late` → 0.7d 且 `applied=True`、
  编排层落库 0.7d 并写一条 `feedback` 审计（old=1.0 / new=0.7）、连续收缩到 0.25d
  后**再 too_late 触发 floor_hit → 归档 + 写 floor_hit_archive 审计**、
  `floor_hit` 仅在 too_late 且已处下界时为真（on_time / human / 未到下界均不触发）、
  L2 拉长与 L3 缩短方向相反。
- **全量套件**：`python -m unittest discover -s tests` → **Ran 580 tests OK**
  （35.8s；原基线 574 + ADR-0009 新增 5 + 续修订新增 1）。
- **四项门禁**：`make mcp-gate` 6 tests OK；`make invariant` 0 violations
  （P1/P2/P3 全 OK）；`scripts/zkc_authority_check.py .` 0 unresolved leaks；
  roadmap skill 的 authority-check clean；`git diff --check` rc=0。
