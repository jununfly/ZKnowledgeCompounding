# Evidence · `_validate_report` R14 遥测字段闸纯函数切片（ticket 41）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与错误文本语义仍以 crate 实现为准。
R14 遥测字段契约真相源是 `src/zkc/r14_telemetry.py` 的 `REQUIRED_FIELDS` + `tests/test_r14_telemetry.py`，本切片只做逐字回放，不新定义字段策略、不产真实 run、不触发 R14 关闭。

## 结论

`src/zkc/r14_telemetry.py::_validate_report`（R14 遥测字段存在性校验）已 port 到 Rust
`rust/telemetry-validation-rs`，**未接线进 app**。
DP：finding 20 + ticket 41（parent 8，derived-from 20，blocks `41→8`）完成并释放租约，ticket 8 仍是唯一活跃租约。

## 选片理由

- 纯 `dict → None | ValueError`：无 dataclass / datetime / Storage / 文件 IO / LLM / callable / 全局可变状态缝，全 JSON-native，
  是剩余候选中编码缝最干净的一个（避开 calibration 的 `AttentionObservation` dataclass + 日期缝、
  repository/pg 的浮点 repr 保真风险、scripts D2 动态代码块、tuning 的 `REGISTRY` 全局可变状态）。
- 此前被"r14_telemetry 无直接测试"笼统带过，但 `tests/test_r14_telemetry.py::test_record_missing_field_raises` /
  `test_record_non_dict_raises` 经 `record_run` 对其抛错行为做了完整间接断言，且有明确业务锚点（R14 埋点字段闸）。
- 读的 `REQUIRED_FIELDS` 是不可变常量，与已 port 的 `detect_injection_markers` 读 `INJECTION_MARKERS` 同类，**不翻任何案**
  （详见 `finding-telemetry-validation-boundary.md`）。

## 实现与录制

- 新 crate `rust/telemetry-validation-rs/`：port 单函数。逐字对应 Python 语义：
  `not isinstance(report, dict)` → 固定 ValueError；按 `REQUIRED_FIELDS` 声明序收集缺失字段；
  非空则 `ValueError(f"report missing required field(s): {', '.join(missing)}")`；否则返回 `None`（录制为 `null`）。
- **关键语义**：缺失字段按常量声明序而非入参键序报告（case 16 乱序键仍按 `completion_fired, main_latency_ms, completion_latency_ms` 序）；
  字段值不做类型校验（case 15 `0`/`"x"`/`false` 仍 `ok:null`），值校验在下游 `record_run`/`judge_r14`。
- 三字段名、两条错误消息文本、`, ` 分隔符全部逐字保留并加 `// recorded-literal:` 同行注释，不 promote。
- 新 alias `spikes/spike-23-telemetry-validation/pure_bridge.py`：纯委托原函数（无编码缝，暴露名 `validate_report`
  固定单函数录制面，避免整包 bridge 混入 `r14_telemetry` 的 `record_run`/`load_runs` 文件 IO 函数）。
- `record --inputs 16 定向 case --count 0`：3 种单字段缺失 + 组合缺失 + 全缺失 + 4 类非 dict（str/list/None/int）
  + 合法最小 report + 额外字段 + 嵌套额外字段 + 乱序键 + 字段值非预期类型。10 threw / 6 ok。

## 验证（全绿）

| 检查 | 结果 |
|---|---|
| crate diff | **16/16** cases match |
| crate gate | Gate passed（size 1.3x，literals 0，api exports validate_report，behavior 16/16） |
| app replay（11 case） | 11/11，fallback **0.0%**（本片未接线，确认未影响既有前门） |
| make test | **671 OK** |
| 三门禁 | mcp-gate 6/6 / invariant 0 violations / authority 0 leaks |

## 边界与风险

- 只证函数级逐字等价，不冒充公开调用者 `record_run` / `load_runs` / `aggregate` 的行为——三者吃文件 IO，按 Q5 文件 IO 边界留 Python。
- 不是 R14 关闭的运行时保证：R14 已于 2026-11-12 由 zj 真实 10 run 裁决收口，真实数据经 dogfood + `r14_telemetry` 落库（过程态）；本片不产真实 run、不触发关闭。
- 测试锚点为间接断言（非直接单测名），已用 16 条定向录制 case 逐字比对补偿。
- 非 dict / 缺字段之外的输入维度（如极深嵌套、超长字段名）未穷尽；函数只检查键存在性，这些不影响输出（`ok:null`）。
- 无 recorded-literal 阈值（字段名/消息文本是契约常量非 tuning 参数），不涉及 CALIBRATED；`src/zkc/**` 零改动。
