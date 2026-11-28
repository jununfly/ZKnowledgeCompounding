# Evidence · to_modeling_artifact 接入 rust/app（ticket 34）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与 kill switch 语义仍以 app 实现为准。

## 结论

`rust/artifact-shaping-rs` 的 `to_modeling_artifact` 已作为新前门 `unit-artifact-shaping` 接入 `rust/app`。
DP：ticket 34（parent 8，blocks `34→8`）已完成并释放租约，ticket 8 仍是唯一活跃租约。

命令形态：

```
metrics-snapshot unit-artifact-shaping to_modeling_artifact '<json-array>'
# json-array = [artifact, produced_by]
# kill switch: RUST_ANYTHING_UNIT_ARTIFACT_SHAPING=original
```

## 接线方式

- 前置登记：`rust/app/src/cli.rs::UNIT_COMMANDS` 与
  `rust/app/rust-anything.json::commands` 加入 `unit-artifact-shaping`。
- 真跑 `rust-anything app wire . artifact-shaping-rs --command unit-artifact-shaping --skip-gate --no-check`：
  生成 Cargo path 依赖（`Cargo.toml`/`Cargo.lock`）、unit 记录（name `artifact-shaping`、
  crate `artifact-shaping-rs`）、switch 名与 glue stub；switch 由工具命名为
  `RUST_ANYTHING_UNIT_ARTIFACT_SHAPING`（由 crate 名生成，不是 oracle key `artifact-shaping`）。
- 照例重写 `units/mod.rs` 丢 `metrics_report`：接线前备份，wire 后手合并回
  metrics 路由 + 九个既有单元 + artifact-shaping，统一 `<fn> <json-array>` 协议。
- 新 glue `rust/app/src/units/artifact_shaping.rs`：1 函数，`artifact` / `produced_by`
  两个位置 `Value` 透传给 `artifact_shaping_rs::port::to_modeling_artifact`。原实现的
  `produced_by` 是 keyword-only，但 spike-19 alias 已还原为位置参，glue 无需特判。
  port 错误是裸 `ValueError: ...` / `TypeError: ...` 文本，与 oracle 一致，
  **无异常前缀缝**（同 `unit-r14`，区别于 `unit-distill` 的 `zkc.distill.` 剥离）。
- `oracle.py` 按路径加载 spike-19 alias（unit key `artifact-shaping`，kebab 与命令名一致）；
  alias `to_modeling_artifact(artifact, produced_by)` 直接接受两位置参，与统一入口
  `target(*args)` 一致，无需 kwargs 特判（区别于 scheduling spike-09 的 `human=`）。
- `smoke_units.py` 新增 8 个 case（来自 10 录制 case 的代表样本）：覆盖完整 dict
  落库形态（顶层 `_` 剔除 + 大写 UUID 规范化）、空 dict 默认值、重复/大写 refs
  规范化、嵌套 `_` 与嵌套 `evidence_refs` 保留在 body、unicode/emoji、混合值类型、
  非法 UUID 的 ValueError、`produced_by` 非 UUID 串原样透传。

## 机械验证

| 检查 | 结果 |
|---|---|
| `smoke_units.py` | **77/77** 逐字匹配（既有 69 + artifact-shaping 8） |
| kill switch（假 python3 包装器） | default 不调 Python（0 次）；`=original` 恰好调一次 oracle 且输出一致；关掉后不再调用（0 次）。错误 case 两路都是 `ValueError: badly formed hexadecimal UUID string`、exit 1 |
| `app replay --build rust/app/target/debug/metrics-snapshot`（既有 11 case） | **11/11 passed**，fallback **0.0%** |
| crate diff / gate | **10/10**；Gate passed（size 1.1x，literals 0） |
| app fmt / clippy -D warnings / build | 全过 |
| `make test` | **671 OK** |
| mcp-gate / invariant / authority | **6/6** / **0 violations** / **0 leaks** |

## 边界与风险

- **新前门，不是 lift**：77 smoke case 是人工选定输入，非全输入空间证明；录制期
  Python 原实现仍是唯一 oracle。
- 本片只证结果落库形态的确定性转换，不跑 `combine`/`apply_combine`/`revert`、
  不写 Storage、不产 R14 遥测；`produced_by` 只是 provenance 载荷透传，不做 UUID
  校验（原实现行为，非缺陷）。非法 UUID 的 `ValueError` 文本仍是 recorded-literal，
  不 promote 为 CALIBRATED；dataclass 仅作输出编码缝，未翻 Q5=C。
- 再次跑 `app wire` 会重写 `units/mod.rs`，必须重新手合并；`refresh` 之后需按
  crate 纪律重新验证 gate。
- `src/zkc/**` 零改动；未提交，按 zj 的 checkpoint 指令再拆 feat/chore 提交。
