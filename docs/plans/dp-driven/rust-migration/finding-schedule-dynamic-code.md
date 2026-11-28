# Finding 23 · D2 消解：scripts 动态代码不构成迁移 blocker（调研结论）

日期：2026-11-28。对应 ticket 13（D2「scripts/ 动态代码 blocker 调研与消解」，task 5）。
触发条件「等待核心 piece 完成后启动」已满足（ticket 8 于 11-28 收口）。

## 调研方法

全仓 `scripts/*.py` 扫描动态代码模式：`eval(` / `exec(` / `importlib` /
`spec_from_file_location` / `__import__` / `globals()[` / `locals()[` /
`runpy` / 动态 `compile(` / 动态 `getattr` / `open()*.py` 执行。每处命中人工读上下文定性。

## 三处命中逐一定性

| 位置 | 模式 | 定性 |
|---|---|---|
| `daily_e1_driver.py:114-119` `_import_meter` | `spec_from_file_location` + `exec_module` 加载 `scripts/e1_calibration_progress.py` | **唯一真缝，但不构成 blocker**（见下） |
| `dogfood_combine_apply.py:163` | `__import__("os")` | 伪缝：等价静态 `import os`，仅写法怪异，语义完全静态 |
| `dogfood_cross_source.py:162` | `__import__("os")` | 同上 |

`re.compile` 命中均为静态模式字符串正则编译，非代码动态执行。

## 唯一真缝为何不是 blocker

1. **加载目标零业务逻辑**：`scripts/e1_calibration_progress.py` 全文 39 行，
   是纯 CLI 转发层（argparse → 转发 `zkc.calibration.build_report/format_human`），
   头部明示「纯逻辑已提升为 zkc.calibration（Form B：zkc meter 子命令复用同一份）」。
   动态加载路径上没有任何业务函数。
2. **目标静态已知**：`METER_SCRIPT = ROOT / "scripts" / "e1_calibration_progress.py"`
   是模块级常量，无用户输入注入；`spec_from_file_location` 在此等价于
   「按文件路径静态 import」，不是运行时任意代码执行。
3. **Rust 侧无需复刻**：`_import_meter`/`do_meter` 属 daily_e1_driver 的
   外壳编排（与 argparse/subprocess 同类，既有 D 系边界留 Python）；
   其效果（调 `zkc.calibration`）在 Rust 录制面完全静态可达——`zkc.calibration`
   可直接静态导入（已实测），spike-24 已证明 sys.path 机制对 scripts 录制面可用。
4. **消解动作 = 定性更新，不改源码**：非侵入原则（不必要不动源码）；
   `__import__("os")` 纯风格问题不处理。

## 消解结论

**D2 作为迁移 blocker 解除**。scripts 的动态代码是「外壳内动态加载零逻辑转发
脚本」，与 Q5 的 dataclass 编码缝不同类，不需要工具升级、不需要源码改造、
不需要黑盒基建。scripts 迁移的真实边界仍是：
- 已迁：`daily_driver_schedule` 渲染层三函数（tk43/44）；
- 弱候选：`_slice_function`/`_is_roadmap_carrier`（无直接单测，锚点弱）；
- 外壳/编排/LLM/Storage 类：留 Python（既有边界不变）。

## 边界（诚实读法）

- 本 finding 消解的是「动态代码 = 迁移 blocker」这个定性，不是「scripts 全部
  可迁」；task 5 剩余弱候选的去留仍待按收益另行评估。
- daily_e1_driver 外壳不因本消解被 port；E1 收口链路的运行时保证不变。
- 若未来 `e1_calibration_progress.py` 被塞入业务逻辑，本结论失效，须重开调研。
