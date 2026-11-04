# MCP 接口契约边界（单边 server + transport seam + 暴露面白黑名单）

Status: accepted (2026-11-03, zj 拍板，经 zj-discuss 多角色收敛 + zj-grill-with-docs Round 1–2)

ZKC 要经 MCP 融入 Codex/WorkBuddy 日常 Agent 流。事实锚点：Codex 与 WorkBuddy 均为**纯 MCP client**（只连 server，不暴露自身），且都支持 **stdio**（本地子进程，零网络面）。据此决定下版本只做**单边 MCP server**，并把接口契约边界、安全边界、暴露面收口为可机械判定的版本门。

## 形态与 seam
- **单边 server**：ZKC 暴露 MCP server，Codex/WorkBuddy 作 client 连上来。双向 client（自动把外部上下文灌入动态轨）推 phase 2，且须复用现有摄入层（DecisionRouter + 双信号弃权 + review_queue 人审），禁止新增旁路摄入通道。
- **transport seam（第四 seam）**：与 storage/provider/encoder 并列。MCP server 只调既有 repository/command API，**handler 不直连 DDL**；对外契约独立版本化 `zkc-mcp-contract v1`（语义化版本，不承诺 12 个月冻结，bump 随 §5 DDL 演进由 seam 适配层吸收）。

## 安全边界
- **默认 stdio**：零网络监听面，无需 token，外部 agent（含同机 Codex/WorkBuddy）一律零信任。
- **跨机才开 HTTP/SSE**：仅当 zj 确需跨机（Mac↔Win Tailscale）时启用，且必须端到端加密隧道，否则**不变式⑤（本地优先/隐私）自动否决**，无需 Human 二次拍板。
- **写操作白名单 + 私人 claim 沙箱**：`meta_claim` 私人事实型 claim 默认脱敏，须显式 scope 授权方可带隐私字段。

## 暴露面白名单 / 黑名单
- **白名单（允许）**：`zkc_capture` / `zkc_query`（带 `evidence_refs` 溯源）/ `zkc_review_queue_list` / `zkc_review_queue_resolve`（仅标 resolved + HITL 归因）/ `zkc_scheduler_due`（只读该关注清单）。
- **黑名单（绝不暴露）**：`distill/trigger` 自动写、`interval_adjustment` 直接写、`meta_claim` 直接写、历史行 delete/update。

## `zkc_capture` 完整规格（agent 输入文档的首要场景）
- **push 模型**：agent 显式调 `zkc_capture` 推文档进 ZKC（非 ZKC 主动拉取）。
- **必须过分流闸**：经 DecisionRouter + 双信号弃权 + review_queue 人审，**禁 agent 直通道**；agent 不替系统预设轨（静态/动态由路由判）。
- **capture profile**：列为独立 `capture` profile，**默认开启**（安全写——只加源节点，不写 interval、不触发 distill、不直写 meta_claim，不绕过 HITL），区别于 opt-in 的 `review_queue` 标注与禁暴露的三类危险写。
- **量级节流**：单次会话 `node` 写入上限 ≤1000，并走 decay 初始化；超上限即分批。
- **注入防护**：不可信文档内容经 agent 注入后调 MCP 写 tool 时，未授权写被拒、私人 claim 不出现在 query 响应体。

## 攻击面枚举表（MCP ADR 强制章节）
| 列 | 内容 |
|---|---|
| 入口（server 暴露端点，stdio 默认） | `zkc_capture`(写,受分流闸) / `zkc_query`(读,带 evidence_refs,私人 claim 默认脱敏) / `zkc_review_queue_list`(读) / `zkc_review_queue_resolve`(写,仅标 resolved+HITL 归因) / `zkc_scheduler_due`(读) |
| 出口（数据流向外部） | 当前**无**（单边 server 不调外部）；phase 2 双向 client 才开放，须显式决议 |
| 信任边界 | stdio 零网络面无需 token；跨机 HTTP/SSE 须加密隧道；外部 agent 零信任；写白名单 + 私人 claim 沙箱 |

- **提示注入验收用例（gate 用例）**：构造注入（不可信内容 → agent 被注入 → 调 MCP 写 tool），断言 ① 未授权写被拒（distill/trigger/interval_adjustment 返回权限拒绝）② 私人 claim 不出现在 query 响应体 ③ 越权企图回写 `review_queue` 留痕。该用例纳入 ADR 验收闸门。

## Considered Options
- 双向 client 一并做：拒绝（phase 2）——旁路双轨分流闸门（破坏不变量①）+ 新增出口攻击面 + D 量化 node 写入与注意力预算瞬时 +1~2 数量级（§6.3 rot=100%）。
- HTTP 默认暴露：拒绝——打破不变式⑤，便利压倒隐私。
- 暴露面直连 DDL：拒绝——§5 DDL 已回填 8 次，每次演进破坏外部契约。

## Consequences
- 新增 `src/zkc/transport/mcp_server.py` 薄适配层（零领域语义单测）。
- `zkc-mcp-contract v1` 对外 schema 快照独立于 §5。
- 关联 ADR-0005（rec-avoid 机械闸）：MCP 须过去模型化测试；图库主存储 EXCLUDED。
- 与 sub-02 对齐：C1（MCP 进版绑 ADR=守 seam/溯源）、C3（不变式⑤自动否决）。
