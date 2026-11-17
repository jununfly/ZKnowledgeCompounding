# 同日两次 daily 触发真值漂移与 c3 收敛读数护栏（2026-11-16，只读取证定位）

> 一次性取证证据。解决对象：2026-11-16 两次每日循环触发（11:05 与 23:51）之间，
> `queue_remaining 3→1` / `completed·labeled 0→1` / `due 3→1 且换条目` /
> `all_exit_criteria_met true→false`。结论：**全部由一次真实的人工复审标注写入驱动，
> 非 meter 非确定性、非伪造、非 bug**；c3 读数翻转是判据设计的正常灵敏度，不构成实质收敛证明。

## 1. 根因：11-16 当天一次人工复审标注

PG `node.last_reviewed_at` 真值（UTC，本机 UTC+8）：

| 时刻(UTC) | 时刻(北京) | node | title | 备注 |
|---|---|---|---|---|
| 2026-11-16 03:17:12 | 11:17 | `0114e739…` | 20260402-Harness工程就是控制论Odysseus深度解读 | 落在 11:05(03:05Z) 与 23:51(15:51Z) 两次触发之间 |

- 时间锚点精确落在两次 daily 触发之间，解释 `completed/labeled 0→1`：
  `attention_observation` 11-16 行当日值 `completed=1 labeled=1 queue_remaining=1`（11-17 11:03 直接查库）。
- `interval_adjustment` 11-16 **无记录**、`review_queue` 11-16 **无记录** → 与 `still_valid` 语义
  （ADR-0011/0012：`still_valid` 仅 `mark_reviewed` + completed/labeled 累加，不调 AIMD、不写 interval 审计）一致。
- 11-17 11:03 由 zj 本人在对话给出 `dd5e8fc3… → still_valid`，`last_reviewed_at=2026-11-17 03:03:43Z`，
  是**另一条独立复审**，与 11-16 那次不是同一事件。

## 2. 链式传导：一次标注如何翻动全部四项读数

1. `zkc daily` = `record_daily_observation_auto`：真值自动计算 `pushed`（当日新建节点数）与
   `queue_remaining`（当前 due 条目数，`list_due_for_review` 长度），**保留当日已累加的 completed/labeled**
   （`src/zkc/web/review.py:261-295`）。所以 completed 的 0→1 只能来自复审标注写入，不是 daily 自己造数。
2. `queue_remaining 3→1` / `due 3→1 换条目`：11-05 那批 due 的三条中
   `0114e739…` 被 11-17 复审 mark_reviewed 后退出 due；`dd5e8fc3…`（20260409-能让Agent长运行的有效Harness）
   成为新的 due。due 是**随时间+复审动态变化**的集合，不是固定清单。
3. c3 `saturated_samples` 首位 0→1：该数组 = 28d 窗口内 `queue_remaining>0` 那些天的 `completed` 值
   （`scheduling.py:306,321`），首位对应 11-16 当天。11:05 当天 completed=0 → 首位 0；
   11:17 写入标注后 completed=1 → 23:51 读数为 1。样本从 `[0,0,0,3,3,3,3]` 变 `[1,0,0,3,3,3,3]`。

## 3. c3 判据机制澄清（"矛盾"不成立）

- **cv/spread 不是 `saturated_samples` 自身的离散度**，而是 7/14/21/28 四个窗口 `estimate` 的
  `(max-min)/mean`（`src/zkc/calibration.py:87-103`）。记忆里 11:05 记 `cv=0.0` 且样本 `[0,0,0,3,3,3,3]`
  并不矛盾：那时四窗口 estimate 全为 0.1 → spread=0。
- 11-17 11:03 复算四窗口（当前数据）：7d=0.1 / 14d=0.5 / 21d=0.5 / 28d=0.5 →
  spread=0.4、cv=1.0、converged=false。11:17 的标注把当天 completed 从 0 抬到 1，
  p25 从 0（下限钳到 0.1）跳到 0.5 → 拉大窗口间离散 → `met` 由 true 回落 false。
- 结论：单次标注即可翻转 c3，判据**灵敏但脆弱**；`saturated_samples` 含 0（离群/断签日）
  使 p25 估计不稳。这**正是不应把 meter 当实质收敛证明的原因**。

## 4. 护栏（维持，不因本次取证松动）

- E1 已于 2026-11-12 并入 1-26 收口；`zkc meter` **只读仪表**，与节点状态解耦。
  不得据 `all_exit_criteria_met` 翻转改写 1-26 的 CALIBRATED 口径、不得触发 L3 参数调整。
- c3 `converged=true` 仅表示窗口估计碰巧聚拢，≠ 复利系数已校准；真实四分量结构性仍为 0
  （cd/rr/mo=0、dc=1.0 归档假象，见项目 MEMORY.md）。
- verdict 仍只能由 zj 本人逐条给；本次只做只读取证，未写任何 verdict、未改任何节点。

## 5. 取证命令与边界

- 只读 SQL：`attention_observation`（近 20 天）、`node.last_reviewed_at >= 11-15`、
  `interval_adjustment`（近 15）、`review_queue`（近 20）、`_budget_trajectory` 复算。
- 未改代码 / 阈值 / REGISTRY；未 commit/push；未 distill、未写 meta_claim；未写 verdict。
