# Slice 1 — 知识复利工具（产品层 tickets）

本目录是知识复利工具 Slice 1（Phase 0 最小闭环）**产品层**的 ready-for-agent tickets，按 zj-to-tickets 本地 `.scratch` 形态落地（agent-grabbable by construction）。

## 仓库分层（方案 B：按层拆）

- **ZKnowledgeCompounding（本仓库，产品层）**：utopia 持久层基建 + 产品编排 / 消费侧。
  - `01` utopia 地基（FR-012）
  - `05` 半自动回流（FR-006）
  - `06` zj 主动 query（FR-008）
  - `07` Seam1+2 端到端验收门禁
- **ZAgentic（技能层）**：`zj-deep-research` skill 内部管线。
  - `02` Ingest 摄入与本地向量索引（FR-001）
  - `03` Decompose+Retrieve+Cite+Report（FR-002/003/004）
  - `04` Groundedness 后端校验环（FR-005）
  - 路径：`ZAgentic/.scratch/knowledge-compounding-slice1/issues/02~04`

## 依赖关系（含跨仓库）

- 本仓库内串行：`01 → 05 → 06 → 07`
- `04`（ZAgentic 技能层）是 `05`、`07` 的跨仓库前置
- `07` 同时依赖 `04`（ZAgentic）+ `05`/`06`（本仓库）

## 验收门禁（三项指标同时达标）

- Seam 1：引用可回溯率 ≥ 90% 且 groundedness ≥ 0.8
- Seam 2：回流率 ≥ 50% 且消费侧 recall ≥ 50%

## 状态

- tickets 形态：本地 `.scratch`（GitHub issues 待本仓库 `zj-repo-init` + MCP 写权限后转换）
- 本仓库此前为纯文档仓库（README 仅标题）；方案 B 后成为产品代码仓库，首批内容为产品层 tickets。
