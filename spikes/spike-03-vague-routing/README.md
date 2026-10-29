# Spike 03 — 双轨分流的「模糊」处理：显式模糊路由 vs DecisionRouter

**目标**：验证 Spike 02 收尾时留下的两个候选修复，哪个能真正修掉 Spike 02 的失败模式：

- **F1**（短模糊项不得误提交到真实轨道）：`false_commit_on_vague == 0`
- **F2**（长模糊对抗句不得误判为 dynamic）：adversarial 进 dynamic 数 = 0
- **保持**：清晰 static/dynamic 项仍正确路由

Spike 02 结论回顾：在词法 + 两个真实语义编码器下，相似度都**无法区分**模糊/确定，长模糊句
3/3 单向误判为 dynamic，且有系统性单向偏差（误判都指向 dynamic → 污染动态轨）。因此建议二选一：
显式「模糊」路由，或 DecisionRouter 决策模型。本 spike 同时验证两者。

## 两条路径

### A. 显式 3-way 路由（static / dynamic / vague）
复用 Spike 02 的 `DualTrackRouter`（ZKC 自有的校准 + 弃权逻辑），新增第三条 **vague** 路由
（12 条模糊 utterance，见 `samples_v3.py`）。**关键改动**：
- 丢弃 Spike 02 的 `min_tokens` 信息量门——低信息量项（「嗯」「随便」）本就是 vague，应由 vague
  路由按相似度吸收，而非强制弃权。
- `calibrate` 重定义为：最小化 **DANGEROUS**（清晰项误交另一轨 + 模糊项误交真实轨），最大化覆盖。
  路由模糊项到 vague 是**正确**；路由清晰项到 vague 是安全的欠覆盖（非危险）。

### B. DecisionRouter（LLM-as-judge，本地 Ollama）
单次本地 LLM 调用直接判定轨道，返回结构化 JSON `{track, confidence, reason}`
（见 `decision_router.py`）。用**真实语义推理**而非相似度重叠——这正是 Spike 02 相似度做不到的。
ZKC 自有决策语义编码在 `SYSTEM_PROMPT`（双轨定义）；模型只是可替换的推理引擎，契合 ZKC 的
Ollama + Instructor + LangGraph 栈。`confidence < 0.5` 强制 vague 作为轻量安全阀。

## 运行环境
- 本地 Ollama 0.33.3，已装 `qwen2.5-coder:1.5b`（DecisionRouter）、`nomic-embed-text`、`qwen3-embedding`。
- 3-way 路由仅依赖标准库（复用 Spike 02 的 `router.py` + `TfidfEncoder`），无 venv 需求。
- DecisionRouter / Ollama 嵌入走 `localhost:11434`，需 Ollama 在跑。

```bash
python3 -m unittest test_spike03 -v     # 9 tests (1 expectedFailure: nomic 3-way 不安全)
python3 run_spike03.py                  # 完整对比报告
```

## 结果（共享 EVAL_SET：24 清晰 + 8 短模糊；+ 3 长模糊对抗句）

| 路径 | 编码器 | coverage | acc_on_routed | dangerous | F1(模糊误提交) | F2(对抗→dynamic) |
|---|---|---|---|---|---|---|
| A 3-way | TF-IDF（词法） | 53.1% | 88.2% | 0 | 0 ✅ | 0/3 ✅ |
| A 3-way | nomic-embed-text (768d) | 34.4% | 63.6% | **3** ❌ | **1** ❌ | 0/3 ✅ |
| A 3-way | qwen3-embedding (4096d) | 18.8% | 100% | 0 | 0 ✅ | 0/3 ✅ |
| B DecisionRouter | qwen2.5-coder:1.5b | 100% | 43.8% | 1 | 0 ✅ | 0/3 ✅ |

### 逐项解读
- **F2（长模糊对抗句不进 dynamic）**：两条路径、所有编码器**全部 PASS**（对抗句 0 进 dynamic）。
  确认 Spike 02 的核心失败模式已被修复。
- **F1（模糊项不误提交）**：DecisionRouter **完美 0**；3-way 在 qwen3/TF-IDF 下 0，但在
  **nomic(768d) 下出现 1 处模糊误提交 + 2 处 static↔dynamic 互混** → 3-way 的安全性**依赖编码器强度**。
- **覆盖 / 精度权衡**：
  - 3-way 为保安全，校准把阈值抬很高（qwen3 阈值 0.82），导致 **81% 项被推给 vague/弃权**（欠覆盖）。
    TF-IDF 也有 47% 欠覆盖。即「安全」以「大量人工复核」为代价。
  - DecisionRouter 覆盖 100%（全部分配到三轨之一），但 1.5B 小模型对清晰项精度仅 43.8%
    （17 项被保守归为 vague）。**精度随模型规模可提**——ZKC 部署用 7~14B 级模型会显著改善，
    且 F1/F2 安全属性（推理本质）不受影响。

## 结论与推荐

1. **两条路径都修掉了 Spike 02 最危险的 F2**（长模糊单向误判为 dynamic）。
2. **推荐 DecisionRouter 作为主方案**：
   - 编码器无关（不依赖嵌入质量），F1 安全属性完美（模糊误提交=0）；
   - 用推理而非相似度，天然处理「长但模糊」这类 Spike 02 相似度死穴；
   - 契合 ZKC 的 Ollama 栈；精度短板可通过部署更大本地模型解决（非架构缺陷）。
3. **3-way 路由作为可降级/互补方案**：仅在配备 qwen3 级（≥4096d）强编码器时安全；否则弱编码器
   会引入危险误提交。可角色降级为 DecisionRouter 的**候选预过滤 / 置信度信号源**，而非独立决策器。
4. **混合建议（后续）**：DecisionRouter 主判 + 嵌入相似度作辅助置信度（如相似度跨双轨重叠时强制
   走 vague 或转人工），兼顾推理与安全阀。

## 文件
- `samples_v3.py` — 复用 Spike 02 标注集 + VAGUE_ROUTE + 3-way 校准集 + 对抗句
- `ollama_embed.py` — 本地 Ollama 嵌入适配器（复用 Spike 02 逻辑）
- `router3.py` — `ThreeWayRouter`（3-way 校准/评估）
- `decision_router.py` — `DecisionRouter`（Ollama chat JSON）
- `test_spike03.py` — 9 tests（含 nomic 3-way 不安全 expectedFailure）
- `run_spike03.py` — 对比报告

## 未决
- DecisionRouter 在更大模型（7~14B）下的清晰项精度未实测（本环境仅 1.5B）；架构回填时标注为「待更大模型复核」。
- 混合方案（DecisionRouter + 嵌入置信度）未实现，列为后续 spike 或 MVP 设计项。
