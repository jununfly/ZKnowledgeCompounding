# 证据 · metrics 标量切片（ticket 8 子切片）

> 2026-11-27。可证范围：`compounding_factor`（`src/zkc/metrics.py:99`）。
> 录制期 oracle = Python 原实现；Rust 单测仅作日常回归（Q3 口径）。

## 机械读数

| 检查 | 结果 |
|---|---|
| `rust-anything bridge --keep ×8` | 仅导出 `compounding_factor`，其余 8 函数声明留 Python |
| `rust-anything record rust/metrics-scalar-rs --count 200` | 243 cases（93 threw，均为原实现故意的异常路径） |
| `rust-anything diff` | **243/243 match，0 mismatch**（红→绿：首轮 226/243，修 `NaN` truthiness 与左到右求值顺序后全绿） |
| `rust-anything gate` | **全 pass**：fmt / clippy / cargo test / unsafe(0) / lockfile / ported / size(0.9x) / literals / tests / error cases / panics / build / api / behavior(243/243) |
| `cargo test` | 10 passed（含 8 个从 `test_metrics.py` 语义译来的回归测试 + 2 个工具自带） |
| `make test`（Python 全量） | 见当日日志（本文件不重复易变的 test count） |

## 红→绿的两处真实语义修复（都是 Python 语义，不是凑数）

1. **`if method_target` 的 NaN truthiness**：CPython 中 `NaN` 为真值 → `min(1.0, mo/NaN)=1.0`；Rust 初版排除了 NaN 导致结果差 0.25（case `method_target=$num:NaN`）。修正为 `target != 0.0` 判定，`f64::min(1.0, NaN)` 与 CPython `min` 一致。
2. **权重乘法的左到右求值**：`weights[0]*cd + weights[1]*rr + ...` 逐项「取索引→乘」。初版先取全部 4 项，`weights=["a",1]` 时在 `get(2)` 抛 IndexError，而 CPython 在第 0 项 `"a"*inf` 就抛 TypeError。修正为循环内逐项取乘，错误优先级与 CPython 一致（15 个 case 由红转绿）。

## 边界（不可写成"metrics 模块等价"）

- 只证明 `compounding_factor` 的**录制输入**；其余 8 函数因 dataclass/Storage 过不了 JSON bridge 留在 Python，见 `finding-metrics-boundary.md`。
- 常量 `METRIC_W_*=0.25 ×4`、`METRIC_METHOD_TARGET=10.0` 是 1-26 的 CALIBRATED seed，port 中标注 `recorded-literal`，不 promote、不写回 REGISTRY。
- `build_report` / `build_report_dict` / `rot_rate` / `decay_controllability` 的口径仍未有 Rust 对应实现；本切片**不**覆盖复利系数之外的四个度量。

## 产物

- `rust/metrics-scalar-rs/`：gate 通过的 crate（port + 243 case + bindings + 回归测试）。
- `rust/metrics-rs/`：全量桥接草稿（不交付，仅对照桥边界）。
- 源码零改动；`src/zkc/**` 未修改。
