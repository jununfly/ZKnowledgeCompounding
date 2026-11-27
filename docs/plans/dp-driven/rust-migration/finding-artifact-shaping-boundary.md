# Finding · 结合产物落库形态的可证边界（ticket 8 / task 2）

> 2026-11-28。类型：工具桥编码边界 + 生产接线边界。归属 task 2，派生 ticket 33。

## 观察

`src/zkc/cross_source.py::to_modeling_artifact(artifact: dict, *, produced_by=None)`
是从结合算子产物（`CrossSourceArtifact` 经 `CrossSourceOperator.combine` 产出的 dict）
到 `ModelingArtifact` 落库行的**纯转换**：

- `title` / `kind`：从 artifact dict 取键，缺省空串；
- `body`：完整 artifact dict，剔除下划线内部键与已升为列的 `evidence_refs`；
- `evidence_refs`：`str -> UUID` 转换（语义前置由 `enforce_citations` 保证 ⊆ 来源集合）；
- `produced_by`：溯源字段（keyword-only，可空）。

不读 store、不调 LLM、不写埋点，输出只依赖入参。测试 `tests/test_cross_source_apply.py`
通过 `apply_combine` 间接覆盖（UUID 化证据、produced_by 溯源、body 完整保留）。

## 边界（不得越过）

- 返回 `ModelingArtifact` dataclass，含 `UUID` / `datetime` 字段：PyO3 JSON bridge 的
  `_enc` 不编码 dataclass/UUID/datetime，硬录只得到 `$repr`。用 process-only alias
  把返回值规范为字段固定 dict（`id/title/kind/body/evidence_refs/produced_by/revises/created_at`，
  UUID→str）；`produced_by` keyword-only 归一为位置参数。只改编码，不改决策文本。
- `apply_combine` / `CrossSourceOperator.combine` / `revert_artifact` 吃 Storage / LLM /
  RCS 漏斗 / 补全回路 / R14 埋点，留 Python；本片不是结合算子的放行保证。
- `evidence_refs` 的 UUID 合法性、kind 值域校验在 `apply_combine`（落库前）负责，
  `to_modeling_artifact` 本身只做 `UUID(e)` 转换；非法输入会在原实现抛 `ValueError`
  （解析错误文本属录制内容，标 recorded-literal 不 promote）。
- 与 Q5=C 的关系：Q5=C 暂留的是 8 个**吃 Storage 的 dataclass/Storage 函数**；本片的
  `to_modeling_artifact` 是纯 dict 入参、dataclass 仅作输出编码缝，与 spike-17 的
  `validate_result`（dataclass→dict）同类，不翻 Q5=C 的案。

## 处置

process-only 别名 `spikes/spike-19-artifact-shaping/pure_bridge.py`：仅做 dataclass→dict、
UUID→str、`produced_by` keyword-only→位置参数的编码缝，决策逐字委托原实现；定向录制后
port 到 Rust；只以录制 case 全匹配 + gate 通过为完成判据。**不接线进 `rust/app`**，
不触碰 `src/zkc/**`。

## 处置结论（2026-11-28）

ticket 33 已完成：10 定向 case（9 ok + 1 非法 UUID ValueError）diff **10/10** 逐字匹配，
gate 全绿（size 1.1x、literals 0）；app replay 11/11 fallback 0%、make test 671 OK、
三门禁全过。证据见 `artifact-shaping-slice-evidence.md`。finding 保留为观察 memo（不关闭）；
未 wire 进 app，未提交（等 zj 的 checkpoint 指令拆 feat/chore）。
