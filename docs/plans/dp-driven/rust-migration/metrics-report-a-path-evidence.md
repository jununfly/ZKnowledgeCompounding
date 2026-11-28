# 证据 · ticket 45：metrics_report A 路径迁移收口

日期：2026-11-28。ADR-0014 的工作承载 ticket（task 4，derived-from finding 22）。
前置：`metrics-report-app-record-evidence.md`（录制基建验证，11-27）。

## 结论

**ticket 45 完成**：`metrics_report(store)` 的 A 路径迁移（front-door Rust glue +
PG 查询层）已通过 11 case 黑盒对照，`app replay --build` **11/11 passed、fallback
0.0%**（2026-11-28 复跑确认）。

## 链路（f7 模式完整落地）

```
scripts/metrics_snapshot.py（Python oracle CLI，连 zkc_metric_record @ zkc-spike-pg:55433）
  → rust-anything app record（--db-reset/--db-dump 固化 seed 与 effect）
  → rust/app/src/units/metrics_report.rs（Rust 实现：5 条 PG 查询 + 四度量 + py_round4 + compounding_factor）
  → rust-anything app replay --build <metrics-snapshot 二进制>（Rust 对照录制 case）
```

- **Rust glue**（`rust/app/src/units/metrics_report.rs`）：复刻
  `pg.py::load_metric_inputs` 的 5 条查询（含 decay float32 边界的
  `::numeric::float8` cast 缝）、`connection_density`/`reuse_rate`/
  `methodology_output`/`decay_controllability`、`py_round4`（banker's rounding）、
  `build_report_dict` 输出形态（cf 吃未舍入 raw 值）、1-26 CALIBRATED 权重
  recorded-literal。
- **录制基建**（`rust/metric-app/seed.py` + `dump.sh`）：确定性 seed（固定 UUID、
  TRUNCATE 重建、两次 dump sha256 一致）+ DB effect 快照。

## 验证读数（2026-11-28）

| 检查 | 结果 |
|---|---|
| `app replay --build rust/app/target/debug/metrics-snapshot` | **11/11 passed，fallback 0.0%** |
| case 场景覆盖 | empty / seeded（五度量非零手算吻合）/ static-only / no-edges / all-connected / all-handled / method-saturated / citation-heavy / decay-boundary（0.9 float32 缝）/ expired-unhandled / memory-empty |
| DB effect | 每 case 带 db-dump 快照（reset 幂等） |
| 前门回退 | fallback 计数 0（无 case 落回 Python CLI） |
| authority / invariant / mcp-gate | 见当日收口快照（0 / 0 / 6 OK） |

## 边界（诚实读法，承 ADR-0014）

1. 这是 **CLI 黑盒级等价证明**：证明 Rust 前门在同一 DB 上与 Python 原实现
   stdout + DB effect 逐字一致；不构成 `build_report_dict` 内部 6 个
   `MetricInputs` 函数的 unit-level port（它们的 glue 重写由黑盒覆盖，ADR-0014
   已定性 7 函数永久留 Python、unit-level 不做）。
2. case 输入是人工构造的确定性组合，不冒充覆盖生产 `zkc_dev` 数据形态。
3. 权重/target/ROT 常量为 recorded-literal（1-26 CALIBRATED seed），不 promote。
4. 本 ticket 交付可证迁移，**不是 lift**：生产 `src/zkc/**` 零改动。
