# Finding · metrics.py 的可录制边界（R7 / §3 发现回灌）

> 归属：task2（核心 domain + repository 迁移）、ticket 8。发现时间 2026-11-27。
> 类型：工具桥约束（不是产品行为缺陷）。结论写入 durable corpus，供后续切片复用。

## 观察

`src/zkc/metrics.py` 共 9 个导出函数。`rust-anything bridge` 全量桥接后 `record --count 100` 得 415 case，其中 **312 threw**。按函数分解：

- **可证**：`compounding_factor`（标量入参 `cd,rr,mo,dc,weights,method_target`）拿到 103 个有效 case（含 NaN/Infinity/负 target/显式 weights/短 list/str weight 等边界）。
- **不可证**：其余 8 个（`connection_density`/`reuse_rate`/`methodology_output`/`decay_controllability`/`rot_rate`/`build_report`/`build_report_dict`/`metrics_report`）全部录制抛 `AttributeError: 'dict'/'list' object has no attribute 'nodes'`。

## 根因（已读生成的 wrapper / driver 源码确认）

`MetricInputs` 是普通 `dataclass`。rust-anything 的 Python wrapper `_enc()` 不编码 dataclass，回退成 `{"$repr": repr(v)}`；driver 只在录制侧有 `$object` 重建逻辑（`dataclass_named`），但 **diff/replay 侧的 wrapper 没有**——Rust 端口拿不到结构化的 `nodes`/`edges` 字段。`metrics_report(store)` 另因 `Storage` 对象同样不可跨 PyO3。

因此这些函数的录制 case 只含"原实现因桥失败而抛的异常文本"，**没有真实行为信息**，不能作为 port 的等价证据。若硬把它们 port 成返回 `E_NOT_PORTED`，diff 只会比较异常文本差异，属伪造等价。

## 处置

- 用官方 `bridge --keep "<fn>: <reason>"` 把 8 个不可证函数声明为**留在 Python**（写进 crate 的 `rust-anything.json`），只桥接 `compounding_factor`。新 crate `rust/metrics-scalar-rs`。
- 全量桥接的草稿 crate `rust/metrics-rs` 保留作对照（不进 gate、不作为交付）。
- 结论约束后续切片：**吃 dataclass / Storage / 复杂对象的函数，unit bridge 无法证明**；这些函数要么走 `app record --effects/--db-dump` 的黑盒路径，要么在 Rust 侧改用显式结构体参数（脱离原签名，不再是等价 port）。不得用录制异常文本冒充行为覆盖。

## zj 决策（2026-11-27 20:34，Q5=C）

8 个不可证函数**暂留 Python**。定性：**工具编码边界导致的暂留，不是业务不可迁、不是永久放弃**。tk8 核心 piece 本轮只交付标量/纯函数层（`compounding_factor`，gate 243/243）；ticket 15 保持 hold、不 close。

- **B 已排除**：Rust 侧改显式结构体参数会脱离原签名，diff/gate 失去机械对照 → 退回自证，与 Q3「录制期 Python 原实现为唯一 oracle」冲突。
- **A 收窄适用面**：仅 `metrics_report(store)` 真吃 Storage，值得在 app record --effects 基建就绪后单独走黑盒；其余 6 个 `MetricInputs` 纯计算 + `build_report`（返回 dataclass）走黑盒会丢失中间输入组合，`MetricInputs` 上 5 个度量的边界组合态尤其无法逐一覆盖，case 密度低于 unit-level，不为此起 DB。
- **防遗忘条款**：
  1. ticket 15 hold 触发条件 = app record --effects 基建就绪 → 只对 `metrics_report` 走 A；
  2. 其余 7 个若要迁，须先解决 wrapper `_enc` 的 dataclass 编码（属改工具生成代码，refresh 会覆盖，需单独评估并留证据），或显式接受永久留 Python——两者都须在 ADR 定性，不得默认翻案；
  3. 本 finding 即 durable 定性载体，后续任何切片不得把"暂留"读成"已验证等价"或"业务不可迁"。

## 与既有边界的关系

与首切片的 `datetime` 过不了 JSON bridge（`finding-port-boundary.md`）同类：都是"结构化值过不了 JSON 桥"。本条把适用面从 datetime 扩展到普通 dataclass 与 Storage 对象；Q5=C 是这条边界在决策层的固化。

## 最终落定（2026-11-28，zj 拍板选项 A，ticket 15 决议）

- `metrics_report(store)`：走 A 路径迁移（依据 finding f7 已验证：front-door + 手写
  glue + PG 查询层，app replay 2/2、fallback 0%）。工作承载 = **ticket 45**（task 4，
  derived-from finding 22）。
- 其余 7 个（6 × MetricInputs 纯计算 + `build_report`）：**永久留 Python**，定性
  「工具编码边界永久留置」，ADR：`docs/zj-adr/0014-q5-metrics-boundary-final.md`。
- ticket 15 关闭（决议已做出）。任何后续重提 7 函数迁移须新 ADR，不得默认翻案。
- 本 finding 的 Q5=C「暂留」定性至此被 ADR-0014 细化：`metrics_report` 由暂留转迁移，
  7 函数由暂留转永久留置。「暂留」读法即日作废。
