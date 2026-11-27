# Evidence · distill 结构化解析/语义校验纯函数切片（ticket 29）

日期：2026-11-28。过程态证据，非长期权威；蒸馏语义仍以 PRD/架构/代码为准。

## 结论

`rust/distill-parse-rs` 复刻了 `src/zkc/distill.py` 的 4 个确定性函数：
`_extract_json`、`_parse_json_output`、`_parse_llm_output`、`validate_result`。
录制期 Python 原实现仍是唯一 oracle。DP：finding 14 已登记（观察 memo 保留未完成），
ticket 29（parent 8，blocks `29→8`）已完成并释放租约，`validate` 0 errors；
ticket 8 仍在进行且是唯一活跃租约。

## 切片范围与录制缝

process-only alias `spikes/spike-17-distill-parse/pure_bridge.py` 暴露四个公开名字：

- `extract_json(raw)` → 原 `zkc.distill._extract_json(raw)`
- `parse_json_output(raw, source_texts)` → 原 `zkc.distill._parse_json_output(...)`
- `parse_llm_output(raw, source_texts)` → 原 `zkc.distill._parse_llm_output(...)`
- `validate_result(result)` → 原 `zkc.distill.validate_result(...)`

PyO3 `_enc` 不编码 `UUID` / dataclass。alias 只在进程边界做
`UUID ↔ str`、`DistillationResult/MetaClaim/Citation ↔ dict` 的编码转换；
UUID 规范化、引用过滤、顺序、`None` 返回与错误文本全部逐字委托原实现。
`source_texts` 以 `[uuid_string, text]` 二元组数组跨桥。无 LLM callable、
Storage、pydantic、datetime 入参。

`rust-anything record rust/distill-parse-rs --count 0 --inputs tmp/distill-inputs.jsonl`
冻结 **61 case**：`extract_json` 16 / `parse_json_output` 26 /
`parse_llm_output` 10 / `validate_result` 9（其中 7 个原实现抛错）。

## 关键语义

- **宽松 JSON 提取**：正则 `\{.*\}`（DOTALL、贪婪）取首 `{` 到末 `}`；
  `{"a": 1} trailing {"b": 2}` 与 `{"a":1}{"b":2}` 都因跨越末括号而解析失败 →
  `None`。非 dict JSON、围栏前后缀、尾随文本、原生 `null` 均按原实现处理。
- **JSON 契约**：`claims` 必须是数组、每项 `text` 去空白后非空；残缺项或零 claim
  整体返回 `None`（走重试，不静默丢 claim）。`text` 两端 strip，`topic` 缺失/假值落
  `"(unclassified)"`，`notes=""`、`attempts=1`（dataclass 默认）。
- **UUID 规范化**：`UUID(str(tok))` 接受大写 hyphen、32-hex、`urn:uuid:` 与花括号形式，
  统一输出小写 hyphenated；非法 token 丢弃。来源集合内才保留，按首次出现顺序去重。
  `citations[]` 与正文内联 `[[uuid]]` 两路并集（内联在前也可，去重顺序照原实现）。
- **文本 fallback**：整段 strip 后文本作唯一 claim；空文本落 `"(empty)"`；
  只有 `[0-9a-fA-F-]{36}` 的 `[[...]]` 标记会被识别，未知来源/畸形标记不计引用。
  覆盖重复标记、大小写标记、空来源集合、中文与换行。
- **语义不变式**：空 claims → `DistillationError: distillation produced no claims`；
  引用数 < 1 → 逐条报错且文本含 Python `repr`（覆盖单引号/双引号/同时含两者、
  tab/newline/反斜杠、中文）。阈值 1 标 `recorded-literal`（tuning.py:136，PLACEHOLDER），
  不 promote 为 CALIBRATED，不改 REGISTRY。
- **异常类型缝**：Python `DistillationError` 是自定义子类，生成的 `error()` 只认内置
  名字；Rust 侧返回 `zkc.distill.DistillationError: ...` 让生成绑定按 dotted path 找到
  原类并构造同一异常。若盲目写裸类名会退化为 `ValueError: DistillationError: ...`，
  7 个错误 case 全挂；此写法不修改生成代码，`refresh` 后仍成立。

## 机械验证

| 检查 | 结果 |
|---|---|
| `rust-anything diff rust/distill-parse-rs` | **61/61** recorded cases match（0 mismatch） |
| `rust-anything gate rust/distill-parse-rs` | **Gate passed**（fmt / clippy / cargo test / unsafe / lockfile / ported / size **3.2x** / literals / tests / error cases / panics / build / api / behavior 全绿） |
| `app replay --build`（既有 11 case） | **11/11 passed**，fallback **0.0%**（本片未接线，零回退） |
| `make test` | **671 OK** |
| mcp-gate / invariant / authority | **6/6** / **0 violations** / **0 leaks** |

过程中的一次真实修正：初版 `push_citation` 的嵌套 `if` 被 `clippy::collapsible_if`
（`-D warnings`）拦下，改成 let-chain 后 gate 全绿；diff 始终保持全匹配。

## 边界与风险

- **不是蒸馏质量门禁**：`distill_node` 重试循环、`_build_prompt` / `DISTILL_SCHEMA_HINT`
  提示文本、`DistillationOperator`、真实 Ollama callable、`revert_claim` /
  `revert_artifact` 的 Storage 级联全部留 Python。本片不证幻觉防护或结论可信度。
- **未 wire 进 `rust/app`**；61 case 是人工定向输入，不是全输入空间证明。
  `py_repr` 只覆盖 ASCII 控制字符与常见引号转义，非 ASCII 不可打印码点不在录制域；
  JSON 中非字符串 `text`/`topic` 的复杂 `repr`、source id 非法 UUID、dict/list 类型
  越界输入也未录制。
- 错误文本、默认 topic/empty 文本与阈值都是原实现的 recorded-literal；原实现改文案须
  重录 case，不得在端口自行"修正"。
- 不触碰 `CALIB_OVERRIDE_AT` caveat，不写回 REGISTRY；`src/zkc/**` 零改动，
  `zkc` CLI 未加命令。
- 未提交：本片代码/证据均留在工作区，按 zj 的 checkpoint 指令再拆 feat/chore 提交。
