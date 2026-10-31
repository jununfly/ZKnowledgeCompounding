# decay_score 刷新不写双时态版本链（派生量，非事实）

Status: accepted (2026-10-31, zj 拍板 A-1a + A-3a)

来自 P1 review 的 Spec 轴 c2：`refresh_decay → update_decay` 原走 `_locked_snapshot`，每次把整行（含派生量 `decay_score`）INSERT 进 `node_history`，并被 `test_decay_pg` 断言「+1 历史行」。造成两害：① 历史膨胀（每轮扫描 N 条动态节点 +N 行）；② 溯源噪声（无法区分「用户改了事实」与「维护扫描重算了 decay」）。与 `ZJ-CONTEXT.md` 对双时态的定义（"核心语义是事实演进与溯源审计"）直接冲突——`decay_score` 是 `compute_decay_score(node, now)` 的纯函数输出，由 `last_reviewed_at + review_interval + now` 可随时重算，不是事实。

## Considered Options

- **A（采纳）：decay_score 是派生量，`update_decay` 不写 `node_history`、不 bump `tx_from`**。pg/memory 两后端同构：只 `UPDATE decay_score + version_seq`，`FOR UPDATE` 仍持行锁保并发，`tx_from` 始终标记「上次事实变更」。收益：与领域术语表自洽、消除膨胀与噪声、OCC 令牌仍保活（`version_seq` 继续自增，不白费 P1 review #1 的协议修复）。代价：历史里查不到 decay 随时间的变化（但本就可重算，零溯源损失）。
- **B：维持现状，补文档声明 decay 刷新也算版本事件**。改动最小，但接受历史膨胀 + 溯源噪声，且等于推翻 `ZJ-CONTEXT.md` 对双时态的定义（需同步改术语表），代价更高。

## Consequences

- `update_decay` 在 pg（`zkc/repository/pg.py`）与 memory（`zkc/repository/memory.py`）均改为轻量路径；`set_interval` 仍快照（它改的是 `review_interval`/`interval_source`/`reason`——真实调度决策事实，snapshot 正确，不动）。
- 测试反向固化已修：
  - A-3a：`tests/test_decay_pg.py::test_refresh_is_derived_only_not_versioned` 断言刷新不增历史、decay 仍算到 0.5、tx_from 不变。
  - A-2：`tests/test_repository.py::run_contract` 双后端锁「update_decay 不增历史 / 不 bump tx_from」。
  - `tests/test_concurrency.py::test_concurrent_decay_and_interval_do_not_corrupt_chain` 期望版本数 3 → 2（仅 `set_interval` 快照）。
- `refresh_decay` 尚未接入生产调度器，本次趁早修成本最低；若未来要「凭过期版本拒绝 decay 写」，strict-OCC 路径（`version_seq` 参数）已保留可用。
- 明确 defer：是否彻底不持久化 `decay_score`（读取时计算）→ 更大改动，不在本决策范围。
