# Evidence · `_require_operator` 人环 operator 守卫纯函数切片（ticket 39）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与 kill switch 语义仍以 crate 实现为准。
人环硬约束真相源是 ADR-0013 + PRD 节点生命周期三态段 + `src/zkc/tombstone.py`，本切片只做逐字回放，不新定义 operator 策略。

## 结论

`src/zkc/tombstone.py::_require_operator`（ADR-0013 人环 operator 守卫）已 port 到 Rust `rust/operator-guard-rs`，**未接线进 app**。
DP：finding 19 + ticket 39（parent 8，derived-from 19，blocks `39→8`）完成并释放租约，ticket 8 仍是唯一活跃租约。

## 选片理由

- 纯 `str | None → str`：无 dataclass / datetime / Storage / LLM / 全局状态缝，全 JSON-native，
  是剩余候选中编码缝最干净的一个（避开 metrics 的 `MetricInputs` dataclass、calibration 的 `AttentionObservation` dataclass、
  transport `_tool_result` 的 `json.dumps(default=str)` 编码缝、sweep 的 datetime 缝）。
- 有直接测试锚点 `tests/test_tombstone_human.py::test_operator_is_required`（operator 空串 → ValueError），
  且其调用者 `mark_tombstone` / `restore_node` 是 ADR-0013 人环硬约束的门，语义值得独立证明。
- 未被任何既有 finding 登记为排除/暂留项；不翻任何案。

## 实现与录制

- 新 crate `rust/operator-guard-rs/`：port 单函数。逐字对应 Python 语义：
  `not operator`（None / 空串 → ValueError）、`operator.strip()`、strip 后为空 → ValueError、否则返回 stripped。
- **关键边界**：Python `str.strip()` 依赖 `str.isspace()`（29 字符，含 ASCII 控制符 `\x1c..\x1f` = FS/GS/RS/US），
  Rust `char::is_whitespace()` 用 Unicode White_Space 属性（**不含**这 4 个控制符）。
  port 用 `py_isspace(c) = c.is_whitespace() || c ∈ {\x1c,\x1d,\x1e,\x1f}` + `trim_matches` 复刻，
  使 trim 字符集与 CPython 逐字符一致；case 10 `"\x1cZJ\x1c" → "ZJ"`、case 11 `"\x1d\x1e\x1f" → ValueError` 证明该边界。
- ValueError 中文文本是 ADR-0013 人环契约的一部分，逐字保留并加 `// recorded-literal:` 同行注释，不 promote。
- 新 alias `spikes/spike-22-operator-guard/pure_bridge.py`：纯委托原函数（无编码缝，
  暴露名 `require_operator` 固定单函数录制面，避免整包 bridge 混合 tombstone 的 Storage 函数）。
- 16 个定向录制 case：`record --inputs --count 0`，覆盖纯文本/中文/ASCII 与 unicode strip/内部空格保留/
  空串/纯空白/tab+换行/全角空格/None/4 个控制符/NBSP/NUL 内部保留/混合空白 strip。

## 验证

| 检查 | 结果 |
|---|---|
| crate diff | **16/16** cases match（6 个 throw case 与 Python 异常文本逐字一致） |
| crate gate | Gate passed（size 0.8x，literals 0，中文契约文本以 `recorded-literal` 同行注释豁免） |
| app replay（11 case） | 11/11，fallback **0.0%**（未接线，零回退） |
| make test | **671 OK** |
| 三门禁 | mcp-gate 6/6 / invariant 0 violations / authority 0 leaks |

唯一踩坑：首次 gate 只差 `cargo fmt`（字面量行被 rustfmt 拆行），格式化后全过，`recorded-literal` 注释仍与字面量同行。

## 边界与风险

- 只证函数级逐字等价，不冒充 `mark_tombstone` / `restore_node` / `sweep_tombstones` / `check_purge_blockers` 的行为——
  这些吃 Storage/UUID/datetime，按 Q5=C 留 Python；墓碑真删闸门与 TTL 月扫语义属 ADR-0013，不在本切片。
- 非 str / 非 None 入参未录制（port 返回防御性 `TypeError` 兜底），不构成等价证据。
- 中文契约文本是 recorded-literal，不涉 CALIBRATED 提升；ADR-0013 人环语义真相源不变。
- `src/zkc/**` 零改动；未翻任何既有 finding 的案。
