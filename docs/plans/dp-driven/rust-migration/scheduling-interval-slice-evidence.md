# scheduling interval 纯数学切片（ticket 21）

日期：2026-11-27。过程态证据，非长期权威；架构 §6.5 与 `zkc.tuning` 才是阈值来源。

## 范围

`rust/scheduling-interval-rs` port 了 `src/zkc/scheduling.py` 的 6 个公开纯函数：

| 函数 | 层 | 作用 |
|---|---|---|
| `extract_horizon_days` | L1 时间锚 | 中英文规则表，多条锚取最早，0 天锚被过滤 |
| `clamp_days` | L1 钳制 | MIN/MAX interval，Python `min/max` 的 NaN 比较顺序 |
| `baseline_for_signals` | L1 基线 | self_loop > captured > connected > orphan，horizon 优先 |
| `classify_review` | L3 分类 | too_early / on_time / too_late |
| `adapt_interval_math` | L3 AIMD | ×1.5 / ×1.0 / ×0.7，human 豁免，floor_hit |
| `l2_target` | L2 目标 | 未确认期 ×1.5；**生产无调用者** |

按 `bridge --keep` 明确留在 Python：18 个吃 `SchedulableNode` / `AttentionObservation` /
`Storage` 的编排函数，以及返回 `timedelta` 的 `days_to_interval`。私有 helper
（`_aimd_factor` / `_rule_days` 等）不单独 port，由公开函数 case 覆盖。

## 红 → 绿过程

1. 直接桥 `src/zkc/scheduling.py`，`record --count 200 --inputs tmp/scheduling-inputs.jsonl`
   得 1244 case。首版 port diff **1204/1244**，两类差异：
   - `adapt_interval_math(human=True)` 原实现原样返回入参：int 入参返回 int，NaN/Inf 用
     `$num`；Rust `f64` 绑定只能发 `$float` / null。
   - `baseline_for_signals` 的 `BASELINE_*` 在 tuning 里是 int，Rust 常量是 f64。
2. 新增 **process-only** 适配器 `spikes/spike-09-review-interval/pure_bridge.py`：只把数值入参
   与 `days` 结果规范成 float，决策逐字委托原实现；重桥后 `record --count 0 --inputs ...`
   得 **208 个定向 case**（49 horizon / 14 clamp / 19 baseline / 12 classify / 84 AIMD / 30 L2）。
   `--count 0` 是关键：工具默认随机生成器会把任意 JSON 值喂给无类型标注的适配器，
   产生“Python 原实现提前返回、Rust 有类型绑定抛 TypeError”的桥伪差异，不能作为 oracle。
3. Rust 侧 `json_f64` 显式写 `$num` 标记；`py_min` / `py_max` 按 Python 比较顺序处理 NaN；
   `py_g` / `py_float_str` 复刻 reason 文本；未知 verdict 的 `KeyError` 用 `py_repr` 对齐。
   diff **208/208**。
4. gate 两处红：size 5.9x（薄适配器 53 行）；literals 18 个。把录制词表、reason 原文、
   决策表与边界写进适配器文档（120 行），并在 port 常量同行加 `recorded-literal` 注释后，
   gate 全过：size 2.6x、literals 0、behavior 208/208。

## 机械验证

| 检查 | 结果 |
|---|---|
| `rust-anything diff` | **208/208 recorded cases match** |
| `rust-anything gate` | **Gate passed**（fmt / clippy / cargo test / unsafe / lockfile / ported / size 2.6x / literals / tests / error cases / panics / build / api / behavior） |
| `app replay --build` | 既有 11 case **11/11，fallback 0.0%**（本切片未接线，零回退） |
| `make test` | 671 tests OK |
| `make mcp-gate` / `make invariant` / `zkc_authority_check.py` | 6/6；0 violations；0 leaks（扫描 982 个 durable source） |

## 工具约束（下次复用）

- `bridge` 重写 `Cargo.toml` 会丢手加的 `regex = "1"`；`refresh` 重写 `src/lib.rs` 会丢
  `use serde_json::Value;`。新增 `restore_lib_patch.py` 幂等恢复两者，实测连续两次
  `already patched`；纪律：`bridge` / `refresh` 后先跑脚本再 gate。
- 修改适配器 `.py` 文件（哪怕只改文档）会让 gate 的 `recording` 检查失效，必须重录：
  `record --count 0 --inputs tmp/scheduling-inputs.jsonl`。
- port 返回 `Value` 时生成绑定会漏 `Value` import，这是工具 bug，不要误判为 port 错误。

## 边界（不可写成什么）

- 只证明 **6 个纯函数在 208 个录制输入上**与 Python 原实现逐字一致；不是整个
  `scheduling.py` 等价，更不是生产调度循环（Storage 编排层全部留 Python）。
- 所有阈值都是 `recorded-literal`：`MIN_INTERVAL_DAYS=0.25` 虽是 CALIBRATED，但
  `CALIB_OVERRIDE_AT` caveat 仍有效；其余为 placeholder / SIMULATION，未 promote。
- `l2_target` 无生产调用者；不得把该 port 写成运行时保证。
- 适配器是 process-only 录制工具，不是迁移目标；本切片**未 wire 进 `rust/app`**。
- `src/zkc/**` 零改动；未 commit/push（本证据写在 checkpoint 提交之后）。
