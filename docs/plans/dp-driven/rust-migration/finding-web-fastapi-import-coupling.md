# Finding · zkc.web 包级 eager import fastapi 拖住 CLI/MCP 录制（ticket 47/接线执行期发现）

状态：未完成（task 3 / task 2 共担）。2026-11-28 执行 task 3 port 切片时实测发现，是 finding-24（web.review 域耦合）的运行时实锤。

## 事实

`src/zkc/web/__init__.py:2` 在包导入时即 `from zkc.web.app import create_app, capture_note, build_routers`，
而 `src/zkc/web/app.py:16` 模块级 `from fastapi import FastAPI, Form`。因此：

- 任何 `import zkc.web.<anything>`（含 `zkc.web.review`）都会触发 `zkc.web.__init__` → 拉起 **fastapi**。
- `src/zkc/cli.py:41` 顶层 `from zkc.web.review import (decide_review, record_daily_observation_auto, review_queue_view)`，
  所以**录制 `cli.parse_args` 需先能 import `zkc.cli`** → 需 fastapi（及 web/app 的其余 import）。本环境无 fastapi，
  `from zkc import cli` 直接 `ModuleNotFoundError`。
- 同理 `src/zkc/mcp/wiring.py` 的 `_LazyRouters` 虽惰性，但 `build_routers` 源也在 fastapi 模块内（惰性可绕 import，
  但 app-wire 阶段仍需运行期 web 依赖或域搬迁）。

## 含义

1. **cli-parser（tk-47）当前不可独立录制**：不是 rust-anything 问题，而是 `cli.py` 顶层 import 拖入 web/fastapi。
   前置条件是把 `web.review` 三函数（及 `build_routers`）按 decision-2 迁出 fastapi-importing 的 `zkc.web` 包路径
   （即 tk-49 的域搬迁），或为 `zkc.web.__init__` 去 eager-import。
2. **argparse 语法本身另有库编码缝**：`parse_args` 在非法 argv 上抛 `SystemExit`（打印 usage），且返回
   `argparse.Namespace` 对象——即便 import 打通，rust-anything 只录我给的定向 case，SystemExit/usage 全表面
   不宜声称等价覆盖（同 Q5「工具/库编码边界」定性）。故 tk-47 若后续做，范围须显式限定为「合法输入 argv→
   Namespace(vars) dict 的字段/默认/choices 映射」，错误面另议。

## 处置

- tk-47 挂 `external_hold`，依赖 tk-49（web.review 域搬迁，现归 task 2）落定；新增跨区 blocks 边 `49→47`。
- 释放 tk-47 的 ticket 租约，不强行安装 web 依赖或产低置信 clap port。

## 处置（2026-11-28 · domain 迁移完成，finding 标记 已完成）

已按 decision-2 物理搬迁，fastapi eager-import 耦合解除：

- `web.review` 的 12 个纯编排函数 + `REVIEW_REASON` + 序列化助手 → 新建 domain 模块 **`src/zkc/review.py`**（无 fastapi 依赖）。
  `src/zkc/web/review.py` 只保留 `REVIEW_HTML` + `register_review_routes`，并从 `zkc.review` re-export 领域公开名（兼容既有 `from zkc.web.review import …`）。
- `build_routers` → **`src/zkc/routing.py`**（纯 stdlib 域工厂）；`web/app.py` 改 `from zkc.routing import build_routers` 并 re-export。
- 解耦敏感导入者 repoint 到 domain：`cli.py`（→ `zkc.review`）、`mcp/wiring.py`（→ `zkc.routing`）、
  `scripts/{daily_e1_driver,cold_start_import,dogfood_faithfulness}.py`。
- 测试 monkeypatch 目标随之校准：`test_web_review.py` 的 `import zkc.web.review as R`（patch `R.ContextAssembler`）
  → `import zkc.review as R`（搬走的函数内部解析 `zkc.review.ContextAssembler`）。`zkc.scheduling` 等共享 module 对象的 patch 不受影响。

**验证（实证）**：无 fastapi 环境下 `import zkc.cli / zkc.mcp.wiring / zkc.review / zkc.routing` 全部成功且 `fastapi not in sys.modules`；
`make test` 改动前 `Ran 671 tests OK`、改动后 `Ran 671 tests OK`（0 FAIL/ERROR）。

**残留（非本 finding，转入工单）**：
- tk-47 cli-parser 仍卡在 **argparse 库编码缝**（`parse_args` 返回 `Namespace`、非法 argv 抛 `SystemExit`/usage）——Q5 类边界，与 fastapi 无关。
- tk-49 web-review 的 Rust **port** 另属任务：`decide_review/review_queue_view/record_daily_observation_auto` 函数体是 Storage 绑定编排（OCC 写/archive/attention 累加），仅 Human-only 载荷门禁是干净纯切片；`spike-27-review-gate` 已备，待 rust-anything 宿主执行通道恢复再 bridge/record。

## tk-47 实证补记（2026-11-28 · 受限 argv→dict 切片尝试，结论=库缝非 gated port）

fastapi 解耦后 `zkc.cli` 已可无 fastapi 导入。据用户选 (a) 做「仅合法 argv → `vars(Namespace)` dict」切片：

- `spikes/spike-28-cli-parser/pure_bridge.py` → `rust/cli-parser-rs`，`record` **13 case / 0 threw**（覆盖 6 子命令 + 嵌套 `tombstone mark|restore|sweep` + 默认/`store_true`/`choices`/`--stale-branch`→`stale_branch` 命名）。
- 手写表驱动 port（值取自输入 token，仅 `pg`/`daily-automation` 为 recorded-literal）：
  **build pass、`diff` 13/13、cargo test pass、literals pass、behavior pass、panics pass**。
- **但 `gate` 的 `size` 判 FAIL：258 行 Rust / 22 行 Python（11.7x）**，提示原话即「over 3x usually means **code a crate already provides** … use the crates `analyze` lists」；
  折叠重复也降不下来（语法数据本身即 ~250 行）。

**定性（不刷指标 / 依 CONTEXT 判据 = 录制全匹配 且 gate 通过）**：合法 argv→dict 的**映射行为**可复现（13/13），
但 `cli.parse_args` 本质是「调 argparse 库」，其 Rust 等价物是 **clap** 而非手搓 parser——gate 的 size 信号正指向此。
与 Q5/本 finding 裁定一致：**tk-47 = argparse→clap 库编码缝，非 clean standalone port**。

**处置**：`rust/cli-parser-rs` 暂留作实证（**非 gated port**，勿当已迁单元参与 `app wire`/`map`）；tk-47 保持未完成 + hold。
可门化的真路是 **clap 版 port**（独立、更重的 ticket：clap 定义语法 + 仅对合法输入做 vars 等价；clap 的 usage/错误语义与 argparse 不同，须另划界）。是否立此 clap ticket 由 zj 定。
