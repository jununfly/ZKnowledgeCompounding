# 墓碑默认时刻时区 bug 修复证据（2026-11-16，独立 TDD 切片）

> 一次性缺陷修复证据。解决对象：`mark_tombstone`/`restore_node` 生产默认路径用 naive
> 本地时区（本机 UTC+8），与 sweep/daily 的 aware UTC cutoff 不一致 → 墓碑时刻被未来化 8h，
> `list_tombstones_before(now)` 恒扫不到（或 naive/aware 比较 TypeError）。

## 1. 缺陷定位（非本次 mark 操作引入，是 S3 遗留）

- `src/zkc/tombstone.py:32,55`：`at = at or datetime.now()`（naive 本地时区）。
- `src/zkc/sweep.py:41-42` + CLI：`now = datetime.now(timezone.utc)`（aware UTC）做 cutoff。
- 本机 TZ=UTC+8（实测 `time.timezone=-28800`）：第一次 mark 把 `17:20+00` 写进 `timestamptz`，而真实标记时刻是 `09:20 UTC` → 未来化 8h。
- 三重后果：
  1. PG `list_tombstones_before`（`deleted_at <= now`）对刚标的墓碑恒 false → `scanned=0`，月扫真删永远不会发生；
  2. memory 后端同比较直接 `TypeError: can't compare offset-naive and offset-aware datetimes`；
  3. TTL 7d 起算点偏 8h（违反 ADR-0013 Q5「TTL 从墓碑时刻起算」的精确语义）。
- 方向是「延迟/失效真删」不是误删，数据安全；但语义错误必须修。
- **测试盲区**：`test_tombstone_human`/`test_tombstone_sweep` 全部显式传 `at=self.now`（aware UTC），`test_cli_mark_and_restore` 虽走生产默认路径却只断言 `is not None`、不查 tzinfo → 全绿漏报。

## 2. TDD 红→绿

- 红测试：新增 `tests/test_tombstone_timezone.py`（3 条，专锁「不传 at」生产路径）：
  - `test_mark_default_time_is_aware_utc`：默认墓碑时刻必须 aware、offset=0；
  - `test_restore_default_time_is_aware_utc`：restore 对称守门；
  - `test_sweep_sees_freshly_marked_tombstone_via_default_path`：生产闭环，此刻 mark 的墓碑此刻 sweep 必扫到。
  - 修复前（UTC+8）：**2 FAIL + 1 ERROR**（ERROR 即 memory 后端 naive/aware TypeError），红证成立。
- 修复：`tombstone.py` import 加 `timezone`，两处默认 `datetime.now()` → `datetime.now(timezone.utc)`。storage 层未动（它只存传入的 at，问题在调用方默认值）。
- 绿：3 条新测试 + `test_tombstone_human`（6）+ `test_tombstone_sweep`（5）= 14/14 OK。

## 3. 已落两条墓碑的时刻校正（restore→remark，追加不涂改）

- 对象：`a5de32cd-a53b-4b8b-88e0-6aa0dccfd76e`（BestPractices）、`3f324c13-105d-4798-a054-e9ce28641ae5`（ClaudeAPIDocs）。
- 动作：每条 restore（清错误未来化墓碑）→ re-mark（`at=真实 UTC = 旧值 - 8h`）。审计链如实追加 `tombstone → restore → tombstone`，不涂改历史。
- 校正结果：两条 deleted_at 从 `17:20:02/17:20:06 +00` 回到 `09:20:02/09:20:06 +00`（真实 UTC）；version_seq 61→63；每条审计 `tombstone×2 + restore×1`，operator=zj。
- 验证：`zkc tombstone sweep --dry-run` 由修复前 `scanned=0` → **`scanned=2`、`eligible=0`**（TTL 未满，正确）、零写入。墓碑不可见性保持（daily --dry-run 不含这两条）。

## 4. 全量门禁

- `make test`：**670 tests OK**（667→670，+3 条时区回归）。
- `make invariant`：0 violations（P1/P2/P3 + P4 墓碑全路径不可见，11 实现）。
- `make mcp-gate`：6 OK。
- `scripts/zkc_authority_check.py`：0 leaks（274 durable sources）。
- 未改阈值 / REGISTRY；未 distill、未写 meta_claim；未对任何节点执行真删 purge；未 commit/push（等 zj 显式触发）。

## 5. 边界与教训

- 根因是「生产默认参数」与「测试注入参数」时区语义不一致——测试全注入 aware UTC 从没走默认分支，是典型盲区。修法：默认值本身必须是正确语义（aware UTC），测试再补一条走默认路径的回归。
- 更一般的护栏：凡 `datetime.now()` 进入持久化时间字段且会与 `datetime.now(timezone.utc)` 比较处，一律用 aware UTC。
