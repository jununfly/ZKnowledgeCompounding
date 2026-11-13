---
name: zj-zkc-daily
description: ZKC 知识复利工具的每日运行 harness 适配器（WorkBuddy 版）。当用户要跑 ZKC 每日循环（真值收口 + 补向量 + 复审人环 decide + E1 进度仪表）时加载；把 zkc CLI（daily/embed/meter/decide）编排为「机械收口与补向量 + 仪表 + 对话内人环复审」流程。绝不自动标注复审结果。
disable-model-invocation: false
argument-hint: "跑 ZKC 每日循环 / 收口 / decide / meter"
source: zagentic
---

# zj-zkc-daily

ZKC（个人知识复利工具）每日运行循环的 **harness 适配器**。底层是已正式化的 `zkc` CLI
（Form B 去服务器化，composer Plan `zkc-daily-run-forms-v1`），本 skill 把它编排成
WorkBuddy 对话里可执行的每日流程。对应 E1 校准闭环。

> **纳管**：本文件是 **canonical（唯一真相源）**，位于 ZKC 仓库
> `skills/zj-zkc-daily/SKILL.md`（git 跟踪）。`~/.workbuddy/skills/zj-zkc-daily/SKILL.md`
> 只是运行副本，由 `scripts/install_harness_skill.py` 同步生成，不要手改副本。
> 详见「纳管与同步」节与 ADR-0007。

## 前置（一次性确认）
- `zkc` 命令可用：ZKC 仓库已 `pip install -e .`（`make setup`）。否则用
  `python -m zkc.cli`（需 ZKC 仓库根在 cwd 或 PYTHONPATH）。
- Postgres 可达：`make db` 起 `zkc-spike-pg`(:55433)，或设 `ZKC_PG_DSN`。
- 项目根（PROJECT_ROOT）：`python -m zkc.cli` 时需在该根目录下；WorkBuddy 沙箱内若
  不可用 docker，须本机 PG 可达（约束见 macos-sandbox-probe）。

## 硬约束（不可违背）
1. **human-in-the-loop 复审**：`decide` 的 verdict（still_valid/changed/stale/browse）
   必须是 zj 在对话里给出的，绝不可由模型自行编造或默认填值。自动标注 = 伪造外生锚 A，
   会废掉 L3 interval 反馈闭环（架构 §6.5.1 通则）。本 skill 只负责「呈现条目 + 捕获
   zj 的 verdict + 写入」，不替 zj 做判断。
2. 预算语义 = A 无状态（ADR-0006），不改；E1 三判据只喂数据不改（E1 校准闭环）。
3. `zkc daily` 只写 `attention_observation` 的 pushed/queue_remaining 真值，不碰业务表、
   不伪造复审标注。
4. **补向量不进 E1 驱动**：`zkc embed` 写 node 派生列，日常由 WorkBuddy 每日定时任务
   作为循环第 2 步执行，不改 ADR-0007 的「两件机械事」边界。本机不启用系统级调度，
   仓库也没有补向量专用的 launchd / schtasks 条目（该实现已撤销）。

## 每日流程（按序）
1. **机械收口（无交互）**：
   `zkc daily`（或 `python -m zkc.cli daily`，下同）
   真值写入 pushed=今日创建节点数、queue_remaining=当前到期数。绝不可手工乱填。
2. **补向量（无交互，best-effort）**：
   `zkc embed`
   把当日新捕获节点的 embedding 双列补齐（全轨、幂等、空正文用标题兜底）。
   Ollama 不可达导致失败时记录并继续后续步骤——它与 E1 收口/仪表是并列任务，
   不写 `attention_observation`、不碰标注埋点，失败不影响 E1 三判据。
3. **取待复审队列**：
   `zkc decide --list --json`
   把返回的 `items`（id/title/track/decay_score/review_interval_days/...）逐条呈现给 zj，
   并给出标注率闸门(gate)与预算(budget)概览。
4. **人环复审（关键）**：
   让 zj 对每条给 verdict。zj 可逐条说，也可一次性给一批（"id1 still_valid, id2 changed"）。
   对每条调用：
   `zkc decide --id <id> --verdict <still_valid|changed|stale|browse>`
   - still_valid：信息仍准（节奏恰当，L3 不缩短）
   - changed / stale：信息比预期腐化更快（L3 缩短复审节奏）
   - browse：仅浏览未标注（复位时钟、completed++ 但不标 labeled，使标注率可 <100%）
   逐条回显写入结果（verdict/applied/new_interval_days/today_observation）。
5. **进度仪表**：
   `zkc meter --json`
   读出 E1 三判据（连续≥7活跃日 / 标注率≥70% / budget 收敛），汇总给 zj：
   >>> E1 全满足 = YES/NO。

## 退出判据（E1）
- [1] 连续 ≥7 活跃日（空队列日豁免、有 due 未复审断签）
- [2] 标注率闸门 ≥70%（滚动 7 日 labeled_completed/completed）
- [3] budget_per_day 派生估计在 [7,14,21,28] 天窗口轨迹收敛（CV≤10% & 28d observed）
三者全满足 → E1 完成，可推进 roadmap 下一节点。

## 触发建议
- 手动：zj 说「跑 ZKC 每日循环」即执行上述五步。
- 日常运行形态（已配置）：WorkBuddy 每日定时任务（23:50）触发本流程；decide 人环那步仍须等待
  zj 在对话里给 verdict（自动化只跑 daily + embed + meter，decide 列表呈现后暂停待人）。
- 本机**不启用系统级调度**。仓库里 `install_daily_driver.*` 是 ADR-0007 既有的
  E1 驱动可选安装脚本（本机未安装），不含任何补向量条目；那条路径同样不包含 decide 人环。

## 纳管与同步（2026-11-05，zj 拍板 skill 纳管）
- canonical = 本文件（ZKC 仓库，git 跟踪）；运行副本 =
  `~/.workbuddy/skills/zj-zkc-daily/SKILL.md`。
- 安装/同步：`python scripts/install_harness_skill.py --dry-run` 预览；
  `python scripts/install_harness_skill.py` 首次安装；内容有分歧时默认**拒绝覆盖**，
  确认后加 `--force`（覆盖前会把旧副本存为 `SKILL.md.bak`）；`--check` 只查漂移。
- 更新流程：改 canonical → `--check` 看差异 → `--force` 同步 → 在 WorkBuddy 侧按既有
  「删除重装」约定重新装载 skill。脚本**不会自动删除** home 下的目录（安全边界）。
- 此纳管方式由 zj 显式选择，仅适用于 ZKC 自有 skill；跨项目通用约定「skills 与项目源码
  分离」在此被显式推翻，理由与边界见 ADR-0007。

## 与其他形态的关系
- B 形态即 `zkc` CLI（去服务器化）；D 形态即本 skill（harness 中立协议的 WorkBuddy 适配器）。
- **Codex / DeepSeek 适配器明确不做**（2026-11-05，zj 拍板）：本机无该侧运行环境，
  凭空产出无法验收的适配器等于伪造完成度。改为在 ADR-0007 落一份 **provider 无关的适配器
  契约**（四步流程 + human-in-loop 硬约束 + CLI seam；本 skill 现为五步——
  第 2 步插入并列的补向量，ADR-0007 两件机械事边界不变）；未来任何 harness 照契约接入即可，
  ZKC 内部不硬编码 provider（防 product gap 陷阱）。
