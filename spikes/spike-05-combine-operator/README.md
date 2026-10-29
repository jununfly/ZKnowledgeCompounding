# Spike 05 · 结合算子（RCS 漏斗 + 双层合并 + 引用强制，落 PG）

**目标**（架构 §6.2 / §9-5）：验证结合算子作为**显式程序**跑通——PaperQA2 的 RCS 漏斗
（逐源条件化摘要 → 重排打分 → 来源上限 → 单次生成）+ LightRAG 双层（local/global）+
Instructor 约束产出**带引用的结构化建模产物**，复用 spike-04 的 `transform`/`produced_by`
级联撤销机制。

**结果**：**9 tests passed（OK）** + 端到端演示跑通。管线机制全部验证；**1.5B 语义综合
不达标**（见「人工评估结论」）——这正是 spike 要量化的。

## 文件

| 文件 | 作用 |
|---|---|
| `schema_ext.sql` | `modeling_artifact` 表：`body jsonb`（结构化产物）+ `evidence_refs uuid[] NOT NULL` + `produced_by` 级联 + `revises`/`tx_to`（append-only 版本化） |
| `models.py` | `ModelingArtifact`（Pydantic）：title/kind/claims(带 evidence_ids)/local/global/methodology_steps；local/global 可空（空层=质量信号） |
| `combine_op.py` | 漏斗 + 双层 + `enforce_citations`（幻觉引用剔除、零引用断言删除、全失效抛错）+ `CombineOperator`（LLM 函数可注入） |
| `store.py` | `persist_combine`（transform+artifact+链式反向连接）、`revise_artifact`（append-only 修订）、`discard_transform`（级联撤销） |
| `test_spike05.py` | 9 tests：漏斗 2 / 引用强制 3 / 持久化与撤销 3 / 真 Ollama e2e 1 |
| `run_spike05.py` | 端到端演示：打印漏斗报告与完整产物，供人工评估 |

## 测试矩阵（9 passed）

- **RCS 漏斗**：逐源一条**面向问题的**条件化摘要；6 源按分取前 4、低分源进 dropped 报告。
- **引用强制**：幻觉引用被剔除且产物 `evidence_refs` 重算；零有效引用的断言被删；全失效 → `ValueError`（**无引用的建模产物不允许存在**）。
- **持久化**：`produced_by` 溯源 + 跨源链式反向连接（N-1 条）；级联撤销删光产物与边、**人工产物存活**；产物修订 append-only（历史行逐字段不变）。
- **真 Ollama e2e**：4-5 源 → 漏斗 → 引用全有效的产物 → 落库。

## 人工评估结论（§9 验收问题：「是否真形成方法论而非摘要堆砌？」）

**管线机制 = 全部通过；1.5B 语义综合 = 不通过。**

qwen2.5-coder:1.5b 产出的「建模产物」实际是**带引用的摘要堆砌**：
- claims 一源一条、每条只引单源（无跨源断言）；
- `global` 层逐句复述 claims；`methodology_steps` 是同一批句子换序；
- `local` 层被错误填成来源 id；
- 出现语义错误（「写放大问题可通过 MVCC 一致性读解决」）。
- 另观察：模型稳定漏填 required 的 `local` 字段 → Instructor 重试 4 次仍不补（重试时
  prompt 线性膨胀），已改为**可空 + 空层上报**而非让产物作废。

**结论**：结合算子的**结构约束、引用强制、溯源与撤销机制已验证可复用**；「真正形成方法
论」的语义质量与 spike-04 蒸馏同源——**模型规模问题，非架构问题**，走 provider seam 切
强模型（≥7B 本地或云端）。架构对策不变，无需推翻选型。

## 环境说明

- 复用 spike-04 venv（`../spike-04-distill-loop/.venv/bin/python`，依赖完全一致）与同一
  PG（`zkc-spike-pg`，端口 55433）。
- 新增坑：本地模块命名 `operator.py` 会**遮蔽标准库 `operator`**（psycopg 等库会
  `import operator`）→ 已改名 `combine_op.py`。

## 未决（留给后续）

- 结合质量评估需强模型复测（同 spike-04 蒸馏质量项）。
- `context` 表（自闭环 ↔ 更高维）的拓扑装配未进入本 spike；`modeling_artifact` 可作其成员。
- RCS 重排目前逐源独立打分；listwise 重排（跨源比较）待强模型验证。
