<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

<!-- zj-roadmap-authority/v1
role: process-state
durable-citation: forbidden
promote-via: ADR|design|contract|runtime-evidence
-->

> 数据文件: `2026-11-14-zkc-verdict-semantics-roadmap.json` | 最后更新: 2026-11-14 21:37:38

[x][Y+] 1. ZKC 复审标注四档语义缺口收敛 · Plan 过程态 roadmap
├── [x][Y+] 1-1. Step 1 语义裁决：收敛四档语义的 Human 逐项拍板（zj-grilling）
├── [x][Y+] 1-2. Step 2 规格与验收判据：把 S0/S1/S2 转成可测断言（zj-to-spec）
│   ├── [x][Y+] 1-2-1. 语义矩阵 v2 规格：内容轴与节奏轴分列、stale 两分支分列
│   ├── [x][Y+] 1-2-2. CLI verdict 与必填内容载荷、stale 分支选择的参数变更清单
│   ├── [x][Y+] 1-2-3. OUTCOME_VERDICT 与终局动作两张表的断言更新清单
│   ├── [x][Y+] 1-2-4. L1 基线重置、archive 退出调度回路与四类审计 reason 的断言口径
│   └── [x][Y+] 1-2-5. 口径切换点记录格式与回归用例清单
├── [x][Y+] 1-3. Step 3 契约与设计评审：锁定外生锚 A 与不变量清单（zj-tech-design-review）
│   ├── [x][Y+] 1-3-1. 复核外生锚 A、标注率闸门与埋点口径的连带影响
│   ├── [x][Y+] 1-3-2. 锁定 AIMD 自适应环路人工输入归零的架构级结论
│   └── [x][Y+] 1-3-3. 产出不变量清单：L1 基线重置与 archive 退出边界
├── [x][Y+] 1-4. Step 4 小切片实现：红绿重构语义矩阵 v2 与 CLI 契约（zj-tdd）
│   ├── [x][Y+] 1-4-1. 红阶段：逐条构造失败在先的语义断言
│   ├── [x][Y+] 1-4-2. 绿阶段：语义矩阵 v2 与 nodes.save 双时态新版本
│   ├── [x][Y+] 1-4-3. 绿阶段：L1 基线重置与 archive 软归档退出调度回路
│   ├── [x][Y+] 1-4-4. 绿阶段：分支选择人工门禁与四类审计 reason 区分
│   └── [x][Y+] 1-4-5. 绿阶段：CLI 契约、全量测试证据与口径切换点记录
├── [x][Y+] 1-5. Step 5 代码审查与证据复核：改动、测试与不变量三方对齐（zj-code-review）
│   ├── [x][Y+] 1-5-1. 复核改动范围、测试证据与不变量是否仍成立
│   └── [x][Y+] 1-5-2. zkc decide --list --json 真值回读与 choices 一致性核对
├── [x][Y+] 1-6. Step 6 长期文档收口：ADR、风险册与证据提炼（zj-doc-health）
│   ├── [x][Y+] 1-6-1. ADR：语义矩阵 v2、外生锚 A 改终局动作、AIMD 人工输入归零与已知取舍
│   ├── [x][Y+] 1-6-2. risks：标注率闸门与 archive 退出调度回路契约
│   └── [x][Y+] 1-6-3. evidence：真值回读证据、口径切换点与一致性检查记录
└── [x][Y+] 1-7. Step 7 注释方向偏差独立收口：tuning.py doc-only 切片（zj-doc-health）
    ├── [x][Y+] 1-7-1. 修订 tuning.py:120-121 的 AIMD_UP / AIMD_DOWN 中文注释方向
    └── [x][Y+] 1-7-2. 一致性检查与独立提交（不并入语义实现批次）
<!-- ROADMAP_SECTION_END -->
