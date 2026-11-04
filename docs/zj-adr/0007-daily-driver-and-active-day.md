# 每日驱动与活跃日语义（fork 1 + 2 + 3）

Status: accepted (2026-11-04, zj 拍板「fork 1 + 2 + 3」全选，经 zj-grill-with-docs 对"手动 UI vs launchd 每日驱动"的对比收敛)

## 背景与 grill 发现

对比「手动 UI」与「launchd 每日驱动」时，grill 暴露 4 个事实/问题，构成本 ADR 的决策基础：

1. **`queue_remaining` 是负载-bearing 字段（纠正此前误判）**：`estimate_budget_from` 的
   `saturated = [r for r in rows if r.queue_remaining > 0]`、`calibration_readiness` 的
   `saturated_days` 同义。无 ≥3 饱和日 → E1-③ 永远拿不到 `confidence=observed`、`can_calibrate`
   永远不 ready。`pushed` 则不被任何 E1 判据消费（纯遥测）。
2. **收口（尤其 `queue_remaining`）必须真值、不可手工乱填**：自动收口若硬编码 `0/0` 会主动毒化校准。
3. **活跃日定义自相矛盾**：roadmap 1-1 决策 2 写"活跃日需 completed≥1 **且**收口"，但仪表
   `_distinct_active_days` 只查 `completed≥1`、不看收口——且按仪表逻辑，不做收口也能"通过"E1-①
   但 E1-③ 永远不达标（无饱和日）。三条判据并非独立。
4. **E1-① 可行性漏洞**：某天 due 队列为空 → `completed=0` → 当天不算活跃日；低活跃期
   "连续 ≥7 活跃日"可能物理上不可达成。

## 决策（fork 1 + 2 + 3 全选）

- **fork 1**：保留人工复审标注（`decide`，不可自动化——那是认知判断，自动化即伪造外生锚）；
  仅用极简每日驱动自动化两件机械事：① 真值收口 ② 跑只读仪表。不碰收口的数字造假。
- **fork 2**：新增服务端真值收口端点 `POST /review/api/observe/auto`（算
  `pushed=今日创建节点数`、`queue_remaining=当前到期数`），由 `scripts/daily_e1_driver.py`
  每日触发。修复「收口须真值、不可手工乱填」的 harness gap（1-1 范围：harness 修复非业务流改动）。
- **fork 3**：
  - **3a 活跃日定义统一**：去掉"需收口"约束（收口只影响 E1-③/can_calibrate），仪表与决策一致。
  - **3b 空队列日豁免**：活跃日 = `completed≥1`；空队列日（`queue_remaining==0 且 completed==0`）
    不破不断；仅「有 due 未复审」（`completed==0 且 queue_remaining>0`）才断签。由
    `scripts/e1_calibration_progress.py` 的 `_evaluate_active_streak` 量。
  - 跨平台调度：macOS `launchd` plist + Windows `schtasks`（`.bat` 包装），驱动脚本本身跨平台。

## Considered Options

- **仅 fork 1（纯手动 + 极简仪表 cron）**：零新代码、零毒化风险；但收口仍需你每天手动填真值，
  漏填即丢饱和日、E1-③/can_calibrate 卡住。拒绝（收口真值源缺失是真实 harness gap，不修会卡 E1）。
- **fork 2 但硬编码 0/0**：实现简单，但主动毒化校准（见发现 1）。明确拒绝。
- **fork 2 真值端点 + fork 1 仪表 + fork 3 语义修正（采纳）**：收口真值自动落库、活跃日语义自洽、
  空队列不惩罚；唯一不可自动化的人工步（decide）保持人工。代价：新增 1 个 HTTP 端点 + 1 个驱动脚本
  + 调度配置，需维护 daemon（服务宕机要重试/告警）。
- **A 无状态预算（见 ADR-0006）与 fork 2 端点正交**：端点只负责写真值 `queue_remaining`，
  不影响预算"无状态重算"的语义。

## Consequences

