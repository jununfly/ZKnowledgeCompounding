<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

<!-- zj-roadmap-authority/v1
role: process-state
durable-citation: forbidden
promote-via: ADR|design|contract|runtime-evidence
-->

> 数据文件: `roadmap.json` | 最后更新: 2026-11-04 18:25:15

[~][X+] 1. ZKC MCP 集成执行路线图
├── [ ][X+] 1-1. E1 校准闭环跑通：复审队列≥7活跃日且标注率≥70%
├── [!][X+] 1-2. E2 transport seam 与 MCP server 骨架（stdio 薄适配层）
├── [!][X+] 1-3. E3 暴露面五 tool 实现与攻击面枚举表
├── [!][X+] 1-4. E4 zkc_capture 完整规格：push+分流闸+注入防护
├── [!][X+] 1-5. E5 提示注入验收用例接入 CI
├── [ ][X+] 1-6. E6 check_invariant.py CI 谓词门禁
├── [ ][X+] 1-7. E7 去模型化测试清单与竞品实测对照
├── [ ][X+] 1-8. E8 护城河实证化：复利度量口径回填与蒸馏抽检
├── [ ][X+] 1-9. E9 对外叙事对齐：caveat+4特征口径统一
├── [ ][X+] 1-10. co-work(ZAgentic #234): E 链推进走 canonical reconcile+apply 路径，向 issue 回填真实一致性证据
├── [ ][X+] 1-11. co-work(ZAgentic #235): 将本 roadmap.json 置为只读副本进 tmp/skills-outputs/ 供回放；另补 ZBrain/ZAgentic 两份样本
└── [ ][X+] 1-12. co-work(ZAgentic #236): E6/E7/E8 复用共享 Work 入双 outline context 时，产出 reference Placement 真实用例供标记复核
<details><summary>阻塞链：4 个节点被阻塞</summary>

- 1-2. E2 transport seam 与 MCP server 骨架（stdio 薄适配层） ← e1: 1-1. E1 校准闭环跑通：复审队列≥7活跃日且标注率≥70% [ ]
- 1-3. E3 暴露面五 tool 实现与攻击面枚举表 ← e2: 1-2. E2 transport seam 与 MCP server 骨架（stdio 薄适配层） [ ]
- 1-4. E4 zkc_capture 完整规格：push+分流闸+注入防护 ← e3: 1-3. E3 暴露面五 tool 实现与攻击面枚举表 [ ]
- 1-5. E5 提示注入验收用例接入 CI ← e4: 1-4. E4 zkc_capture 完整规格：push+分流闸+注入防护 [ ]

</details>


### 下一步可开工（ready 前 3）

- 1-1. E1 校准闭环跑通：复审队列≥7活跃日且标注率≥70% [ ]
- 1-10. co-work(ZAgentic #234): E 链推进走 canonical reconcile+apply 路径，向 issue 回填真实一致性证据 [ ]
- 1-11. co-work(ZAgentic #235): 将本 roadmap.json 置为只读副本进 tmp/skills-outputs/ 供回放；另补 ZBrain/ZAgentic 两份样本 [ ]
<!-- ROADMAP_SECTION_END -->
