# ZKC 文档地图

> 本页是治理工具（`zj-docs-ontology`）选定的文档系统索引：声明类别与权威归属，不承载正文。
> 事实归属遵循「one home per fact」：规则与解释只在唯一权威页出现，其余页链接到此。
> 历史沿革见 `docs/zj-adr/`；一次性取证/运维读数见 `docs/evidence/`（**不作 proof/evidence 的产品语义来源**）。

## Boundaries

- 产物边界（docs / code / roadmap 解耦约定）：[BOUNDARIES.md](BOUNDARIES.md)
- 过程权威边界（过程态不得作 proof/evidence）：[ADR-0008](zj-adr/0008-process-authority-boundary.md)
- 风险与降级链（长期单一真相源）：[risks.md](risks.md)
- 技术约束：[constraints.md](constraints.md)
- 术语表：[glossary.md](glossary.md)

## Long-lived categories

| 类别 | 目录 | 承载 | 本仓状态 |
|---|---|---|---|
| prd | [prds/](prds/) | 问题 / 目标 / 非目标 / 范围 | `knowledge-compounding-prd.md` |
| architecture | [architecture/](architecture/) | 系统边界 / 分层 / 数据流 / 关键不变量 | `ZKC-architecture-v1.2.md`（§6.5 interval 三层） |
| zj-adr | [zj-adr/](zj-adr/) | 长生命周期决策（verdict / 边界 / 阈值 / 墓碑） | 0001–0013 + cutover |
| testing / benchmarks | — | 测试策略 / 度量定义 | 测试在 `tests/`；度量口径在架构 + `docs/evidence/` |
| methods / references | [user-guide.md](user-guide.md)、[setup/](setup/) | 使用方法 / 安装 | 用户手册 + Windows 安装 |

## Root entries

- 上下文与护栏：[ZJ-CONTEXT.md](../ZJ-CONTEXT.md)
- 项目说明：[README.md](../README.md)

## Target-defined / evidence surfaces

- [evidence/](evidence/)：一次性取证读数与逐字决策归档，**不参与产品语义的权威判定**。
  - 逐字归档（历史溯源，非 proof）：[verdict-semantics 决策](evidence/verdict-semantics-decisions-2026-11-14.md)、[physical-delete 决策](evidence/physical-delete-decisions-2026-11-16.md)
  - 一次性取证：[meter 真值漂移与 c3 护栏](evidence/daily-repeat-truth-drift-2026-11-16.md)（对应 `zkc meter` 只读口径）、[迁移 sha re-baseline](evidence/migration-sha-rebaseline-2026-11-16.md)（对应迁移 verify 运维）、[墓碑时区修复](evidence/tombstone-timezone-fix-2026-11-16.md)（对应 ADR-0013）
- [setup/](setup/)：安装与运行指引（target-defined）。

## Process material

本仓无在册过程态目录。`docs/plans/` 已于 2026-11-17 文档治理中解耦移除：其逐字决策沉淀至 `docs/evidence/*-decisions-*.md`，语义结论此前已沉淀至 ADR-0011/0012/0013 与 risks R15/R16。门禁 `scripts/zkc_authority_check.py` 按内容签名识别过程态，**不硬编码任何目录名**。
