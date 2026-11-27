# sqlx / serde 依赖研究（D37 / D38）

> 来源：crate 官方文档（docs.rs/sqlx、serde.rs、rustanything.ai/docs/languages/python），2026-11-27 实读。结论在未做 port 前均为 `[待实证]`，不写回长期权威文档。

## psycopg → sqlx（D37）
- SQLx 是 async Postgres driver，**不是 ORM**；支持 Tokio / async-std，须显式启用 runtime feature，否则「nearly any async function in the API will panic without at least one runtime feature enabled」（docs.rs/sqlx）。
- 查询可 `query!` 编译期校验（需 DATABASE_URL / offline metadata）或 `query_as` 运行时校验；ZKC 现有 repository seam 的 SQL 在 `migrations/` + `src/zkc/repository/pg.py`，迁移时可保留 SQL 文本、用运行时查询先对齐。
- 连接池 / 事务：`PgPool` + `Transaction`；ZKC 的 UoW / OCC / version_seq 双时态写入必须集中在应用服务层（11-27 架构 `[planned]` 约束），不能散到 adapter。
- `timestamptz` → `chrono::DateTime<Utc>` / `time::OffsetDateTime`；ADR-0013 的 aware UTC 硬约束要靠类型系统守住，禁止 naive。
- **未覆盖**：psycopg 的 row_factory、错误文本、NULL/JSONB 边界；必须录 case 对照（`app record --db-reset --db-dump` + test DB zkc-spike-pg :55433 已确认在运行）。

## pydantic → serde（D38）
- Serde 靠 `Serialize` / `Deserialize` derive 在编译期生成实现，「avoids any overhead of reflection or runtime type information」（serde.rs）；JSON 由 `serde_json` 负责，仓库已用其 `preserve_order` / `float_roundtrip` 特性。
- 校验：Serde 只管序列化形状，业务校验需 `garde` 或手写 validator；**Python 的 ValidationError 文本不会等价**，D38 官方建议「use serde, garde, and record cases for the behavior it does not cover」。
- 枚举/联合类型表示需逐项录 case（Python Enum / Optional / Literal → Rust enum / Option），不得凭直觉改写 wire format。

## rust-anything 的 Python 桥限制
- Python unit bridge = PyO3 (abi3)，Python 3.9+；类型来自 type hints，int-or-float 用 `crate::pynum::Num`。
- gate 只证明录制覆盖的输入；`datetime` 无法穿过 JSON bridge（首切片已实证），DB/network 副作用需 `app record --effects/--db-dump` 才纳入比较。