- 新增 `NodeRepository.count_nodes_created_since(since)`（pg + memory 双实现，只读）。
- `src/zkc/web/review.py`：`record_daily_observation_auto` 纯函数 + `POST /review/api/observe/auto` 路由。
- `scripts/daily_e1_driver.py`：真值收口（带重试）+ 跑 E1 仪表 + JSONL 日志；退出码 0/2/3。
- `scripts/launchd/com.zkc.daily-e1.plist` + `scripts/daily_e1_driver.bat`：跨平台调度样本。
- `scripts/e1_calibration_progress.py`：`_evaluate_active_streak` 取代 `_distinct_active_days` /
  `_longest_consecutive_streak`，实现空队列豁免语义。
- roadmap 1-1：决策 2 标记 superseded，新增正确活跃日定义 + fork 1+2+3 决策；`glossary.md` 活跃日与
  预算条同步。

## 风险点解决（2026-11-04 后续，经 zj-tdd 收口）

采纳 fork 1+2+3 后，实操暴露两个风险点，均以 TDD（红→绿）闭环解决，测试见
`tests/test_memory_created_at.py`、`tests/test_daily_e1_driver.py`。

### 风险 B：`created_at` 内存后端缺失
- **问题**：PG 的 `node.created_at` 由 INSERT 列默认 `now()` 生成；内存实现 `MemoryNodeRepository.save`
  不补 `created_at`，导致 `count_nodes_created_since`（= 真值收口 `pushed` 的源）对内存后端恒返 0，
  与 PG 行为不一致——内存路径下 `pushed` 失真。原 ADR「残留风险」即指此。
- **修复**：`memory.py` 插入分支补 `node.created_at = node.created_at or datetime.now(timezone.utc)`
  （仅 INSERT 生效，UPDATE 不重写，与 PG 列默认语义对齐）。新增 `test_memory_created_at.py` 三断言：
  缺省补齐 + 更新不重置 + 早于此前的节点不计入。
- **状态**：已解决（TDD 红→绿通过）。

### 风险 A1：驱动依赖 HTTP 服务常驻
- **问题**：原 `daily_e1_driver.py` 收口走 `POST /review/api/observe/auto`，要求 review 服务常驻，
  否则收口失败（exit 2），且 plist/.bat 的 python/路径是占位符、装前须手改（Risk A2）。
- **修复（A1）**：真值收口本质是 `record_daily_observation_auto(store)` 纯函数，故驱动新增
  **direct 模式（默认）**——直接对存储层跑，复用同一 `store` 供收口与仪表，review 服务宕机不再阻塞每日收口。
  `load_config` / `run(cfg, store)` 抽出可注入配置；`build_report` 增 `storage=None` 可注入参数以共享 store
  （内存后端两次 `get_storage("memory")` 会得不同实例，须复用同一 store）。
  `--http` 仍保留（需服务常驻的边界场景）。`test_daily_e1_driver.py` 断言：不启任何 HTTP 服务、
  内存 store 含 1 今日创建节点 + 1 到期节点时，`observe_ok=True` 且 `pushed/queue_remaining` 为真值、
  meter 报告含 criteria。
- **修复（A2）**：新增 `scripts/install_daily_driver.sh`（macOS）自动解析真实 python（venv 优先 →
  `python3`）与 `PROJECT_ROOT`，把 `scripts/launchd/com.zkc.daily-e1.plist` 模板的 `__PYTHON__` /
  `__PROJECT_ROOT__` 占位符渲染为真实路径并安装到 `~/Library/LaunchAgents/`；支持 `--dry-run` 预览。
  plist 模板化、`.bat` 改为探测 venv python。消除「装前须手改占位符」摩擦。
- **状态**：已解决（direct 模式 CLI 冒烟通过 exit 0；dry-run 渲染无占位符残留）。

> 注：direct 模式仅去除「收口对 HTTP 服务的依赖」；复审标注（`decide`）仍须人工，不在自动化范围。
