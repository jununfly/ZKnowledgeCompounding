# ZKC 下版本开发计划（Next-Version Development Plan）

> **合并来源**：`discussions/zkc-next-version-improvements/`（zj-discuss 多角色讨论 + zj-grill-with-docs 拍板）+ `docs/research/similar-oss-landscape/`（竞品横比 + 证据账本）。
> **本文为下版本唯一执行真相源**；原 `discussions/` 与 `docs/research/` 已于 2026-11-03 归档删除，其内容（含证据账本）已并入本文 §1 与下列各节。
> 生成：2026-11-03。配套决策记录：**ADR-0004**（MCP 接口契约边界）、**ADR-0005**（rec-avoid 机械闸）、`docs/rec-avoid-gate.md`（守门记录）；架构 §7 图库 EXCLUDED 行、PRD §9 决策清单已同步回填。

---

## 0. TL;DR（一页结论）

| 维度 | 决定 |
|---|---|
| MCP 形态 | **单边 server**（stdio 默认），双向 client 推 phase 2 |
| 优先级 P0 | **校准闭环跑通**（budget/L3 产真实数据）+ **护城河实证化**列为验收 |
| 捕获摩擦 | agent 辅助 `zkc_capture`（push）并行启动，验收=手动步骤≤1 且人工干预率不升 |
| 护城河守门 | **rec-avoid 机械闸**：去模型化测试 + `check_invariant.py` + 图库主存储 EXCLUDED |
| 安全边界 | 默认 stdio（零网络面）；跨机才 HTTP/SSE+加密隧道，否则不变式⑤自动否决 |
| 对外叙事 | 唯一性主张带 `caveat: moat-unverified-vs-mem0`；特征口径统一为 **4 项** |

---

## 1. 竞品定位与护城河（来自 research/）

### 1.1 一句话定位
ZKC 是唯一把「双轨（静态/动态）+ 衰减 + 双时态 + 注意力预算」建模为第一性对象的项目（caveat: moat-unverified-vs-mem0 — mem0 因编译限制未纳入对照，该唯一性主张未经 mem0 复核）；khoj 与 ZKC 共享 Postgres+pgvector 基底；logseq / SilverBullet 是本地优先的静态图 / 文件化方案；letta 的 main 分支已是落地页（实现在 archive），无法核验；mem0 因编译器 submodule 限制被排除。

### 1.2 differentiator 两层拆分（报告 §5.1）
> 原单值度量（ZKC=4 / 其余=0）混同「未核验(0)」与「已证伪(0)」，已拆分为两层：

- **已核验差异化轴（ZKC 成立，可独立复现）**：生命周期衰减建模 ✔、注意力稀缺预算约束 ✔、双轨（静态/动态）建模 ✔、双时态（bitemporal）自建语义 ✔（无对照实现可证伪，属「无竞品对照」非「证伪」）。
- **存疑轴（unknown，非证伪）**：letta 的 `architecture_storage` 与 `compounding` 两项（main 落地页无实现，仅 archive）；mem0 对照整体缺失（编译限制排除）。
- **其余项目**：logseq / SilverBullet / khoj 在 4 项特征上均为 0；其中 letta 的 2 项须标注为 unknown 而非证伪 0。

### 1.3 证据账本摘要（来自 evidence-ledger.md）
原报告声明 24 条 evidence，但完整行级清单已随中间产物删除，**仅 5 个 commit-pinned 锚点可复验**（约 79% 证据行不可直验）。定位决策仅采信这 5 锚点 + 复采证据：

| 项目 | commit | 关键文件 | 采证内容 |
|---|---|---|---|
| ZKC（基线） | `69d3b26` | `docs/architecture/ZKC-architecture-v1.2.md` | 双轨 schema / 资源感知调度 / Ollama 接线 / HITL / `evidence_refs NOT NULL` |
| letta | `8816d3a` | `AGENTS.md` | main 落地页 + archive 分支（实现弃用） |
| khoj | `ae229ca` | `docker-compose.yml`、`.devcontainer/Dockerfile` | pgvector:pg15 / UV+Bun / docker-compose |
| logseq | `e7e9c97` | `.agents/.../libraries`、`modules/README.md`、`AGENTS.md` | Datascript / Block 树 / db-sync |
| SilverBullet | `657cd3b` | `docs/ADR/003 Indexed Object Graph.md`、`Dockerfile` | Markdown 真相源 / Object Index / Space Lua |

