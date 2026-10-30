# Spike 13 · 幻觉判定器 human-in-the-loop 接入设计

> 状态：**设计草案（未实现）**。闭环 Spike 12 §6 的 open 项「阈值与策略 / 判定模型选型 / 格式对齐」，
> 并把 `judge.py`（Spike 12 的分解式忠实度判定器）接入两条 MVP 主链路：
> **T3.1 半自动蒸馏管线** 与 **Spike 09 每日复审队列**。
>
> 本设计不写实现代码，只定边界、路由规则、注意力预算占用、schema 增量、LangGraph 接线、
> 验收门槛、风险。实现待 judge 执行模型（见 §1 阻塞项）敲定后开 Spike 13b。

---

## 1. 前置约束 / 阻塞项（必须先解决）

Spike 12 §5 已证：`qwen3.5:4b-mlx` 在本机 16GB 上 **~110–130s/条 + 不产 JSON**，
`instructor` 流式解析卡死 → **4B 不能作本地自动化判定器**。

因此「判定器能不能跑」本身是 open（Spike 12 §6 待决项 ②「判定模型选型」）。本设计把它显式建模为
**可插拔 judge_fn**（同 Spike 12 的 `llm_fn` 注入模式），并规定：

- **judge 是 best-effort 预过滤器，不是硬保证**。人审闸门才是硬保证。
- **若 judge 不可用（无合规模型）→ 安全降级为「全人工」**：所有 claim 直接进 `pending_human`，
  不动用任何 auto-pass。设计不依赖 judge 必须存在。
- MVP 判定器选型三选一（待决策，非本设计结论）：
  1. **更大本地模型**（9B 需 >16GB，与本机冲突）→ 需换卡 / 离盒；
  2. **云端 judge**（Ollama 之外的 API）→ 违背 MVP「本地/离线」前提，仅可作显式 opt-in；
  3. **judge 完全后置**：蒸馏产物先全人工抽检，判定器待模型就位再接。

> ⚠️ 这是 #1 阻塞项。不解决它，本设计的「自动预过滤」价值归零，但**安全降级路径保证 MVP 仍不漏幻觉**。

### 1.1 决策（2026-10-30，方向已定 / 待 Spike 13b-probe 实测确认）

**推荐：本地 7B–9B instruct 模型（4-bit，如 qwen2.5-7b-instruct / qwen3:8b）+ 批量异步预过滤 + 裸 completion + `parse_judgment` 解析（不用 instructor 流式）。云端 judge 仅作 opt-in。**

- **否决 4B 复用**：Spike 12 已证 4B 非纯速度问题而是**不产 JSON**（吐 Markdown 分析文，instructor 流式解析永久卡死）→ 自动化不可用。
- **否决纯人工(D) 作主路径**：judge 的核心价值是**保护注意力**（auto-pass 安全项、只把风险项给人）。纯人工让注意力预算在蒸馏产量下崩溃，违背 ZKC 第一性 → 仅作安全降级。
- **否决云端为默认**：judge 看到全部 claim+来源（比蒸馏更敏感），离盒违反 MVP「本地/离线」前提 → 仅显式 opt-in。
- **为什么 7B–9B 可行**：4-bit 下 7B≈4.5GB / 9B≈5–6GB，16GB 可载；instruct 模型 JSON 合规与分解推理显著强于 4B；延迟用**批量异步**吸收（judge 在蒸馏后后台跑，人从每日队列异步复审，非同步等待）。

**关键实证 gate（Spike 13b 前必过，不能拍脑袋）**：在 16GB 实测 7B/9B 的
① JSON 合规率（裸 completion + `parse_judgment`）、② 单条延迟、③ 危险漏检率（跑 Spike 12 `run_spike12.py`）。
任一不达标 → 降级链：**字面 rubric 预过滤（Spike 10/11 verbatim/overlap/citation_hit 抓明显 unsupported）+ 人工兜底剩余**。

**降级链（确定性，按可用性递减）**：
1. 7B–9B 本地批量 judge（默认，待实测）
2. 字面 rubric 自动预过滤 + 人工兜底
3. 纯人工（judge 完全后置，绝不静默 auto-pass）

### 1.2 实证结果（2026-10-30 · Spike 13b-probe）

**本地 7B–9B 在 16GB 本机被实证否决** → 降级链落到 **第 2 级（字面 rubric + 人工）**。

