# Evidence · faithfulness 字面 rubric 纯度量切片（ticket 23）

> 过程态证据，非持久权威。ticket 8 仍在进行；本片是它的第一个子切片。

## 结论

`rust/faithfulness-rubric-rs` 复刻了 `src/zkc/faithfulness.py` 的 7 个字面 rubric
纯函数。DP：finding 11 + ticket 23（parent 8，blocks `23→8`）已完成，租约释放，
`validate` 0 errors。录制期 Python 原实现仍是唯一 oracle。

## 切片范围

`normalize` / `ngrams` / `lcs_length` / `verbatim_rate` / `overlap` /
`rubric_flags` / `is_forced`。全部是标量/字符串/字符串列表入参，无 Storage、
LLM、dataclass、callable、datetime。

## 红→绿与关键语义

- **`_ngrams` 返回 `set[str]`**：PyO3 JSON bridge 不编码 set；process-only
  别名 `spikes/spike-10-model-quality/pure_bridge.py` 把结果规范为 **sorted list**
  （仅改编码，决策逐字委托原实现）。Rust 侧用 `HashSet` 计算、排序后输出。
- **`n <= 0` 的 Python 切片语义**：录制包含 `n=0 → [""]` 与
  `n=-1 → ["", "shor"]`，Rust 的 `gram_at` 显式复刻 `t[i:i+n]` 的负索引回绕，
  不把它当作普通范围。
- **threshold recorded-literal**：`FAITH_RUBRIC_VERBATIM_MAX=0.5`、
  `FAITH_RUBRIC_OVERLAP_MAX=0.7` 都是 tuning placeholder；Rust 常量同行
  `recorded-literal` 注解，gate `literals` 项通过，未 promote 成 CALIBRATED。
- **`$float` 编码**：录制输出里全值 float（0.0 / 1.0）写成 `{"$float":"0.0"}`，
  diff 机制会与 Rust 的普通 f64 输出归一化；本片沿用 scheduling 切片的口径。
- **标点类**：`_PUNCT` 正则手写为 `is_punct` 谓词；录制覆盖中文/英文标点、
  空白、emoji、650 字符长文本和 `[:600]` 截断边界。

## 机械验证

| 检查 | 结果 |
|---|---|
| `rust-anything diff` | **74/74** recorded cases match（0 threw） |
| `rust-anything gate` | **Gate passed**（fmt/clippy/cargo test/unsafe/lockfile/ported/size 2.6x/literals/tests/errors/panics/build/api/behavior 全绿） |
| `app replay --build` 既有 11 case | **11/11 passed**，fallback **0.0%**（本片未接线，零回退） |
| `make test` | **671 OK** |
| mcp-gate / invariant / authority | **OK** / **0 violations** / **0 leaks** |

## 边界与风险

- **不是生产放行**：`faithfulness.gate_new_claims` 仅 dogfood/测试；rubric flags
  按 Spike 10 盲点只作 pending-human 标注，本片只证明字面度量函数行为。
- `aggregate`（`AtomicFact` dataclass）、`parse_judgment`（pydantic）、
  `build_judge_prompt`（长 prompt）、`route_claim` / `gate_new_claims` /
  `adjudicate` / `daily_faithfulness_queue`（Storage/LLM/callable/datetime）留 Python。
- **未 wire 进 `rust/app`**；74 case 是人工定向输入，不是全输入空间证明。
- `src/zkc/**` 零改动；`zkc` CLI 未加命令。