**缺口账册（unknown，非证伪）**：governance×4（ZKC/khoj/logseq/SilverBullet LICENSE 未采）+ letta×2（architecture_storage / compounding）+ mem0 整体排除（最具参照性 AI 记忆层被遗漏，残余风险「中」）。

### 1.4 对外叙事约束
- 任何「ZKC 绝对领先 / 唯一」表述须绑定 §1.2 拆分 + `caveat: moat-unverified-vs-mem0`。
- 特征口径统一为 **4 项**（双轨/衰减/双时态/注意力预算），报告 §1/§4.2/§5/§10 已对齐；新文档不得回退到 3 项口径。
- 分层决策：(a) 现在可定——双轨+衰减+注意力为第一性、rec-avoid 守门；(b) 等补 governance 后声明——跨项目许可兼容；(c) 永久 unknown（非等补）——letta 现役实现、mem0 对照。

---

## 2. 下版本优先级（来自 sub-02）

### 2.1 P0 校准闭环（隐藏前置）
真正的 P0 不是加功能，而是把**已交付的每日复审队列 UI 背后的 calibration 闭环（budget/L3 阈值）跑通、产出真实使用数据**。它是捕获摩擦、复利面板、MCP 三者共同的隐藏前置。
- **DoD**：连续 ≥7 活跃日 + 复审标注率闸门 ≥70% + `budget_per_day` 估计从初始值收敛到稳定值。
- 不做完此闭环，2.2/2.3/3 都建在沙上。

### 2.2 捕获摩擦降低（可并行）
借鉴 SilverBullet「纯源文件 + 自动抽取可查询图」降低录入摩擦，但验收硬指标=**不新增外生锚摩擦**（手动步骤≤1、人工干预率不升）。agent 辅助 `zkc_capture` 即该路径的落地（见 §3.3）。
- 反例风险：自动抽取若把更多待审项灌进复审队列，是用一种摩擦替换另一种，净收益可能为 0——故验收必须量化人工干预率。

### 2.3 rec-avoid 机械闸（来自 ADR-0005）
把护城河从文档口号落成**版本门**（详见 §4）。三件套：去模型化测试 + `check_invariant.py` + 图库主存储 EXCLUDED。

### 2.4 护城河实证化（P0 验收，闭合 R concern）
护城河目前部分是「架构论点非经验证据」，下版本须实证化：
- 架构 §9 回填复利度量最终口径；
- zj 人工抽检蒸馏产物，记录漏检/误蒸馏率，给本机 4B/9B 上界估计；
- 该度量进 rec-avoid 经验证伪闸（见 §4.4）。

### 2.5 证据缺口分层（不阻塞排期）
6 项 unknown 只延迟对外定位叙事、不阻塞任何工程排期（详见 §1.4 分层）。

---

## 3. MCP 集成（来自 sub-01 / ADR-0004）

### 3.1 形态与 seam
- **单边 server**：ZKC 暴露 MCP server，Codex/WorkBuddy 作 client 连上来（事实锚：两者皆纯 client 且支持 stdio）。双向 client（自动灌外部上下文入动态轨）推 phase 2，且须复用现有摄入层（DecisionRouter + 双信号弃权 + review_queue 人审），禁止新增旁路摄入通道。
- **transport seam（第四 seam）**：与 storage/provider/encoder 并列。MCP server 只调既有 repository/command API，**handler 不直连 DDL**；对外契约独立版本化 `zkc-mcp-contract v1`（语义化版本，不承诺 12 个月冻结，bump 随 §5 DDL 演进由 seam 适配层吸收）。

