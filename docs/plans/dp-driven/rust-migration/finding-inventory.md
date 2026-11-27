# Finding · ZKC 迁移盘点（来自 analyze 输出 + 仓库实物）

## 规模
129 source files / 78 test files / 16,700 LOC / 20 units；`make test` 实跑 **671 tests OK**（2026-11-27，旧记忆里的 626 已过时），CI required = authority / mcp-gate / invariant。

## 生产单位
| Unit | LOC | wave | readiness | status | 备注 |
|---|---:|---:|---:|---|---|
| `src/zkc/` | （与 repo/web 合并计 8283） | 0 | — | — | CLI、decay、scheduling、search、distill 等 |
| `src/zkc/repository/` | 同上 | 0 | 0 | caution | PG + memory seam，psycopg |
| `src/zkc/web/` | 同上 | 0 | 23 | **blocked** | FastAPI/uvicorn 无等价 crate（D3–D5） |
| `src/zkc/mcp/` + `src/zkc/transport/` | 823 | 1 | 71/80 | ready | 零依赖协议层 + MCP 适配 |
| `scripts/` | 3218 | 1 | — | **blocked** | 动态代码（eval/计算 import），D2 |

## 实验单位（spikes/）
14 个单元、约 4,876 LOC，多为一次性探针；analyze 把其本地模块误判为 dependency（D6–D36 中大部分）。默认**不纳入**迁移范围。

## 依赖决策摘要
- D3/D4/D5：FastAPI / uvicorn → 官方建议「只重实现本 app 用到的部分，并由录制 case 证明」
- D37：psycopg → sqlx（部分映射，ORM 层手写）
- D38：pydantic → serde + garde（validation error 必然不同，需录 case）
- D39/D40：互相 import 的单位作为单个 piece 迁移（无 glue）
- D2：scripts/ 先调研 blocker，再决定随使用方一起迁或留在 Python

## 已登记的生产接线偏差（11-27 校订）
`apply_distill` 未在生产注入 distiller；`faithfulness.gate_new_claims` 仅 dogfood/测试；`scheduling.l2_target` 无生产调用者；`resolve_classify` 未回灌词法语料。迁移时按**实际接线**对齐，不把「代码能力」误作运行时保证。
