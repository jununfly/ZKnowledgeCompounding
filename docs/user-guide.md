# ZKC 使用指南（MVP）

本指南面向**使用者**：如何跑起本地应用、每天做复审、看懂复利度量、以及**每周一次度量复盘**该看什么。

> 设计哲学：ZKC 不是更好的笔记软件，而是让有限的「时间精力（长期）+ 注意力（短期）」对知识产生复利。
> 两个闭环（调度反馈 + 预算估计）都靠**你每天的真实操作**驱动——不操作，系统就停在冷启动。

---

## 1. 启动本地应用

```bash
pip install -e .          # 首次一次性：editable 安装（src 布局，包名 zkc）
python -m zkc.web         # FastAPI + SSR，localhost:8000
```

页面与接口：

| 路径 | 作用 |
| --- | --- |
| `/` | 快捕获：粘贴一条笔记，自动分流（静态/动态）或转人工定轨 |
| `/review` | **每日复审队列**（MVP 核心，见 §2） |
| `/metrics` | **复利度量面板**（见 §3） |
| `/review/api/queue`、`/review/api/decide`、`/review/api/observe` | 队列相关 JSON 接口 |
| `/review/api/tasks`、`/review/api/tasks/complete` | 今日任务队列（见 §2 顶部） |
| `/review/api/classify`、`/review/api/classify/resolve` | 人工定轨队列（见 §2.3） |
| `/metrics/api` | 度量报告 JSON 接口（供周报/管道消费） |

---

## 2. 每日复审队列（`/review`）

动态轨条目会随注意力衰减。一旦 `decay_score` 越过 **0.6（进入注意力）** 且距上次复审超过 `review_interval`，该条目就进入队列。

**同一界面承载两个外生锚——这是整个系统能自我修正的唯一支点：**

### 页面顶部 · 今日任务队列
打开 `/review` 第一眼看到的是**任务卡片区**（看板卡片风）。任务由系统按规则自动生成，无需手工录入：

| 类型 | 生成规则 | 例子 |
| --- | --- | --- |
| 周期 | 按日历每天/每周五出现 | 每日复审标注、每日收口、每周快照 |
| 预警 | 从观察期/预算数据派生，带到期日 | orphan 尖峰（11/05-06）、标注复审判定（≥20 条时） |
| 一次性 | 显式登记 | commit+push |

- 点「完成」即标记 done，计数从「开放 N」里扣掉；**刷新后不会复活**（按天幂等）。
- 周期任务第二天自动重新生成；预警任务只在窗口期内出现。
- 注意：**「commit+push」卡片点完成只是标记待办已完成，不会替你执行 git**。

### 锚 A · 复审结果标注（驱动 L3 复审节奏）
对每条待复审条目，按真实状态点一个按钮：

| 按钮 | 含义 | 系统反应 |
| --- | --- | --- |
| 仍有效 | 信息仍新鲜，节奏刚好 | interval 基本不变（on_time） |
| 已变 | 信息比预期变得快 | 缩短 interval（too_late → ×0.7） |
| 已腐 | 已经腐化、该更早看 | 缩短 interval（too_late → ×0.7） |
| 仅浏览 | 看了但暂不标注 | 只复位时钟、计数，不触发节奏学习 |

> 关键：标注率（近 7 天 `labeled_completed / completed`）需 ≥ **70%** 且样本 ≥ **10** 条，L3 才改写节奏；
> 否则 L3 停机（节奏停在基线）。不标注的复审等于没给系统任何学习信号。

### 锚 B · 每日收口（驱动注意力预算估计）
每天收工前，在底部「每日收口」填两项并点记录：

- **今日推送 pushed**：今天新进入队列的条目数
- **收口剩余 queue_remaining**：收工时还剩几条没处理

每处理一条（锚 A 的任意按钮）会自动累加当天的 `completed` 与 `labeled_completed`。
系统据此**删失感知**地估计你的真实注意力容量 `budget_per_day`——容量只能被观测，不能拍脑袋定。

> 没有这个界面，预算估计器永远停在 `confidence='none'`、L3 闸门永远没样本：两个自指闭环全废。
> 所以**每天打开 `/review` 处理几条 + 收口一次**是 MVP 的硬前提。