### 3.2 暴露面白名单 / 黑名单
- **白名单（允许）**：`zkc_capture` / `zkc_query`（带 `evidence_refs` 溯源）/ `zkc_review_queue_list` / `zkc_review_queue_resolve`（仅标 resolved + HITL 归因）/ `zkc_scheduler_due`（只读该关注清单）。首个 resource 强制含注意力语义（该关注清单），否则与 khoj 同质被反例推翻。
- **黑名单（绝不暴露）**：`distill/trigger` 自动写、`interval_adjustment` 直接写、`meta_claim` 直接写、历史行 delete/update（守 §6.5 不变式：未标注禁止写 interval）。

### 3.3 `zkc_capture` 完整规格（agent 输入文档的首要场景）
- **push 模型**：agent 显式调 `zkc_capture` 推文档进 ZKC（非 ZKC 主动拉取）——**正是对你「经 Codex/WorkBuddy 给 ZKC 输入文档」诉求的固化**，且支撑 §2.2 捕获摩擦降低。
- **必须过分流闸**：经 DecisionRouter + 双信号弃权 + review_queue 人审，**禁 agent 直通道**；agent 不替系统预设轨（静态/动态由路由判）。
- **capture profile**：列为独立 `capture` profile，**默认开启**（安全写——只加源节点，不写 interval、不触发 distill、不直写 meta_claim，不绕过 HITL），区别于 opt-in 的 `review_queue` 标注与禁暴露的三类危险写。
- **量级节流**：单次会话 `node` 写入上限 ≤1000，并走 decay 初始化；超上限分批。
- **注入防护**：不可信文档内容经 agent 注入后调 MCP 写 tool 时，未授权写被拒、私人 claim 不出现在 query 响应体。

### 3.4 安全边界
- **默认 stdio**：零网络监听面，无需 token，外部 agent（含同机 Codex/WorkBuddy）一律零信任。
- **跨机才开 HTTP/SSE**：仅当确需跨机（Mac↔Win Tailscale）时启用，且必须端到端加密隧道，否则**不变式⑤（本地优先/隐私）自动否决**，无需 Human 二次拍板。
- **写操作白名单 + 私人 claim 沙箱**：`meta_claim` 私人事实型 claim 默认脱敏，须显式 scope 授权方可带隐私字段。
- 若 Codex/WorkBuddy 仅支持 HTTP MCP 不支持 stdio → 禁止上线，回退本地文件导出。

### 3.5 攻击面枚举表 + 注入测试验收（ADR-0004 强制章节）

| 列 | 内容 |
|---|---|
| 入口（stdio 默认） | `zkc_capture`(写,受分流闸) / `zkc_query`(读,带 evidence_refs,私人 claim 默认脱敏) / `zkc_review_queue_list`(读) / `zkc_review_queue_resolve`(写,仅标 resolved+HITL 归因) / `zkc_scheduler_due`(读) |
| 出口 | 当前**无**（单边 server 不调外部）；phase 2 双向 client 才开放，须显式决议 |
| 信任边界 | stdio 零网络面无需 token；跨机 HTTP/SSE 须加密隧道；外部 agent 零信任；写白名单 + 私人 claim 沙箱 |

**提示注入验收用例（gate 用例）**：构造注入（不可信内容 → agent 被注入 → 调 MCP 写 tool），断言 ① 未授权写被拒（distill/trigger/interval_adjustment 返回权限拒绝）② 私人 claim 不出现在 query 响应体 ③ 越权企图回写 `review_queue` 留痕。该用例纳入 ADR 验收闸门。

---

## 4. 机械守门（来自 ADR-0005 / rec-avoid-gate.md）

### 4.1 去模型化测试（model-stripping test）
判据：某候选功能去掉 LLM 后若仍可被 SilverBullet / logseq 等价实现，即**稀释项**，默认拒绝。由 C 角色维护可证伪清单（图数据库查询、纯结构抽取面板在列），并对 SilverBullet/logseq 做实测对照；PR 须附结论。已知非稀释项：带 `evidence_refs` 强制溯源的 claim 落库、衰减+预算可观测性、双时态投影。

