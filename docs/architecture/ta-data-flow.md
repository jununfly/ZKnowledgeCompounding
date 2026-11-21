---
doc-kind: architecture-flow
authority: primary
authority-id: architecture.flow.data-flow
---

## Question

一条知识从被摄入到可被检索，经过哪些环节、每个环节改变什么状态、失败时如何退出？本页是这条主链路及其旁路的唯一 durable owner。

## Scope

- [implemented] 覆盖三条入口（CLI `zkc`、MCP transport、Web）共用的摄入→分流→落库→衰减→到期决策→复利变换→检索主链路。
- [implemented] 覆盖两条旁路：interval 三层调度（L1/L2/L3）与复审终局分支（verdict v2）。
- [out of scope] 各状态位的物理结构归 Data Storage 页；阈值取值理由归[架构本体·调度与预算（原 §6.5）](../evidence/architecture-v1.2-source-2026-11-19.md) 与 ADR；一次性取证读数归 `docs/evidence/`（不作 proof）。本页只讲「状态如何随时间迁移、谁触发谁」。

## Boundaries

- [implemented] 主链路的唯一写入闸是 `ingest_with_routing`：任何来源（MCP `capture` / Web `capture_note`）都必须过它分流，绕过它直接写 node 是禁止的（MCP `CaptureProfile` 默认只写 node，且强制走此闸）。
- [implemented] transport（`src/zkc/transport/`）是零领域语义的 JSON-RPC 2.0 协议层，只做帧编解码与分发；领域逻辑在 `mcp/handlers.py`。契约 `contract_v1.json` 白名单五个 tool + blacklist，防换名调用。
- [implemented] LLM 调用全部走原生 Ollama API（`/api/chat` + `format:json`；`/api/embed`），不经 `/v1`、`response_format`、Instructor/LangGraph。
- [inference] 旁路 A（interval）与终局分支（verdict v2）共享 `node.review_interval` 字段但语义不同：前者是调度参数，后者在 changed/stale-cover 时会把该字段**重置回 L1 基线**。这是两套机制的耦合点，也是易错点。

## Trigger

- [implemented] **摄入**：`zkc capture` / MCP `zkc_capture` / Web `capture_note` 收到原始文本或文档。
- [implemented] **衰减到期**：调度查询 `list_due_for_review` 命中 `decay_score >= SURFACE_THRESHOLD(0.6)` 且 `last_reviewed_at + review_interval <= as_of` 的动态节点；或 `zkc daily` 的收口。
- [implemented] **人工复审**：`zkc decide --id --verdict` 对 review_queue 中的 due 条目做终局裁决。
- [implemented] **检索**：MCP `zkc_query` / `/browse` 收到查询串。

## Sequence

**主链路（6 步）：**

1. [implemented] **摄入**：`capture_documents` / `capture_note` → `ingest_with_routing`（`ingest.py`）。
2. [implemented] **双轨分流**：`routing.route_text` → `DecisionRouter.predict`（信号 A：`OllamaClient.chat_json` → `/api/chat`，`temperature=0`，失败返回 None 走离线兜底）+ `LexicalRouter.predict`（信号 B：TF-IDF，embedding-free，语料 `data/lexical_corpus.json`）。产出 `track ∈ {static, dynamic, unrouted}`。
3. [implemented] **落库**：`store.nodes.save` 写双时态版本链 → 初始化 decay → 更新 lexical corpus；`vague/unrouted` 入队 `review_queue`（`action='classify'`）等人工标注。
4. [implemented] **衰减到期决策**：仅动态轨。`refresh_decay` → `store.nodes.update_decay` → `list_due_for_review` → `expiry.route_expired`：三类终局 `captured→ARCHIVE`（或 28d 观察期）、`contextual→DISTILL`、`orphan→ABSTAIN`。`decay < ROT_THRESHOLD(0.9)` 不可路由。
5. [implemented] **复利变换**：`distill.distill_node` → `_build_prompt` + `DISTILL_SCHEMA_HINT` → `llm.ollama_chat`（`/api/chat` + `format:json` + `think:false` + `num_ctx=8192` + `num_predict=1024`）→ `validate_result`（每条 claim ≥1 引用）→ `store.claims.save` + `store.scores.record(LLMCallScore)`（成功失败都记）→ `mark_reviewed` → 进入 captured 观察期。结合/装配算子产物走 `ArtifactRepository.save` + `store.assemble_context`。
6. [implemented] **检索输出**：`search.search` → 结构化筛选（`store.nodes.search`）+ 向量候选（`encoder([q])` → `/api/embed` → `store.nodes.search_by_embedding`，默认 `embedding_4096` 列）→ `/browse` 脱敏（不返 content/statement）。

