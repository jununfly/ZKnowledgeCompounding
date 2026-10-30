# Spike 12 — 幻觉判定（LLM-as-judge 忠实度闸门）

> 状态：**进行中。judge 机制 + golden 数据集 + stub 单测已就位（tests passed）；真实 4B 评测见 §5，环境若阻塞则诚实标注 open。**
> 目标：关闭 Spike 10/11 反复挂起的 open 项——**字面 rubric 抓不到内容幻觉**，并回答部署问题：MVP 的 4B 模型能否作为自动化忠实度 gate，还是必须 human-in-loop / 更大判定模型。

## 1. 背景：Spike 10/11 留下的 blind spot

Spike 10 的 `quality_rubric.py` 能量化四类失败：

- `verbatim_rate` / `overlap`：字面复述 / 拼接复述（抓「抄」）。
- `cross_source_rate`：跨源综合是否达标（抓「不综合」）。
- `citation_hit`：引用的 source id 是否是最相似来源（弱信号，抓「错填 id」）。

但它在 docstring 与 README §6/§9 明确记账了一个**盲点**：

> 忠实度 / 幻觉**无法字面测**。一条抽象 claim 本就该用来源里没有的词，「好抽象」与「无据编造」的字面重叠都低——rubric 分不清二者。→ **需 LLM judge 或人工**。

Spike 11 §6 再次确认：跨源 claim 是否真由所指来源支撑，仍需 LLM judge 或人工。

**本 spike 的判定对象**：一条 claim 即便 `citation_hit` 满分（引用的 id 都合法、且字面相似），仍可能**内容未被来源支撑**（在合法 id 的来源里根本没说过这句话 = 内容幻觉）。这正是字面指标跨不过的鸿沟，也是 ZKC 复利链最危险的失效模式——一个被蒸馏成「元认知 claim」的编造事实，会污染整条知识链且难以回溯。

## 2. 研究问题（本 spike 要回答）

1. **机制可行吗**：能否用「分解→逐条核验→推导」的 LLM-as-judge，稳定判定 claim 是否忠实于来源？
2. **部署可行吗（核心）**：MVP 判定模型 `qwen3.5:4b-mlx` 能否可靠当自动化忠实度 **gate**？还是 4B 判定器自身会「过度信任 / 幻觉式误判」，必须 human-in-loop 或上更大判定模型？
3. **最危险的失败模式**：幻觉被判定器放过（truth=unsupported/contradicted 却判 supported）——即**危险漏检率**。这是决定是否自动化的唯一关键指标。

## 3. 设计：分解式忠实度判定（单次结构化调用）

代码见 `judge.py`。关键立场：**不信任模型的自总结**，而是强制它先把 claim 拆成原子事实、逐条标注，再由我们确定性地推导 overall。

### 3.1 判定合同（可注入，单测不依赖模型）

```
judge_claim(llm_fn, claim, sources) -> Judgment
  llm_fn(prompt, system) -> Judgment(atomic_facts[], overall, reason)
```

- **输入**：claim 文本 + 全部来源（full-context，降低「真理由别的来源支撑却被误判 unsupported」的假阳性；抓内容幻觉才是目的，citation 对错由 Spike 11 的 `enforce_citations` 管）。
- **单调用结构输出**：
  - `atomic_facts[]`：每条原子事实 + `verdict` ∈ {supported, unsupported, contradicted} + `evidence`（来源 id 或「无」）。
  - `overall`：模型自报（**仅当 atomic_facts 为空时**才回退采用）。
- **确定性推导** `aggregate(facts)`：
  - 任一 contradicted → `contradicted`；
  - 混有 unsupported → 有 supported 则 `partial`，否则 `unsupported`；
  - 全 supported → `supported`。
- **重试**：atomic_facts 为空时重试一次（小模型偶发不产结构），仍空则信任 `overall`。

### 3.2 为什么是「分解 + 推导」而非「直接要 overall」

Spike 10/11 已实证 4B 在结构化生成上对硬约束可跟但偶尔摆烂。直接问「这 claim 忠实吗？」会让 4B 用一句话敷衍、且最容易犯「过度信任」（默认 yes）。强制逐条原子事实标注，把「整体判断」降维成多个更简单的「这条事实在来源里吗」子问题，既提高可判定性，也让危险漏检可追溯（哪条原子事实被错标）。

### 3.3 golden 标注数据集（评估判定的前提）

评估一个 judge 必须有**带真值的样本**。数据集在 `judge.py::GOLDEN`，基于 Spike 10 冻结语料（5 条互关联中文动态条目）构造，分三类、共 13 例：

- **supported（5）**：claim 内容确由来源支撑。
- **contradicted（5）**：claim 说的事实与来源**明确冲突**（如「安全评审要求权限判断在客户端」vs 来源说服务端；「返工三周」vs 来源说两周；「台账二分之一清理」vs 三分之一；「复盘五个项目」vs 三个；「内存泄漏瓶颈」vs 连接池）。
- **partial（3）**：claim 混合一条 supported + 一条 unsupported（如「安全评审打回客户端鉴权 ✓，并要求所有代码评审必须在服务端 ✗」）。

每例带 `decomp`（人工标注的原子事实分解），`truth` 由 `aggregate(decomp)` **确定性推导**，保证标签自洽、无人工口径漂移。

