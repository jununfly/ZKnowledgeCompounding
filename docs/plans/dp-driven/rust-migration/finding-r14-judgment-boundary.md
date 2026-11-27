# Finding · judge_r14 的可证边界（风险册 R14 判据落地）

> 归属：task2（核心 domain + repository 迁移）、ticket 8。发现时间 2026-11-28。
> 类型：纯函数可证切片（无产品行为缺陷）。结论为过程态，durable 定性以 risks.md R14 行为准。

## 观察

`src/zkc/cross_source.py::judge_r14(runs, *, min_runs=10)` 是纯函数：不读 IO、不碰 DB、不改入参，
把一组跨源补全 run 的 report dict 聚合成 `R14Verdict` dataclass。tests/test_r14_judgment.py
以 7 个 case 覆盖全部 reason 分支（`trigger_rate_and_latency_exceed_budget` /
`trigger_rate_within_budget` / `completion_latency_within_budget` / `no_completion_fired` /
`insufficient_data` / 自定义 min_runs / 入参不变性）。

判据（risks.md R14 / 架构 §8）：触发率 > 0.5 且 completion 延迟中位 > 主生成延迟中位 × 1.5
→ 关补全；数据不足（total < min_runs 或补全延迟缺失）一律保持 open 并给出 reason，
绝不伪造裁决。

## 编码缝（process-only alias）

- **dataclass 返回**：`R14Verdict` 是普通 dataclass，PyO3 wrapper `_enc` 不编码，会回退 `$repr`；
  alias 将返回结构编码为字段固定的 dict（total / fired / trigger_rate /
  completion_latency_median / main_latency_median / should_close_completion / reason），
  决策逐字委托 Python 原实现。
- **keyword-only 参数**：`min_runs` 在 Python 是 keyword-only；alias 暴露为第二位置参数并
  内部还原为 `min_runs=` 关键字（同 scheduling spike-09 的 `human=` 归一）。
- **median 语义**：`statistics.median` 奇数取中位、偶数取两中平均；Rust port 须精确复现
  排序 + 奇偶分支，浮点除法一致性由 recorded case 保证。

## 处置

新增 ticket 31（parent 8，blocks `31→8`）：定向录制（20 case、0 throw、无随机 JSON 伪差异）后
port 到 Rust；只以录制 case 全匹配（20/20）+ gate 通过为完成判据。**不接线进 `rust/app`**，
不触碰 `src/zkc/**`。阈值 0.5 / 1.5 / min_runs 默认 10 标 recorded-literal，不 promote 为 CALIBRATED
（判据来自 risks.md R14，非 tuning 校准参数）。已收口：ticket 31 完成并释放租约，证据
`r14-judgment-slice-evidence.md`；finding 作为观察 memo 保留未完成。

## 边界（不得读成）

- 这不是 R14 关闭的运行时保证：真实 run 仍由 zj 经 dogfood 脚本产生、经 `r14_telemetry` 落库，
  本 port 只证判据函数的确定性聚合，不伪造 completion_fired / 延迟，也不触发关闭动作。
- 录制 case 是人工定向输入，非全输入空间；NaN/Infinity 等极端浮点若未录制不得声称覆盖。
- `r14_telemetry`（文件 IO / append-only 落库）、`combine` / `apply_combine`（LLM + Storage）
  留 Python；Q5=C 的 dataclass/Storage 编码边界未被翻案。
