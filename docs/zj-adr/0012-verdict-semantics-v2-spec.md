# ADR-0012 · 复审标注四档语义矩阵 v2 · 规格与验收判据（Step 2 规格链产出）

> 配套：`docs/zj-adr/0011-verdict-semantics-v2.md`（决策定案，本文件是其 Step 2 规格链产出）。
> 本文件**不是新决策**，只把 ADR-0011 已定的语义矩阵 v2 转成**可测规格 + 失败在先的验收断言**，
> 供 Plan `2026-11-14-zkc-verdict-semantics-plan.md` 的 Step 4（zj-tdd）红绿实现直接消费。
> 权威输入仅来自 ADR-0011（durable 决策）与下方「代码事实」中当前可核对文件；**不引用过程态 Plan 作 proof**。

Status: spec-frozen（2026-11-14，由 zj「A 授权落码(Step 2 规格链)」显式授权产出）

## 1. 范围与输入

- **输入**：ADR-0011 §语义矩阵 v2、§决策（①–④ / S0 / S1 a–d / S2）、§外生锚 A 架构级结论；当前代码事实（见 §2）。
- **输出（本文件）**：语义矩阵 v2 的可测规格、CLI 契约变更清单、OUTCOME_VERDICT 与终局动作两表断言更新、L1 基线重置与 archive 退出调度回路断言、四类审计 reason 口径、口径切换点记录格式、回归用例清单。
- **不在本文件范围**：Step 4 的实际代码/测试实现、Step 3 设计评审、Step 5 审查、Step 6/7 文档与注释切片。落码属 Step 4，未在本步执行。
- **硬约束（来自 ADR-0011 / Plan §Intent.constraints）**：verdict 与内容载荷、stale 分支选择**只能由 Human 本人逐条给**；历史 3 条 changed **不回填、不重标记、不撤销 interval 调整**；不得静默改动阈值常量；不得引入节点物理删除；清除只映射 `archive` 软归档。

## 2. 代码事实（当前基线，实现时以测试守住）

| 位置 | 现状 | v2 要求 |
|---|---|---|
| `src/zkc/web/review.py:40-44` `OUTCOME_VERDICT` | `{"still_valid":"on_time","changed":"too_late","stale":"too_late"}` | `changed`/`stale` 不再映射 `too_late`；改为终局动作映射（见 §4） |
| `src/zkc/web/review.py:90-143` `decide_review` | 对非 browse 走 `S.adapt_interval`（AIMD 乘因子） | `changed`/`stale` 不再调用 `adapt_interval`；只 `mark_reviewed`（时钟复位）+ 标注埋点；外生锚 A 人工输入归零 |
| `src/zkc/cli.py:47` `VERDICTS` | `("still_valid","changed","stale","browse")` | 集合不变；新增必填参数（见 §3） |
| `src/zkc/cli.py:73-74` `--verdict` | 仅 `--id`/`--verdict` | 新增 `--content`（changed / stale 覆盖必填）、`--stale-branch`（stale 必填：`cover`/`purge`） |
| `src/zkc/repository/protocols.py:30` `NodeRepository.save` | 支持 `nodes.save` 双时态新版本（OCC + 历史快照，`repository/memory.py:52-88`） | `changed`/`stale 覆盖` 经 `save` 写节点双时态新版本 |
| `src/zkc/repository/protocols.py:103` `NodeRepository.archive` | 软归档（`archived_at=now`），无 `delete` 节点接口 | `stale 清除` 只映射 `archive`；**不得**新增物理删除 |
| `src/zkc/expiry.py:35-37` 动作枚举 | `distill`/`archive`/`abstain` | 不变；`stale 清除` 复用 `archive`，审计 reason 与 D2 区分 |
| `tests/test_web_review.py:79-86` `test_decide_changed_shrinks_interval` | 断言 `changed → too_late → AIMD_DOWN(0.7) → 缩短` | **必须改写**：`changed` 不再缩短，改为内容新版本 + interval 重置 L1 基线 |
| `tests/test_web_review.py:108` `test_record_daily_observation_preserves_counts` | `decide_review(...,"stale",...)` | stale 需带 `--stale-branch`，旧调用形式须更新或拆分 |

## 3. CLI 契约变更清单（参数名待 Step 4 实现时定稿，Human 可调整）

