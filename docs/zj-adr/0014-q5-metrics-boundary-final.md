# ADR-0014 · Q5 落定：metrics_report 走 A 路径迁移，7 个 dataclass/Storage 函数永久留 Python

日期：2026-11-28
状态：已接受（zj 拍板，ticket 15 决议）
关联：`docs/plans/dp-driven/rust-migration/finding-metrics-boundary.md`（Q5=C 定性载体）、
`decisions.md` Q5 段、ticket 15（关闭）、ticket 45（新工作承载）、finding f7（A 路径已验证）。

## 背景

Q5（2026-11-27）选 C：8 个不可证函数暂留 Python，定性为「工具编码边界导致的暂留，
不是业务不可迁、不是永久放弃」，ticket 15 hold 待 zj 按收益决定。ticket 8 收口
（2026-11-28）后，ticket 15 是 lift 链（ticket 9→10→11→12）前最后一个待决边界。

## 决议（zj 2026-11-28，选项 A）

1. **`metrics_report(store)` 走 A 路径迁移**（Rust 等价 + PG 查询层）。
   依据：唯一真吃 Storage 且在 metrics-snapshot CLI 生产路径上的函数；
   A 路径已验证（finding f7：front-door + 手写 glue + PG 查询层，app replay
   2/2、fallback 0%）。迁移工作由 **ticket 45**（task 4，derived-from finding 22）承载。
2. **其余 7 个函数永久留 Python**（6 个吃 `MetricInputs` 的纯计算 +
   `build_report` 返回 dataclass）。定性：**工具编码边界导致的永久留置**——
   unit bridge `_enc` 不能编码 dataclass；改签名违反 Q3 机械对照（Q5-B 已排除）；
   改工具本体（`_enc` 支持 dataclass）为 7 个低业务价值函数不值得（refresh
   覆盖风险 + 影响所有 crate）。它们是 report 中间计算，核心
   `compounding_factor` 已 gate 243/243。
3. **ticket 15 关闭**：决议已做出，ticket 使命完成。

## 后果

- 正面：lift 链解锁——metrics-snapshot 前门可以走「Rust 链 + `metrics_report`
  storage glue」的明确形态；Q5 边界不再悬置。
- 代价：7 个函数在 Rust 侧无等价物；lift 时 metrics CLI 仍需 Python 执行
  `MetricInputs` 计算（或 Rust 侧自证重写，那将违反 Q3、不作为等价 port）。
- 边界不变式：本 ADR 不改变「录制期 Python 原实现为唯一 oracle」；ticket 45 的
  A 路径同样受 Q3 约束（Python 侧真跑录制，Rust 仅回归不自证）；7 个留置函数
  任何后续重提须新 ADR，不得默认翻案。
- 「代码能力 ≠ 生产接线」caveat 不变：ticket 45 交付的是可证迁移，不是 lift。
