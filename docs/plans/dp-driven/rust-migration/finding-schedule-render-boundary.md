# Finding · scripts 渲染层可证切片与 D2 边界隔离

日期：2026-11-28。过程态 finding（非长期权威），供 ticket 8 选片依据。

## 结论

`scripts/daily_driver_schedule.py` 的三个纯渲染函数（`build_task_action` /
`build_register_command` / `build_unregister_command`）是**可独立 port 的纯函数切片**：
JSON-native 入参（str/list）与返回（str/list[str]）、无 dataclass/Storage/UUID/
datetime/LLM/callable/全局状态缝、有 6 条直接单测锚点
（`tests/test_daily_driver_schedule.py::ScheduleRenderTest`）。已 port 到
`rust/schedule-render-rs`，26/26 diff、gate 全过。

## 与 D2 / ticket 13 的边界隔离（关键，不翻案）

- **Q1=B**（`decisions.md:8,30`）已明确把 `scripts/` 纳入迁移范围，故跨入 scripts 本身不翻案。
- `finding-inventory.md:13` 把整个 scripts 标为 D2 blocked 是**粗粒度判断**。逐文件实测：
  scripts 下 25 个 .py 中 `eval`/`exec`/`compile` 零命中；唯一真动态代码缝是
  `scripts/daily_e1_driver.py:115-118` 的 `_import_meter()`（`spec_from_file_location`
  + `exec_module`），在**函数体内**，且不在本切片三函数的任何导入路径上。
- 本切片所在模块 `daily_driver_schedule.py` 顶层只有静态 import + 常量 + 正则编译 +
  `Path(__file__).resolve()`（静态路径解析，非动态代码），可用 process-only alias 录制。
- **DP ticket 13（scripts 动态代码 blocker 调研与消解，task 5，未完成，external_hold）保持不变**。
  本切片不消费、不关闭 ticket 13，也不声称消解 D2；它只证明"scripts 中不带动态
  代码缝的纯渲染函数可独立 port"。ticket 8 的下一片选择不等于 D2 blocker 已解。

## 与 print 副作用方向的裁决

上一轮留下的另一个待评估方向（剥离 print 得纯函数）**被证伪，不采用**：
- `src/zkc/` 顶层含 print 的仅 `calibration.py` / `cli.py` / `migrate.py`；
- 唯一"主体纯计算 + print"的两枚 `calibration.format_human` / `format_p64_human`
  签名均 `-> None`，剥离 print 后仅剩为 print 服务的死代码，不构成 JSON-native
  返回的纯函数；且 `format_p64_human` 唯一测试（`test_p64_progress.py:88-97`）
  的断言正是 print 输出（`'P6.4' in buf.getvalue()`），剥离 print 等于测试自毁（翻案）。
- `cli.dispatch` / `migrate.cmd_*` 剥离 print 后仍含 Storage/datetime/subprocess/文件 IO。
故本轮唯一干净方向是 scripts 渲染层。

## 已登记边界（不伪造等价证据）

1. **Unicode Nd 时间不覆盖**：Python `_TIME_RE` 的 `\d` 是 Unicode Nd，
   `'02:5０'`（全角零）→ True；port 的 `py_time_match` 只接受 ASCII `0..9`。
   录制 case 全部为 ASCII HH:MM，Unicode-Nd 时间不在本片证据内，明确登记为边界，
   不写进 case、不冒充已证。真实 CLI `--time` 输入是 ASCII。
2. **`$` 末尾换行已复刻**：探针确认 Python `$` 匹配单个尾部 `\n`（`'23:50\n'`→True），
   但不匹配 `\r` / `\n\n`；port 用 `strip_suffix('\n')` 精确复刻，已录 case。
3. **`strip()` 判空缝已复刻**：Python `str.strip()` 的 isspace 含 `\x1c-\x1f`，
   Rust `char::is_whitespace()` 不含；port 复用 operator-guard 的 `py_isspace`。
   注意本模块 `strip()` 只用于判空、返回原文（非 strip 后的值），port 保持一致。
4. **不证 main / 真实注册**：`main()`（argparse + subprocess.run + 可注入 runner/out）、
   `resolve_paths()`（sys.executable）与真实 Windows schtasks 注册行为留 Python，
   本片只证确定性命令渲染；不声称"Windows 实机注册可用"（ADR-0007 复核仍挂 1-24）。
5. **非 lift**：新 crate 是 app/eval 侧等价回放单元，`src/zkc/**` 与 `scripts/**` 源码零改动，
   生产仍走 Python 原函数。
