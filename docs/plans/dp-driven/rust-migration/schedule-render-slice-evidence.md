# Evidence · scripts 渲染层三函数纯函数切片（ticket 43）

日期：2026-11-28。过程态证据，非长期权威；CLI 录制路径与 kill switch 语义以 crate 实现为准。
真相源：`scripts/daily_driver_schedule.py`（ADR-0007 跨平台调度条款），本切片只做逐字回放。

## 结论

`scripts/daily_driver_schedule.py` 的 `build_task_action` / `build_register_command` /
`build_unregister_command` 已 port 到 Rust `rust/schedule-render-rs`，**未接线进 app**。
DP：finding 21 + ticket 43（parent 8，derived-from 21，blocks `43→8`）完成并释放租约，
ticket 8 仍是唯一活跃租约。**ticket 13（D2 blocker）保持不变，本片不消解 D2**。

## 选片理由

- 两个 Explore agent 全仓扫描：print 副作用方向被证伪（返回 None / 断言即 print），
  严格干净候选仅 scripts 渲染层三函数 + 少量弱候选（详见 finding 21）。
- 三函数是 ADR-0007 Windows schtasks 注册的命令渲染层，有 6 条直接单测锚点，
  JSON-native、无编码缝（除记录的中文错误文本/末尾换行/isspace，均逐字复刻）。
- Q1=B 已纳入 scripts；本模块无动态代码缝，唯一真 D2 缝在另一文件，不翻案。

## 实现与录制

- 新 crate `rust/schedule-render-rs/`：port 三函数。逐字对应 Python 语义：
  - `build_task_action`：`str()` 归一化 → isspace 判空 → `__`/`%CD%`/`%~dp0` 占位符拒绝
    → 整路径加双引号（`/tr` 容忍空格）。中文错误文本 recorded-literal。
  - `build_register_command`：`_TIME_RE` 时间校验（`HH:MM`，`$` 容单尾 `\n`）→ 任务名判空
    → action 渲染 → 拼 `schtasks /create /tn /tr /sc daily /st /f` 数组。
  - `build_unregister_command`：任务名判空 → 拼 `schtasks /delete /tn /f`。
- spike-24 `pure_bridge.py`：纯委托三函数（scripts 非 package，绝对路径 sys.path 加载，
  同 `test_daily_driver_schedule.py`），无编码缝（str/list 全 JSON-native）。
- `record --inputs 26 定向 case --count 0`（14 threw）：
  - 路径：普通/带空格/中文/内嵌 NUL/空/空白/纯 `\x1c`/NBSP/三类占位符
  - 时间：`00:00`/`23:59`/`23:50`/`07:15` 合法，`25:99`/`23-50`/`23:5`/空 非法，`23:50\n` 合法（`$` 缝）
  - 任务名：默认/自定义/空/空白/纯 `\x1c`
- 复刻的三处缝：①`$` 末尾单 `\n`（`strip_suffix`）；②`str.strip()` 的 isspace 全集
  （复用 `py_isspace` 含 `\x1c-\x1f`）；③4 类中文 ValueError 文本 recorded-literal 同行注释不 promote。
- 未录边界：`\d` 的 Unicode Nd 分支（`02:5０`→True）——case 全 ASCII，不冒充已证，finding 登记。

## 验证（全绿）

| 检查 | 结果 |
|---|---|
| crate build / diff / gate | diff **26/26**；gate 全过（fmt/clippy/test/unsafe/lockfile/ported/size 2.1x/literals 0/panics/build/api/behavior） |
| gate 首跑 | 只差 fmt + `unreachable!`（panics 规则），已内联消除并 fmt，二跑全过 |
| app replay | 11/11，fallback 0%（未接线，确认前门未受影响） |
| make test | 671 OK |
| 三门禁 | mcp-gate 6/6 / invariant 0 / authority 0 leaks |

## 边界

新 crate 非 lift；不证 `main()`/`resolve_paths()`/真实 Windows schtasks 注册（留 Python）；
Unicode-Nd 时间不在证据内；`src/zkc/**` 与 `scripts/**` 源码零改动；ticket 13（D2）不变。
未 commit/push（等 zj 显式触发）。
