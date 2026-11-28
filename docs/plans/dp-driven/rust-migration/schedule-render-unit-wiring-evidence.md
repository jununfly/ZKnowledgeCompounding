# Evidence · `schedule-render` 三函数接线进 rust/app（ticket 44）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与 kill switch 语义以 crate 实现为准。
真相源：`scripts/daily_driver_schedule.py`（ADR-0007 Windows schtasks 渲染层），本接线只做逐字回放。

## 结论

`rust/schedule-render-rs` 的 `build_task_action` / `build_register_command` /
`build_unregister_command` 已 wire 进 `rust/app`，新前门 `unit-schedule-render`：
```
metrics-snapshot unit-schedule-render build_task_action '["C:\\Scripts\\d.bat"]'
# → {"ok":"\"C:\\Scripts\\d.bat\""}
metrics-snapshot unit-schedule-render build_register_command '["C:\\Scripts\\d.bat","ZKC Custom","07:15"]'
# → {"ok":["schtasks","/create","/tn","ZKC Custom","/tr","\"C:\\Scripts\\d.bat\"","/sc","daily","/st","07:15","/f"]}
# kill switch: RUST_ANYTHING_UNIT_SCHEDULE_RENDER=original 回 Python（spike-24 alias）
```

## 接线方式（既有模式）

- 前置登记 `cli.rs::UNIT_COMMANDS` + `rust-anything.json` commands，真跑
  `rust-anything app wire . schedule-render-rs --command unit-schedule-render --skip-gate --no-check`
  （生成 Cargo 依赖、unit 记录、switch 名、glue stub）。
- wire 重写 `units/mod.rs`（丢 metrics_report），照例备份/手合并回
  metrics 路由 + 十四既有单元 + 新 `schedule_render` 分支 = 十五单元。
- 手写 glue `units/schedule_render.rs`：三函数按名分发（1/3/1 参，全部 JSON string），
  port 返回 `Result<Value,String>` 且错误文本自带 `ValueError:` 前缀（无异常前缀缝），
  `emit` 匹配 app 输出契约。
- `oracle.py`：加载 spike-24 alias（unit key kebab `schedule-render`）+ `SCHEDULE_RENDER`
  三函数表项进 `TABLES`；`smoke_units.py` +14 case（含 `\x1c` isspace 缝、`23:50\n`
  末尾换行缝、三类占位符拒绝、空/空白/非法时间/中文路径）。
- kill switch `RUST_ANYTHING_UNIT_SCHEDULE_RENDER`。

## 验证（全绿）

| 检查 | 结果 |
|---|---|
| smoke vs oracle | **123/123**（109+14）逐字一致 |
| kill switch 三态 | default 0 次 / `=original` 1 次且输出逐字一致（str 与 list 返回、`ValueError` exit 1）/ 关掉 0 次 |
| app replay | 11/11，fallback 0% |
| crate diff | 26/26 |
| app fmt/clippy/build | 全过（Cargo.lock +10，同前几次接线） |
| make test | 671 OK |
| 三门禁 | mcp-gate 6/6 / invariant 0 / authority 0 leaks |

## 边界

新前门非 lift；不证 `main()`/`resolve_paths()`/真实 Windows schtasks 注册（留 Python，
ADR-0007 实机复核仍挂 1-24）；`$` 单尾 `\n` / `py_isspace` 判空 / 中文 ValueError
recorded-literal 三处缝接线不改语义；`\d` Unicode Nd 时间不在证据内（finding 21 登记）；
`src/zkc/**` 与 `scripts/**` 零改动；ticket 13（D2）不变。未 commit/push（等 zj 显式触发）。
