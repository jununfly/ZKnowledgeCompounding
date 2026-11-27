# Evidence · distill 解析层四函数接入 rust/app（ticket 30）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与 kill switch 语义仍以 app 实现为准。

## 结论

`rust/distill-parse-rs` 的四个函数已作为新前门 `unit-distill` 接入 `rust/app`。
DP：ticket 30（parent 8，blocks `30→8`）已完成并释放租约，ticket 8 仍是唯一活跃租约。

命令形态：

```
metrics-snapshot unit-distill <fn> '<json-array>'
# fn = extract_json | parse_json_output | parse_llm_output | validate_result
# kill switch: RUST_ANYTHING_UNIT_DISTILL_PARSE=original
```

## 接线方式

- 前置登记：`rust/app/src/cli.rs::UNIT_COMMANDS` 与
  `rust/app/rust-anything.json::commands` 加入 `unit-distill`。
- 真跑 `rust-anything app wire . distill-parse-rs --command unit-distill --skip-gate --no-check`：
  生成 Cargo path 依赖、unit 记录、switch 名与 glue stub；switch 由工具命名为
  `RUST_ANYTHING_UNIT_DISTILL_PARSE`（不是按 oracle key `distill` 推导）。
- 照例重写 `units/mod.rs` 丢 `metrics_report`：接线前备份，wire 后手合并回
  metrics 路由 + 七个既有单元 + distill，统一 `<fn> <json-array>` 协议。
- 新 glue `rust/app/src/units/distill_parse.rs`：4 函数 `Value` 端到端透传。
  **异常前缀缝**：port 为让 PyO3 绑定还原自定义类而返回 dotted
  `zkc.distill.DistillationError: ...`；此 front door 没有 PyO3 层，glue 在输出前
  剥掉 `zkc.distill.` 前缀，与 oracle 的 `DistillationError: ...` 逐字一致。只改编码，
  不改决策文本。
- `oracle.py` 按路径加载 spike-17 alias（unit key `distill`），`smoke_units.py` 新增
  10 个 case；unit key 与 CLI 命令名保持一致（`unit-distill` / `distill`）。

## 机械验证

| 检查 | 结果 |
|---|---|
| `smoke_units.py` | **61/61** 逐字匹配（既有 51 + distill 10，含 4 个 DistillationError） |
| kill switch（假 python3 包装器） | default 不调 Python；`=original` 恰好调一次 oracle 且输出一致；关掉后不再调用；错误 case 退出码 1 与文本也一致 |
| `app replay --build`（既有 11 case） | **11/11 passed**，fallback **0.0%** |
| crate diff / gate | **61/61**；Gate passed（size 3.2x） |
| app fmt / clippy -D warnings / build | 全过 |
| `make test` | **671 OK** |
| mcp-gate / invariant / authority | **6/6** / **0 violations** / **0 leaks** |

## 边界与风险

- **新前门，不是 lift**：61 smoke case 是人工选定输入，非全输入空间证明；录制期
  Python 原实现仍是唯一 oracle。
- `distill_node` 重试循环、prompt/schema、LLM callable、`revert_claim` /
  `revert_artifact` 的 Storage 级联与 tuning 校准继续留 Python；本片不证蒸馏质量。
- 再次跑 `app wire` 会重写 `units/mod.rs`，必须重新手合并；`refresh` 之后需按
  crate 纪律重新验证 gate。glue 中的异常前缀剥离只在 front door 生效，不影响
  PyO3 录制路径。
- `src/zkc/**` 零改动；未提交，按 zj 的 checkpoint 指令再拆 feat/chore 提交。
