# ZKC 文档地图

> 本页是治理工具（`zj-docs-ontology`）选定的文档系统索引：声明类别与权威归属，不承载正文。治理作用对象 = 本仓整个 docs system（`--object docs`）。
> 事实归属遵循「one home per fact」：规则与解释只在唯一权威页出现，其余页链接到此。派生视图不得与原文构成并行体系。
> 历史沿革见 `docs/zj-adr/`；一次性取证/运维读数见 `docs/evidence/`（**不作 proof/evidence 的产品语义来源**）。

仅 architecture handbook 的视图页声明 `role:`（primary = 权威架构视图，supporting = 派生/退役视图），供架构校验器套用页面契约；其余长期页由 doc-kind/authority 声明角色，不在此标注。

## Boundaries

- 产物边界（docs / code / roadmap 解耦约定）：[BOUNDARIES.md](BOUNDARIES.md)
- 风险与降级链（长期单一真相源）：[risks.md](risks.md)
- 技术约束：[constraints.md](constraints.md)
- 术语表：[glossary.md](glossary.md)
- 过程权威边界：[ADR-0008](zj-adr/0008-process-authority-boundary.md)

## Product definition

- [PRD](prds/knowledge-compounding-prd.md) — 做什么 / 不做什么 / 怎么算成

## Architecture handbook

每个 primary 视图有一个唯一 authority-id，绑定到此处的单一路径。规则与解释只在唯一 owner 页出现，其余页链接到此。

- [Data storage](architecture/ta-data-storage.md) — 存储分层、node 表结构与双时态/双轨/decay/embedding 落点; role: primary; authority-id: architecture.subsystem.data-storage
- [Data flow](architecture/ta-data-flow.md) — 摄入到检索的主链路、旁路 interval 三层与 verdict v2 终局; role: primary; authority-id: architecture.flow.data-flow

## Method

- [使用指南](user-guide.md) — MVP 使用 / 复审 / 度量复盘
- [rec-avoid 门禁](rec-avoid-gate.md) — 复利度量经验证伪闸与口径

## Decisions（zj-adr）

长生命周期决策，按权威层级声明 role。0011/0012 为 verdict v2 语义的定案与规格（primary），其余历史决策 supporting。0013 为墓碑软删定案（primary）。

- [ADR-0001 MVP 交付形态](zj-adr/0001-mvp-delivery-form.md)
- [ADR-0002 单程票捕获](zj-adr/0002-captured-single-way-ticket.md)
- [ADR-0003 衰减刷新非版本化](zj-adr/0003-decay-refresh-not-versioned.md)
- [ADR-0004 MCP 接口契约](zj-adr/0004-mcp-interface-contract.md)
- [ADR-0005 rec-avoid 机械门禁](zj-adr/0005-rec-avoid-mechanical-gate.md)
- [ADR-0006 budget 无状态](zj-adr/0006-budget-stateless.md)
- [ADR-0007 每日驱动与活跃日](zj-adr/0007-daily-driver-and-active-day.md)
- [ADR-0009 sub-day interval 下界](zj-adr/0009-sub-day-interval-lower-bound.md)
- [ADR-0010 R4 收缩动态集](zj-adr/0010-r4-shrink-dynamic-set.md)
- [ADR-0011 verdict 语义 v2](zj-adr/0011-verdict-semantics-v2.md)
- [ADR-0012 verdict 语义 v2 规格](zj-adr/0012-verdict-semantics-v2-spec.md)
- [ADR-0013 节点墓碑软删](zj-adr/0013-node-tombstone-soft-delete.md)
- [verdict 语义切换点](zj-adr/2026-11-14-verdict-semantics-cutover.md)

## Ontology model（L4 · 单一模型）

`docs/ontology/model.json` 是本仓 docs system 的**唯一本体模型实例**（schema: `ontology-model/v1`，skill 侧 meta-schema: `ontology-meta-schema/v1`）。它把全仓长期文档按**实体 / 属性 / 关系 / 规则**拆解，每页一条 decomposition receipt；语义冲突以各权威页为准，本模型不新增产品语义。页面可用 `model-elements` frontmatter 锚点镜像其 receipt（receipt 为真源）。退役派生视图的逐字归档见 `docs/evidence/ontology-v1-derived-views-archived-2026-11-21.md`（历史溯源，非语义来源）。

## Root entries

- 上下文与护栏：[ZJ-CONTEXT.md](../ZJ-CONTEXT.md)
- 项目说明：[README.md](../README.md)

## Target-defined / evidence surfaces

以下为目录入口（导航说明，非 page entry）。evidence 是一次性取证与逐字归档，**不参与产品语义权威判定**；setup 是安装与运行指引（target-defined）。

- evidence 目录：`docs/evidence/`（架构 v1.2 逐字归档、verdict 决策归档、physical-delete 决策归档、verdict v2 真值回读均在此，不作 proof）
- setup 目录：`docs/setup/`

- [Windows 安装与运行](setup/windows-install-and-run.md)

## Process material

本仓无在册过程态目录。`docs/plans/` 已于 2026-11-17 文档治理中解耦移除：其逐字决策沉淀至 `docs/evidence/*-decisions-*.md`，语义结论此前已沉淀至 ADR-0011/0012/0013 与 risks R15/R16。门禁 `scripts/zkc_authority_check.py` 按内容签名识别过程态，**不硬编码任何目录名**。