### 4.2 `check_invariant.py`（CI 谓词）
PR 门禁，至少两条断言：① claim 落库仍受 `meta_claim.evidence_refs uuid[] NOT NULL` 约束；② 任何 feature 不得提供关闭 `decay` / `attention` 的全局开关。

### 4.3 图数据库主存储 EXCLUDED
图数据库（Kuzu / TerminusDB）作主存储显式拒绝（EXCLUDED）；仅允许 Kuzu **只读投影**。理由：仓库切换成本 + 偏离 pgvector 基底；递归 CTE 已够用；保持 repository seam 可切。依据：架构 §7 该行「延后」→「EXCLUDED」。

### 4.4 经验证伪闸（护城河实证化，呼应 §2.4）
任何新增功能须证明**不降低**「衰减+预算可观测性」，否则触发 rec-avoid③。护城河由系统外信号证伪：锚1=复审标注率闸门持续 ≥70%；锚2=zj 人工抽检蒸馏产物记录漏检率（系统外信号 vs 系统自算「复利系数」）。

---

## 5. 执行清单（按依赖排序）

- [ ] **E1 · 校准闭环跑通（P0）**：在已交付复审队列上运行 ≥7 活跃日，确认 budget/L3 收敛 + 标注率≥70%；产出真实数据后再开工 E2–E4。（DoD 见 §2.1）
- [ ] **E2 · transport seam + MCP server 骨架**：`src/zkc/transport/mcp_server.py` 薄适配层（stdio，零领域逻辑、handlers 不直连 DDL），契约 `zkc-mcp-contract v1`；先于业务 tool 落地（E3 依赖）。
- [ ] **E3 · 暴露面 5 tool 实现 + 攻击面枚举表**：实现白名单 5 tool（capture/query/review_queue_list/resolve/scheduler_due），黑名单拒绝逻辑；写入攻击面枚举表（§3.5）。
- [ ] **E4 · `zkc_capture` 完整规格**：push + DecisionRouter 分流闸 + capture profile 默认开 + ≤1000 节流 + 注入防护（§3.3）。
- [ ] **E5 · 注入测试验收用例**：实现 §3.5 的 gate 用例并接入 CI；未授权写被拒 + 私人 claim 不泄露 + 越权留痕。
- [ ] **E6 · `check_invariant.py`**：CI 谓词（§4.2）；任何新 PR 门禁。
- [ ] **E7 · 去模型化测试清单**：C 角色维护可证伪清单 + SilverBullet/logseq 实测对照，进 `rec-avoid-gate.md`；PR 须附结论。
- [ ] **E8 · 护城河实证化**：架构 §9 回填复利度量最终口径；zj 人工抽检蒸馏漏检率给本机 4B/9B 上界；进经验证伪闸（§4.4）。
- [ ] **E9 · 对外叙事对齐**：README/PRD/报告定位段落统一 `caveat: moat-unverified-vs-mem0` + 4 特征口径（报告+PRD 已完成，README 无定位表述无需改）。

> 依赖链：E2 → E3 → E4 → E5（MCP）；E1 是 E2–E4 的隐藏前置但可并行观察；E6/E7/E8 为独立守门/实证任务，可随时启动。

---

## 6. 风险与未决（honest）

- **mem0 未复核**：最具参照性的 AI 记忆层因编译限制被排除，唯一性主张已挂 `caveat: moat-unverified-vs-mem0`，补采后可据实升级或撤回。
- **护城河仍部分为架构论点**：实证化（E8）进行中，完成前「复利可观测」属设计论点非经验证据。
- **证据账本复现性半开**：原报告 24 行级 evidence 已删，仅 5 锚点可复验（§1.3）；任何细粒度复核须按 commit-pinned 路径复采。
- **报告 §12 自陈 `healthy=true` 但证据行已删**：该质量门与实证留存度不匹配，已由 evidence-ledger 修复性底稿弥补。
- **cli 仅支持 stdio 风险**：若 Codex/WorkBuddy 某环境仅支持 HTTP MCP，按 §3.4 禁止上线、回退本地导出。
