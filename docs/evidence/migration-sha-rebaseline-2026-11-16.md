# 迁移 sha re-baseline 证据（2026-11-16）

> 本文件是**一次性运维动作的证据记录**，不是产品行为变更、不是新语义决策。
> 解决对象：本地 `zkc_dev` 库 `python -m zkc.migrate verify` 对 0007/0008/0009 持续返回非 0（sha 漂移）。

## 1. 根因（三方证据钉死，非猜测）

| 版本 | DB 记录 sha（应用时旧值） | `1209dcc^` 改动前 blob sha | 当前磁盘文件 sha |
|---|---|---|---|
| 0007 | `edd52c747c625964fae03e735ccf3fd1add630688adea9e9495378eca70e40ab` | 同左 ✅ 完全相等 | `5e31ae325a761563ecc3f38bdf4d276aaca17e9604a2c29a3884b2c6d7e4a4bf` |
| 0008 | `99f1f32281adb877dcd12a3bf4b55cf517c36cd09f4e15207c38392b8da40871` | 同左 ✅ 完全相等 | `076d19873dbf5ff754851c4347e68794510ebb67920485951c98e67004205069` |
| 0009 | `69cccb49e4b7cb3cd16a856833e8fcca6caabf114c3d6785e34178c93b9f5efc` | 同左 ✅ 完全相等 | `4d3f5d6e2268f40999c252f6b271f81c64344686bba64d7a32445825b5592ab9` |

- DB 记录值 **精确等于** 2026-11-13 改动前的那版文件——证明记录的是「当时真实应用的文件」，没有污染、没有错记。
- 改动来自 commit `1209dcc`（chore: 全仓 roadmap 节点 id 通配为长期锚点）。对三个 up.sql 的 diff **仅注释行**：`1-5-6`→「蒸馏结构化接线」、`1-8-4-1/1-8-4`→「双列共存/R18」、`1-9 任务队列 UI（roadmap 1-9）`→「任务队列 UI」。commit message 自述「纯注释/文档措辞改动，未触运行期逻辑」。**零 DDL、零数据操作**——schema 语义逐字未变。
- 结论：这是「合法的非语义改动导致 verify 指纹失配」，不是「历史迁移被偷偷改坏」。verify 闸门正确地把两者都标出来；此处经人工判定为前者。

## 2. CI 影响面（澄清风险前提）

- CI `.github/workflows/ci.yml` 的 `full` job **已经**在 Apply migrations 步骤跑 `python -m zkc.migrate verify`（L181）。
- 该 job 每次 `docker run --name zkc-spike-pg ... pgvector/pgvector:pg16` 全新空容器（L148-155），随后 `upgrade` 从零应用全部迁移——已应用 sha 用**当前磁盘文件**现写，`verify` 必然一致。
- 因此本地漂移**进不了 CI 判定**，「将来把 verify 设成 required 会被本地漂移卡住」这个担忧的前提不成立。本次动作解决的是**本地 verify 持续非 0**这一运维噪音，顺带消除任何复用持久库跑 verify 的隐患。

## 3. 采取的动作：forward-only sha re-baseline

选择理由：downgrade → upgrade 会重放 0007-0009 的 DDL，且 downgrade 清真实节点数据（当前 `public.node` = 68 行），不可逆，**不采用**。既然已证明改动纯注释、schema 未变，正确的 re-baseline = 把 DB 里的 sha 更新为当前文件 sha，声明「当前文件内容就是已应用版本」。

- 范围：仅 `schema_migration` 表三行 `sha256` 字段。
- 不改：任何 `.sql` 文件（历史原文不涂改）、任何领域表、任何节点数据、任何源码。
- 前置：完整三方证据如上；已记录旧 sha 作为回滚值（见 §1 表左列）。
- 保护：UPDATE 带 `WHERE version=? AND sha256=<旧值>` 乐观锁，只更新恰好三条；先 `BEGIN` 核对行数再 `COMMIT`。

## 4. 执行结果

- 更新行数：3/3（预期 3）。
- 节点计数：操作前 68 → 操作后 68（无变化）。
- `python -m zkc.migrate verify`：由「3 个已应用迁移被改动」→ **全部 sha 一致，exit 0**。
- 0011（本轮墓碑迁移）自身 sha 从头到尾一致，未在本次触及。

## 5. 回滚

如需回到操作前状态，把三行 sha 改回 §1 左列旧值即可（纯元数据回滚，不动 schema/数据）：

```sql
BEGIN;
UPDATE schema_migration SET sha256='edd52c747c625964fae03e735ccf3fd1add630688adea9e9495378eca70e40ab' WHERE version='0007' AND sha256='5e31ae325a761563ecc3f38bdf4d276aaca17e9604a2c29a3884b2c6d7e4a4bf';
UPDATE schema_migration SET sha256='99f1f32281adb877dcd12a3bf4b55cf517c36cd09f4e15207c38392b8da40871' WHERE version='0008' AND sha256='076d19873dbf5ff754851c4347e68794510ebb67920485951c98e67004205069';
UPDATE schema_migration SET sha256='69cccb49e4b7cb3cd16a856833e8fcca6caabf114c3d6785e34178c93b9f5efc' WHERE version='0009' AND sha256='4d3f5d6e2268f40999c252f6b271f81c64344686bba64d7a32445825b5592ab9';
COMMIT;
```

## 6. 边界与教训

- 本次是**本地运维库 zkc_dev 的一次性修复**，不是产品代码变更；源码 / 历史 SQL / 阈值 / REGISTRY 均未改。
- 正解的一般原则：历史迁移的**注释/文档**改动 legitimate，但 verify 会把它们当指纹漂移抓出——要么接受重放（有数据风险），要么在确证非语义后 re-baseline 并留证据（本次采用）。
- 更根本的改进（未做，另议）：verify 可考虑对「仅注释变化」做语义归一化后比对，但那会削弱闸门强度，需单独权衡，不在本次范围。
