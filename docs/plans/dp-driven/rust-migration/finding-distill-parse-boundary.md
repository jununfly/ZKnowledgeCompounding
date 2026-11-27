# Finding 14 · distill 结构化解析层的可证边界

> 过程态观察 memo（非 durable 权威）。2026-11-28 由 ticket 8 续租时登记。

## 事实

`src/zkc/distill.py` 的四个确定性函数构成蒸馏产出的解析/语义校验层，且不依赖 LLM callable、
Storage 或 pydantic：

- `_extract_json(raw)`：宽松正则 `\{.*\}`（DOTALL、贪婪）取第一段 JSON 对象，`json.loads`
  失败或非 dict 返回 `None`。
- `_parse_json_output(raw, source_texts)`：JSON 契约解析；`claims` 必须是列表、每项须有非空
  `text`；引用来自 `citations[]` 与正文内联 `[[uuid]]` 两路并集，仅保留源集合内且按首次
  出现顺序去重；结构残缺或零 claim 返回 `None`。
- `_parse_llm_output(raw, source_texts)`：旧文本标记 fallback；整段文本作为唯一 claim，
  `[[uuid]]` 标记合法来源才进 `citations` / `reverse_links`。
- `validate_result(result)`：ZKC 自建蒸馏语义不变式——每条 claim 至少
  `tuning.DISTILL_MIN_CITATIONS_PER_CLAIM`（当前 1，PLACEHOLDER）条引用，空 claims 拒绝；
  错误信息带 claim 文本的 Python `repr`。

## 编码缝

PyO3 bridge 的 `_enc` 不编码 dataclass / UUID。process-only alias
（`spikes/spike-17-distill-parse/pure_bridge.py`）只在进程边界做
`UUID ↔ str`、`DistillationResult/MetaClaim/Citation ↔ dict` 的编码转换；所有解析、过滤、
排序、错误文本仍逐字委托 Python 原实现。alias 不是迁移目标，也不是生产代码。

## 不纳入本切片

- `distill_node` 重试循环、`_build_prompt` / `DISTILL_SCHEMA_HINT` 提示文本、
  `DistillationOperator`、真实 LLM callable（Ollama 铁律）；
- `revert_claim` / `revert_artifact` 的 Storage 与 capture-loss 级联；
- tuning 校准状态与权重（阈值 1 标 `recorded-literal`，不 promote 为 CALIBRATED）；
- 任何「蒸馏质量」判断：此切片只证确定性结构/字面行为，不是幻觉防护或放行门禁。

新增 ticket 29（parent 8，blocks `29→8`）：定向录制后 port 到 Rust，只以录制 case 全匹配
与 gate 通过为完成判据；不接线进 `rust/app`，不触碰 `src/zkc/**`。

结果（2026-11-28）：61 case 定向录制（7 个原实现抛错），Rust port diff **61/61**、
gate 全过（size 3.2x）；既有 app replay 11/11 fallback 0%、671 单测与三门禁全绿。
错误类 `DistillationError` 需 dotted path `zkc.distill.DistillationError` 才能被生成绑定
还原，裸类名会退化为 ValueError。证据见 `distill-parse-slice-evidence.md`。
