# Evidence · to_modeling_artifact 结合产物落库形态切片（ticket 33）

日期：2026-11-28。过程态证据，非长期权威；落库形态语义仍以 `src/zkc/cross_source.py` / ADR-0013 / 架构为准。

## 结论

`rust/artifact-shaping-rs` 复刻了 `src/zkc/cross_source.py::to_modeling_artifact` 这一纯转换
函数：把结合算子产物 dict 塑形成 `ModelingArtifact` 落库行（title/kind 取值、body 键过滤、
evidence_refs UUID 规范化、produced_by 溯源）。录制期 Python 原实现仍是唯一 oracle。
DP：finding 16 已登记（观察 memo 保留未完成）、ticket 33（parent 8，blocks
`33→8`）已完成并释放租约，`validate` 0 errors；ticket 8 仍在进行、是唯一活跃租约。

## 切片范围与录制缝

process-only alias `spikes/spike-19-artifact-shaping/pure_bridge.py` 只暴露一个公开名字：

- `to_modeling_artifact(artifact, produced_by)` → 原 `zkc.cross_source.to_modeling_artifact(artifact, produced_by=produced_by)`

三个编码缝，决策仍逐字委托原实现：

1. **keyword-only → 位置参数**：Python 侧 `produced_by` 是 keyword-only，alias 暴露为第二
   位置参数并在委托时还原为 `produced_by=`（同 spike-09 `human=` / spike-18 `min_runs=`）。
2. **dataclass → 固定键 dict**：返回 `ModelingArtifact` dataclass（含 UUID/datetime 字段），
   PyO3 `_enc` 不编码、会回退 `$repr`；alias 编码成 8 键 dict
   （id/title/kind/body/evidence_refs/produced_by/revises/created_at），UUID→str、
   datetime→isoformat。键序即 dataclass 字段序，由 `preserve_order` + `Map` 插入序保住。
3. **UUID 入参保持字符串**：evidence_refs 入参是 str（JSON-native），原实现 `UUID(e)` 转换；
   produced_by 原实现**不强制类型**（str 原样保留、不规范化）。alias 不篡改此语义。

`rust-anything record rust/artifact-shaping-rs --count 0 --inputs tmp/artifact-inputs.jsonl`
冻结 **10 case**（1 throw），覆盖 tests/test_cross_source_apply.py 间接断言的全部形态加边界。

## 关键语义

- **字段取值**：`title` / `kind` 从 artifact dict 取键，缺省空串（case 1/9 无 kind → `""`）。
- **body 过滤**：完整 artifact dict 保序，剔除 `_` 前缀内部键（`_internal`/`_lead`/`_tail`/
  `_dropped_claims`）与已升为列的 `evidence_refs`；嵌套 `_inner` 键在 `data` 内**不被剔除**
  （只过滤顶层，case 4），`data.evidence_refs` 字符串同样保留（非顶层列）。
- **evidence_refs UUID 规范化**：每个字符串经 `UUID()` → 小写连字符形式；大写
  `AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE` → 小写（case 2），重复 id 不去重（case 2 两次）。
  非法串 → `ValueError: badly formed hexadecimal UUID string`（case 8，错误文本逐字录制）。
- **produced_by 原样透传**：UUID 入参 → str、str 入参原样（大写不规范化、非法串也不报错，
  case 0/9）、None 保留；因原实现直接赋值到 dataclass 字段、无 `UUID()` 强制。Rust port
  把 produced_by Value 原样放入输出，不做规范化。
- **固定空字段**：`id` / `revises` / `created_at` 恒 null（原实现不设置，dataclass 默认值）。
- **body 值类型**：int/float/bool/null/list/dict 原样保序透传（case 7）；整数值 float（如
  `0.5`）与非整数 float 由 bridge 对称序列化，逐字一致。

## 机械验证

| 检查 | 结果 |
|---|---|
| `rust-anything diff rust/artifact-shaping-rs` | **10/10** recorded cases match（0 mismatch） |
| `rust-anything gate rust/artifact-shaping-rs` | **Gate passed**（fmt / clippy / cargo test / unsafe / lockfile / ported / size **1.1x** / literals **0** / tests / error cases / panics / build / api / behavior 全绿） |
| `app replay --build`（既有 11 case） | **11/11 passed**，fallback **0.0%**（本片未接线，零回退） |
| `make test` | **671 OK** |
| mcp-gate / invariant / authority | **6/6** / **0 violations** / **0 leaks** |

## 边界与风险

- **不是结合算子的放行保证**：`CrossSourceOperator.combine`（RCS 漏斗 + 引用强制 + 单次补全）、
  `apply_combine`（源节点校验 / kind 值域 / Storage 落库）、`revert_artifact` 级联撤销、
  R14 埋点全留 Python。本片只证 dict→落库行的确定性塑形。
- **未 wire 进 `rust/app`**；10 case 是人工定向输入，不是全输入空间。非 dict 入参、
  evidence_refs 非数组、嵌套非字符串引用、`produced_by` 非 str/UUID/datetime 等越界输入
  不在录制域内（未录制不得声称覆盖）；port 里对此类越界的 isinstance/AttributeError 分支
  只是对齐 Python 错误措辞，未被 diff 覆盖。
- 非法 UUID 错误文本标 recorded-literal，不 promote 为 CALIBRATED、不写回 tuning REGISTRY。
- 与 Q5=C 的关系：Q5=C 暂留的是吃 Storage 的 dataclass/Storage 函数；本片入参是纯 dict、
  dataclass 仅作输出编码缝（同 spike-17 `validate_result`），未翻案。
- 不触碰 `CALIB_OVERRIDE_AT` caveat；`src/zkc/**` 零改动，`zkc` CLI 未加命令。
- 未提交：本片代码/证据均留在工作区，按 zj 的 checkpoint 指令再拆 feat/chore 提交。