- `qwen3.5:9b-mlx`（8.9GB）单条判定 **~6min/条**（decode ~0.4 tok/s，运行期系统空闲内存仅 ~90MB，疑似内存压力拖慢）；Ollama 日志交叉印证单次 4m11s / 5m0s 超时 / 2m47s。
- **不吐 JSON**：输出结构化自然语言（`Label: contradicted` / `Evidence: [s1]` / `Overall: contradicted`），`parse_judgment` 报 `no-json-block-in-output`。
- **能力本身成立**：g6 矛盾被正确识别（claim「客户端」vs 来源「服务端」→ contradicted）且引用正确来源 `[s1]`——与 Spike 12 的 4B 同款（能力有、卡速度+格式）。
- 结论：速度属**硬件绑定**，本机不解决则本地 LLM judge 不可用；格式可修（定制 parser / 强制 JSON 模式）但救不了速度。
- **MVP 忠实度闸门 = human-in-the-loop（§3/§4）+ 字面 rubric 预过滤**（Spike 10/11 verbatim/overlap/citation_hit，快且可自动化）。自动 LLM 预过滤层在本机暂时缺席，直至更快 judge（更快硬件 / 离盒 / 云端 opt-in）就位——届时 `judge.py` + `run_spike12.py` 零改动可启用（能力已验证）。

---

## 2. 接入点总览

```
T3.1 蒸馏管线 (LangGraph)
  distill → 结构化产物(claims + evidence_refs)
      │
      ├─[judge_fn 可用]→ judge_each_claim → Judgment(atomic_facts + overall)
      │                        │
      │                  apply_routing（§3 路由规则）
      │                        │
      │            ┌───────────┴───────────┐
      │      forced(矛盾/空分解)        非 forced
      │            │                          │
      │      interrupt(human)           auto_pass / sampled
      │            │                          │
      └─[judge 不可用]─→ 全部 claim → pending_human
                                     │
                           Spikes 09 每日复审队列 (UI)
                                     │
                          human 看到 claim+来源+judge 分解 → confirm/reject/edit
                                     │
                              resume → 写 faithfulness_status + 落校准语料
```

两条链路共享同一个 `faithfulness_status` 字段与同一套人审 UI；区别仅在于 claim 的**来源**
（新蒸馏产物 vs 每日队列里待复审的存量）。

---

## 3. 判定路由规则（核心）

以 `judge.py` 的 `Judgment`（逐条 `AtomicFact.verdict ∈ {supported, unsupported, contradicted}`）
为输入，确定性推导动作（**不信任模型自总结的 overall**，用 `aggregate()` 重算）：

| 判定输出 | 路由动作 | 占比 | 注意力占用 |
|---|---|---|---|
| `atomic_facts` 为空（模型拆不出事实 = 高不确定） | **强制人审** `forced_empty_atomic` | 100% | 是（安全关键） |
| 任一 `contradicted` | **强制人审** `forced_contradicted` | 100% | 是（安全关键） |
| 有 `unsupported` 但无 `contradicted` | **抽检** `sampled_unsupported`，比例 `R_unsupported`（默认 0.3） | 抽样 | 是（受预算封顶，§4） |
| 全 `supported` | **auto_pass** `auto_supported`，并入周期抽检池 `periodic_audit`（默认 0.05） | 0%（仅审计抽样） | 审计抽样占用预算 |

规则要点：
- **空分解 / 矛盾 永远强制人审，绝不 auto-pass**——这是防幻觉的最后一道硬闸。
- `unsupported` 不全量人审，靠抽样 + 预算封顶控制注意力成本；未被抽中的标 `sampled_pending`
  记录，后续可被审计或用户主动翻查。
- `auto_supported` 仍进 `periodic_audit` 池：因「全 supported」也可能错（Spike 12 危险漏检率视角），
  用 5% 审计估计真实危险漏检率（衔接 Spike 12 §6 待决项 ①）。

---

## 4. 注意力预算占用估算（防压垮用户）

ZKC 第一性前提：**注意力是稀缺资源**。faithfulness 人审是**第二条需求流**，与 Spike 09 的
decay 复审队列竞争同一个每日注意力预算 `B = budget_per_day`（容量，删失观测，见 Spike 09 §6.5.1）。

设计原则：**faithfulness 抽样永不饿死 decay 复审（生存相关、更高优先）**。

- 设 `F_cap = 0.2`（默认）：faithfulness 人审占用 ≤ 20% × 当日剩余预算。
- 当日 faithfulness 需求 `D_f = 强制项(矛盾+空分解) + 抽检(unsupported) + 审计(supported)`。
  - **强制项无预算上限**（安全关键，必须服务）。
  - `抽检 + 审计` 受 `F_cap·B_remaining` 封顶。
- **自适应降级**：若 `抽检+审计 > 封顶`，先降 `R_unsupported`（可降到 0），最后手段是把低优先
  claim 的复审**顺延到次日队列**（强制项永不顺延）。
- 此耦合是安全的：最坏情况 faithfulness 占 ≤20% 注意力，且安全关键项始终被服务。

> 注：`budget_per_day` 本身是删失/自指估计（Spike 09 已证），故 `R_unsupported` / `F_cap`
> 初始为占位，需真实 UI 埋点后校准（与 Spike 09 同源约束：需真实每日队列 UI 每天写埋点）。