```
zkc decide --id <uuid> --verdict still_valid                 # 无载荷
zkc decide --id <uuid> --verdict changed  --content "<载荷>" # 内容载荷必填
zkc decide --id <uuid> --verdict stale --stale-branch cover  --content "<载荷>"  # 分支+载荷必填
zkc decide --id <uuid> --verdict stale --stale-branch purge                  # 仅分支必填
zkc decide --id <uuid> --verdict browse                      # 无载荷
```

**门禁断言（CLI 层）**
- C1 `changed` 缺 `--content` → 拒绝（退出码非 0），**不得**自动填充或推测。
- C2 `stale` 缺 `--stale-branch` 或取值非 `cover|purge` → 拒绝；**不得**默认 `purge` 或自动判定。
- C3 `stale --stale-branch cover` 缺 `--content` → 拒绝（覆盖载荷必填）。
- C4 `still_valid` / `browse` 带 `--content` / `--stale-branch` → 忽略或拒绝（实现定，须一致）。
- C5 `VERDICTS` 集合保持四档，无 `too_early`。

## 4. 语义矩阵 v2 · 终局动作映射（两表）

**表 A · OUTCOME_VERDICT（复审标注 → 终局动作，不再走 AIMD 乘因子）**

| verdict | 终局动作 | interval | 调度回路 | 内容载荷 | 审计 reason |
|---|---|---|---|---|---|
| `still_valid` | 仅时钟复位（维持） | 维持 | 维持 | 无 | `still_valid` |
| `changed` | `nodes.save` 双时态新版本 | **重置 L1 基线** | 维持（不退出） | **必填·只由人给** | `changed` |
| `stale` + `cover` | `nodes.save` 双时态新版本（≠蒸馏 claim） | **重置 L1 基线**（同构，不继承收缩） | 维持（不退出） | **必填·只由人给** | `stale_overwrite` |
| `stale` + `purge` | `archive` 软归档 | —（已退出） | **退出**（due 队列消失） | 无（仅分支必填） | `stale_purged` |
| `browse` | 时钟复位 + `completed++` | 维持 | 维持 | 无 | `browsed_without_label` |

**表 B · 四类审计 reason 口径（互不相同，含与 D2 区分）**

| reason 值 | 触发 | 与 D2 关系 |
|---|---|---|
| `still_valid` | 人工判仍有效 | 无关 |
| `changed` | changed 写内容新版本 | 无关 |
| `stale_overwrite` | stale 覆盖写内容新版本 | 无关 |
| `stale_purged` | stale 清除走 archive | **须与 D2（expiry archive「价值已升元认知层」）区分记录** |
| `browsed_without_label` | 仅浏览 | 无关 |
| `D2`（expiry archive reason） | 到期分流 archive（价值升元认知层） | 单列，不与 `stale_purged` 混同 |

## 5. 可测验收断言（Step 4 红绿实现须逐条满足）

> 每条以「失败在先」姿态写出；实现后 `make test` 全绿（基线 574）。

**A. 内容轴 / 节奏轴分列**
- A1 `changed` 结果**不再**含 `verdict="too_late"`、`applied` 不再走 AIMD 缩短；`new_interval_days` 为 L1 基线值（非旧内容收缩结果）。
- A2 `stale` 结果不再以 `too_late` 形式出现；`cover`/`purge` 各自走 §4 表 A 动作。
- A3 外生锚 A 不变式：`decide_review` 对 `changed`/`stale` **不调用** `S.adapt_interval`；仅 `mark_reviewed` + 标注埋点。用 spy/monkeypatch 断言 `adapt_interval` 调用次数为 0（changed/stale 分支）。

**B. changed**
- B1 缺内容载荷 → 抛错/拒绝，节点状态不变、`list_due_for_review` 仍含该节点。
- B2 带载荷 → 节点写出双时态新版本（历史快照 +1），`review_interval` 重置为 L1 基线，节点**仍在** `list_due_for_review`（不退出）。
- B3 审计 reason == `changed`，且与 `stale_overwrite`/`stale_purged`/`browsed_without_label`/`still_valid` 互异。

**C. stale → cover**
- C1 缺 `--stale-branch` 或缺失 content → 拒绝，节点不变。
- C2 `cover` → 节点写双时态新版本（内容载荷落库），`review_interval` 重置 L1 基线（**同构**，不继承旧收缩），节点**仍在** `list_due_for_review`（不退出调度回路）。
- C3 reason == `stale_overwrite`，与另三类互异。