### 人工定轨（捕获弃权队列）
在 `/` 快捕获时，如果 LLM 说「内容太模糊/置信度不够」且词法路由也未挂载，系统**宁可弃权不猜**：笔记照样落库（`track=unrouted`），并进入 `/review` 的「人工定轨」区（任务卡片下方）。

- 每条带内容预览（截 120 字），右侧两个按钮：
  - **静态轨**：事实型知识——不衰减、不进复审、不吃注意力预算（定义/方法论，忘了也能查回来）
  - **动态轨**：存活型信息——线性衰减、进复审调度、吃注意力预算（会过期、要跟进的动态）
- 决策规则一句话：**这条内容半年后还需要你主动维护吗？** 需要 → 动态；不需要 → 静态。
- 定轨一次性生效（版本链有记录），拿不准时**倾向静态**：误定静态的代价只是不主动提醒；误定动态则它会反复占你的注意力预算。
- 你的每次定轨同时喂标注率闸门（近 7 天 ≥70% 是 L3 学习的前提）。

---

## 3. 复利度量面板（`/metrics`）

五个度量合成「复利健康度」。每项区间 [0,1]（方法论产出为计数），复利系数默认等权（各 0.25）合成。

**口径状态（2026-11-06）**：等权权重与 `method_target=10` 的 `source=SIMULATION`，即受控仿真给出的设计口径，**不是按真实行为校准过的值**（依据见 `docs/evidence/metric-weights-simulation.md`；升 `CALIBRATED` 仍需真实埋点与人工价值排序）。特别地，当连接密度 / 复用率 / 方法论产出结构性为 0 时，复利系数可能只由「到期节点已归档」撑起——**复盘必须拆看四项分量，不要只看合成值一个数字**。

| 度量 | 口径 | 读这个数 |
| --- | --- | --- |
| **连接密度** | 被 `reverse_link`/`derived_from` 边触达的动态节点占比 | 知识是否连成网 |
| **复用率** | 被后续条目 `citation` 引用的 claim 占比 | 提炼出的结论是否真被复用 |
| **方法论产出** | 结合算子（combine）产出的建模/方法论条目数（按目标值饱和归一到 1） | 动静结合是否产出新知 |
| **衰减可控** | 到期（decay≥0.9）动态节点中，被引用或已归档的比例 | 腐化前有没有被处理（而非静默丢失） |
| **复利系数** | 上述四项等权合成 | 整体复利健康度 |

**衰减可控的前提**：必须满足注意力预算 `n / (0.6 × interval)`（节点 R4）。
预算不满足时该值预期偏低——这是**供给问题**，先查预算再查指标，不要误判系统失效。

面板每 30 秒自动刷新；`/metrics/api` 返回带口径说明与当前注意力预算需求的 JSON，方便接入周报。

---

## 4. 每周度量复盘节奏

**每周固定一个时间（如周五收工）做 15 分钟复盘。** 目的不是追求数字，而是发现「系统是否在帮你省注意力、产复利」。

```bash
python scripts/metrics_snapshot.py        # 打印当前度量快照（JSON）
```

复盘清单：

1. **复利系数趋势**：比上周升/降？连续两周下降 → 进入第 2 步。
2. **拆四项**：哪一项拖累？
   - 连接密度低 → 是否在结合/蒸馏时主动建反向连接（derived_from）？
   - 复用率低 → 提炼的 claim 是否带可回溯来源、是否被后续条目引用？
   - 方法论产出为 0 → 这周有没有跑结合算子？是不是只捕获不蒸馏？
   - 衰减可控低 + 预算不足 → **先扩注意力预算**（R4），而非改指标。
3. **标注率闸门**：上周标注率是否 ≥70%、样本是否 ≥10？低于阈值说明 L3 没在学习，节奏是僵的。
4. **收口纪律**：每天是否都收口了？`budget_per_day` 估计的 `confidence` 是否已是 observed（有足够饱和日）？
5. 记一条结论到周记（项目外任意笔记），下周五对照。

> 复盘只产出「下一步动作」，不产出焦虑。系统是你的外脑，复盘是校准它、不是被它考核。

---

## 5. 每日驱动自动运行（可选，跨平台）

界面手工操作之外，可以把**两件机械事**交给系统每天 23:50 自动跑：① 真值收口
（写今日 `pushed` / `queue_remaining`，不手工乱填）② 跑 E1 进度仪表。
**复审标注（`decide`）永远不在此自动化范围内**——那是需要你本人判断的外生锚。
设计与边界见 ADR-0007；底层是 `zkc` CLI（`daily` / `meter` / `decide`）。

