# Evidence · cross_source 引用强制/跨源统计纯函数切片（ticket 27）

日期：2026-11-28。过程态证据，非长期权威；复利变换语义仍以 PRD/架构/代码为准。

## 结论

`rust/cross-source-rs` 复刻了 `src/zkc/cross_source.py` 的 2 个字面纯函数：
`count_cross_source` 与 `enforce_citations`。录制期 Python 原实现仍是唯一 oracle。
DP：finding 13 已登记（观察 memo 保留未完成）、ticket 27（parent 8，blocks
`27→8`）已完成并释放租约，`validate` 0 errors；ticket 8 仍在进行。

## 切片范围与录制缝

process-only alias `spikes/spike-16-cross-source-enforcement/pure_bridge.py`
只提供两个公开名字：

- `count_cross_source(claims)` → 原 `zkc.cross_source.count_cross_source(claims)`
- `enforce_citations(artifact, source_ids)` → 原
  `zkc.cross_source.enforce_citations(artifact, set(source_ids))`

`source_ids` 在生产是 `set[str]`，JSON bridge 传数组；alias 的 `set(...)` 只是编码缝，
成员判断、丢 claim 决策、汇总与错误文本全部逐字委托原实现。无 Storage、LLM、
dataclass、callable、datetime 入参。

`rust-anything record rust/cross-source-rs --count 0 --inputs tmp/cross-source-inputs.jsonl`
冻结 **26 case**（count 12 / enforce 14，其中 5 个 Python 抛错）。

## 关键语义

- **跨源计数**：`len(set(evidence_ids)) >= 2`；`["s1","s1"]` 计 0，
  `["s1","s2","s2"]` 计 1；缺 `evidence_ids` 键按空列表处理。覆盖 Unicode 来源 id
  与多条 claim 混合。
- **引用强制**：逐条保留在来源集合中的 evidence id（保留原顺序与重复项），
  无有效引用则丢 claim 并累加 `_dropped_claims`；顶层 artifact 的键序与每条 claim
  的键序照 Python `dict(...)` 语义保留，新键按 `claims → evidence_refs →
  _dropped_claims` 追加，覆盖已存在的同名键但不改变其位置。
- **汇总**：`evidence_refs = sorted(去重后的有效引用)`，与来源集合顺序、claim 顺序
  无关；录制含 `["β","a","A","中"]` → `["A","a","β","中"]`（UTF-8 字节序与 Python
  code point 序一致）。
- **全崩塌**：无 claim 存活时抛 `ValueError`，文本含 claim 总数；录制覆盖 0/1/3
  三种总数，Rust 侧按 recorded-literal 复刻，未 promote。
- **编码伪差异**：录制中 `confidence: 0.0` 被 bridge 记作 `{"$float":"0.0"}` 标记；
  Rust 侧克隆原 `Value` 不改写该字段，逐字对齐。

## 机械验证

| 检查 | 结果 |
|---|---|
| `rust-anything diff rust/cross-source-rs` | **26/26** recorded cases match（0 mismatch） |
| `rust-anything gate rust/cross-source-rs` | **Gate passed**（fmt / clippy / cargo test / unsafe / lockfile / ported / size **1.4x** / literals / tests / error cases / panics / build / api / behavior 全绿） |
| `app replay --build`（既有 11 case） | **11/11 passed**，fallback **0.0%**（本片未接线，零回退） |
| `make test` | **671 OK** |
| mcp-gate / invariant / authority | **6/6** / **0 violations** / **0 leaks**（1077 durable sources） |

## 边界与风险

- **不是复利变换放行**：`CrossSourceOperator`（RCS 漏斗、tuning 阈值、单次有界补全
  回路、R14 latency 埋点）、pydantic 模型、LLM callable 与 repository 落库留 Python。
  本片不证跨源质量、幻觉防护或引用真实性。
- **未 wire 进 `rust/app`**；26 case 是人工定向输入，不是全输入空间证明。
  `source_ids` 非字符串、artifact/claim 非对象等越界输入不在录制域内。
- 全崩塌错误文本是 CPython 原实现的 recorded-literal；若原实现改文案，录制的 case
  须重录，不能在此端口自行"修正"。
- 不触碰 tuning 阈值与 `CALIB_OVERRIDE_AT` caveat，不写回 REGISTRY；`src/zkc/**`
  零改动，`zkc` CLI 未加命令。
- 未提交：本片代码/证据均留在工作区，按 zj 的 checkpoint 指令再拆 feat/chore 提交。