### 3.4 评估口径

`evaluate(llm_fn)` 对 GOLDEN 跑判定，产出：

- 混淆矩阵（supported / partial / unsupported / contradicted 四类的预测 vs 真值）；
- `accuracy`；
- **`dangerous_false_negative_rate`**：真值在 {unsupported, contradicted} 却被判 `supported` 的比例——**唯一决定是否自动化的指标**；
- **`hallucination_catch_rate`**：真值 ≠ `supported`（partial/unsupported/contradicted）被判 ≠ `supported` 的比例。

## 4. 单测证据（stub 注入，不依赖模型；tests passed）

`test_judge.py` 用 stub 注入 `llm_fn`，验证机制本身正确：

| 测试 | 验证点 |
|---|---|
| `PromptStructureTests` | 提示含全部来源 id、claim 文本、分解/判定任务关键词 |
| `AggregateTests` | aggregate 在 4 种原子事实组合下推导正确 |
| `OracleTests` | oracle stub（返回真值分解）→ 准确率 100%、危险漏检 0 |
| `AlwaysSupportedTests` | 永远判 supported 的坏 judge → 危险漏检率 = 全部非 supported 样本比例（证明评估能抓出坏判定器） |
| `EmptyAtomicFallbackTests` | 空 atomic_facts → 回退信任 overall；重试一次后填充则走推导 |
| `ArtifactTests` | judge_artifact 对含 supported+contradicted 的 artifact 聚合 faithful_rate 正确 |

机制层面已证明：判定与评估流水线正确，能在「完美判定器」下满分、在「烂判定器」下暴露危险漏检。

## 5. 真实模型评测（qwen3.5:4b-mlx）—— 结论：本机不可用，需 human-in-loop / 更快判定模型

`run_spike12.py` 已接 Ollama + 裸 OpenAI 客户端（**不用 instructor**：`instructor.Mode.JSON` 在该模型经 Ollama 的推理流上会卡死）+ Spike 10 冻结的 `resilient_create` 重试 + 防御式 `parse_judgment`。但实测在本机（16GB）遭遇两个**操作性阻塞**，真实评测无法在此硬件完成：

### 5.1 阻塞一：延迟 ~110–130s / 条
单条分解式判定调用 `qwen3.5:4b-mlx` 经 Ollama(MLX) 耗时 110–130s（冷热均如此）。根因链路：**`HTTP_PROXY` 指向本机 WorkBuddy 代理**，`localhost:11434` 需 `NO_PROXY=localhost,127.0.0.1` 绕过，否则 httpx 把本地 Ollama 也走代理导致无限挂起——该坑已固化进 `run_spike12.py`。即便绕过代理，4B 对该分解任务仍 ~2min/条：作为交互式或批量自动闸门都不可接受（13 条 × 2min ≈ 26min / 样本）。

### 5.2 阻塞二：4B 不输出 JSON，instructor 卡死
即便指令「只输出 JSON」，4B 仍返回 Markdown 分析文（含「整体结论 / 理由」段落），不产出结构化 JSON。`instructor.Mode.JSON` 的流式解析在推理流上永久等待闭合 JSON → 卡死。已改用裸调用 + 正则抽取首段 `{...}` + pydantic 校验的 `parse_judgment`；但 4B 不产 JSON → 抽取必失败 → 全部回退判 `unsupported`，自动化指标失真，故本机不跑全量。

### 5.3 正向信号：4B 的判定能力本身是对的
唯一实际跑通的一条（g7「返工三周」vs 来源「两周」）中，4B 准确识别出**数值冲突**并判 `contradicted`，理由正确。说明**能力有、格式与速度不达标**——方法论成立，挡在「运算操作性」而非「概念」。

### 5.4 部署结论（回答 §2 研究问题 2 / 3）
- **4B 在本硬件上不能作为自动化忠实度 gate**：~2min/条延迟 + 非 JSON 合规。
- 字面 rubric（Spike 10/11 的 verbatim/overlap/citation_hit）仍是**唯一可自动化**的信号；内容幻觉检测在拿到**更快 / 合规的判定模型**前，必须走 **human-in-the-loop**（MVP 蒸馏产物人工抽检）或**离盒判定**（更强机器 / 云端）。
- **判定器本身已就绪**：`judge.py` + golden + `run_spike12.py` 在换上合规判定模型后**零改动可跑**，直接出混淆矩阵与危险漏检率——这是本 spike 的可复用产出。

## 6. 仍 open（诚实标注）

- **真实危险漏检率 / 混淆矩阵**：需更快或 JSON 合规的判定模型实跑 `run_spike12.py`（本机 4B 因 §5.1/§5.2 阻塞，指标失真不可用）。
- **判定模型选型**：MVP 判定器若上更大模型（9B 在 16GB 不可迭代）→ 需权衡延迟/成本/离盒；或评估云端 / 更强本地卡。
- **阈值与策略**：gate 的「放过」策略（auto-pass / 抽检 / 全人工）及危险漏检容忍度，待真实分布定。
- **golden 集规模小（13 例）**，需更大人工标注样本校准阈值与置信区间。
- **格式对齐**：若坚持用 4B 类小模型，需研究 TOOLS 模式 / 更强 JSON 提示 / 离盒，先解决 §5.2 的合规问题。
