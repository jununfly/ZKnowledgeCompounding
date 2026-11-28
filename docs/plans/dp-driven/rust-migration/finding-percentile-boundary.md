# Finding · `_percentile` L2 预算分位数纯数学可证边界（ticket 8 下一片）

> 归属：task2 / ticket 8。发现时间 2026-11-28。过程态观察，不替代架构 §6.5 / ADR-0010。

## 为什么这一片

ticket 8 已交付 14 个 crate（decay / metrics 标量 / transport / context / expiry / scheduling
interval / faithfulness rubric / routing tfidf / cross-source / distill parse / r14 judgment /
artifact shaping / injection detection）。`scheduling.py::estimate_budget_from` 是 L2 删失感知
预算点估计（confidence: observed / provisional / lower_bound / none），其核心数学是私有 helper
`_percentile(values, q)`——对饱和日的 completed 值求分位数。

**公开调用者 `estimate_budget_from` 吃 `list[AttentionObservation]` dataclass 缝，按
`finding-interval-math-boundary.md` / `finding-metrics-boundary.md` 不能 unit port；因此
`_percentile` 无法由公开函数 case 间接证明，值得独立成片。**

这不是对既有边界的翻案：
- `finding-interval-math-boundary.md` 排除的私有 helper 是 `_aimd_factor` / `_rule_days`——
  它们读 `tuning.get` 全局状态；`_percentile` 不读 tuning、无全局状态、无 dataclass / Storage /
  LLM / datetime 缝。
- `finding-metrics-boundary.md` 暂留的是吃 `MetricInputs` dataclass 的 5 个度量；`_percentile`
  是全标量 / JSON-native 入参。

## 可证函数（本片）

| 函数 | 层 | 入参 | 出参 | 备注 |
|---|---|---|---|---|
| `_percentile` | L2 预算分位数 | `values: list[float]`, `q: float` | `float` | 内部 sorted；线性插值；单元素快路径 |

精确语义（Python 原实现逐字录自 `src/zkc/scheduling.py`）：

```python
s = sorted(values)
if len(s) == 1: return float(s[0])
pos = q * (len(s) - 1)
lo = int(pos)
hi = min(lo + 1, len(s) - 1)
frac = pos - lo
return float(s[lo] + (s[hi] - s[lo]) * frac)
```

边界：
- 空列表 → `IndexError: list index out of range`（`s[0]` 或 `s[lo]`），需录异常文本。
- 单元素 → 快路径返回该元素（`q` 被忽略）。
- `q=0` / `q=1` → 首 / 末元素。
- 一般 `q` → `pos = q*(n-1)`，`int(pos)` 截断向下，`frac = pos - lo`，线性插值。
- 未排序入参 → 原实现先 `sorted`，返回值与顺序无关。
- Python `int(pos)` 对浮点负数向零截断；`q` 通常 ∈ [0,1]，但录制可覆盖越界 `q`。

## 与既有能力的分工

- `estimate_budget_from` 的间接业务测试锚点：`tests/test_scheduling.py` 的
  `estimate_budget_from` 饱和日 p90 估计（confidence / estimate 断言）——证明 `_percentile`
  在真实口径下被调用；本片只证函数级逐字等价，不冒充公开函数行为。
- 浮点精度：Python `float` 与 Rust `f64` 同为 IEEE 754 双精度，`q*(n-1)` / `int` 截断 /
  插值乘法需逐位对齐；由录制 case（含 0.9 / 0.5 / 0.0 / 1.0 与多元素）机械对照。
- 无 recorded-literal 阈值（q 与 values 都是入参），无 CALIBRATED 提升问题。

## 排除

- `estimate_budget_from` / `update_budget_from` / `labeling_rate_from` 等吃 dataclass 的函数仍留 Python。
- `tuning` 全局状态（MIN/MAX_INTERVAL、AIMD、ROT_THRESHOLD 等）不由本片触碰。
- 只 port 不 wire（接线另起 ticket）。
