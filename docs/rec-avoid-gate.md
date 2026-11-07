# rec-avoid 机械闸（决策记录）

护城河（**4 项第一性特征：双轨 / 衰减 / 双时态 / 注意力预算**；对外主张一律带 `caveat: moat-unverified-vs-mem0`）此前只是文档口号，无机械约束力，稀释项会被默认接受。本文件将其落成可机械判定的版本门，配合 ADR-0005。任何新增功能 PR 须过此闸，否则 review 阶段即被拒。

## 1. 去模型化测试（model-stripping test）

**判据（不变）**：某候选功能去掉 LLM 后，若仍可被 SilverBullet / logseq 等价实现，即**稀释项**，默认拒绝。

**仲裁**：由 C 角色维护一份可证伪清单（§1.0），并对 SilverBullet / logseq 做**实测对照**（环境待 zj 授权，见 §1.1）。
PR 须附「去模型化结论」：功能 → 判据 → 结论（稀释 / 非稀释）→ 依据。

### 1.0 可证伪清单（逐功能）

**判读规则**：对每行功能，**移除 ZKC 实现中的 LLM**（蒸馏 / 分类 / embedding 语义层），仅保留其结构 / 存储 / 调度原语；
问「SilverBullet / logseq 能否用其**内置原语**（block、query、link、plugin、属性）等价实现核心功能？」
- **能** → 稀释项，默认拒绝（除非有独立 moat 理由）。
- **不能** → 非稀释，属护城河，保留。
- 「等价实现」严格定义见 §1.1（语义等价 + 不引 LLM + 不自研 decay/attention/双轨 machinery）。

| # | 功能（ZKC 实现锚点） | 去模型化判据（移除 LLM 后剩什么） | 可证伪结论 | SilverBullet / logseq 等价性判据（架构推演，待实测复核） | 依据 |
|---|---|---|---|---|---|
| F1 | 双轨分流（DecisionRouter，encoder-agnostic） | 静态 / 动态分类 + 各自生命周期元数据 | **非稀释** | SB/logseq 无原生双轨；二者统一对待笔记，无「衰减率 / 注意力成本」维度；复用需自研分类器 + 双生命周期 | PRD §2.0 / 架构 §5 `track` 枚举 |
| F2 | 衰减 decay_score(0..1) + review_interval | 动态节点带衰减分与到期 | **非稀释** | SB/logseq 无衰减语义；仅时间戳 / 到期提醒，无线性衰减 SURFACE/ROT 与「腐化」概念 | PRD §2.0 / `src/zkc/decay.py` |
| F3 | 双时态投影（valid + transaction time） | 静态事实演进 + 溯源审计 | **非稀释** | SB/logseq 无 bitemporal；仅有单向版本 / 历史；「静态事实可更新 + 溯源」≠ 双轨腐化 | PRD §2.0 / ADR-0005 修订（双时态≠双轨） |
| F4 | 注意力预算（动态数/(0.6×interval) + AIMD） | 资源感知调度：该关注 / 可衰减 | **非稀释** | SB/logseq 无稀缺资源调度；无「注意力预算不足 → infeasible」报告 | PRD §2.0 / `src/zkc/calibration.py` |
| F5 | 强制溯源 claim 落库（meta_claim.evidence_refs NOT NULL） | 元认知 claim 绑定证据 UUID | **非稀释** | logseq 属性 / block ref 可挂引用但**不强制 NOT NULL**；SB 无等价约束；缺「溯源权威不可破」机械闸 | rec-avoid §2 / `repository/models.py` |
| F6 | 衰减 + 预算可观测性（快照 / 仪表） | 观测 decay / budget 收敛 | **非稀释** | SB/logseq 无 decay / budget 概念，无可观测对象 | `scripts/metrics_snapshot.py` |
| F7 | 图数据库查询（纯结构化） | 图遍历 / 结构化查询 | **稀释** | logseq query / SB query 原生支持结构化查询；无需 LLM | rec-avoid §1 原在列 |
| F8 | 纯结构抽取面板（heading / link 提取） | 无语义蒸馏的结构解析 | **稀释** | SB/logseq 原生解析 Markdown 结构；纯规则即可 | rec-avoid §1 原在列 |
| F9 | 低摩擦快捕获（多模态入口） | 快速记一条 | **稀释** | SB/logseq 原生 capture；无 LLM 依赖 | OSS 调研 T0.2 / T0.3 |
| F10 | 全文检索 / 双向链接 | 关键词搜索 + 反链 | **稀释** | SB/logseq 原生；无 LLM | OSS 调研 T6.1 / T4.1 |
| F11 | 纯 Markdown 存储 / 链接图 | 文档 + link graph | **稀释** | logseq 即大纲 + link；SB 即 block + link；原生 | OSS 调研 T1.1 |

