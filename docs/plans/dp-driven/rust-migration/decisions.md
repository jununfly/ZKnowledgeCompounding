# 迁移门禁 · 需要 zj 拍板的决策

> 每题给出推荐答案；zj 未答前，对应 ticket 挂 `external_hold`，不得自行放行。
> rust-anything whole-app skill 要求「decisions only you can make」先收敛，再写 `rust/DECISIONS.md`。

## Q1 · 迁移范围（对应 analyze D2/D39/D40）
- A：只迁生产路径 `src/zkc/**`；`spikes/`（14 个探针，~4.9k LOC）保留 Python 作研究档案；`scripts/` 最后单独评估（动态代码 blocker）。
- **B（已选）**：生产 `src/zkc/**` + `scripts/`（3,218 LOC）一起迁，先解 scripts 的动态代码 blocker；`spikes/` 仍留作研究档案。zj 同时重申：**不保留 Web**（与 Q2=C 一致）。
- C：全仓（含 spikes）都迁。

## Q2 · Web 层策略（对应 D3/D4/D5）
- **A（推荐）**：生产接线用 Rust 重写 FastAPI 实际用到的路由/表单/SSR 行为（axum 等），由 `app record/replay` 的 HTTP case 证明；保留 Python web 作参照直到 app lift。
- B：Web 层暂留 Python，只迁 domain + repository + CLI/MCP，先交付「核心 Rust」。
- C：直接砍掉 Web（/browse、/review 等），只保留 CLI/MCP。

## Q3 · 等价性证据源
- **A（推荐）**：`record --from-tests -- pytest`（复用现有 ~626 单测）+ 真实 PG test DB 的 `app record --effects/--db-dump` 双轨；录制覆盖不到的语义另补 case。
- B：只做 `app record/replay` 黑盒（CLI/HTTP），不录单测级调用。
- C：先把现有 Python 测试移植成 Rust 测试，再以 Rust 测试为 oracle（风险：失去原实现对照）。

## Q4 · 首个落地切片
- **A（推荐）**：`src/zkc/decay.py`（纯函数、低风险、单测覆盖）做首 port，打通 bridge→record→build→diff→gate，作为工具链与纪律的证明，再扩到核心 piece。
- B：从 `src/zkc/transport/`（零依赖协议层，400 LOC）起步。
- C：直接啃 8,283 LOC 的 tangled 核心 piece（D39 推荐，但风险最高）。

## 记录（2026-11-27）
- **Q2 = C（砍掉 Web）**：/browse、/review 等 Web 能力退出迁移范围；D3/D4/D5 随之关闭。注意：现有 Python Web 保留作参照直到 app lift，但不再有 Rust 对应实现。
- **Q3 = C + 修正（zj 接受）**：移植成 Rust 测试作为**日常回归**；但**录制/证明期仍以 Python 原实现为唯一 oracle**，先 `record` 冻结 case 并 `diff/gate` 全通过，再切 Rust 测试回归。绝不在录制前改写 Python 测试，否则失去独立参照。
- **Q4 = A（decay.py 首切片）**：先打通 bridge→record→build→diff→gate，再扩核心 piece。
- **Q1 = B（生产 + scripts，不保留 Web）**：scripts 动态代码 blocker 单列 ticket；spikes 不迁。
- 四项门禁全部收敛；不代答、不推测。

## Q5 · metrics.py 中 dataclass/Storage 函数的处置（tk8 子切片边界）

> 2026-11-27 20:34 zj 确认 **C**。对应 ticket 15（保持 hold，不 close）。

- A：`app record --effects/--db-dump` 黑盒录制（起 test DB `zkc-spike-pg :55433`）。评估：仅 `metrics_report(store)` 真吃 Storage、值得走此路；其余 6 个纯计算 + 1 个 dataclass 返回函数走黑盒会丢失中间输入组合，case 密度低于 unit-level，性价比低。
- B：Rust 侧改显式结构体参数。排除——脱离原签名后 diff/gate 失去机械对照，退回自证，与 Q3 修正口径冲突。
- **C（已选）**：8 个函数**暂留 Python**，核心 piece 本轮只交付标量/纯函数层（`compounding_factor`，已 gate 243/243）。定性为**工具编码边界导致的暂留，不是业务不可迁、不是永久放弃**。
- 配套动作（防"暂留"变"遗忘"）：
  1. ticket 15 保持 hold，触发条件写进 finding：**app record --effects 基建就绪后，只对 `metrics_report` 单独走 A**；
  2. 6 个 `MetricInputs` 纯计算函数：若要迁，须先解决 wrapper `_enc` 的 dataclass 编码（改工具生成代码，refresh 会覆盖，需单独评估），或接受永久留 Python——二者都须在 ADR 定性，不默认；
  3. durable 文档明确写"工具边界暂留，非业务不可迁"。

### Q5 落定（2026-11-28，ticket 15 决议）

zj 拍板选项 A：`metrics_report(store)` 走 A 路径迁移（ticket 45 承载，f7 路径已验证）；
其余 7 个永久留 Python（ADR-0014 定性「工具编码边界永久留置」）。ticket 15 关闭，
lift 链解锁。详见 `docs/zj-adr/0014-q5-metrics-boundary-final.md` 与
`finding-metrics-boundary.md` 最终落定段。
