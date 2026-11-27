# metrics_snapshot 黑盒 case 扩展：11 case 覆盖与 float32 边界 bug

> 2026-11-27 · 过程态证据（**非 durable 权威**，closeout 随 `docs/plans/` 删除）。
> 承接 `metrics-report-rust-equivalence-evidence.md`（2 case → 本轮 11 case）。

## 结论（一句话）

把 CLI 黑盒 case 从 **2 个扩到 11 个**（10 个 PG 变体 + memory），`app replay --build`
**11/11 passed、fallback 0.0%**。扩覆盖**抓到并修复了一个真实 bug**：
PG `real`（float32）列经 `::float8` 会把 0.9 展开成 0.8999999761581421，
导致 Rust 侧 decay 边界比较 `>= 0.9` 失败（`decay_controllability` 1.0→0.0，
`compounding_factor` 0.75→0.5）；原 2 case 覆盖不到这条边界。

## 10 个 PG 变体（覆盖的分支）

| case | 覆盖分支 | cd / rr / per / mo / dc / cf |
|---|---|---|
| `pg-seeded` | 五度量全非零（原 case） | 0.75 / 1.0 / 1.5 / 1 / 0.6667 / 0.6292 |
| `pg-empty` | 全空库，所有除零 guard | 0 / 0 / 0 / 0 / 0 / 0 |
| `pg-static-only` | 无动态节点：cd、dc 的 dyn 空集 guard | 0 / 0 / 0 / 0 / 0 / 0 |
| `pg-no-edges` | 有动态节点但无 qualifying 边：cd=0 | 0 / 0.5 / 0.5 / 0 / 0 / 0.125 |
| `pg-all-connected` | cd 饱和 1.0 | 1.0 / 1.0 / 1.0 / 0 / 0 / 0.5 |
| `pg-expired-unhandled` | 到期但无 handled：dc=0 | 0 / 0 / 0 / 0 / 0 / 0 |
| `pg-all-handled` | dc 饱和 1.0 | 0 / 1.0 / 1.0 / 1 / 1.0 / 0.525 |
| `pg-method-saturated` | mo=12 > target 10：mo_norm 饱和 | 1.0 / 1.0 / 1.0 / 12 / 0 / 0.75 |
| `pg-citation-heavy` | per=2.0（引用强度 >1） | 1.0 / 1.0 / 2.0 / 0 / 0 / 0.5 |
| `pg-decay-boundary` | decay **恰好 0.9** 算 expired（本次 bug） | 1.0 / 1.0 / 1.0 / 0 / 1.0 / 0.75 |

## 发现的工具约束（必须记住）

**`app record --db-reset` 不继承 case 的 `env`**。最初把 `ZKC_SEED_VARIANT` 放在 case 的
`env` 里，10 个 pg case 录出来全是 seeded（effects 哈希机械核对证实：10/10 都等于
seeded 的 b23e5dfae2…）。**解法**：把变体写进 case 的 `files`（`variant.txt`），
seed.py 优先从 cwd 的该文件读取；db-reset 在 case 工作目录里跑，能读到。改后
10/10 变体的 effects 哈希精确命中预期（`pg-empty` 的 effects 只有 `b'db\n'` 头，
哈希口径差一个尾随换行，但 cf=0.0 正确）。

## 红→绿：float32 边界 bug

- **现象**：`pg-decay-boundary` case，Rust 输出 dc=0.0 / cf=0.5，原实现 dc=1.0 / cf=0.75。
- **定位**：`decay_score` 列是 PG `real`。`decay_score::float8 = 0.9::float8` 在 PG 里为
  **false**（float32 的 0.9 = 0.8999999761581421）；psycopg 读 real 列则返回 Python
  float 0.9（精确），`>= 0.9` 为真。Rust 的 `::float8` cast 与原实现精度语义不同。
- **修复**：SQL 改 `COALESCE(decay_score, 0)::numeric::float8`——经 numeric 保留显示精度，
  与 psycopg 一致。PG 验证：`0.9::numeric::float8 >= 0.9` → t，`0.8999` → f。
- **回归**：11/11 replay 全过。

## 验证读数

| 检查 | 结果 |
|---|---|
| 原实现 `app replay`（11 case） | **11/11 passed** |
| Rust `app replay --build`（11 case） | **11/11 passed，fallback 0.0%** |
| 每变体 dump 幂等 | 10/10（同变体两次 sha256 相同） |
| case effects vs 预期变体哈希 | 10/10 命中（pg-empty 仅尾随换行口径差） |
| clippy `-D warnings` / fmt check | pass |
| `make test` | 671 OK |
| authority / invariant / mcp-gate | 0 leaks / 0 violations / 6 OK |

## 边界（仍成立）

1. 11 个 case 都是**CLI 黑盒**（stdout/exit/DB effects），不是 `metrics_report` 函数级契约。
2. 变体是**人工设计的边界态**，不是生产流量回放；真实数据形态仍未覆盖。
3. 8 个 dataclass/Storage 函数仍未逐个 port；本轮只加强既有 CLI glue 的证明密度。
4. 常量仍标 `recorded-literal`，未 promote。
5. `zkc_dev`（70 nodes）全程未污染，录制只用独立库 `zkc_metric_record`。
