<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `roadmap.json` | 最后更新: 2026-11-01 17:21:05

[~][X+] 1. ZKC MVP 上线（P0→P6，4h/周）
    ├── [ ][X+] 1-5. P3 复利变换（最大块，HITL 串行）
    │   ├── [~][X+] 1-5-5. P3.5 忠实度闸门：字面 rubric 预过滤 + 人工兜底（Spike 12/13/13b）
    │   ... 该层还有 5 个兄弟，0 个 in_progress ▸
    ... 该层还有 7 个兄弟，0 个 in_progress ▸
<details><summary>阻塞链：1 个节点被阻塞</summary>

- 1-7-4. P6.4 达成累计 ≥20 个带标注复审动作 + 标注率 ≥70%（R10 降级判定） ← e20: 1-7-2. P6.2 真实数据冷启动引导（导入 ≥60 条动态型素材） [ ]

</details>


### 当前施工：1-5-5. P3.5 忠实度闸门：字面 rubric 预过滤 + 人工兜底（Spike 12/13/13b）

**决策：**
- Q: 1-5-5 第一切片范围与路由语义？ → zkc/faithfulness.py 纯函数闸门核心：① 字面 rubric 预过滤=spike-10 normalize/ngrams/verbatim/overlap 移植（不 import spikes），红旗=verbatim/overlap 超 tuning 阈值，仅作 reason 标注**不是放行信号**（spike-10 盲点：rubric 抓不到内容幻觉）；② judge seam 移植 spike-12 分解式判定（atomic_facts + aggregate 确定性推导 + parse_judgment 防御解析），pydantic 可用（fastapi 传递依赖）；③ 路由双模式：judge_fn=None（本机现状，13b-probe 4B/9B 双否决）→ 全部 pending_human/human_only，绝不 auto-pass；judge_fn 可用 → Spike 13 §3 四分支（空分解/矛盾→forced 人审；unsupported→抽检 R_unsupported；supported→auto_pass+periodic_audit 5% 审计）。R11 独立预算：F_CAP_RATIO(0.20 已有)只封顶抽检+审计侧，强制项永无上限。④ 人工兜底 adjudicate(store, claim_id, verdict)：confirm/reject/edit → human_confirmed/human_rejected + human_verdict_at；校准语料**不建新表**=judge_raw 非空且有人判的 claim 行本身（judge vs 人判同 row 可查询导出，Spike 13 §7 最小实现）。⑤ ClaimRepository.list_by_status 消费口（memory+pg 同构）。验收③（无记录人判或带 judge_raw 的显式 auto-pass 不得离开 pending）在 route/adjudicate 内 enforcement + 测试。Web UI 卡片/F_cap 与每日队列联动/dogfood 脚本属后续切片。

### 下一步可开工（ready 前 3）

- 1-5. P3 复利变换（最大块，HITL 串行） [ ]
- 1-5-6. P3.1 后续切片：Ollama/Instructor/LangGraph 接线 + score 表/rubric（延后，不阻塞 critical path） [ ]
- 1-6. P5 复用+度量 [ ]
<!-- ROADMAP_SECTION_END -->
