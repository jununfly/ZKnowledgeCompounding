# D2 导入语料隔离 · 真实 PG 清理留痕（2026-11-05）

## 前置发现的真实缺陷

`list_due_for_review` 在 `src/zkc/repository/pg.py` 与 `memory.py` 双实现里
**都没有过滤 `archived_at`**：只调 `nodes.archive()` 并不能把节点移出复审队列。
本轮先修双实现（加 `archived_at IS NULL` / `n.archived_at is not None: continue`），
再执行批量归档，否则清理动作无效。

## 识别口径（等价字段，未新增 schema 列）

动态轨 + `decay_score=1.0` + `review_interval=1 day`
+ `last_reviewed_at` 日期为 `2026-11-01` + `archived_at IS NULL`。
这是导入语料的派生特征；归档本身（`archived_at` + 本留痕）即后续可识别标记。
**边界**：该口径按历史批次识别，未来新导入语料若形态不同需另补结构化 `corpus_tag` 列。

## 命令与结果

```text
python -m zkc.cli archive --corpus --dry-run --json    # matched=24, archived=0, dry_run=true
python -m zkc.cli archive --corpus --json              # matched=24, archived=24
```

| 指标 | 清理前 | 清理后 |
|---|---|---|
| due（旧口径，含归档） | 24 | 24 |
| due（新口径，排除归档） | 24 | **0** |
| `attention_observation` 行数 | 1 | 1 |
| `review_queue` open 条目 | 0 | 0 |
| `archived_at IS NOT NULL` 节点 | 0 | 24 |

`labeled_touched=0`、`attention_observation_touched=0`、`review_queue_resolved=0`：
**未写任何标注、未动校准埋点、未伪造成人审结果**，标注率闸门不受污染。

## 数字偏差（不静默套用旧值）

节点 notes 记「27 条导入语料」，本轮真实 PG 复核为 **24 条**，且清理前
`due_total=24` —— 到期队列**全部**是这批语料。以本次实测为准，不改写历史条目。

## 对 E1 的影响（如实声明）

归档后 `queue_remaining` 会从 24 降为 0，进入「空队列日豁免」口径
（ADR-0007：空队列日不破不断）。本轮**未**新增任何 `attention_observation`，
E1 三判据仍由既有真实埋点决定；批量清理不得被计入 E1 达成证据。

## 可逆性

`archive` 只写 `archived_at`（不动历史行、不删数据），需要恢复时可按
`archived_node_ids` 将该列置回 NULL；本轮不提供自动 unarchive 命令。

## 完整性补强（2026-11-05 23:25，zj 再点「D2 藏着真 bug」）

上一轮修的只是 **due 查询** 一层；复核发现归档节点仍未完全退出调度回路：

1. `decay.refresh_decay` 走 `list_by_track("dynamic")`，而该方法在 pg / memory 双实现
   **都不过滤 `archived_at`** → 每次打开 `/review`、跑 `zkc decide --list`、
   `record_daily_observation_auto` 都会把归档节点重算 decay 并 `update_decay` 写回
   （无谓写放大 + `version_seq` 空转）。本轮在 `refresh_decay` 里跳过归档节点。
2. PG 侧原本只有**静态源码断言**（`assertIn("archived_at IS NULL", body)`），
   不能证明 SQL 真跑通。本轮新增 `PgArchiveExitTest` 真实 PG 集成测试：建独立迁移库、
   造到期节点、归档，断言 `list_due_for_review` 只返回活跃节点，且 `refresh_decay` 的
   `update_decay` 调用只落在活跃节点上。
3. 契约与防回归：`protocols.NodeRepository.list_due_for_review` docstring 固化
   「必须排除 archived_at」硬契约；`scripts/check_invariant.py` 新增 **P3 谓词**，
   扫 `repository/*.py` 的每个 `list_due_for_review` 实现 + `decay.refresh_decay`，
   缺过滤即 `E_INVARIANT_ARCHIVE_EXIT` 非零退出，由 CI 的 `invariant (rec-avoid)` job 守门。

TDD：新增 `tests/test_archive_exit_scheduling.py` 7 条用例，缺陷态 6 红 → 修复后
17 条（含既有 check_invariant 10 条）全绿；真实仓库 P3 检查 4 个实现、0 violations。
