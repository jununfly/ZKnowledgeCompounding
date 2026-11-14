# 2026-11-14 复审标注语义口径切换点

> 配套：ADR-0011（决策定案）、ADR-0012（规格 + §9 设计评审不变量 DI-1..DI-9）。
> 本文件只记录**口径切换点事实**，不承载新决策、不作校准证据（过程态结论须提炼至 ADR/PRD/架构/risks/evidence，见护栏#9）。

## 1. 映射切换

- **旧映射**（v1，已于本步移除）：
  `OUTCOME_VERDICT = {still_valid:on_time, changed:too_late, stale:too_late}`
  → 经 `S.adapt_interval` 走 AIMD 乘因子（`too_late×0.7` 缩短 / `on_time` 维持）。
- **新映射**（v2，终局动作替代 AIMD 乘因子，见 ADR-0012 §4 表 A）：
  | outcome | 终局动作 | 节奏影响 |
  |---|---|---|
  | `still_valid` | 仅 `mark_reviewed`（时钟复位）+ 标注埋点 | interval 不变，不调 AIMD |
  | `changed` | 写节点双时态新版本（`nodes.save`）+ `review_interval` 重置 L1 基线；**不退出**调度回路 | 不缩短、不继承旧收缩 |
  | `stale`+`cover` | 写节点双时态新版本 + 重置 L1 基线；**不退出** | 同 changed |
  | `stale`+`purge` | `archive` 软归档（退出调度回路） | 退出 due/衰减扫描/higher_dim seeds |
  | `browse` | 仅 `mark_reviewed` + `completed++` | 不标注、不调 L3 |
- **审计 reason**：旧 `OUTCOME_VERDICT` 删除，改由 `REVIEW_REASON` 集中常量承载（`still_valid` / `changed` / `stale_overwrite` / `stale_purged` / `browsed_without_label`，五值互异，不再含 `too_late`/`on_time`）。

## 2. 外生锚 A 归零（最硬不变量 DI-1）

- `decide_review` 对**任何** outcome 都**不再调用** `S.adapt_interval`（AIMD 自适应环路的人工输入由此归零）。
- 仅保留：`mark_reviewed`（时钟复位）+ 每日标注埋点（`labeled_completed`）。标注率闸门口径不受影响（由埋点驱动，与 AIMD 反馈路径正交）。
- 测试锁死：A3 `spy(S.adapt_interval)` 断言调用次数 = 0（`tests/test_verdict_v2.py::test_aimd_loop_human_input_zeroed`）。

## 3. Human-only 门禁（DI-3，绝不默认/自动填）

- `changed` 缺 `--content` → `ValueError` 拒收（不默认、不静默填）。
- `stale` 缺/非法 `--stale-branch` → `ValueError` 拒收，**绝不默认 purge**。
- `stale`+`cover` 缺 `--content` → `ValueError` 拒收。
- `still_valid`/`browse` 携带 `--content`/`--stale-branch` → `ValueError`（一致处理，避免静默丢信息）。
- 路由层：`/review/api/decide` 捕获 `ValueError` → `HTTPException(400)`；CLI 捕获 → `print(..., file=stderr); return 2`；前端 `decide()` 对 `changed`/`stale` 弹 `prompt` 取载荷/分支，`!r.ok` 时 `alert` 报错。

## 4. 受影响历史与未回填声明（对应 ADR-0011 S1-d）

- **历史 3 条 `changed`**：保留旧语义产物，**不回填、不重标记、不撤销 interval 调整**（ADR-0011 明示）。
- 本步**未**对既有节点做任何物理删除（DI-5）；清除仅映射 `archive` 软归档。
- 本步**未**改动任何阈值常量（`tuning.py` 的 `AIMD_UP`/`AIMD_DOWN`/`MIN_INTERVAL_DAYS`/`METRIC_W_*`），不写回 `REGISTRY`（DI-6，与 1-26 CALIBRATED 口径正交）。

## 5. 改动面与证据（Step 4 TDD 落码，2026-11-14）

- **源码**
  - `src/zkc/web/review.py`：`decide_review` 重写为终局动作分支 + `REVIEW_REASON` 常量（替代 `OUTCOME_VERDICT`）；
    新增 `_write_content_version` / `_reset_to_l1_baseline` helper；`/review/api/decide` 透传 `content`/`stale_branch` + 400 拒收；前端 `decide()` JS 接内容载荷/分支。
  - `src/zkc/cli.py`：`zkc decide` 新增 `--content`、`--stale-branch`（choices=cover/purge）；`ValueError`→`exit 2`。
- **测试**
  - 新增 `tests/test_verdict_v2.py`（12 项：B/C/D/E/A3/F1/G1/C5 全覆盖）。
  - 改写 `tests/test_web_review.py`（22 项：`test_decide_changed_requires_content_v2`、`test_decide_api_runs_v2_changed`、`test_decide_api_rejects_stale_without_branch`、历史 `stale` 用例补 `--stale-branch` 等）。
- **未改动**：`src/zkc/scheduling.py`（`adapt_interval` 保留，仅 `decide_review` 不再调用）、`tuning.py`、`repository/memory.py`、`models.py`、`tests/test_labeling_gate.py`（仅 browse 调用，兼容）。

## 6. 门禁与健康度（收口证据）

- 全量测试：**626 tests OK**（基线 613，+13）。
- `scripts/zkc_authority_check.py`：**0 unresolved leaks**（process boundary）。
- `make mcp-gate`（`tests.test_mcp_injection_gate`）：**6 OK**（CI 同口径）。
- `make invariant`（`scripts/check_invariant.py`）：**0 violations**（P1 meta_claim.evidence_refs / P2 无全局衰减开关 / P3 archived 退出调度回路）。
- roadmap 过程态 carrier `docs/plans/2026-11-14-zkc-verdict-semantics-roadmap.json` 节点 `1-3`（设计评审）/ `1-4`（TDD）及其子树已转 `completed`（非权威源，只作进度投影）。

## 7. 未决 / 后续

- Step 5 代码审查与证据复核、Step 6/7 文档与注释切片（含 `tuning.py:120-121` 注释方向偏差独立 doc-only 切片）尚未启动，需 Human 单独授权。
- `stale` 分支选择 / 内容载荷由 zj 逐条给，清除只映射 `archive`，无物理删除（DI-5）。
