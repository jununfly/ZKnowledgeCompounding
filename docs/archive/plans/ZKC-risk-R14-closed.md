# 风险 R14 — 补全回路延迟成本（已闭合归档）

> 归档时间：2026-11-12
> 闭环节点：roadmap 节点 1-27-2（真实 10 run 裁决收口）
> 原始登记册：原 `docs/risks.md` 风险登记册表行 R14；本文件为其归档副本。
> 闭环证据：roadmap `docs/roadmap/roadmap.json` 1-27-2 决策记录 + `ROADMAP.md`；`data/r14_telemetry.jsonl`（10 条真实 Ollama run，run_id 去重）；`scripts/r14_status.py` 裁决输出；`src/zkc/cross_source.py:judge_r14` 纯函数 + `tests/test_r14_judgment.py` / `tests/test_r14_telemetry.py`（共 17 测试全绿）。

## 风险原描述
**补全回路的延迟成本未入预算**：跨源补全在主生成不达标时 **+1× LLM 调用**（spike-11:92），若补全频繁触发或补全延迟显著超过主生成，MVP 延迟预算将失真。

## 来源
审计 B2（spike-11:92）

## 影响
MVP 延迟预算失真；「0/3 触发」只是 4B 样本，换语料后真实触发率未知——补全回路是否可 safely 保留默认开启无生产数据支撑。

## 降级预案（默认处置）
- **埋点 + kill switch 已随 1-5-2 落地**（commit 1097bc6）：`report.completion_fired` / `main_latency_ms` / `completion_latency_ms` + `complete_on_shortfall` 开关。`complete_on_shortfall` 默认 ON = 主生成不达标时自动触发补全回路。
- **触发率聚合与超预算判定判据**（roadmap 1-8-2 decide 模板）：`trigger_rate > 0.5` 且 `completion_latency_median > main_latency_median × 1.5` → 关补全（kill switch）。
- 该判据经 1-19 衔接补 `judge_r14` 纯函数 + 单测，成为可机械判定实现；关闭仍依赖真实生产 run 落库聚合，不伪造、不误判。

## 闭环状态与证据（2026-11-12）
- **状态**：已确认安全 · 收口（保持 `completion` 开启，补全回路预算可控）
- **闭环节点**：1-27-2（1-27 子节点，root 1 随之 completed）
- **真实裁决证据**（`judge_r14` 对 `data/r14_telemetry.jsonl` 的 10 条真实 Ollama `qwen3.5:9b` run）：
  - `total = 10`、`fired = 2`、`trigger_rate = 0.200`
  - `main_latency_median = 43.9s`、`completion_latency_median = 13.5s`
  - `reason = trigger_rate_within_budget`、`should_close_completion = False`
  - 结论：真实触发率远低于 50% 阈值，且补全延迟中位（13.5s）远小于主生成中位（43.9s），补全回路不超预算 → **默认 `complete_on_shortfall` 维持 ON 安全**。
- **数据真实性**：10 条均为本机 Ollama 真实 LLM 调用落库（2 smoke + 8 后台交替 cross_source / combine_apply）；`dogfood_cross_source.py` 原 `run_id=cross_source:{kept_ids}` 恒定会去重阻塞积累，已改为追加毫秒 nonce 使每次真实 run 作为独立样本入 telemetry。

## 残余与观察（保留）
- 样本为 dogfood 同构语料，非 zj 有机生产使用；真实生产分布可能更宽。
- `data/r14_telemetry.jsonl`（gitignore）可随时 append 新真实 run，`python3 scripts/r14_status.py` 即重判；若未来真实触发率突破 0.5 且补全延迟超主生成 1.5×，再触发 kill switch 关闭补全。

## 结论
补全回路的延迟成本风险已通过真实 10 run 裁决闭合：在真实数据下触发率 0.20、补全延迟可控，默认 `complete_on_shortfall=ON` 安全，无需关闭补全。风险册本表（`docs/risks.md`）R14 表行与「关键降级链」bullet 已移除，归档至本文件。