---

## 5. 数据模型增量（扩展 Spike 01 claim 表）

在 Spike 01 的 `claim` 表（已有 `evidence_refs` 强制）上新增：

| 字段 | 类型 | 说明 |
|---|---|---|
| `faithfulness_status` | enum | `auto_passed` / `pending_human` / `human_confirmed` / `human_rejected` / `sampled_pending` |
| `judge_raw` | jsonb | `Judgment`（atomic_facts + overall + reason），可空（judge 不可用时） |
| `judge_model` | text | 判定器标识（可复现 / 离盒追溯） |
| `faithfulness_route` | text | `forced_contradicted` / `forced_empty_atomic` / `sampled_unsupported` / `periodic_audit` / `auto_supported` / `human_only`（judge 不可用） |
| `human_verdict` | enum(confirm\|reject\|edit) | 可空 |
| `human_verdict_at` | timestamptz | 可空 |

索引：`faithfulness_status`、`faithfulness_route`、`human_verdict_at`。

---

## 6. LangGraph 接线（复用 Spike 10/11 蒸馏研究结论）

- **distill 节点**：产出结构化产物（claims + `evidence_refs`）——既有 T3.1。
- **judge_each_claim 节点**：对每个 claim 调 `judge_fn` → `Judgment`（新节点）。
- **apply_routing 节点/路由**：按 §3 规则分流；命中强制项 → `interrupt(human_adjudication)`。
- **human interrupt/resume**（LangGraph + Postgres checkpoint，落在 substrate 同库）：
  人看到 claim + 引用来源 + judge 分解 + 逐条 verdict → `confirm` / `reject` / `edit`。
  resume 后写最终 `faithfulness_status`，并把「judge 输出 vs 人判」追加进**校准语料**。
- **终端**：claim 落库，带 `faithfulness_status`。

> 判定器通过 `judge_fn` 注入，与 Spike 12 `run_spike12.py` 的 `llm_fn` 同源——换合规模型零改动。

---

## 7. 校准语料自举（衔接 Spike 12 §6 待决项 ④ golden 规模小）

每个 `human_verdict` 都随 judge 的原子分解一并记录：
- `confirm` = judge 判对；`reject`/`edit` = judge 判错（即真实危险漏检 / 误杀样本）。

→ 生产流量**自然生长出标注语料**，无需单独标注工程即可把 golden 从 13 例扩到百/千级
（Spike 12 §6 待决项 ④ 的可行解法）。这是「human-in-the-loop 顺带养数据」的复利结构。

---

## 8. 验收门槛（仿 Spike 09 闸门风格）

1. **100%** 矛盾 + 空分解 claim 必达人审，绝不 auto-pass。 ← 安全
2. `unsupported` 按 `R_unsupported` 抽检，且占用 ≤ `F_cap·B`。 ← 预算
3. 任何 claim 不得在无「记录的人判」或「带 `judge_raw` 的显式 auto-pass」下离开 `pending`。 ← 无静默放行
4. **每个**人判都落入校准语料（judge vs 人）。 ← 衔接 ③
5. 当日 faithfulness 需求 > 封顶时，`R_unsupported` 自动降；强制项永不丢弃。 ← 安全降级

---

## 9. 风险 / 仍 open

- **🔴 阻塞：judge 执行模型未定**（Spike 12 §6 ②）。不解决则 auto-pre-filter 归零，
  但 §1 安全降级保证 MVP 不漏幻觉。决策：本地大模型 / 云端 opt-in / 后置。
- **预算耦合**：蒸馏爆发期仍可能挤占 decay 复审；靠 `F_cap`+顺延缓解，但 `budget_per_day`
  本身删失/自指（Spike 09），需真实埋点校准 `R_unsupported`/`F_cap` 初值。
- **审计 vs 预算张力**：`auto_supported` 的 5% 审计也吃预算，与 `F_cap` 竞争，需统一进预算总账。
- **存量重判**：来源后续被推翻时，是否对已入库 claim 触发重判——MVP v1 范围外，未来项。
- **双轨差异**：静态(事实) claim 与动态(存活) claim 的 faithfulness 检查在创建时同源；
  动态条目衰减快，重判触发策略未来再议（不阻塞 MVP）。

---

## 10. 下一步

1. **决策 judge 执行模型**（§1 阻塞项）→ 单独决策点或 Spike 13b。
2. judge 模型敲定后，开 **Spike 13b 实现**：judge 节点 + 路由 + LangGraph interrupt/resume
   + claim 表增量 + 每日队列 UI 的人审卡片。
3. 借生产人判流量扩 golden（Spike 12 §6 ④ / 本设计 §7），回填真实危险漏检率（Spike 12 §6 ①）。
