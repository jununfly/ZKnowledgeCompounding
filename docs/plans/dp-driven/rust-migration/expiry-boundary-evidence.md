# Evidence · expiry 纯函数决策表切片（ticket 19）

> 2026-11-27，DP carrier 过程态证据；长期结论须提炼到 ADR / 架构，不把本文件当权威源。

## 范围与 oracle
- 目标：`src/zkc/expiry.py::route_expired` 的确定性决策表，不是整个 expiry 模块。
- 桥接边界：`Storage` 过不了 PyO3 JSON bridge；process-only 适配器 `spikes/spike-08-expiry-routing/pure_bridge.py` 用 JSON rows 构造原 `SchedulableNode` + 单方法 fake store，**逐字调用原 `route_expired`**，不重实现决策逻辑。Python 原实现仍是唯一 oracle。
- 留 Python：`apply_archive` / `enqueue_review` / `apply_distill` / `route_and_apply` / `process_expired_dynamic_nodes`（Storage / callable / datetime，Q5=C）。

## 录制与证明
- `record --count 5 --inputs tmp/expiry-inputs.jsonl` → **57 cases（26 成功决策 + 31 adapter/UUID 预期异常）**。
- 定向覆盖：无/错 id/archived row；decay 0.899999976（float32 展开）、0.9 边界、0/0.5/1/2.5/-1/NaN/Infinity；captured→archive；conn/self_loop/higher_dim 三路 contextual；pressure 0.79/0.8/0.81/NaN/±Infinity；orphan→abstain；坏 UUID 与非 dict row。
- `diff`：**57/57 cases match**。
- `gate`：**全 pass**（fmt / clippy -D warnings / cargo test 4 tests 6 assertions / unsafe / lockfile / ported / size 254 Rust vs 81 Python / literals（1 条 library 错误文本已按 gate 要求标注）/ error cases / panics / build / api / behavior）。

## 语义保真点 / 红→绿
- Python `:g`（6 位有效数字）必须复刻：`0.8999999761581421` 的 reason 输出是 `decay 0.9 < ROT 0.9`。Rust 实现 `py_g`（`{:.5e}` 科学计数 + 定点裁剪 + 指数两位补零）。
- `tuning.get("ROT_THRESHOLD")=0.9` / `PRESSURE_DEFER=0.8` 当前是 **SIMULATION，不是 CALIBRATED**；Rust 侧标 `recorded-literal`，不得 promote。
- NaN 输入：`decay=NaN` 不满足 `< 0.9` → 继续路由；`pressure=NaN` 不满足 `>= 0.8` → distill（与 Python 比较语义一致）。
- adapter 的 `dict(row)` 异常文本也被录进 oracle（`TypeError: 'bool' object is not iterable`、`ValueError: dictionary update sequence element #0 has length 1; 2 is required`），Rust 侧照录，不伪造。
- gate size 初报 5.2x，因为比较对象是 48 行的 process-only shim；shim 文档补足决策表与边界说明后为 81 行 / 3.1x。**这不是与 `expiry.py` 的行数对比**。

## 边界
- 只证明决策表在录制快照上的行为；真实 `load_schedulable()` 过滤、archive/review_queue 写入、distiller 注入均未覆盖。
- 生产接线事实不变：`route_and_apply` 在生产未传 distiller（DISTILL 只入队）；本切片不改变该行为。
- `src/zkc/**` 零改动；未 commit/push。
