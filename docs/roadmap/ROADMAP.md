<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

<!-- zj-roadmap-authority/v1
role: process-state
durable-citation: forbidden
promote-via: ADR|design|contract|runtime-evidence
-->

> 数据文件: `roadmap.json` | 最后更新: 2026-11-12 21:54:50

[x][X+] 1. ZKC MCP 集成执行路线图
├── [x][X+] 1-1. E1 校准闭环：已由 1-26 显式覆盖收口（不再追求统计收敛）
├── [x][X+] 1-2. E2 transport seam 与 MCP server 骨架（stdio 薄适配层）
├── [x][X+] 1-3. E3 暴露面五 tool 实现与攻击面枚举表
├── [x][X+] 1-4. E4 zkc_capture 完整规格：push+分流闸+注入防护
├── [x][X+] 1-5. E5 提示注入验收用例接入 CI
├── [x][X+] 1-6. E6 check_invariant.py CI 谓词门禁
├── [x][X+] 1-7. E7 去模型化测试清单与竞品实测对照
├── [x][X+] 1-8. E8 护城河实证化：复利度量口径回填与蒸馏抽检
├── [x][X+] 1-9. E9 对外叙事对齐：caveat+4特征口径统一
├── [x][X+] 1-10. co-work(ZAgentic #234): 隔离 fixture 验收 canonical reconcile+apply 与 direct bypass 收口，产出可复核一致性证据（不依赖 E1、不计入产品完成度）
├── [x][X+] 1-11. co-work(ZAgentic #235): ZKC 内交付 roadmap 只读副本 + 本仓库脱敏内容供回放（不跨项目取样、不计入产品完成度）
├── [x][X+] 1-12. co-work(ZAgentic #236): E6/E7/E8 复用共享 Work 入双 outline context 时，产出 reference Placement 真实用例供标记复核
├── [x][X+] 1-13. D1 L3 AIMD 下界触底：1.0d 节点反馈恒 no-op，拍板处置
├── [x][X+] 1-14. D2 导入语料隔离：corpus 标记 + zkc archive 归档切片，移出调度回路
├── [x][X+] 1-15. D3 文档与实物对齐：R18 关停结论回填 + embedding_strong 旧名清理
├── [x][X+] 1-16. D4 反向连接候选召回切 4096 + 相似度阈值重校准
├── [x][X+] 1-17. PRD §9 P6.4 观察期收口：累计 ≥20 带标注复审 + 滚动 7 天标注率 ≥70%
├── [x][X+] 1-18. PRD §9 下版本决策收口：护城河锚 2 抽检 + 6 项 unknown 口径 + checkbox 勾销
├── [x][X+] 1-19. 风险册观察期终判组：R4/R5/R6/R10/R14 终判与阈值 source 升级
├── [x][X+] 1-20. 风险册独立 open 项：R17 工期裁剪 / R1 judge opt-in / R8 版本回归
├── [x][X+] 1-21. 工程尾巴 A：每日驱动跨平台补齐 + harness 适配器纳管
├── [x][X+] 1-22. 工程尾巴 B：lexical 语料冷启动 + 占位阈值（routing gate）校准收口
├── [x][X+] 1-23. G1 过程权威泄漏治理：7 处分类 + 真违规修复 + 门禁自包含接入 CI
│   └── [x][X+] 1-23-1. G1 follow-up：对齐上游结构性判据，收敛 6 条白名单
├── [x][X+] 1-24. 工程尾巴 A 实机复核：Windows schtasks 4 步验证（关停 1-21 未实测偏差）
├── [x][X+] 1-25. spike07 复利度量权重口径定案：METRIC_W_* 四权重 + METRIC_METHOD_TARGET 由 PLACEHOLDER 升 SIMULATION（CALIBRATED 需外生锚，另开跟踪；从 1-22 拆出）
├── [x][X+] 1-26. spike07 复利度量权重升 CALIBRATED：真实埋点 + zj 四分量价值排序外生锚（承接 1-25 的遗留未决）
└── [x][X+] 1-27. R14 关闭：补全回路延迟成本真实数据侧落库聚合
    ├── [x][X+] 1-27-1. telemetry 落库+聚合模块 + TDD（record_run/load_runs/aggregate）
    └── [x][X+] 1-27-2. 真实 run 积累（zj 经 dogfood）+ 据实裁决与 risks.md R14 更新
<!-- ROADMAP_SECTION_END -->
