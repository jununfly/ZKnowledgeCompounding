# Evidence · MCP capture CaptureProfile 校验切片（ticket 48）

日期：2026-11-28。过程态证据，非长期权威；crate 实现与 gate 语义以 `rust/capture-profile-rs` 为准。

## 结论

`src/zkc/mcp/capture.py::CaptureProfile.__post_init__` 的写集合重叠不变量已 port 到 Rust
`rust/capture-profile-rs::validate_capture_profile`，**gate 全 pass（6/6 recorded cases match，含 3 个 ValueError）**。
**未接线进 `rust/app`**（安全契约校验门，非运行期 per-call 函数）。DP：ticket 48（parent 9，task 3）已完成并释放租约。

## 选片与边界（为什么只取这一块）

- `capture.py` 里真正 JSON-native、可干净录制的只有 `CaptureProfile.__post_init__` 的重叠校验：
  入参 `allowed/forbidden`（list[str]），输出 `True` 或 `ValueError`。spike 用 list→frozenset 包装委托原 dataclass，
  决策逐字来自原实现。
- **`capture_documents` 与 `initialize_decay` 明确出局**（不在 ticket 48 范围）：它们绑 callable（`audit_sink`/routers）、
  `Storage`（`store`）、`datetime.now`、领域 `node` 对象——即 Q5 记录的 dataclass/Storage 编码缝；
  且 `initialize_decay` 本质是 `decay.compute_decay_score` 的薄委托，已由 `decay-rs` 覆盖。归入 tk-51（capture 编排，待工具链 + 依赖）。

## 录制与实现要点

- `rust-anything bridge . spikes/spike-26-capture-profile/pure_bridge.py --name capture-profile-rs -o rust/capture-profile-rs`。
- `record --count 0 --inputs <6 定向 case>`：disjoint（→true）×3、overlap（→ValueError）×3，**6 recorded / 3 threw**。
- 错误串逐字复现：`ValueError: capture profile 写集合自相矛盾：<sorted(overlap) list-repr>`。
  Python `sorted()` 对 ASCII 标识符 = 码点序 = Rust `BTreeSet`（UTF-8 字节序）；list-repr 用单引号 + `", "` 连接，
  多元素（`['a', 'b']`）与单元素（`['meta_claim']`）均经 case 实证匹配。

## 机械验证

| 检查 | 结果 |
|---|---|
| record | **6 cases（3 threw）** |
| build | PyO3 模块构建成功 |
| crate diff | **6/6 cases match**（3 ok + 3 错误串逐字一致） |
| gate | **Gate passed**：fmt / clippy 0 warn / cargo test / unsafe 0 / lockfile / ported / size 2.7x / literals 0 / tests 2·4 / error cases / panics 0 / build / api（exports validate_capture_profile）/ behavior **6/6** |

## 边界与风险

- 允许写 / 禁止写集合的真相源是 Python 侧 `CaptureProfile` + `FORBIDDEN_WRITES`（ADR-0004 安全契约）；
  Rust port 是录制期等价回放，非策略新源。集合变更须先改 Python 并重录。
- 覆盖的 overlap 逻辑仅 `__post_init__`；`CaptureProfile` 其余字段（enabled / max_documents / untrusted_content）
  是默认值 passthrough，不构成本片证明，也不声称覆盖 `capture_documents` 的运行语义。
- 非 list / 非 str 入参未录制，port 中的 `TypeError:` 分支是防御性兜底、非等价证据。
- `src/zkc/**` 零改动；未接线进 app。
