<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `roadmap.json` | 最后更新: 2026-11-01 01:21:57

[~][X+] 1. ZKC MVP 上线（P0→P6，4h/周）
    ├── [ ][X+] 1-5. P3 复利变换（最大块，HITL 串行）
    │   ├── [~][X+] 1-5-4. P3.4 context 拓扑装配 + produced_by 级联撤销（Spike 06）
    │   ... 该层还有 5 个兄弟，0 个 in_progress ▸
    ... 该层还有 7 个兄弟，0 个 in_progress ▸
<details><summary>阻塞链：2 个节点被阻塞</summary>

- 1-6-1. P5.1 复利产出检索/浏览（T6.1，原无 spike 覆盖） ← e19: 1-5-4. P3.4 context 拓扑装配 + produced_by 级联撤销（Spike 06） [~]
- 1-7-4. P6.4 达成累计 ≥20 个带标注复审动作 + 标注率 ≥70%（R10 降级判定） ← e20: 1-7-2. P6.2 真实数据冷启动引导（导入 ≥60 条动态型素材） [ ]

</details>


### 当前施工：1-5-4. P3.4 context 拓扑装配 + produced_by 级联撤销（Spike 06）

**决策：**
- Q: 1-5-4 第一切片范围？ → Port spike-06 到生产：schema(context/context_member/transform)已在 0001 基线就绪，无需新迁移。本切片在 repository seam 上加 assemble_context(一transform->一context+members,produced_by级联)+revert_assembly(删transform->FK CASCADE 撤 context+members)+discover_higher_dim(pgvector k-NN,T4.1)+人审成员 add/remove。补 zkc/context.py 算子与双实现单测。R15：membership 先用已验证的 junction 表(非高频重算即无写放大)；查询时动态视图留作压测后选项。

### 下一步可开工（ready 前 3）

- 1-4. P4 调度+复审闭环（S1：先于 P3） [ ]
- 1-4-3. P4.3 budget_per_day 统计估计（删失感知+单调护栏+EMA+oversubscribe） [ ]
- 1-4-5. P4.5 已捕获条目「单程票」规则（ADR-0002，含边界 1/2） [ ]
<!-- ROADMAP_SECTION_END -->