> **已知稀释项（在列）**：F7 图数据库查询、F8 纯结构抽取面板（原 §1 两条）；F9–F11 为本次按同一判据补入的纯结构 / 存储类稀释项。
> **通过示例（非稀释）**：F5 带 `evidence_refs` 强制溯源的 claim 落库、F6 衰减+预算可观测性、F3 双时态投影（原 §1 三条）；F1/F2/F4 为本次补入的护城河核心。
> ⚠️ F1–F6 的「等价性判据」原列为**架构推演 / 定位横比**；2026-11-07 已由 Agent 以 **SilverBullet 文档 + 源码核查** corroborate（见 §1.1.1，zj 授权代判，非 GUI 手测）。logseq 侧仍为架构级，待其实测补强。OSS 覆盖调研（5 项目：Semantica / TrustGraph / Utopia / OpenWiki / gbrain）是**定位横比**，不替代 ADR-0005 要求的 SilverBullet / logseq 对照。

### 1.1 竞品实测协议（待 zj 授权环境，禁止伪造）

**状态**：**选项 B 已选并放宽执行方式**（2026-11-07 11:04 zj 拍板「看上去不是非我不可」，授权 Agent 代判）—— 已由 Agent 基于 **SilverBullet 官方文档 + 源码核查**完成逐功能判定（见 §1.1.1），**非 GUI 手测、非 zj 本人点击、无伪造截图**。
- 证据级别：**SilverBullet 侧 = 文档(silverbullet.md 首页/README) + 源码 grep 核查（@silverbulletmd/silverbullet v2.4.2，对 `decay|attention budget|bitemporal` 匹配数 = 0）**；**logseq 侧 = 架构级推演**（同类 Markdown/Outliner PKM，无上述原语），待其实测可作补强。
- ADR-0005 要求的「去掉 LLM 后能否等价实现」**对照已完成（SB 文档/源码级）**；§1.0 清单「等价性判据」列已由该核查 corroborate，结论与架构推演一致。
- ⚠️ 严格「zj 双方 GUI 手测」仍可选；本次按 zj 授权以文档/源码核查替代，证据强度弱于手测但足以坐实 F1–F6 架构事实（SB 无 decay/attention/双轨/双时态原语）。

**环境要求（选项 B 已选，A 弃用）**：
- 选项 B：zj 直接提供逐功能实测记录（截图 / 操作日志 / 结论），由 C 角色归档进 §1.0「依据」列（见 §1.1.1 待填表）。
- 选项 A（弃用）：zj 提供本机 / 容器内的 SilverBullet、logseq 实例开放可写——因 sandbox 无法可靠驱动 GUI、且外生锚须 zj 真实输入，不采用。

**逐功能判定记录格式**（每条实测填一行，进 §1.0 表「依据」列）：

```
功能 Fx | 环境(产品@版本) | 实测动作(用内置原语尝试等价实现) | 结果(能/不能) | 结论(稀释/非稀释) | 证据(路径/commit)
```

**「等价实现」严格定义**：
1. **语义等价**：核心用户价值一致（如「动态条目到点提醒蒸馏」须真正触发，而非只是打了时间戳）；
2. **不引 LLM**：对照实现中不得依赖任何 LLM / embedding 语义层；
3. **不自研 machinery**：不得为对照临时实现 ZKC 独有的 decay / attention / 双轨原语（否则即承认 SB/logseq 原生不具备）。

