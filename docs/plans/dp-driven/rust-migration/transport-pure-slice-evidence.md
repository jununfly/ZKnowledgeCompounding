# Evidence · transport 纯函数切片（ticket 17）

> 2026-11-27，DP carrier 过程态证据；长期结论须提炼到 ADR / 架构，不把本文件当权威源。

## 范围与 oracle
- Unit：`src/zkc/transport/`（analyze: 400 LOC / readiness 80 / 11 bridgeable exports）。
- `bridge` 导出 10 个纯函数：`contract_snapshot` / `tool_schema` / `is_blacklisted` / `is_allowlisted` / `validate_arguments` / `decode_message` / `encode_message` / `is_notification` / `result_response` / `error_response`。
- `--keep` 留 Python：`serve_stdio`（stdio I/O，非纯函数）；桥接器自动保留 `main` / `build_server` / `ToolSpec` / `ResourceSpec` / `McpServer` / `JsonRpcError`（类或 callable 持有者）。
- 录制期唯一 oracle = Python 原实现；Rust 单测只做已证行为的日常回归。

## 录制
- 命令：`rust-anything bridge <root> src/zkc/transport/ --out rust/transport-rs --name zkc-transport-rs --keep "serve_stdio: ..."`，随后 `record --count 30 --inputs tmp/transport-inputs.jsonl`。
- 结果：**429 cases（57 expected errors）**；输入分布 decode_message 60 / error_response 61 / is_blacklisted 56 / tool_schema 50 / is_allowlisted 47 / validate_arguments 43 / result_response 41 / encode_message 35 / is_notification 34 / contract_snapshot 2。
- 定向输入覆盖：JSON-RPC 帧合法/非法（parse、非对象、版本错、method 空/非字符串）、中文与嵌入换行转义、契约白/黑名单别名（`history/delete`、`meta.claim`、`delete_history`、大小写/前后空白）、JSON Schema required/type 的 bool-vs-int 与缺省分支、`data=None` 省略。

## 红→绿修正
1. 首轮 `diff` 375/429，唯一差异族：`decode_message` 的 `JsonRpcError` 抛出被生成 wrapper 的通用 `named_error` 降级为 `ValueError: JsonRpcError: ...`。根因是 `JsonRpcError.__init__(code, message, data)` 需要 3 参，而通用 helper 只 `call1((text,))`。在生成的 `src/lib.rs` 增加 `JsonRpcError` 专门分支，按错误文本映射 code（-32700/-32600/-32601/-32602/-32603）并用原类构造；**这是生成绑定 patch，`refresh` 会覆盖**，已写入 `lib.rs` 注释。
2. clippy 三修：连续 `replace` 合并为 `replace(['-', '.'], "_")`；嵌套 `if` 改 let-chain；单测 `&&str` 比较改 `Some(&"...")`。`cargo fmt` 后复跑。

## 终态
- `diff`：**429/429 cases match**。
- `gate`：**全 pass**（fmt / clippy -D warnings / cargo test 5 tests 10 assertions / unsafe / lockfile / ported / size 273 lines Rust vs 400 Python / literals / error cases / panics / build / api / behavior）。
- 语义保真点：`contract_v1.json` 以 `include_str!` 嵌入，配 `serde_json` `preserve_order` 保 key 序；黑名单词形归一化保留 `/`、折叠 `-`/`.` 的非对称行为照抄；`validate_arguments` 对 `None` schema / 非 dict arguments 的错误文本照录。

## 边界
- 只证明**录制输入上的纯函数行为**；`McpServer` 分发/审计/注册表不变量、stdio 循环、contract 文件后续演进均不在本 gate 覆盖内。
- transport ↔ mcp 的 import cycle 不因本切片消失；Rust 侧替换 seam 仍须整对接线，不得宣称「transport 已可独立插拔」。
- `src/zkc/**` 零改动；未 commit/push。
