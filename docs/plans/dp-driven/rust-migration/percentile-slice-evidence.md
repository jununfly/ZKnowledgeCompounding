# Evidence · `_percentile` L2 预算分位数纯函数切片（ticket 37）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与 kill switch 语义仍以 crate 实现为准。
架构口径（L2 预算校准 / 删失感知点估计）真相源是架构 §6.5 + `src/zkc/scheduling.py`，本切片只做逐字回放。

## 结论

`src/zkc/scheduling.py::_percentile`（L2 预算分位数）已 port 到 Rust `rust/percentile-rs`，**未接线进 app**。
DP：finding 18 + ticket 37（parent 8，derived-from 18，blocks `37→8`）完成并释放租约，ticket 8 仍是唯一活跃租约。

## 选片理由

- `estimate_budget_from` 是 L2 删失感知预算点估计（confidence: observed/provisional/lower_bound/none），
  核心数学是私有 helper `_percentile`（对饱和日 completed 值求分位数）。
- 公开调用者 `estimate_budget_from` 吃 `list[AttentionObservation]` dataclass 缝，按既有边界不能 unit port；
  因此 `_percentile` 无法由公开函数 case 间接证明，值得独立成片。
- 不违反 `finding-interval-math-boundary.md`（其排除的私有 helper `_aimd_factor`/`_rule_days` 读 tuning 全局状态；
  `_percentile` 无全局状态、无 dataclass/Storage/LLM/datetime 缝）与 `finding-metrics-boundary.md`
  （其暂留的是吃 `MetricInputs` dataclass 的 5 个度量）。

## 实现与录制

- 新 crate `rust/percentile-rs/`：port 单函数。逐字对应 Python 语义：内部 `sorted`、
  单元素快路径（`q` 被忽略）、`pos = q*(len-1)`、`int(pos)` 向零截断（Rust `as i64` 同义）、
  `frac = pos - lo`、`s[lo] + (s[hi]-s[lo])*frac`；空列表返回 CPython `IndexError: list index out of range`。
- 数值解码兼容 `{"$float":"N.0"}` / `{"$int":"N"}` marker（录制桥对整数值 float 的表示），
  普通 JSON number 直接取 `as_f64`；负索引兜底覆盖越界 q（录制的 q=-0.5 / 1.5 case）。
- 新 alias `spikes/spike-21-percentile/pure_bridge.py`：纯委托原函数（无编码缝，
  暴露名 `percentile` 去掉下划线前缀以固定单函数录制面，避免整包 bridge 混合 scheduling 的 dataclass 函数）。
- 16 个定向录制 case：`record --inputs --count 0`，覆盖空列表异常、单元素快路径（q=0.9/0.0）、
  q=0/1/0.5、多元素 p90（3/5 元素）、未排序输入、重复值、负数、分数 q、越界 q（负/ >1）。

## 验证

| 检查 | 结果 |
|---|---|
| crate diff | **16/16** cases match |
| crate gate | Gate passed（size 1.8x，literals 0，无 recorded value 字面量） |
| app replay（11 case） | 11/11，fallback **0.0%**（未接线，零回退） |
| make test | **671 OK** |
| 三门禁 | mcp-gate 6/6 / invariant 0 violations / authority 0 leaks |

gate literals 0：异常文本是 CPython 通用 `IndexError` 文本（非录制的业务常量），不被判为 recorded value。

## 边界与风险

- 本片只证函数级逐字等价，**不冒充** `estimate_budget_from` 公开函数行为；
  其 dataclass 缝函数（含 `update_budget_from` / `labeling_rate_from`）仍留 Python。
- 无 recorded-literal 阈值（q / values 都是入参），不涉及 CALIBRATED 提升；tuning 全局状态未被本片触碰。
- 浮点对齐依赖 IEEE 754 双精度与 `int` 向零截断语义；多元素 / 分数 q case 已机械覆盖。
- `src/zkc/**` 零改动；未翻任何既有边界 finding 的案。