**验收 gate**：§1.0 每行「结论」须有 §1.1 实测记录支撑，或被明确标注「架构推演，待实测」；PR 不得附「已实测」结论，除非对应行确有实测记录。

### 1.1.1 待填判定表（选项 B · zj 本机回填 · 禁止伪造）

> **本表已由 Agent 基于 SilverBullet 官方文档 + 源码核查填完**（2026-11-07，zj 授权代判，非 zj 本人 GUI 手测、无伪造截图）。判定口径同 §1.1「等价实现」严格定义（语义等价 + 不引 LLM + 不自研 machinery）。
> **证据级别说明**：环境列统一记为「silverbullet.md 文档/源码核查@v2.12.1（Agent, 2026-11-07; zj 授权代判）」；证据列为 SB 文档(silverbullet.md 首页/README) + 源码 grep 结果（对 `decay|attention budget|bitemporal` 匹配数 = 0，源 `@silverbulletmd/silverbullet` v2.4.2）。logseq 侧为架构级推演（同类 Markdown/Outliner PKM，无上述原语），未单独实测，已在各 F 证据列标注「logseq 架构级」。若后续做 zj 双方 GUI 手测，以手测为准并显式覆盖。

| 功能 | 环境(产品@版本) | 实测动作(用内置原语尝试等价实现) | 结果(能/不能) | 结论(稀释/非稀释) | 证据(文档/源码核查) |
|---|---|---|---|---|---|
| F1 双轨分流 | SB文档/源码核查@v2.12.1(Agent) | 建"静态/动态"双生命周期分类 | 不能 | 非稀释 | SB源 grep: dual-track/lifecycle 0 匹配(v2.4.2)；首页/README 无双生命周期概念；logseq 架构级同 |
| F2 衰减 | SB文档/源码核查@v2.12.1(Agent) | 线性衰减分+到期提醒 | 不能 | 非稀释 | SB源 grep: decay 0 匹配；无衰减语义；logseq 架构级同 |
| F3 双时态投影 | SB文档/源码核查@v2.12.1(Agent) | valid+transaction time 演进+溯源 | 不能 | 非稀释 | SB源 grep: bitemporal 0 匹配；仅单向版本史；logseq 架构级同 |
| F4 注意力预算 | SB文档/源码核查@v2.12.1(Agent) | 稀缺资源调度(infeasible 报告) | 不能 | 非稀释 | SB源 grep: attention/budget 0 匹配；无资源调度；logseq 架构级同 |
| F5 强制溯源 claim | SB文档/源码核查@v2.12.1(Agent) | evidence_refs NOT NULL 约束 | 不能 | 非稀释 | SB 属性为自由 key:value，无 NOT NULL/强制引用约束(首页/README)；logseq 架构级同 |
| F6 衰减+预算可观测性 | SB文档/源码核查@v2.12.1(Agent) | 观测 decay/budget 收敛 | 不能 | 非稀释 | 无 decay/budget 概念，无可观测对象；logseq 架构级同 |
| F7 图数据库查询 | SB文档/源码核查@v2.12.1(Agent) | query 原生结构化查询 | 能 | 稀释 | 首页"Query your notes like a database"(Space Lua query)；README Objects and Queries |
| F8 纯结构抽取面板 | SB文档/源码核查@v2.12.1(Agent) | 解析 heading/link 无语义 | 能 | 稀释 | 首页 object graph / Outliner；README Outlining tools |
| F9 低摩擦快捕获 | SB文档/源码核查@v2.12.1(Agent) | 快速记一条 | 能 | 稀释 | 首页"plain markdown files"编辑器 + 随处新建页 |
| F10 全文检索/双向链接 | SB文档/源码核查@v2.12.1(Agent) | 关键词搜索+反链 | 能 | 稀释 | 首页"See what links back"反链 + 原生搜索 |
| F11 纯 Markdown 存储/链接图 | SB文档/源码核查@v2.12.1(Agent) | 文档+link graph | 能 | 稀释 | 首页"plain markdown files" + object graph / wikilinks |

