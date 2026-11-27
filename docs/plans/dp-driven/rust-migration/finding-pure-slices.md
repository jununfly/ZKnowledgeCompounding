# Finding · 纯函数模块切片盘点（transport / context / expiry）

> 2026-11-27 22:2x，来源：`rust-anything analyze --whole-app --json` 的 unit 元数据 +
> 逐个 `src/zkc/**` 文件 AST 签名盘点（只读，未改 Python 源码）。

## 目标与纪律
- 用户指令：转纯函数模块切片（transport / context / expiry）。
- 沿用 Q3 修正口径：**录制/证明期 Python 原实现是唯一 oracle**；Rust 单测只做已证明行为的日常回归。
- 不把「部分函数 gate 通过」写成模块等价；Storage / LLM / callable / datetime 入参的函数若过不了 PyO3 JSON bridge，必须显式 `--keep` 留 Python 或另走 app 黑盒（见 Q5/C）。

## transport（`src/zkc/transport/`，analyze: 400 LOC / readiness 80 / 11 bridgeable exports）
- `protocol.py`：全部纯函数 + 常量，`decode_message` / `encode_message` / `is_notification` / `result_response` / `error_response`；`JsonRpcError.as_dict` 属 class 方法，record 覆盖取决于桥接器。
- `contract.py`：从同目录 `contract_v1.json` 加载事实源；纯函数 `contract_snapshot` / `tool_schema` / `is_blacklisted` / `is_allowlisted`。注意 `contract_snapshot()` 返回 dict 深拷贝，key 顺序是契约文件顺序（Rust 侧须 `preserve_order`）。
- `mcp_server.py`：注册表/分发器是有状态类（`McpServer` + `ToolSpec` / `ResourceSpec` dataclass），不进本纯函数切片；可录制的纯 helper = `_public_tool_view` / `_tool_result` / `_type_ok` / `validate_arguments`。
- analyze 标注 `transport ↔ mcp` 有 import cycle；unit-level PyO3 bridge 调原 Python 不受影响，但 Rust 侧若替换实现须整对接线，不能只换 transport 就宣称 seam 可插拔。

## context（`src/zkc/context.py`，位于 `src/zkc/` caution unit）
- 纯且参数可桥：`_clean_title(str)`、`fallback_name(list[str], int)`（正则 tokenize + Counter 排序 + CJK/ascii 单字符规则）。
- `ContextNamer.name` 吃可选 callable LLM、`ContextAssembler.*` 吃 Storage / UUID / dataclass proposal，均不属于本轮 unit bridge 可证范围；`HigherDimProposal` 是 dataclass（Q5 同类边界）。
- 关键语义陷阱：`sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))` 的二级字典序；`token` 正则 `[a-z0-9]+|[\u4e00-\u9fff]` 只取小写/CJK 单字；ASCII 单字符丢弃而 CJK 单字保留；`_clean_title` 首非空行 + 去首尾引号（含弯引号）+ 32 字符截断。

## expiry（`src/zkc/expiry.py`，位于 `src/zkc/` caution unit）
- `_as_uuid(node_id)` 是唯一天然标量/字符串可桥函数；`route_expired` 的决策表本身确定性但入参为 `Storage` + UUID，unit bridge 录到的是桥接器退化的 `$repr`，不能证明决策逻辑。
- `apply_archive` / `enqueue_review` / `_already_open` / `_resolve_open` / `apply_distill` / `route_and_apply` / `process_expired_dynamic_nodes` 全部吃 Storage / callable / `datetime` / dataclass，按 Q5=C 暂留 Python；若后续要证决策表，须走 app 黑盒或另行提供可注入 snapshot seam（改 Python 源码前需 zj 拍板）。
- 阈值来自 `tuning.get("ROT_THRESHOLD")` / `tuning.get("PRESSURE_DEFER")`；Rust 侧只能标 `recorded-literal`，不得 promote 成 CALIBRATED。

## 拟展开的 ticket
1. transport 纯函数 port：bridge / record / port / diff / gate，覆盖 JSON-RPC 帧与契约白黑名单。
2. context 纯函数 port：`_clean_title` + `fallback_name`，补中文/ASCII/排序边界 case。
3. expiry 边界确认：只录 `_as_uuid` 可证部分；决策表与 Storage 依赖显式登记 hold，不伪造等价。

## 边界
本 finding 是**盘点**，不是等价证明；每个子 ticket 必须各自有 cases.jsonl + diff/gate 证据才允许置「已完成」。