> **第三个条目是并列的，不塞进 E1 驱动**：`zkc embed`（补向量）每天 **23:55** 由
> 独立任务触发，比 E1 驱动晚 5 分钟避免并发抢 PG / Ollama。它写 `node` 派生列，
> 不写 `attention_observation`、不碰标注埋点；失败不影响 E1 两件机械事与三判据。
> 所以 ADR-0007 的「两件机械事」边界和 `daily_e1_driver.py` 都没有被改动。

### macOS（launchd）

```bash
scripts/install_daily_driver.sh --dry-run    # 预览渲染后的 E1 plist，不安装
scripts/install_daily_driver.sh              # 写入 ~/Library/LaunchAgents/ 并注册 E1 驱动
scripts/install_daily_driver.sh --embed --dry-run   # 预览并列的补向量 plist
scripts/install_daily_driver.sh --embed      # 注册每日 23:55 的 zkc embed
launchctl unload ~/Library/LaunchAgents/com.zkc.daily-e1.plist && rm ~/Library/LaunchAgents/com.zkc.daily-e1.plist
launchctl unload ~/Library/LaunchAgents/com.zkc.daily-embed.plist && rm ~/Library/LaunchAgents/com.zkc.daily-embed.plist
```

脚本自动解析 venv python 与仓库根；两个 plist 模板在 `scripts/launchd/`
（`com.zkc.daily-e1.plist` 23:50 / `com.zkc.daily-embed.plist` 23:55），Label 不同、互不覆盖。
补向量任务的日志单独写 `<仓库>/logs/daily_embed.out` / `.err`。

### Windows（计划任务）

```bat
scripts\install_daily_driver.bat --dry-run     :: 预览 schtasks 命令，不注册
scripts\install_daily_driver.bat                :: 注册每日 23:50
scripts\install_daily_driver.bat --uninstall    :: 卸载
scripts\install_daily_driver.bat --time 07:15   :: 改触发时间
scripts\install_daily_driver.bat --embed --dry-run  :: 预览并列的补向量任务
scripts\install_daily_driver.bat --embed        :: 注册每日 23:55 的 zkc embed
scripts\install_daily_driver.bat --embed --uninstall :: 卸载补向量任务
```

E1 任务调用 `scripts\daily_e1_driver.bat` 包装（venv python 优先、`ZKC_MODE=direct`）；
补向量任务调用独立的 `scripts\daily_embed_driver.bat`（`-m zkc.cli embed`），
任务名 `ZKC Daily Embed` 与 E1 的 `ZKC Daily E1` 分开。
`--dry-run` 不写任何计划任务，重复安装用 `/f` 覆盖同名任务。
> **未实机验证**：本仓库开发机是 macOS，Windows 注册流程只经过命令契约单测与 dry-run 冒烟，
> 未在 Windows 上真实注册过。首次在 Windows 使用时按 ADR-0007 的复核清单逐条确认。

E1 驱动两端日志都写 `<仓库>/logs/e1_daily.log`（JSONL，每次运行一行）；
补向量条目的输出单独落在 `logs/daily_embed.out` / `.err`，互不混写。

### WorkBuddy 侧的 zj-zkc-daily skill

canonical（唯一真相源）在仓库 `skills/zj-zkc-daily/SKILL.md`；运行副本在
`~/.workbuddy/skills/zj-zkc-daily/SKILL.md`，由脚本同步，**不要手改副本**：

```bash
python scripts/install_harness_skill.py --check     # 只查漂移（drift → 退出 1）
python scripts/install_harness_skill.py --dry-run   # 预览
python scripts/install_harness_skill.py --force     # canonical 更新后同步（旧副本留 .bak）
```

脚本不删除 home 下目录；副本被手工改过时默认拒绝覆盖。在 WorkBuddy 里说
「跑 ZKC 每日循环」即按该 skill 走五步流程（收口 → 补向量 → 列队列 → 人环复审 → 仪表），
其中 `decide` 会停下来等你给 verdict；补向量为 best-effort，失败不阻塞其余步骤。

---

## 6. MCP stdio server（E2 骨架）

ZKC 以**单边 MCP server** 形态接入 Codex / WorkBuddy（两者均为纯 MCP client）。
默认 stdio：**零网络监听面、无需 token**，client 以子进程方式启动：

