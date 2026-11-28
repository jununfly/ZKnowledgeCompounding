# Ticket 8 收口结案证据（D39：核心 domain+repository piece 迁移）

日期：2026-11-28
结论：**ticket 8 关闭（已完成）**——可证纯函数切片已穷尽，剩余部分各有明确归属与排除理由。
性质：过程态证据（`docs/plans/`），结案事实以本文件 + DP carrier 记录为准。

## 一、关闭判据

ticket 8（D39「核心 domain+repository piece 迁移」，parent_id=NULL）的原 hold 为
「等待首切片与依赖研究」。该 hold 早已解除：首切片（transport 系）之后 24 个子
ticket 全部完成，且三轮全仓扫描证明**严格干净候选已穷尽**。

「可证」定义（贯穿 24 子 ticket 的验收口径）：
1. 纯函数：入参/返回 JSON-native，无 dataclass/Storage/UUID/datetime/LLM/callable 缝；
2. 不读全局状态（tuning.get / 模块级可变）；
3. 有直接测试锚点或明确业务锚点；
4. 录制（Python oracle）→ Rust port → diff 逐字一致 → gate 通过的完整证据链。

## 二、已完成的 24 个子 ticket（12 对 slice/wire）

| 切片 | slice | wire | 前门 |
|---|---|---|---|
| pure-slices（transport/context/expiry/decay 系早期切片） | 16 | —（早期已含 wire） | — |
| scheduling-interval-math | 21 | —（早期已含 wire） | — |
| faithfulness-rubric / wiring | 23 | 24 | unit-faithfulness |
| routing-tfidf / wiring | 25 | 26 | unit-routing |
| cross-source / wiring | 27 | 28 | unit-cross-source |
| distill-parse / wiring | 29 | 30 | unit-distill |
| r14-judgment / wiring | 31 | 32 | unit-r14 |
| artifact-shaping / wiring | 33 | 34 | unit-artifact-shaping |
| injection-detection / wiring | 35 | 36 | unit-injection |
| percentile / wiring | 37 | 38 | unit-percentile |
| operator-guard / wiring | 39 | 40 | unit-operator-guard |
| telemetry-validation / wiring | 41 | 42 | unit-telemetry-validation |
| schedule-render（scripts 首片）/ wiring | 43 | 44 | unit-schedule-render |

对应 16 个 port crate（`rust/*-rs/`），每个的 diff/gate 数字与缝处理见各
`*-slice-evidence.md` 与 `*-unit-wiring-evidence.md`；DP carrier（events.jsonl /
mmd / html）含全部 tk/f 记录。

## 三、穷尽性论证（为何「没有下一片」）

三轮系统性候选扫描（2026-11-28，两个 Explore agent 全仓 AST 级盘点 × 2 轮 +
人工复核）结论一致：

1. **src/zkc 顶层严格干净候选 = 0**。全部模块逐一核对：
   - calibration / metrics / faithfulness 聚合：dataclass（MetricInputs 等）→ Q5=C；
   - mcp/exposure：双真相源排除；
   - repository/*：psycopg/Storage/UUID/datetime；
   - sweep：datetime 缝；
   - r14_telemetry：文件 IO（`record_run`/`load_runs`/`aggregate`）留 Python，
     仅 `_validate_report` 纯校验已被 port（tk41/42）；
   - print 副作用类（`format_human`/`format_p64_human` 等）：返回 None、唯一测试
     断言即 print，剥离 = 翻案（死路，已证伪）。
2. **scripts/ 唯一干净方向已取**：`daily_driver_schedule` 三渲染函数（tk43/44，
   scripts 首片）。剩余 scripts 函数：`_slice_function`/`_is_roadmap_carrier`
   无直接单测（锚点弱）、`simulate_weights` 有 RNG 跨语言缝、`_import_meter`
   是 D2 动态代码缝本体（归 ticket 13）。
3. 排除项全部落在 21 个 durable finding（`finding-*.md`）中，非口头结论。

## 四、剩余部分的归属（不因 ticket 8 关闭而丢失）

| 剩余工作 | 归属 | 状态 |
|---|---|---|
| scripts 动态代码 blocker（`_import_meter` 等） | ticket 13（D2，task 5） | 未完成，external_hold；**tk43/44 不消费不关闭它** |
| CLI/MCP/Web adapters 迁移 | ticket 9（D3/D4/D5/D40） | external_hold 等待 Q2 |
| app record + front-door 证明 | ticket 10 | external_hold 等待基线 |
| app wire + lift 纯 Rust 化 | ticket 11 | external_hold 等待 adapters |
| ADR/架构长期文档收口 | ticket 12 | external_hold 等待 lift |
| D39-boundary：8 个 dataclass/Storage 函数是否逐个应用层重写 | ticket 15（Q5=C） | 未完成，**待 zj 按收益决定**（本收口不代答） |

## 五、诚实边界（本收口不冒充的事）

- ticket 8 关闭 ≠ lift 完成：`src/zkc/**` 生产仍是 Python，16 个 crate 是
  process-only port + 前门 wire，**代码能力 ≠ 生产接线**（既有 caveat 不变）；
- 关闭 ≠ scripts 全迁：D2 动态代码仍在 ticket 13；
- 关闭 ≠ R18/R14 产品闭环变化：那些是产品侧节点，与本迁移 ticket 无关；
- Unicode Nd 等未录边界已在各 finding 诚实登记，不因收口被隐没。

## 六、机械验证快照（收口时点）

- 最后一次全绿记录（tk44 wire 后）：smoke 123/123、replay 11/11 fallback 0%、
  crate diff 26/26、make test 671 OK、三门禁 6/6/0/0；
- DP validate 0 errors；活跃 claim 收口后为空（ticket 8 release）。
