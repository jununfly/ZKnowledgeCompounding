# Finding · Web 域函数与适配器的物理耦合（Q2=C 后的残余）

状态：未完成（待 zj 定性）。task 3 认领方 `zj-qwenwork-agent` 在拆 ticket 9 时发现的边界事实。

## 事实

Q2=C 砍掉的是 **Web HTTP 层**（/browse、/review 路由、SSR、uvicorn 服务常驻）。但适配器仍**物理依赖** `src/zkc/web/` 下的两个 server-agnostic 模块：

1. `src/zkc/cli.py`：
   ```python
   from zkc.web.review import (decide_review, record_daily_observation_auto, review_queue_view)
   ```
   用于 `zkc daily` / `zkc decide` 子命令。这些函数是 ADR-0007「去服务器化」的域编排，不是 HTTP endpoint，只是历史放在 `web/` 包内。

2. `src/zkc/mcp/wiring.py`（惰性 provider）：
   ```python
   from zkc.web.app import build_routers
   decision_router, lexical_router = build_routers()
   ```
   MCP server 构造路由引擎的唯一入口在 `web/app.py`。

## 含义（待 zj 确认，不代答）

- **推荐**：把这 3 个 review 函数 + `build_routers` 定性为 **domain（CLI/MCP 共用）**，纳入迁移范围，归属 task 2「核心 domain」而非 task 3 的「Web」残名；`web/` 包内仅 HTTP endpoint 才是 Q2=C 真正出局的部分。
- 反例：若 zj 认定它们随 Web 一起出局，则 `zkc daily/decide` 与 MCP `zkc_capture` 的分流闸无 Rust 对应入口，CLI/MCP 编排层只能整体回落 Python。

## 影响的工作单

task 3 拆分的 handler 编排（tk-50）、capture 编排（tk-51）、CLI 前门（tk-53）均 `blocks` 于本 finding 落定 + 对应 review/routers 单元处置（tk-49）。本 finding 未处置前，上述编排 ticket 挂 `external_hold`。

## 落定（2026-11-28，zj 拍板）

zj 确认 **定性为 domain，纳入迁移**：`web/review.py` 的 `decide_review` / `record_daily_observation_auto` / `review_queue_view` 与 `web/app.py::build_routers` 均为 server-agnostic 域编排（ADR-0007 去服务器化），随 CLI/MCP 一起纳入迁移；Q2=C 真正出局的仅是 `web/` 包内 HTTP endpoint 本体。

处置动作：
1. web-review-domain 工单（原 tk-49）从 task 3 **热插到 task 2**（核心 domain），归属对齐；跨区 `blocks` 边（49→50/51/53）保留，由 §3.6 F2 外层投影承接。
2. 本 finding 处置为「已完成」。
3. tk-49 仍受 **rust-anything 工具链缺失** 阻塞（见当前会话探测：沙箱与宿主均无 `rust-anything`），hold 改为工具链等待，不再等待本定性问题。