```bash
python -m zkc.transport
```

MCP client 的 `command` / `args` 配置：

```json
{"command": "python", "args": ["-m", "zkc.transport"]}
```

协议基线 `2024-11-05`；对外契约 `zkc-mcp-contract/v1` 的机器可读快照在
`src/zkc/transport/contract_v1.json`（独立于 §5 DDL 版本化，DDL 演进由 seam 吸收）。
白名单五 tool、黑名单四类危险写、capabilities 与信任边界都以该快照为唯一事实源。

**stdout 纪律**：stdout 只写 JSON-RPC 帧，诊断信息一律走 stderr；单帧一行、
通知（无 id）不回帧。**transport 层不 import repository / 驱动，也不直连 DDL**——
所有 tool / resource 的 handler 由上层在构造 `McpServer` 时注入（第四 seam）。

> 五个白名单 tool 与 `zkc://scheduler/due` resource 已接线：`zkc_capture` 走 push +
> 分流闸（弃权入人审），`zkc_query` 默认脱敏并带 `evidence_refs` 溯源，
> `zkc_review_queue_resolve` 只标 resolved + 记 HITL 归因，
> `zkc_scheduler_due` 返回带衰减/复审节奏的「该关注清单」。
> 黑名单四类危险写（`distill/trigger` / `interval_adjustment` / `meta_claim` /
> 历史行 delete/update）不注册为 tool，越权调用被拒并留审计事件。
> `zkc_capture` 已按 capture profile 落地：默认开启、只加源节点、单次 ≤1000 条
> 并走 decay 初始化；不可信内容只作纯文本存储，命中注入标记仅留痕、不解析执行，
> 注入指令冒充 HITL 归因回写队列会被拒绝并留痕。
> 提示注入 gate 用例已接 CI 独立 job（`make mcp-gate`），只依赖 memory backend，
> 不需要 PG / Ollama，本地可随时复跑。

设计与安全边界见 `docs/zj-adr/0004-mcp-interface-contract.md`。

---

## 7. 补向量运行契约（`zkc embed`）

**为什么需要单独一步**：`zkc_capture` 走 capture profile（ADR-0004），默认**只加源节点**，
不计算 embedding。所以刚摄入 / 快捕获的条目能被结构化检索找到，但**不会被语义召回**
（`/browse` 默认走 `embedding_4096` 列）。补向量是独立、可调度的一步：

```bash
zkc embed --dry-run --json   # 只看缺口，不编码不写库
zkc embed                   # 全轨补齐双列（幂等，可每天挂调度重复跑）
zkc embed --storage memory  # 单测 / 无 PG 环境
```

行为口径（`src/zkc/embedding_backfill.py`）：

- **全轨**：static / dynamic / unrouted 都扫，不只动态轨；已归档节点跳过（已移出召回，不再补向量）；
- **空正文兜底**：`text = title + "\n" + content`，无正文时只用标题——旧脚本
  `and n.content` 会把这类节点永久跳过，已修复；
- **双列共存**：`embedding`(nomic 768d) 与 `embedding_4096`(qwen3 4096d) 各自补齐；
- **幂等 / 去重**：只写缺失列；相同文本只编码一次（重复节点共享同一向量）；
- **原子**：先全部编码成功再统一写；Ollama 不可达导致任一编码失败 → 零写入，不留半成品；
- **不污染版本链**：走 `set_embedding_column` 轻量路径，不写 `node_history`、不 bump `tx_from`。

> **边界（刻意不自动化）**：补向量**没有**接进 capture 链路。在 capture 时编码会把
> encoder 依赖引入 transport seam、扩大 capture profile 写入面，并让每次 MCP 捕获
> 多等十几秒（长文 4096d 编码），属需单独拍板的架构变更。当前以 `zkc embed` 作为
> 显式、可调度的正式入口；如需「捕获即补」，先落 ADR 再改，不要在这里偷偷接线。

历史脚本 `scripts/backfill_embedding_4096.py` 仍保留 R18 的「dynamic + 4096」窄口径，
但已修掉空正文漏补；日常一律用 `zkc embed`。**每日调度已挂**：见 §5 的并列条目
（macOS `--embed` launchd / Windows `--embed` schtasks，均 23:55），
WorkBuddy 里跑「ZKC 每日循环」也会把它作为第 2 步执行。
