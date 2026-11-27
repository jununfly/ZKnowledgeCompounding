# ZKC → Rust · 任务上下文（DP 驱动）

## Destination
ZKC 纯 Rust 实现：`rust-anything app replay` 100% + 每个 port `gate` 通过；原 Python 代码仅作参照，不再运行。

## 范围事实（来自 `rust-anything analyze . --whole-app --json`，2026-11-27）
- `schema=rust-anything/analyze@1`，`language=python`，`shape=server`
- `source_files=129`，`test_files=78`，`loc=16700`，`units=20`（ready 12 / caution 6 / blocked 2）
- 3 个生产 tangled piece：`src/zkc/ + src/zkc/repository/ + src/zkc/web/`（8283 LOC，wave 0，D39）、`src/zkc/mcp/ + src/zkc/transport/`（823 LOC，wave 1，D40）、`scripts/`（3218 LOC，wave 1，D2 blocked）
- 14 个 `spikes/` 单元（约 4876 LOC）是历史实验探针，不是生产路径；默认不纳入迁移，除非 zj 另有指示
- 关键 dependency 决策：FastAPI/uvicorn 无 Rust 等价（D3/D4/D5）、psycopg→sqlx 仅部分（D37）、pydantic→serde/garde 部分（D38）

## 项目硬约束（来自 durable 文档与项目记忆，非过程态）
- 双轨 ≠ 双时态；decay=linear（SURFACE 0.6 / ROT 0.9）；interval 三层 L1×L2×L3；budget 删失感知 + 单调护栏 + EMA + 校准期×1.5
- `tuning.REGISTRY` 中 CALIBRATED 参数（4×METRIC_W_*、METRIC_METHOD_TARGET、MIN_INTERVAL_DAYS）不得借迁移改名改值；`CALIB_OVERRIDE_AT` 永久 caveat
- Ollama 原生 `/api/chat` + `format:json`；think=false、num_ctx=8192；禁止 `/v1` + `response_format`（qwen3.5-mlx 永久挂死）
- pg 双时态与 tombstone/TTL 语义见 ADR-0011/0012/0013；aware UTC 硬约束
- 禁止伪造 verdict / 标注 / 外生锚；`decide --verdict` 只能由 zj 给
- 代码/长期文档不得引用过程态 carrier；authority check 对 `docs/plans/` 整类剪枝
- backend 可换（repository seam），但行为必须逐 case 对齐原实现

## 工作流（rust-anything 5.0.0，文档对 5.0.1）
`analyze --whole-app` → 决策门禁（本 carrier 的 T0）→ `app record` / `app front-door` → 逐单元 `bridge → record → port.rs → build → diff → shadow → gate` → `app wire` → `app lift`
CLI 无需 `setup`（WorkBuddy 走 CLI 而非 Claude/Codex MCP）；`doctor` 的 agent-setup 缺失项不影响本工作流。

## 证据边界
- `tmp/rust-analyze-whole-app.json` 是工具输出（tmp/ 已 gitignore），非权威；结论须提炼到本 md / ADR / 架构才能长期留存。
- 每个 port 的通过判据 = 录制 case 全匹配 + gate 通过；录制覆盖不到的行为不算证明（见 rust-anything docs/concepts/limits）。
