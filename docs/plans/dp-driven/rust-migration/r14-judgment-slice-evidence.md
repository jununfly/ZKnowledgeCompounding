# Evidence · judge_r14 R14 判据聚合纯函数切片（ticket 31）

日期：2026-11-28。过程态证据，非长期权威；R14 判据语义仍以 risks.md R14 / 架构 §8 / 代码为准。

## 结论

`rust/r14-judgment-rs` 复刻了 `src/zkc/cross_source.py::judge_r14` 这一确定性纯函数：
把一组跨源补全 run 的 report dict 聚合成 R14 裁决。录制期 Python 原实现仍是唯一 oracle。
DP：finding 15 已登记（观察 memo 保留未完成）、ticket 31（parent 8，blocks
`31→8`）已完成并释放租约，`validate` 0 errors；ticket 8 仍在进行、是唯一活跃租约。

## 切片范围与录制缝

process-only alias `spikes/spike-18-r14-judgment/pure_bridge.py` 只暴露一个公开名字：

- `judge_r14(runs, min_runs)` → 原 `zkc.cross_source.judge_r14(runs, min_runs=min_runs)`

两个编码缝，决策仍逐字委托原实现：

1. **keyword-only → 位置参数**：Python 侧 `min_runs` 是 keyword-only，alias 暴露为第二
   位置参数并在委托时还原为 `min_runs=`（同 scheduling spike-09 的 `human=` 归一）。
2. **dataclass → 固定键 dict**：返回 `R14Verdict` dataclass，PyO3 `_enc` 不编码、会回退
   `$repr`；alias 把它编码成 7 键 dict（total / fired / trigger_rate /
   completion_latency_median / main_latency_median / should_close_completion / reason）。
   键序即 Python dataclass 字段序，由 `serde_json preserve_order` + `Map` 插入序保住。

`rust-anything record rust/r14-judgment-rs --count 0 --inputs tmp/r14-inputs.jsonl`
冻结 **20 case**（0 throw），覆盖 tests/test_r14_judgment.py 的全部 5 个 reason 分支
加边界。

## 关键语义

- **触发率优先**：`fired / total`；默认阈值 `> 0.5` 才进入延迟门槛。录制覆盖 4/10（率内）
  与 6/10（率超）两路；恰好 5/10（=0.5，不严大于）保持 open，reason=`trigger_rate_within_budget`。
- **延迟中位**：`statistics.median` 奇数取中位、偶数取两中平均。录制含 3 条 completion
  延迟（250/300 中位）与 4 条（100/200/300/400 中位 250）验证奇偶两分支；main 延迟用
  6+4 条的偶数组中位验证。Rust 侧 `statistics_median` 排序后按奇偶分支复刻。
- **关补全判据**：率 > 0.5 且 completion 中位 > main 中位 × 1.5 → 关。录制含 200>150（关）、
  120≤150（不关，reason=`completion_latency_within_budget`）、恰好 150=150（不严大于，不关）。
- **数据不足**：`total < min_runs` → `insufficient_data`；0 触发 → `no_completion_fired`；
  completion 延迟缺失（None 字段被过滤）→ 中位 None → 不伪造关闭。录制覆盖 min_runs
  默认 10、放宽 2、边界 0 与空 runs。
- **Python 数值转换**：延迟字段可为 JSON 数字或数字字符串（录制含 `"100"`/`"200"`），
  `float()` 转换后参与中位数；`completion_fired` 用 Python truthiness（bool / int 0-1）。
  None 字段在进入列表推导前被 `is not None` 过滤，且 `r["..."]` 索引不抛（过滤保证存在）。
- **编码伪差异**：整数值 float（如 `300.0` / `1.0`）被 bridge 记作 `{"$float":"..."}` 标记，
  非整数 float（如 `0.6`）是裸数字；Rust 正常返回 f64，序列化层对称处理，逐字一致。
- **入参不变性**：tests 的 `test_does_not_mutate_input` 由原实现保证（只读 `r.get` / `r[...]`），
  Rust port 对 `&Value` 只读迭代，无写回；此性质由原测试守护，非本录制 case 直接断言。

## 机械验证

| 检查 | 结果 |
|---|---|
| `rust-anything diff rust/r14-judgment-rs` | **20/20** recorded cases match（0 mismatch） |
| `rust-anything gate rust/r14-judgment-rs` | **Gate passed**（fmt / clippy / cargo test / unsafe / lockfile / ported / size **2.3x** / literals **0** / tests / error cases / panics / build / api / behavior 全绿） |
| `app replay --build`（既有 11 case） | **11/11 passed**，fallback **0.0%**（本片未接线，零回退） |
| `make test` | **671 OK** |
| mcp-gate / invariant / authority | **6/6** / **0 violations** / **0 leaks** |

## 踩坑（本片实际遇到）

1. **gate literals**：5 个 reason 字符串是 Python 原实现里明写的返回文本，gate 视作
   recorded value，须逐个加 `// recorded-literal: cross_source.py R14 reason branch` 同行注释
   才过 literals 检查（未 promote 为可调参数）。
2. **clippy unreachable_patterns**：`py_truthy` 的 match 已穷举 `Option<&Value>` 全部分支，
   末尾 `_ => true` 冗余，clippy -D warnings 拦下；删掉后 gate 全绿。

## 边界与风险

- **不是 R14 关闭的运行时保证**：真实 run 由 zj 经 dogfood 产生、经 `r14_telemetry`
  以 append-only 落库；本 port 只证判据函数的确定性聚合，不产生 completion_fired /
  延迟数据、不触发任何补全关闭动作。R14 节点仍 open（关闭挂真实数据）。
- **未 wire 进 `rust/app`**；20 case 是人工定向输入，不是全输入空间。NaN/Infinity、
  负数延迟、超大 min_runs、`runs` 非数组等越界输入不在录制域内（未录制不得声称覆盖）。
- 阈值 0.5 / 1.5 / min_runs 默认 10 均来自 risks.md R14，标 recorded-literal，不 promote
  为 CALIBRATED，不写回 tuning REGISTRY。
- `r14_telemetry`（文件 IO / append-only）、`combine`/`apply_combine`（LLM + Storage）、
  pydantic 模型留 Python；Q5=C 的 dataclass/Storage 编码边界未被翻案。
- 不触碰 `CALIB_OVERRIDE_AT` caveat；`src/zkc/**` 零改动，`zkc` CLI 未加命令。
- 未提交：本片代码/证据均留在工作区，按 zj 的 checkpoint 指令再拆 feat/chore 提交。