**旁路 A — interval 三层（全部在 `scheduling.py`）：**

- [implemented] L1 基线：`baseline_for_signals` → `assign_baselines` 写 `baseline_interval` 与 `review_interval` 同值（`set_baseline_interval`）。
- [implemented] L2 预算归一：`fit_budget_rows` → `fit_budget` → `set_interval` + `audit_interval(kind='budget')` + `record_transform('budget_fit')`。预算估计 `estimate_budget_from`（删失感知 p25）→ `update_budget_from`（EMA + 护栏 + oversubscribe×1.5）。
- [implemented] L3 AIMD：`classify_review` + `adapt_interval_math`（`AIMD_UP=1.5` / `AIMD_DOWN=0.7`）→ `adapt_interval` + `audit_interval(kind='feedback')`；触底 `floor_hit` → `archive`。标注率闸门 `<70%` 时 L3 停机；`MIN_INTERVAL_DAYS=0.25`。`interval_source='human'` 全程豁免自动改写。
- [implemented] **verdict v2 后**：`decide_review` 不再调用 `adapt_interval`（外生锚归零）。

**终局分支 — verdict v2（`web/review.py` 的 `decide_review`）：**

- [implemented] 五值互异 reason：`still_valid / changed / stale_overwrite / stale_purged / browsed_without_label`。
- [implemented] `browse` → `mark_reviewed`，留回路；`still_valid` → `mark_reviewed`，interval 不变，留回路。
- [implemented] `changed`（content 必填）→ `_write_content_version`（写双时态新版本，不触发 distill）+ `_reset_to_l1_baseline`（interval 重置回基线）+ `mark_reviewed`，**留回路**。
- [implemented] `stale/cover`（branch+content 必填）→ 同 changed（reason=`stale_overwrite`）；`stale/purge`（branch 必填）→ `store.nodes.archive`，**退出回路**（reason=`stale_purged`）。
- [implemented] 末尾统一累加今日 `AttentionObservation`（`completed++`；非 browse 才 `labeled_completed++`）。

## State and effects

- [implemented] **node**：track 由 unrouted→static/dynamic；decay_score 被 `update_decay` 刷新；changed/stale-cover 触发新版本 + baseline 重置；stale-purge 触发 `archived_at`（退 due）。
- [implemented] **review_queue**：unrouted 入 `classify`；到期条目被 `decide` resolve；注入标记检测（`injection.py`）拦截四类写 + 提示注入话术。
- [implemented] **claim / modeling_artifact / context**：DISTILL 分支产出 claim；结合算子产出 artifact + context（`assemble_context` / `revert_assembly`）。
- [implemented] **attention_observation**：每次复审累加日观测，是 `labeling_rate` 与预算闸门的唯一外生锚。
- [implemented] **llm_call_score / interval_adjustment / node_history**：分别记录 LLM 调用、区间调整审计、双时态版本快照。
- [inference] 主链路对 `meta_claim.version_seq` 的 OCC 更新与 node 版本链是两条独立的并发控制路径，本页未逐行核对二者在并发复审下的先后关系。

## Failure or exit behavior

