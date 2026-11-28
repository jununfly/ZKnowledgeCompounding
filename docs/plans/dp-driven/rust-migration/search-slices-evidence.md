# Evidence · search 域两切片 port + 剩余 A 路径/缝定性（tk-50/52/53 前置）

日期：2026-11-28。过程态证据；crate 实现以 `rust/search-structured-rs` / `rust/search-embedding-rs` 为准。

## 结论：2 个干净纯切片已 gate 通过；search 的「生产路径」仍是 A 路径/缝

`src/zkc/search.py::search` + `repository.search*` 经只读分析拆为三层：

| 层 | 表面 | 定性 | 处置 |
|---|---|---|---|
| 结构化过滤排序 | `MemoryNodeRepository.search`（pg.py 的 ILIKE/COALESCE/ORDER BY 同构） | **纯可录**（受控 datetime/casefold 见下） | ✅ **已 port + gate** `search-structured-rs` |
| 余弦 top-k | `MemoryNodeRepository.search_by_embedding`（pg.py 的 `<=>` 同构） | **纯浮点** | ✅ **已 port + gate** `search-embedding-rs` |
| 生产 SQL 路径 | `pg.py::search`/`search_by_embedding`（pgvector `<=>`、ILIKE、row→Node） | **A 路径**（sqlx + pgvector + Node serde） | ⏸ 未做 |
| 外部模型 | `encoder`（nomic 768 / qwen3 4096 调用） | **外部服务缝**（Q5 类） | ⏸ 留 Python/fallback |
| `search()` 编排 | 去重 by id、embedding 追加、degraded 旗标 | 绑上面三者 | ⏸ 未做（非独立可录） |

## 已门化两切片

### search-structured-rs（`filter_sort_nodes`）
- `spikes/spike-30-search-structured` 内建真实 `MemoryNodeRepository` + Nodes，委托原 `search` verbatim。
- `record` **13 case / 1 threw**（三 order、track、ASCII/中文 q 子串、decay_min/max、archived/deleted 可见性、limit、非法 order）。
- **gate pass**：diff **13/13**、clippy 0、size 3.9x（经迭代器式压缩后过）、literals、behavior 全 pass。
- **Q5 划界（明写）**：`created_at` 仅取**规范 UTC-ISO**（字典序==时序、null→`_MIN_DT`）；非 UTC/naive datetime、`.lower()` 的非 ASCII casefold 边（İ/ß）**不在本切片**。

### search-embedding-rs（`search_embedding_knn`）
- `spikes/spike-29-search-embedding`，委托原 `search_by_embedding`（含 `_cos`、column 校验、top-k）。
- `record` **9 case / 1 threw**（排序、零范数→0.0、墓碑/归档可见性、None embedding 跳过、k 截断、embedding/embedding_4096 双列、非法 column）。
- **gate pass**：diff **9/9**、size 3.2x、literals 0。cosine 逐位对齐 memory `sum(x*x …)` 左折叠 + `zip` 截断。

## 仍未消解（诚实定性）

1. **pg.py SQL 生产路径**是 memory 同构实现背后的**真查询**；上面两 port 证明的是**逻辑等价**（PG 同构契约），不是 SQL 本身。要让 `search` 在生产纯 Rust 化，需 **A 路径**：`rust/app` 用 sqlx 直接查 PG（ILIKE/COALESCE/`<=>` pgvector）+ `row→Node` serde（Node 含 UUID/datetime/timedelta/`embedding` 向量 ~20 字段）。这是 metrics_report A 路径（ticket 45）同型的**较大工程**。
2. **encoder** 是外部模型调用（Ollama），属服务缝，A 路径下走 fallback 或专用 Rust HTTP（R16：embedding 严禁安全判定，仅候选召回）。
3. 因此**这两切片并不单独解锁 tk-50/52/53**：MCP handlers / CLI dispatch 前门需要的是**完整 A 路径 search 入口**（含 SQL + encoder + Node 序列化 + 编排），而非 memory 等价逻辑单元。

## 机械验证

| 检查 | structured | embedding |
|---|---|---|
| record | 13 / 1 threw | 9 / 1 threw |
| diff | **13/13** | **9/9** |
| gate | **pass**（size 3.9x） | **pass**（size 3.2x） |

## 风险与边界

- 两切片真相源是 `memory.py`（=pg.py 同构契约），**非 pg SQL 本身**；SQL 侧任何与 memory 不一致处不被本 port 覆盖（应属仓库既有「PG 同构」不变式测试）。
- structured 的 created 排序仅在**规范 UTC-ISO** 下等价；datetime 跨时区/naive 是已知 Q5 缝。
- 未接线进 `rust/app`、未进 `app-cases`、未提交（按 zj checkpoint 约定）。
