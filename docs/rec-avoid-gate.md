# rec-avoid 机械闸（决策记录）

护城河（双轨+衰减+注意力预算为第一性）此前只是文档口号，无机械约束力，稀释项会被默认接受。本文件将其落成可机械判定的版本门，配合 ADR-0005。任何新增功能 PR 须过此闸，否则 review 阶段即被拒。

## 1. 去模型化测试（model-stripping test）
**判据**：某候选功能去掉 LLM 后，若仍可被 SilverBullet / logseq 等价实现，即**稀释项**，默认拒绝。
**仲裁**：由 C 角色（产品专家）维护一份可证伪清单（见下），并对 SilverBullet/logseq 做实测对照；清单进本文件，PR 须附结论。
**已知稀释项（在列）**：图数据库查询、纯结构抽取面板。
**通过示例（非稀释）**：带 `evidence_refs` 强制溯源的 claim 落库、衰减+预算可观测性、双时态投影——这些去掉 LLM 后 SilverBullet/logseq 无法等价提供。

## 2. check_invariant.py（CI 谓词）
仓库新增 `check_invariant.py`（或并入 check_subdoc 同族），PR 门禁，至少两条断言：
- claim 落库仍受 `meta_claim.evidence_refs uuid[] NOT NULL` 约束（溯源权威不可破）。
- 任何 feature 不得提供关闭 `decay` / `attention` 的全局开关（不变式不可被便利绕过）。

## 3. 图数据库主存储 EXCLUDED
**决定**：图数据库（Kuzu / TerminusDB）作**主存储**显式拒绝（EXCLUDED）；仅允许 Kuzu **只读投影**。
**理由**：仓库切换成本 + 偏离 pgvector 基底；递归 CTE 已够用；保持 repository seam 可切。
**依据**：ADR-0005；架构 §7 该行「延后」→「EXCLUDED」。

## 4. 经验证伪闸（护城河实证化，呼应 sub-02 C2）
任何新增功能须证明**不降低**「衰减+预算可观测性」，否则触发 rec-avoid③。护城河须由系统外信号证伪：
- **锚1**：复审标注率闸门持续 ≥70%（外生锚载体）。
- **锚2**：zj 人工抽检蒸馏产物，记录漏检/误蒸馏率，给本机 4B/9B 上界估计（系统外信号 vs 系统自算「复利系数」）。
- **DoD**：架构 §9 回填最终口径 + 抽检漏检率给上界 + 该度量进本闸。

## 关联
- ADR-0004（MCP 接口契约边界）：MCP 须过去模型化测试。
- ADR-0005（rec-avoid 机械闸）：本文件的来源决策。
- 架构 §7：图库主存储 EXCLUDED 行。
- PRD §9：下版本优先级与 MCP 集成决策清单。