- [implemented] **分流离线**：`DecisionRouter` 调 Ollama 失败返回 None，退回 LexicalRouter 信号 + 保持 unrouted 入队 classify，不阻断摄入。
- [implemented] **检索降级**：编码器抛 `EncoderError` → `degraded=True`，只返结构化结果，不返回空。
- [implemented] **蒸馏失败**：`validate_result` 不通过（引用缺失/JSON 非法）→ claim 不落库，但 `LLMCallScore` 仍记一条失败读数；节点不 mark_reviewed，可重试。
- [implemented] **终局 gate**：changed 缺 content、stale 缺/非法 branch、cover 缺 content、非内容类携带载荷 → `ValueError` 拒收（Human-only 约束）。
- [implemented] **L3 停机**：标注率 `<70%` 或样本 `<10` 时 gate closed，`adapt_interval` 不改写 interval。
- [implemented] **调度触底**：`floor_hit`（interval 触及 `MIN_INTERVAL_DAYS` 下界）→ `archive`，节点退出 due 集合。
- [implemented] **MCP 黑名单**：`register_tool` 拒黑名单名（`distill/trigger`、`interval_adjustment`、`meta_claim`、`history/delete`、`history/update`），握手阶段 `_LazyStore`/`_LazyRouters` 不连库/Ollama。

## Observable evidence

- [implemented] `zkc meter` / `zkc p64`：`calibration.py` 的 `build_report` / `build_p64_report` 从存储只读读数，与节点状态解耦。
- [implemented] `llm_call_score` 表 + `interval_adjustment` 表 + `node_history`：支撑调用成败、区间调整、版本演进三类回放。
- [implemented] `data/r14_telemetry.jsonl`（`r14_telemetry.py` 产出）+ `scripts/r14_status.py`：R14 延迟裁决读数。
- [implemented] `data/lexical_corpus.json`：LexicalRouter 标注语料，反映分流学习闭环的当前状态。
- [evidence] verdict v2 真值回读（`docs/evidence/verdict-v2-truth-readback-2026-11-14.json`）是单时刻快照，仅作时点取证，不作持续 proof；持续回归依赖 `make mcp-gate` + `make invariant` + `scripts/zkc_authority_check.py`。

## Source map

- `../../src/zkc/cli.py` — CLI 入口 dispatch
- `../../src/zkc/ingest.py` — ingest_with_routing 写入闸
- `../../src/zkc/routing.py` — route_text / DecisionRouter / LexicalRouter / OllamaClient
- `../../src/zkc/decay.py` — refresh_decay / compute_decay_score / SURFACE
- `../../src/zkc/expiry.py` — route_expired / route_and_apply / apply_distill / apply_archive
- `../../src/zkc/distill.py` — distill_node
- `../../src/zkc/llm.py` — ollama_chat（format:json）
- `../../src/zkc/encoder.py` — encode_texts（/api/embed）
- `../../src/zkc/search.py` — search（结构化 + 向量双路）
- `../../src/zkc/scheduling.py` — interval 三层纯函数与落库编排
- `../../src/zkc/web/review.py` — decide_review（verdict v2 分支）
- `../../src/zkc/web/browse.py` — /browse 检索与脱敏
- `../../src/zkc/transport/contract_v1.json` — MCP 工具白名单 / blacklist
- `../../src/zkc/transport/mcp_server.py` — McpServer 分发与黑名单拒接
- `../../src/zkc/mcp/wiring.py` — build_zkc_server composition root
- `../../src/zkc/mcp/handlers.py` — 五 tool handler
- `../../src/zkc/mcp/capture.py` — CaptureProfile / capture_documents
- `../../src/zkc/calibration.py` — build_report / build_p64_report

## Related authority

- [Data Storage](ta-data-storage.md) — 本链路所改变的状态的物理结构。
- [架构本体·调度与预算（原 §6.5 interval 三层）](../evidence/architecture-v1.2-source-2026-11-19.md) — L1/L2/L3 设计论证与阈值校准来源。
- [ADR-0011 verdict 语义 v2](../zj-adr/0011-verdict-semantics-v2.md)（accepted）与 [ADR-0012 规格](../zj-adr/0012-verdict-semantics-v2-spec.md)（spec-frozen）— 终局分支的语义定案与可测规格。
- [ADR-0008 过程权威边界](../zj-adr/0008-process-authority-boundary.md)（accepted）— evidence/过程态不作 proof 的约束来源。
