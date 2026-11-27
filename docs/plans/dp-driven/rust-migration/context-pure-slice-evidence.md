# Evidence · context 纯函数切片（ticket 18）

> 2026-11-27，DP carrier 过程态证据；长期结论须提炼到 ADR / 架构，不把本文件当权威源。

## 范围与 oracle
- 目标：`src/zkc/context.py` 的两个纯 helper —— `_clean_title`（首非空行 / 去 ASCII 引号 / 32 字截断）与 `fallback_name`（正则 tokenize + Counter 排序降级命名）。
- 工具限制：bridge 只导出 public 函数；`_clean_title` 是私有函数。采用 process-only 别名模块 `spikes/spike-06-context-assembly/pure_bridge.py`（已被 analyze 识别的研究归档 unit），两个 alias **逐字委托** `zkc.context`，不重实现；Python 原实现仍是唯一录制 oracle。
- 不进切片：`ContextNamer`（callable LLM）、`ContextAssembler`（Storage）、`HigherDimProposal`（dataclass），按 Q5=C 暂留 Python。

## 录制与证明
- `record --count 40 --inputs tmp/context-inputs.jsonl` → **131 cases（0 threw）**：clean_title 66 / fallback_name 65。
- 定向输入：首非空行、ASCII 引号剥离（中文弯引号保留）、32 字边界；停用词全命中、ASCII 单字符丢弃 vs CJK 单字保留、词频并列字典序、`İ` 小写展开为 `i`+组合点后 `i` 被丢弃、负数/零 `n_members`。
- `diff`：**131/131 cases match**。
- `gate`：**全 pass**（fmt / clippy -D warnings / cargo test 4 tests 6 assertions / unsafe / lockfile / ported / size 116 Rust vs 38 Python / literals / error cases / panics / build / api / behavior）。

## 语义保真点 / 红→绿
- 初版误把 `_clean_title` 的 strip 字符集理解为含中文弯引号；录制 case `“中文引号” → 未变化` 证伪。源码字面量实为重复 ASCII `"`/`'`，Rust 改 `trim_matches(|c| c == '"' || c == '\'')`。
- Python `str.splitlines()` 的换行集比 Rust `str::lines()` 宽（`\r`、`\x0b`、`\x0c`、`\x1c`–`\x1e`、`\u2028`、`\u2029`），Rust 侧手写边界扫描并把 `\r\n` 当单个 break。
- tokenize 对 `to_lowercase()` 的输出逐字符扫描：ASCII `[a-z0-9]+` 连续成词，CJK `U+4E00..U+9FFF` 逐字成词，其余字符 flush；`BTreeMap` + `sort_by(count desc, token asc)` 复刻 `Counter` + 复合排序。
- gate `size` 初报 10.3x，因为比较对象是 10 行的 alias shim 而非 300 行的 `context.py`；shim 文档补足了为何 Rust 需显式实现 Python 标准库语义（现 38 行、3.1x）。**这不是与 `context.py` 的行数对比**，不得据此宣称整体模块已 port。

## 边界
- 只证明两个 helper 在录制输入上的行为；命名 LLM 路径、Storage 装配、proposal dataclass 均未覆盖。
- alias shim 是研究归档里的 process-only 文件；删除它只影响重新录制，不影响生产。`src/zkc/**` 零改动；未 commit/push。
