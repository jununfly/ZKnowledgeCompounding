# Finding 13 · cross_source 引用强制/跨源统计的可证边界

> 过程态观察，结论须提炼到 durable 文档后才算长期事实。

## 观察

`src/zkc/cross_source.py` 的复利变换（结合算子）底层有两个全 JSON 标量的确定性函数：

- `count_cross_source(claims: list[dict]) -> int`：统计 `evidence_ids` 含 ≥2 个**不同**来源 id 的 claim 数；重复 id 不构成跨源。
- `enforce_citations(artifact: dict, source_ids: set[str]) -> dict`：剔除幻觉引用、丢弃引用全灭的 claim、按 `evidence_refs=sorted(...)` 汇总，并写 `_dropped_claims`；全部 claim 崩塌时抛 `ValueError`。

两者无 Storage、LLM、dataclass、callable、datetime；可作下一个纯函数切片，录制期 Python 原实现仍是唯一 oracle。

## 边界与风险

- `CrossSourceOperator`（RCS 漏斗、tuning 阈值、单次有界补全回路、`statistics`/`time` 埋点）吃注入 callable 与 tuning，留 Python；本片不是结合算子的生产放行。
- `source_ids` 是 `set[str]`，PyO3 JSON bridge 不编码 set；process-only alias 需在编码缝把 list 转回 set，决策逐字委托原实现。
- `enforce_citations` 返回 `dict(artifact, ...)`：Python 的字典键序与 `evidence_refs` 的 `sorted()` 必须逐字对齐；JSON 比较须保留键序，否则产生伪差异。
- 全崩塌 `ValueError` 文本含 claim 总数，需作为 `error` case 录制，Rust 侧按 recorded-literal 复刻，不得 promote 成业务策略。
- R14 埋点、tuning 阈值与 `CALIB_OVERRIDE_AT` caveat 不在本片范围，绝不写回 REGISTRY。

## 处置

新增 ticket 27（parent 8，blocks `27→8`）：process-only alias 暴露两函数，定向录制后 port 到 Rust；只证字面数值/结构行为，不构成跨源质量或幻觉防护保证。

## 结果（2026-11-28）

ticket 27 已完成：`rust/cross-source-rs` 26/26 diff + gate 全绿，既有 app replay
11/11 fallback 0%。详见 `cross-source-enforcement-slice-evidence.md`。本 finding 作为
边界观察 memo 保留未完成（未 dispose），供后续 wire / lift 复用。