**D. stale → purge**
- D1 缺 `--stale-branch` → 拒绝；**不得默认 purge 或自动判定**。
- D2 `purge` → 节点走 `archive` 软归档（`archived_at` 置位），**不写**节点新版本；节点从 `list_due_for_review` 消失（`due_count` 减 1）。
- D3 reason == `stale_purged`，且**与 D2（expiry archive reason）分别记录**，不得混同。

**E. still_valid / browse**
- E1 `still_valid` → 时钟复位、`review_interval` 维持、reason == `still_valid`。
- E2 `browse` → 时钟复位 + `completed++`、不触发 L3、reason == `browsed_without_label`、`verdict=None`。

**F. 四类 reason 互异（结构性）**
- F1 同一次 `review_queue` / 审计日志内，`changed`/`stale_overwrite`/`stale_purged`/`browsed_without_label` 四值两两不同（用枚举或常量集中定义，禁止字符串散落）。

**G. 历史 3 条 changed 不回填**
- G1 已实现后，对今日已写入的 3 条 `changed`（旧语义产物）`make test` 与 `node.decay_score`/`review_interval` 保持原值；不得因 v2 落地被重标记或撤销 interval 调整。

**H. 口径切换点记录**
- H1 落地时新增 `docs/zj-adr/`（或 `data/`）下 `2026-11-14-verdict-semantics-cutover.md`，记录旧映射→新映射切换点、受影响节点计数、未回填声明（对应 S1-d）。

## 6. 回归用例清单（Step 4 须新增/改写）

- **改写** `tests/test_web_review.py::test_decide_changed_shrinks_interval` → 改为断言 B1/B2（内容载荷必填、interval 重置 L1 基线、不退出）。
- **改写/拆分** 涉及 `decide_review(...,"stale",...)` 的用例（含 `test_record_daily_observation_preserves_counts`）→ 补 `--stale-branch` 参数，断言 D1/D2/D3。
- **新增** `tests/test_web_review.py::test_decide_changed_requires_content`（B1）、`::test_decide_stale_cover_writes_new_version`（C2/C3）、`::test_decide_stale_purge_archives_and_exits`（D2/D3）、`::test_aimd_loop_human_input_zeroed`（A3，spy `adapt_interval`）、`::test_four_audit_reasons_distinct`（F1）。
- **新增** CLI 层 `tests/test_cli_decide.py`：`--content`/`--stale-branch` 缺失拒收（C1–C4）、`VERDICTS` 集合不变（C5）。
- **保留** `test_observation_accumulates_across_reviews` 等埋点语义用例，确认标注率闸门仍由 `labeled_completed` 驱动（外生锚 A 归零不影响埋点）。

## 7. 口径切换点记录格式（H1）

```markdown
# 2026-11-14 复审标注语义口径切换点
- 旧映射: OUTCOME_VERDICT = {still_valid:on_time, changed:too_late, stale:too_late}
- 新映射: 见 ADR-0012 §4 表 A（终局动作替代 AIMD 乘因子）
- 受影响: 今日已写入 changed 3 条 = 保留旧语义产物，不回填/不重标记/不撤销 interval 调整
- 外生锚 A: decide_review 不再调用 adapt_interval（人工输入归零），仅 mark_reviewed + 标注埋点
- 未决: stale 分支选择/内容载荷由 zj 逐条给；清除只映射 archive，无物理删除
```

## 8. 与既有不变量/风险册的衔接

- **外生锚 A**：见 ADR-0011 §外生锚 A；本规格 A3 以测试锁死「verdict 不再触发乘因子」。
- **风险册 R15**（docs/risks.md，本次联动新增）：承载上述硬不变量，状态「缓解·待 Step 4 测试守卫」。
- **1-26 CALIBRATED 口径**：本规格**不改**任何阈值常量（`tuning.py` 的 `AIMD_UP`/`AIMD_DOWN`/`MIN_INTERVAL_DAYS`/`METRIC_W_*`），不写回 `REGISTRY`；与 verdict 反馈路径正交。
- **注释方向偏差（裁决④）**：`tuning.py:120-121` 注释修订是独立 doc-only 切片（Plan Step 7），**不并入本规格的实现批次**。
