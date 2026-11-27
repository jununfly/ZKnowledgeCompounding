# Finding · scheduling 的 interval 纯数学可证边界（ticket 8 下一切片）

> 归属：task2 / ticket 8。发现时间 2026-11-27。过程态观察，不替代架构 §6.5。

## 为什么先切这一片

ticket 8 是「核心 domain + repository 迁移」。已完成的 5 个切片（decay 标量、metrics 标量、
transport、context、expiry 决策表）都没有触碰 interval 三层主线。`scheduling.py` 里有
一组**全标量/JSON 入参、无 Storage 依赖**的纯函数，正好覆盖架构 §6.5 的 L1 基线、
L3 AIMD 与 L2 目标，风险低于直接啃 `SchedulableNode`/`AttentionObservation` 数据类层。

## 可证函数（本切片）

| 函数 | 层 | 入参 | 备注 |
|---|---|---|---|
| `extract_horizon_days` | L1 时间锚 | `text` | 中英文规则表，多条锚取最早 |
| `clamp_days` | L1 钳制 | `days` | MIN/MAX 走 `tuning.get` |
| `baseline_for_signals` | L1 基线 | 8 个标量 | 返回 `{days, reason, tier}` |
| `classify_review` | L3 分类 | `decay_at_review` | too_early/on_time/too_late |
| `adapt_interval_math` | L3 AIMD | `old_days, verdict, human` | 含 floor_hit 语义（ADR-0009） |
| `l2_target` | L2 目标 | `budget, confidence` | oversubscribe ×1.5；**生产无调用者** |

## 明确排除（不是本切片）

- 吃 `SchedulableNode` / `AttentionObservation` / `Storage` 的函数：与
  `finding-metrics-boundary.md` 同类——PyO3 JSON bridge 不编码 dataclass/Storage，
  硬录只会得到桥失败异常文本，不能冒充行为覆盖。
- `days_to_interval` 返回 `timedelta`，同样过不了 JSON bridge；如需迁，另起适配器切片。
- 私有 helper（`_aimd_factor` / `_rule_days` 等）不单独 port，其行为由公开函数 case 覆盖。

## 证据与语义纪律

- 录制期 Python 原实现为唯一 oracle；Rust 侧只做 diff/gate 回归。
- 阈值全部来自 `zkc.tuning`：`MIN_INTERVAL_DAYS=0.25`(CALIBRATED)、
  `MAX_INTERVAL_DAYS=180`(SIMULATION)、`BASELINE_{SELF_LOOP,CAPTURED,CONNECTED,ORPHAN}_DAYS`
  = 3/28/14/7(placeholder)、`EARLY_THRESHOLD=0.3`、`ROT_THRESHOLD=0.9`(SIMULATION)、
  `AIMD_UP=1.5`、`AIMD_DOWN=0.7`、`OVERSUBSCRIBE_FACTOR=1.5`(SIMULATION)。
  Rust 侧一律标 `recorded-literal`，**不 promote 成 CALIBRATED**；`CALIB_OVERRIDE_AT` caveat 仍有效。
- 字符串 reason 含 Python `:g` 渲染（如 `3d`、`0.9d`），必须按录制 case 逐字对齐。
- 与既有偏差一致：`l2_target` 无生产调用者，`apply_distill` / `faithfulness.gate_new_claims`
  的未接线状态不得因本切片被误读成运行时保证。
