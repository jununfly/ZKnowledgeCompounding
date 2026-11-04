# rec-avoid 守门落成机械闸（去模型化测试 + check_invariant.py + 图库主存储 EXCLUDED）

Status: accepted (2026-11-03, zj 拍板，经 zj-discuss 多角色收敛 + zj-grill-with-docs Round 1)

护城河（双轨+衰减+注意力预算为第一性）此前只是文档口号，无机械约束力，稀释项会被默认接受。我们决定把 rec-avoid 落成**版本门**，三件套：
1. **去模型化测试**：每个候选功能先问「去掉 LLM 后 SilverBullet/logseq 能否等价实现」——能即稀释项，默认拒绝（图数据库查询、纯结构抽取面板在列）。
2. **check_invariant.py**（CI 谓词）：claim 落库仍受 `evidence_refs` NOT NULL 约束；任何 feature 不得提供关闭 decay/attention 的全局开关。
3. **图数据库主存储从「延后」升 EXCLUDED**：仅允许 Kuzu 只读投影，禁止把图库当主存储（仓库切换成本 + 偏离 pgvector 基底）。

## Considered Options
- 维持文档口号（拒绝）：无约束力，稀释项静默进入。
- 仅 CI 谓词（部分）：缺去模型化测试则「功能是否稀释第一性」无人判。
- 三件套（采纳）：去模型化测试管「该不该做」，check_invariant 管「做完没破不变式」，EXCLUDED 管「存储基底不漂移」。

## Consequences
- 架构 §7 图库主存储「延后」→「EXCLUDED」+ 拒绝理由行；新增 rec-avoid 守门说明。
- 仓库新增 `check_invariant.py`（或并入 check_subdoc 同族），PR 门禁。
- 任何新增功能 PR 须附去模型化测试结论，否则 review 阶段即被拒。
