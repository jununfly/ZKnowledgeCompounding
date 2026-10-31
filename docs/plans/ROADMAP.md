<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `roadmap.json` | 最后更新: 2026-10-31 22:53:25

[~][X+] 1. ZKC MVP 上线（P0→P6，4h/周）
    ├── [ ][X+] 1-5. P3 复利变换（最大块，HITL 串行）
    │   ├── [~][X+] 1-5-1. P3.1 蒸馏算子：Ollama 4B + Instructor + LangGraph HITL
    │   ... 该层还有 4 个兄弟，0 个 in_progress ▸
    ... 该层还有 7 个兄弟，0 个 in_progress ▸
<details><summary>阻塞链：6 个节点被阻塞</summary>

- 1-5-2. P3.2 跨源强制算子（≥2 断言 + 单次补全回路，Spike 11） ← e14: 1-5-1. P3.1 蒸馏算子：Ollama 4B + Instructor + LangGraph HITL [~]
- 1-5-3. P3.3 结合算子 RCS 漏斗 + 引用强制 + 级联撤销（Spike 05） ← e15: 1-5-1. P3.1 蒸馏算子：Ollama 4B + Instructor + LangGraph HITL [~]
- 1-5-4. P3.4 context 拓扑装配 + produced_by 级联撤销（Spike 06） ← e16: 1-5-1. P3.1 蒸馏算子：Ollama 4B + Instructor + LangGraph HITL [~]
- 1-5-5. P3.5 忠实度闸门：字面 rubric 预过滤 + 人工兜底（Spike 12/13/13b） ← e17: 1-5-1. P3.1 蒸馏算子：Ollama 4B + Instructor + LangGraph HITL [~]
- 1-6-1. P5.1 复利产出检索/浏览（T6.1，原无 spike 覆盖） ← e19: 1-5-4. P3.4 context 拓扑装配 + produced_by 级联撤销（Spike 06） [ ]
- ... 另有 1 个节点被阻塞未列出

</details>


### 当前施工：1-5-1. P3.1 蒸馏算子：Ollama 4B + Instructor + LangGraph HITL

**决策：**
- Q: 1-5-1 第一切片的范围与依赖策略？ → 切片1 只交付 ZKC 自建蒸馏语义 + provider 无关算子，不引入 Ollama/Instructor/LangGraph 重依赖（沙箱装不上；调研 distill-llm 亦指出蒸馏语义必须自建、候选均不提供）。算子可注入 LLM callable，真实抽取接线前即可单测，不阻断 critical path。校验规则：每条 meta-claim 须引用≥1 来源（去繁非凭空）。Ollama/Instructor/LangGraph 接线 + score 表留作后续切片。

### 下一步可开工（ready 前 3）

- 1-4. P4 调度+复审闭环（S1：先于 P3） [ ]
- 1-4-3. P4.3 budget_per_day 统计估计（删失感知+单调护栏+EMA+oversubscribe） [ ]
- 1-4-5. P4.5 已捕获条目「单程票」规则（ADR-0002，含边界 1/2） [ ]
<!-- ROADMAP_SECTION_END -->
