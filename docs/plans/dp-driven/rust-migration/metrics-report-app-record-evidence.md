# 证据 · metrics_report 走 A（app record 黑盒录制）验证

> 时间 2026-11-27 20:4x。对应 Q5=C 配套动作 ①、ticket 15 触发条件「app record --effects 基建就绪 → 仅对 metrics_report 走 A」。
> 结论：**A 路径的录制环节已验证可行**（可复现、DB effect 可捕获）；但录制可复现 ≠ Rust port 等价，见「边界」节。

## 做了什么

用 `rust-anything app record` 对 CLI 入口 `scripts/metrics_snapshot.py` 做黑盒录制（它内部调 `zkc.metrics.metrics_report(store)`）。为避免污染开发者历史库 `zkc_dev`（70 nodes），全程走独立库 `zkc_metric_record`（同容器 :55433，11 个 migrate 全绿）。

**录制基建**（`rust/metric-app/`）：
- `seed.py`：固定 UUID 的确定性 seed，TRUNCATE 后重建 5 nodes / 2 edges / 2 claims / 3 citations / 1 combine artifact，让五度量全非零且可手算验证。两次运行 DB dump 的 sha256 一致（`b23e5dfa...`），reset 幂等。
- `dump.sh`：`--db-dump` 命令，规范化输出 DB 状态作 effect。

**seed 的五度量预期值**（手算，已实测吻合）：
| 度量 | 值 | 来源 |
|---|---|---|
| connection_density | 0.75 | 动态 4 节点中 3 个被 reverse_link/derived_from 触达 |
| reuse_rate | 1.0 | 2 claims 均被 citation 引用 |
| citations_per_claim | 1.5 | 3 citations / 2 claims |
| methodology_output | 1 | 1 个 combine 产出的 artifact |
| decay_controllability | 0.6667 | 3 个到期动态节点中 2 个被引用或归档 |
| compounding_factor | 0.6292 | 0.25×(0.75+1.0+0.1+0.6667)，1-26 CALIBRATED 权重 |

## 验证读数

| 检查 | 结果 |
|---|---|
| `app record`（--db-reset --db-dump，2 inputs） | 5 cases（含 3 个 docstring 误抓的 `embed` 噪声 case，后剔除） |
| 有效 case | `pg-seeded`（stdout 五度量非零 + effects 带完整 db 快照）、`memory-empty`（恒 0） |
| `app replay`（原实现重放，收窄后） | **2/2 passed**，exit 0，failures [] |
| reset 幂等 | 两次 db-dump sha256 相同 |
| authority / invariant / mcp-gate | 0 leaks / 0 violations / 6 OK（见下） |

录制产物：`rust/app-cases/`（`pg-seeded.*`、`memory-empty.*`、`rust-anything.json`）。`rust-anything.json` 固化了 `db_reset`/`db_dump` 命令，replay 会重跑它们。

## 边界（必须如实读）

1. **录制可复现 ≠ Rust 等价**。`app replay` 不带 `--build` 时跑的是**原 Python 实现**，5/5（收窄后 2/2）通过只证明「录制对原实现可复现、DB effect 稳定」，**没有任何 Rust 代码参与**。
2. **A 录的是 CLI 黑盒，不是 `metrics_report` 函数级契约**。case 只覆盖 `metrics_snapshot.py` 的 stdout/exit + DB 快照，不覆盖 `metrics_report(store)` 的入参/返回值边界，也不覆盖 `build_report_dict` 之外的 `rot_rate` 等函数。
3. **要证明 Rust 等价仍需完整链路**：`app front-door` → 把 gate 通过的 Rust unit `wire` 进去 → `app replay --build`。且 Rust 侧必须实现 `load_metric_inputs` 的 PG 查询（5 张表快照）+ 五度量，才能在同一 DB 上匹配 stdout 与 effects——这远超「只 port `metrics_report` 一个函数」。因此 A 的真实成本比 Q5 讨论时估计的更高，进一步印证 C 的收窄是对的。
4. **只证明录制到的输入**：seed 是人工构造的确定性组合，真实历史库 `zkc_dev` 的 70 nodes / 边界分布未录；不得据此声称覆盖生产数据形态。
5. 权重/目标常量是 1-26 CALIBRATED seed（0.25×4、target=10），本轮只读未改、不 promote。

## 下一步（ticket 15 触发条件已部分满足）

触发条件「app record --effects 基建就绪」**已满足**（seed/dump/case/replay 全通）。剩余选择：
- **A 继续**：做 `app front-door` + wire Rust unit，让 `app replay --build` 有 Rust 对照——前提是愿意承担上述完整链路成本（含 PG SQL 查询层）。
- **维持 C**：以本证据作为「A 已验证录制可行、但等价成本过高」的 durable 记录，8 函数继续暂留 Python，tk8 只交付标量层。

不代答，待 zj 拍板。