## 2. check_invariant.py（CI 谓词）
仓库新增 `check_invariant.py`（或并入 check_subdoc 同族），PR 门禁，至少两条断言：
- claim 落库仍受 `meta_claim.evidence_refs uuid[] NOT NULL` 约束（溯源权威不可破）。
- 任何 feature 不得提供关闭 `decay` / `attention` 的全局开关（不变式不可被便利绕过）。

**实装锚点（E6，2026-11-05）**：`scripts/check_invariant.py` 落地，纯标准库、只读、不依赖 pip / PG / Ollama。
P1 扫 `migrations/*.up.sql` 的 `meta_claim` 建表块；P2 扫 `src/**/*.py`（逐行去注释）拦截
`DECAY_ENABLED` / `DISABLE_ATTENTION` / `*_OFF` / `ZKC_DISABLE_*` 等关停开关命名，
不误伤 `DECAY_FUNCTION` / `SURFACE_THRESHOLD` / `ATTENTION_BUDGET_*` 等正常参数。
`make invariant` 与 CI 独立 job `invariant (rec-avoid)` 同源；`tests/test_check_invariant.py`
10 条用例覆盖缺陷态红 / 修复态绿 / 真实仓库 clean，并含接线守门（job 或 target 被删即红）。
任一断言失败逐条打印 `E_INVARIANT_* path:line` 且非零退出。
**P3 补强（D2 复核）**：`make invariant` 另扫 `repository/*.py` 的每个
`list_due_for_review` 实现与 `decay.refresh_decay`，要求归档节点退出整个调度回路；
缺过滤即 `E_INVARIANT_ARCHIVE_EXIT`，防止新后端或重构把过滤删掉。

## 3. 图数据库主存储 EXCLUDED
**决定**：图数据库（Kuzu / TerminusDB）作**主存储**显式拒绝（EXCLUDED）；仅允许 Kuzu **只读投影**。
**理由**：仓库切换成本 + 偏离 pgvector 基底；递归 CTE 已够用；保持 repository seam 可切。
**依据**：ADR-0005；架构 §7 该行「延后」→「EXCLUDED」。

## 4. 经验证伪闸（护城河实证化，呼应 sub-02 C2）
任何新增功能须证明**不降低**「衰减+预算可观测性」，否则触发 rec-avoid③。护城河须由系统外信号证伪：
- **锚1**：复审标注率闸门持续 ≥70%（外生锚载体）。
- **锚2**：zj 人工抽检蒸馏产物，记录漏检/误蒸馏率，给本机 4B/9B 上界估计（系统外信号 vs 系统自算「复利系数」）。
- **DoD（部分达成，2026-11-06）**：rec-avoid-gate §4 锚2 要求的**蒸馏质量度量口径**（漏检率/误蒸馏率）已落架构 §8 已定 E8 锚2，抽检结果（9 gold / 17 claim，两率 0%）与上界结论已落 `docs/evidence/e8-anchor2-sampling-kit.md` §6，该度量（蒸馏质量抽检）已进本闸（见锚2）。**注：§8 的 spike07 复利度量「最终口径」已按设计口径定为 `source=SIMULATION`（等权 0.25×4 + `method_target=10`，依据受控仿真），但升 `CALIBRATED` 仍 open（需 ≥14d 埋点 + ≥3 饱和日 + 外生价值排序），不因本次锚2 抽检而视为达成；两套度量严格区分。锚2 抽检证据弱、待真实长文档复测，不替代 spike 12/13 的 MVP 忠实度闸门 HITL 定案。**

## 关联
- ADR-0004（MCP 接口契约边界）：MCP 须过去模型化测试。
- ADR-0005（rec-avoid 机械闸）：本文件的来源决策。
- 架构 §7：图库主存储 EXCLUDED 行。
- PRD §9：下版本优先级与 MCP 集成决策清单。
