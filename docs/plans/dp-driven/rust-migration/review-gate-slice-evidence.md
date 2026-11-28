# Evidence · web.review 域迁移 + decide_review 载荷门禁切片（ticket 49）

日期：2026-11-28。过程态证据，非长期权威；crate 实现与 gate 语义以 `rust/review-gate-rs` 为准。

## 结论（两件事）

1. **域迁移完成**：`zkc.web.review` 的纯编排函数 + `REVIEW_REASON` + 序列化助手物理迁到无 fastapi 的
   领域模块 `src/zkc/review.py`；`build_routers` 迁到 `src/zkc/routing.py`。`src/zkc/web/review.py` 仅留
   `REVIEW_HTML` + `register_review_routes` 并 re-export 领域名。**`make test` 改动前后均 `Ran 671 tests OK`（0 FAIL/ERROR）**。
2. **干净切片已 port 并 gate 通过**：`decide_review` 的 Human-only 载荷门禁 → `rust/review-gate-rs::review_payload_gate`，
   **gate 全 pass、diff 10/10**（含 5 条 ValueError 逐字）。**未接线 `rust/app`**。

## 为什么只 port 门禁这一片（Q5 类边界定性）

`decide_review / review_queue_view / record_daily_observation_auto` 函数体是 **Storage 绑定编排**：
读 `store.nodes` / `store.attention`，做 OCC 版本写（`nodes.save`）、`archive` 软归档、attention 观测累加，
且 `now` 默认 `datetime.now`。这与 Q5 的 metrics_snapshot 同属「dataclass/Storage 编码缝」，
standalone port 是有损且不可信——按纪律留在 Python，归 app-wire 阶段。`build_routers` 返回 router 对象 +
读 env/file，非 JSON-in/out，同样不是独立 port 面。

唯一自包含、JSON-native 的是 `decide_review` 入口的 **Human-only 载荷门禁**（ADR-0011/0012 安全契约：
content / stale_branch 必须人工逐条给出、绝不自动填/绝不默认 purge）。spike 在 wrapper 内部造真实
`get_storage("memory")` + 一条节点、委托**原** `decide_review`（同 capture-profile 用真实 dataclass 的做法），
使门禁与 dispatch 的 `unknown outcome` 分支都 verbatim 跑到，仅暴露 3 个 JSON 标量。

## 录制与实现要点

- `rust-anything bridge . spikes/spike-27-review-gate/pure_bridge.py --name review-gate-rs -o rust/review-gate-rs`。
- `record --count 0 --inputs <10 定向 case>`：**10 recorded / 5 threw**，覆盖 changed(缺/有内容)、
  stale(purge / cover缺内容 / cover有内容 / 非法分支)、still_valid、browse、browse携带载荷、unknown outcome。
  （`PYTHONPATH=<repo>/src:<repo>/spikes/spike-27-review-gate` 让 recorder import zkc；域迁移后已无 fastapi 依赖。）
- 错误串逐字保留（含全角 `（）；`、半角空格），5 条加 `// recorded-literal:` 过 literals 检查。
- 复现两处 Python 语义细节：① `not content` = `None` 或 `""` 皆「缺内容」（`not_present`）；
  ② still_valid/browse 的 `content is not None` 判携带（空串 `""` 仍算携带 → 拒）（`is_not_none`）。
  两者区分正是 case 实证点（`["changed","",null]` 仍拒、`["browse","",null]` 仍拒）。

## 机械验证

| 检查 | 结果 |
|---|---|
| make test（迁移后） | **Ran 671 tests OK**（0 FAIL/ERROR，live PG 容器 `zkc-spike-pg:55433`） |
| 无 fastapi 解耦 | `import zkc.cli / zkc.mcp.wiring / zkc.review / zkc.routing` 全成功，`fastapi not in sys.modules` |
| record | **10 cases（5 threw）** |
| build | PyO3 模块构建成功 |
| crate diff | **10/10 cases match**（5 ok + 5 错误串逐字一致） |
| gate | **Gate passed**：fmt / clippy 0 warn / cargo test / unsafe 0 / lockfile / ported / size 2.5x / literals / tests 2·9 / error cases / panics 0 / build / api（exports review_payload_gate）/ behavior **10/10** |
| `app replay` | N/A：未接线 app，无 per-call 前门（同 ticket 35/46 注入/暴露切片） |

## 边界与风险

- 真相源仍是 Python `decide_review` 的门禁分支；Rust port 是录制期等价回放，非新策略源。HITL 契约变更须先改
  `zkc/review.py` 并重录。recorded-literal 文本不 promote 为 CALIBRATED。
- 只覆盖「载荷组合 → 接受/拒绝」，**不**覆盖通过门禁后的 store 写副作用（版本链、archive、观测累加）——
  那些留 app-wire + `app record/replay` 证明。
- 非字符串 `outcome` / 非 str·非 null 的 content 不在录制面；`unknown outcome` 仅对非空 str 成立（Python 同义）。
- 迁移已改 `src/zkc/**` 生产源码（纯物理搬迁，无逻辑改动），未提交，按 zj checkpoint 指令再拆提交。
