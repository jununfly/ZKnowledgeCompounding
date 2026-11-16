<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

<!-- zj-roadmap-authority/v1
role: process-state
durable-citation: forbidden
promote-via: ADR|design|contract|runtime-evidence
-->

> 数据文件: `2026-11-16-zkc-physical-delete-roadmap.json` | 最后更新: 2026-11-16 17:09:23

[x][X+] 1. ZKC 「物理删除」真实需求对齐 → 方案设计 → 实施
├── [x][X+] 1-1. 阶段一 · grilling 对齐「物理删除」的真实需求
│   ├── [x][X+] 1-1-1. Q1 · 「删除」要的是哪个终局状态？
│   ├── [x][X+] 1-1-2. Q2 · 为什么要删除（触发动机）？
│   ├── [x][X+] 1-1-3. Q3 · 归档软删除为何不够？
│   ├── [x][X+] 1-1-4. Q4 · 是否接受推翻 ADR-0012 DI-5「无物理删除」？
│   ├── [x][X+] 1-1-5. Q5 · TTL 时长与起算点（多久不恢复才真删）
│   ├── [x][X+] 1-1-6. Q6 · 真删范围（node 行级联带走哪些关联数据）
│   ├── [x][X+] 1-1-7. Q7 · 墓碑期可逆操作（is_delete=0 恢复由谁/在哪触发）
│   ├── [x][X+] 1-1-8. Q8 · 真删后审计与外生锚怎么处理
│   └── [x][X+] 1-1-9. Q9 · 运行时污染：补 discover 过滤 vs 靠删除规避（第1点能否独立解决）
├── [x][X+] 1-2. 阶段二 · 技术方案设计（待阶段一结论）
└── [x][X+] 1-3. 阶段三 · 实施（待方案批准）
    ├── [x][X+] 1-3-1. S1 · schema+model+repo 读写（0011 迁移 / deleted_at / tombstone·restore·hard_delete）
    ├── [x][X+] 1-3-2. S2 · 全功能不可见谓词（10 路径 + discover 漏洞 + invariant P4）
    ├── [x][X+] 1-3-3. S3 · 人环入口（CLI mark/restore + web 按钮 + operator）
    ├── [x][X+] 1-3-4. S4 · 真删引用闸门（evidence_refs+citation，拒删 + task_queue 兜底）
    ├── [x][X+] 1-3-5. S5 · 真删 CASCADE + 独立审计事件（node_id 无 FK、不记 content）
    ├── [x][X+] 1-3-6. S6 · 月扫 sweep 幂等（挂现有 automation + 月度门闩 + dry-run）
    └── [x][X+] 1-3-7. S7 · 持久权威同步 + 全量门禁（ADR-0013 勘误/PRD/architecture/risks）
<!-- ROADMAP_SECTION_END -->
