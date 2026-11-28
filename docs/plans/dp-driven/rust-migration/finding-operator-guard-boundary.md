# Finding · `_require_operator` 人环 operator 守卫边界（finding 19）

> 2026-11-28。来源：`src/zkc/tombstone.py::_require_operator` 的只读 AST + 行为探针 +
> `tests/test_tombstone_human.py::test_operator_is_required` 测试锚点。
> 本 finding 是边界盘点与切片授权，不是等价证明；子 ticket 须各自有 cases.jsonl + diff/gate 证据才允许置「已完成」。

## 目标函数与语义

`_require_operator(operator: str) -> str`（`src/zkc/tombstone.py:18`）：

```
if not operator or not operator.strip():
    raise ValueError("operator 必填且非空：墓碑标记/恢复是 zj 本人的人环操作，不得缺省")
return operator.strip()
```

行为探针确认：

| 入参 | 返回 / 异常 |
|---|---|
| `"zj"` / `"中文操作员"` | 原样 |
| `"  zj  "` / `" 中文 "` / `" z j "` | `strip()` 后返回（内部空格保留） |
| `""` / `"   "` / `"\t\n"` / `None` | `ValueError: operator 必填且非空：…不得缺省` |
| `"a\x00b"` | 原样（`\x00` 非 whitespace） |

- 纯 `str | None → str`：无 dataclass / datetime / Storage / LLM / 全局状态缝，全 JSON-native。
- 是 ADR-0013 墓碑人环硬约束的实现守卫（`mark_tombstone` / `restore_node` 均经它）；port 只做逐字回放，不弱化、不重写中文契约文本。
- 测试锚点：`tests/test_tombstone_human.py::test_operator_is_required`（operator 空串 → ValueError）。

## 关键边界：strip 的 whitespace 语义差

Python `str.strip()` 依赖 `str.isspace()`（29 字符，含 ASCII 控制符 `U+001C..U+001F` = FS/GS/RS/US）；
Rust `char::is_whitespace()` 用 Unicode White_Space 属性，**不含** `U+001C..U+001F`。
因此 port 不得直接用 `str::trim()`，须按 Python `isspace()` 集合实现 trim（含这 4 个控制符），
并对 `"\x1cZJ\x1c"` 这类输入留定向 case 证明逐字一致。

## 字面量与安全契约

- ValueError 中文文本是 ADR-0013 人环契约的一部分，在 port 中逐字保留并加
  `// recorded-literal: ...` 同行注释（同 r14 reason 分支模式），不 promote 成任何 CALIBRATED 参数。
- 真相源仍是 `src/zkc/tombstone.py::_require_operator` + ADR-0013 + PRD 节点生命周期三态段；
  Rust 侧只做录制回放，不新定义 operator 策略。

## 切片范围与边界

- **in scope**：单函数 `_require_operator` 的 port（空/空白/None/strip/内部空格/unicode whitespace/控制符）。
- **out of scope**：`mark_tombstone` / `restore_node` / `sweep_tombstones` / `check_purge_blockers` 等吃 Storage/UUID/datetime 的函数按 Q5=C 暂留 Python；墓碑真删闸门与 TTL 月扫语义属 ADR-0013，不在本切片。
- 不翻任何既有 finding 的案；`src/zkc/**` 零改动。

## 拟展开的 ticket

- ticket 39：spike alias → bridge → record（定向 case）→ port.rs → diff/gate → replay/回归。
  先 port 不 wire（接线另开 ticket）。
