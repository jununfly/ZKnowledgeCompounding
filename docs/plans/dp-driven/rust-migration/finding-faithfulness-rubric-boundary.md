# Finding · faithfulness 字面 rubric 的录制边界（ticket 8 / task 2）

> 2026-11-27。类型：工具桥编码边界 + 生产接线边界。归属 task 2，派生 ticket 23。

## 观察

`src/zkc/faithfulness.py` 的字面 rubric 层有 7 个全标量/文本函数，可录制：

| 函数 | 入参 | 返回 | 备注 |
|---|---|---|---|
| `_normalize` | `str` | `str` | 正则剥标点/空白 |
| `_ngrams` | `str, int=3` | `set[str]` | **set 过不了 JSON bridge** |
| `_lcs_length` | `str, str` | `int` | 两侧截断 600 字符 |
| `verbatim_rate` | `str, list[str]` | `float` | LCS / 归一化 claim 长度 |
| `overlap` | `str, list[str]` | `float` | 3-gram 交集率 |
| `rubric_flags` | `str, list[str]` | `list[str]` | 阈值来自 `tuning.get` |
| `_is_forced` | `Optional[str]` | `bool` | `forced*` / `human_only` 前缀 |

阈值实测：`FAITH_RUBRIC_VERBATIM_MAX=0.5 (placeholder)`、`FAITH_RUBRIC_OVERLAP_MAX=0.7 (placeholder)`。
按项目铁律，迁移只能把它们当 **recorded-literal**，不得 promote 成 CALIBRATED。

## 边界（不得越过）

- `_ngrams` 返回 `set[str]`：PyO3 JSON bridge 的 `_enc` 不编码 set，会退化成 `$repr`，
  diff/replay 侧无法重建。用 process-only alias 把结果规范为 **sorted list**（只改编码，
  不改决策，逐字委托原实现）。
- `aggregate` 吃 `list[AtomicFact]` dataclass、`parse_judgment` 返回 pydantic `Judgment`：
  与 `finding-metrics-boundary.md` 同类工具边界，本片不迁。
- `build_judge_prompt` 虽可录制，但产出是长 prompt 文本，不属于确定性 rubric 判定，本片不迁。
- `route_claim` / `gate_new_claims` / `adjudicate` / `daily_faithfulness_queue` 等吃
  Storage / LLM / callable / datetime，留 Python；与 Q5=C 口径一致。
- **生产接线偏差**：`faithfulness.gate_new_claims` 仅 dogfood/测试使用，未在生产注入。
  rubric flags 按 Spike 10 盲点记账**只作 pending_human 排序标注，不构成放行依据**；
  本片证明的是字面度量函数行为，不是忠实度放行保证。

## 处置

process-only 别名 `spikes/spike-10-model-quality/pure_bridge.py`：仅把 `_ngrams` 的 set
结果规范成 sorted list；其余函数逐字委托 `zkc.faithfulness`。录制期 Python 原实现仍是
唯一 oracle；删除别名只影响重录和 kill switch，不影响 Rust port。
