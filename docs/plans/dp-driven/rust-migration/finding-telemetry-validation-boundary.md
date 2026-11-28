# Finding 20 · `_validate_report` R14 遥测字段闸的可证边界（ticket 8 / task 2）

> 2026-11-28。类型：纯函数可证切片（无编码缝）。归属 task 2，派生 ticket 41。
> 本 finding 是边界盘点与切片授权，不是等价证明；子 ticket 须各自有 cases.jsonl + diff/gate 证据才允许置「已完成」。

## 结论

`src/zkc/r14_telemetry.py::_validate_report` 是一个此前被"r14_telemetry 无直接测试"笼统带过、
但**实际干净可证**的纯函数：入参 `dict`、返回 `None` 或抛 `ValueError`，全 JSON-native，
无 dataclass / Storage / 文件 IO / datetime / LLM / callable 缝。port 到 `rust/telemetry-validation-rs`，
16/16 diff、gate passed。

## 为何不翻任何既有 finding 的案

- `finding-r14-judgment-boundary.md:42` 把 `r14_telemetry` 整体标注为"文件 IO / append-only 落库"
  并排除——但那句话针对的是 `record_run` / `load_runs` / `aggregate` 三个**做文件 IO 的函数**。
  `_validate_report` 不碰文件、不碰 `Path`、不读时间，是本模块里唯一的纯校验 helper，从未被单独排除。
  本片只 port 这个 helper，落库/读回/聚合仍按 Q5 文件 IO 边界留 Python。
- 它读的 `REQUIRED_FIELDS` 是模块级**不可变常量**（3 字段名 tuple），与已 port 且 gate 通过的
  `detect_injection_markers` 读 `INJECTION_MARKERS`（finding 17）同类；不是 `tuning.get` 全局可变状态
  （finding-interval-math 排除项），不是 `REGISTRY` 可变参数（finding-metrics Q5=C）。
- 测试锚点虽是**间接**的：`tests/test_r14_telemetry.py::test_record_missing_field_raises` /
  `test_record_non_dict_raises` 经 `record_run` 完整断言其抛错行为（非直接 import）。
  这与 percentile 的"公开调用者吃 dataclass 缝、_percentile 独立成片"是同向逻辑：
  函数本身可直接录制，调用者的缝不阻挡它独立证明。

## 语义与录制

- `if not isinstance(report, dict): raise ValueError("report must be a dict")`：
  非 dict（str/list/None/int）→ 固定错误文本。
- `missing = [f for f in REQUIRED_FIELDS if f not in report]`：按声明序 `completion_fired` /
  `main_latency_ms` / `completion_latency_ms` 检测缺失，**与入参 dict 键序无关**。
- `raise ValueError(f"report missing required field(s): {', '.join(missing)}")`：
  动态错误文本，缺失字段名按声明序 `", "` 拼接。
- 字段值本身**不做类型校验**（case `"completion_fired":0` / `main_latency_ms:"x"` 仍 `ok:null`）——
  值类型校验发生在下游 `record_run` 的 `bool()/float()` 转换与 `judge_r14`，不在本片。

## 切片范围与边界（不得读成）

- **不是 R14 关闭的运行时保证**：真实 run 由 zj 经 dogfood 产生、经 `r14_telemetry.record_run` 落库，
  R14 已于 2026-11-12 由真实 10 run 裁决收口（见 `docs/risks.md`）。本片不产真实 run、不触发关闭。
- **out of scope**：`record_run` / `load_runs` / `aggregate`（文件 IO / append-only JSONL）、
  `combine` / `apply_combine`（LLM + Storage）按文件 IO 与 Q5=C 留 Python。
- 三字段名、固定错误消息、`, ` 分隔符均为 `recorded-literal`（port 同行注释），不 promote 为 CALIBRATED。
- 测试锚点为间接断言，故补 16 条定向录制 case（覆盖 3 种单字段缺失、组合缺失、全缺失、4 类非 dict、
  乱序键、嵌套额外字段、字段值非预期类型），逐字比对补偿"无直接单测名"的弱点。
- 无 dataclass / Storage / 文件 IO / datetime 缝；`src/zkc/**` 零改动；此 finding 不是生产放行。
