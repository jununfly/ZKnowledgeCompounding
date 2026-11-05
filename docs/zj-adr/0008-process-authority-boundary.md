# 过程权威边界：仓库内自包含门禁 + 上游对齐的结构性过程态判据

Status: accepted（2026-11-05，zj 以「开始 1-23」拍板）；2026-11-05 修订（1-23-1，zj 以「a」拍板收敛 6 条白名单）

## 背景与实测

zj-roadmap-driven 的权威边界规定：roadmap 只回答「当前计划 / 进度 / 下一步」这类过程状态；
产品行为、架构、发布状态与正确性必须由代码、测试、运行时结果、契约、design 或 ADR 建立。
因此代码与长期文档不得引用过程编排稿，也不得把「节点已完成」直接写成 proof / evidence。

该门禁此前**从未接入本仓 CI**（`ci.yml` 零命中），且 CI runner 上没有用户级 skill 安装，
任何依赖 `~/.workbuddy/skills` 路径的接法都不可执行。2026-11-05 上午复跑门禁实测 7 行：

| 分类 | 位置 | 判定 |
| --- | --- | --- |
| 真违规 1 | `docs/prds/knowledge-compounding-prd.md:168` | PRD 是长期文档，却把过程编排稿当作决策引用源 |
| 误扫 4 | `.workbuddy/memory/2026-11-04.md:6/27/33`、`.workbuddy/memory/2026-11-05.md:59` | append-only 过程日志（记忆系统硬约束禁改；第 4 条是 1-21 收口日志本会话引入） |
| 误扫 2 | `docs/roadmap/roadmap.json:3`、`:419` | roadmap 事实源自身：root description（CLI 无 `--description` 可改、Agent 禁手改 JSON）与节点 1-18 notes（含证据缺口分层原文） |

当时的根因（上游旧版实现）：`authority_boundary.py` 把过程产物目录下的文件当作 process target，
却扫描 `root.rglob('*')` 下全部 durable 后缀文件，而 `EXCLUDED_DIR_PARTS` 只有
`{node_modules, tmp}` —— 过程日志与事实源自身被一并当成 durable code 判定；
`cmd_authority_check` 只收 `project_root`，没有 exclude 参数。该缺陷已由 ZAgentic #239 / #240
修复，见下文 Follow-up。

治理还有一个自指陷阱：检查器按行做子串匹配，凡在事实源 / 过程日志 / 长期记忆里写出
process target 的完整相对路径，记录行为本身就会新增一条泄漏（1-23 建模期间曾由 7 涨到 10，
改用「仅文件名 / 占位表述」后回到 7）。本轮所有新增文本一律不携带完整触发串。

## 决策

1. **真违规修复**：PRD §9 第 168 行改引 `docs/zj-adr/0004-mcp-interface-contract.md`、
   `docs/zj-adr/0005-rec-avoid-mechanical-gate.md` 与 `docs/rec-avoid-gate.md`；
   同时把原先只存在于过程编排稿里的「6 项 unknown 分层结论」（governance×4 / letta×2 /
   mem0 整体排除，及 (a)(b)(c) 三层决策）沉淀进 PRD 正文，保证决策摘要内容不丢失。
2. **新增仓库内自包含检查器** `scripts/zkc_authority_check.py`：只依赖标准库，复刻门禁的
   三类判定（直接引用 / markdown link / roadmap 完成声明），**不 import 用户级 skill**。
   判定语义与上游 `authority_boundary.py` 对齐，一条都不放宽。
3. **过程态对象按结构性判据识别，不做枚举式豁免**：
   - 目录剪枝：`.git` / `.workbuddy` / `__pycache__` / `node_modules` / `tmp` 及过程产物目录自身；
   - 单文件 roadmap carrier：按结构签名 `title / version / nodes / metadata` 齐备且每个节点带
     `status` 识别（普通 `nodes.json` 长出同名键不得借机逃逸）；
   - `render` / `section` 产出的 Markdown 视图：按开头 512 字节内完整的
     `zj-roadmap-authority/v1` 权威信封识别。
   初版（1-23）曾用 6 条 (相对路径 + 行内容锚点 + 命中上限 1) 显式白名单兜底并逐条打印
   `ALLOW` / `STALE`；上游 #240 修复并重装后，1-23-1 删除全部条目。理由：每新增一天过程日志、
   一条节点 notes、一次 carrier 改写都要人工加条目或处理 STALE，而结构判据可在同一 tree 上
   复刻验证，无需维护清单。**剪枝只改扫描范围、判定规则不放宽**；跳过清单逐条打印，替代原
   `STALE` 的「静默吞掉」防线。
4. **接入 CI**：`.github/workflows/ci.yml` 新增独立 `authority (process boundary)` job，
   `checkout` + `setup-python` 后直接跑仓库内脚本。CI 上没有 `.workbuddy/`（gitignore），
   过程态目录被剪枝不产生假阳性；carrier 与带信封的视图按结构签名跳过并逐条打印。
5. **不动**：用户级 skill 源码（其维护主场所是 ZAgentic workspace）、append-only 日志已有行、
   `roadmap.json` 事实源内容（只能经 CLI 读写）。

## Considered Options

- **A 改 skill 的 `EXCLUDED_DIR_PARTS`**（1-23 时拒绝）：当时属跨项目资产，需单独授权 +
  删除重装；即使改了，CI runner 仍没有该 skill，自包含 wrapper 照旧要做，收益不抵协调成本。
  *修订*：#240 已由 ZAgentic 侧修复并重装，协调成本由上游承担；ZKC 侧拿到的是**语义基准**，
  因此 1-23-1 只同步本仓 wrapper 的扫描范围，仍不改 skill 本体。
- **B 仓库内自包含 wrapper + 显式白名单**（1-23 时采纳）：一次改动同时解决「CI 可执行」与
  「6 处误扫」；白名单逐条可审，新泄漏仍 fail。*修订*：1-23-1 用结构性判据替换白名单，
  保留 wrapper 与 CI job 不变（命令仍是同一入口）。
- **C 归档过程编排稿后全量清引用**（拒绝）：root description 无 CLI 命令可改，
  4 条过程日志 append-only 禁改，且证据缺口原文须先沉淀到持久权威，阻塞面最大。
- **1-23-1 追加：issue #3 的 A（同步语义、收敛白名单）/ B（显式维持分叉）** → 采纳 A。
  B 会长期维护两套判定口径且每增一处过程态引用都要加白名单。可重复 `--exclude` 属**扩展能力**
  而非判定语义，当前 tree 无新增过程态目录需求，先不加（YAGNI）；未来若需要，须与上游语义一致
  地补，不得放宽判定。

## Consequences

- 本地复跑：`python scripts/zkc_authority_check.py .` → `exit 0`，输出 `scope` 行（process
  target 数 / 剪枝目录 / 扫描的 durable 源数 / 跳过的过程态文件数）、`skipped:` 清单与
  `summary: 0 unresolved leaks`。全量回归 `make test` 内含 12 条门禁测试。
- CI 复跑入口：`authority (process boundary)` job。若要在合并前强制通过，需在 GitHub
  仓库的 branch protection 里把该 job 设为 required check —— 属仓库设置，不在本仓文件内。
- 上游用户级 skill 的 `authority-check` 已在 #240 修复并重装，同一 tree 上返回
  `Authority boundary: clean.` / `exit 0`；本仓 wrapper 同为 `0 unresolved` / `exit 0`。
  两套实现判定结论一致，1-23 时期「上游仍报 6 行已知误扫」的口径差已消失。
- 结构性判据维护约定：新增过程态目录时改 `EXCLUDED_DIR_PARTS` 并补测试；carrier 结构签名
  与权威信封必须**完整匹配**，不得放宽成「只要出现标记行就跳过」；任何新增泄漏不得靠
  扩大排除集合了事，须先判断它是否真是过程态。测试里有防 `nodes.json` 逃逸与防半截信封
  逃逸两条守门用例。
- 未引入上游的可重复 `--exclude`：当前无项目侧额外过程态路径需要声明；该取舍只影响扩展
  能力，不影响判定语义。若未来出现，须同步上游语义并补测试，不要偷偷放宽。
- 检查器自身与治理文档都不得携带完整 process target 串，否则「记录治理」会自引入新泄漏。
- 判定语义若与上游 skill 分叉，以本 ADR + 测试为准，并在 roadmap 立节点追踪偏差
  （本条在 1-23-1 语义对齐后仍有效，作为未来分叉的处置规则）。

## Follow-up

### 2026-11-05：维护主场所澄清与上游 bug 追踪

zj 澄清了本 ADR 中「跨项目资产」这一表述：真正的边界不是抽象的「需单独授权」，而是
**维护主场所**。1-21 拍板的「repo 完全纳管 + 安装脚本」**只适用 ZKC 自有 skill**
（`skills/zj-zkc-daily/`），其语境默认都是本项目的；`zj-roadmap-driven` 的维护主场所是
**ZAgentic workspace 与对应 chats with agent** —— 为避免多个 Agent 产生混乱，不在 ZKC
仓库就地改它，也不在本机 ZAgentic 目录里顺手改。

当时发现的上游实现缺陷（扫描范围把过程日志与 carrier 自身当 durable code、且
`authority-check` 无按项目排除入口）已带完整上下文提报到
[ZAgentic #239](https://github.com/jununfly/ZAgentic/issues/239)（`bug`）。判据材料在 issue
里分层给出：skill 主体功能不受影响，受影响的是 `authority-check` 子命令在这类项目结构下
恒非零退出、无法直接接 CI。

当时的待办写的是「若判定影响正常使用：zj 在 ZAgentic 修复并重装后，ZKC 侧复跑上游门禁，
复核 6 条白名单是否可收敛（**上游不再误报即可删除**）」。该括号内判据**不成立**，见下节修正。

### 2026-11-05：1-23-1 收敛（上游修复后）

- ZAgentic #239 `CLOSED(COMPLETED)`，PR #240 / #241 均 `MERGED`，用户级
  `zj-roadmap-driven` 已删除重装到修复版；修复只改扫描范围（目录剪枝 + carrier 结构签名 +
  权威信封视图 + 可重复 `--exclude`），三类判定语义不变。
- 本仓 issue #3 判定该开放项归属 ZKC（ZAgentic 只提供语义基准），并指出原待办判据错误：
  上游误报消失 ≠ 独立 wrapper 误报消失 —— 上一轮反事实清空 6 条白名单仍得到 6 unresolved。
  **修正为可验证条件**：「本仓 wrapper 自身不再产生这 6 处命中」，以本地复跑 +
  CI checkout 模拟 + 缺陷态红 / 修复态绿为准。
- zj 以「a」采纳 issue #3 的 A 方案。1-23-1 执行：删 `ALLOWANCES` 6 条及 `STALE` 逻辑、
  wrapper 对齐上游三类结构判据、重写测试（3 条白名单用例改为结构判据用例，补防 carrier
  签名逃逸与防半截信封逃逸）、更新本 ADR 与 `ci.yml` 注释；CI job 命令未变。
- **真实环境实测（2026-11-05，zj 授权提交并推 main）**：实现 commit `75db9a0` 推 main 后
  触发 run [42007556572](https://github.com/jununfly/ZKnowledgeCompounding/actions/runs/42007556572)
  （event=push，runner Python 3.13.17），4/4 job success：`lint (actionlint)` 6s、
  `unit (PG disabled)` 14s、`full (PG + migrations + anchors e2e)` 57s、
  `authority (process boundary)` 7s。authority job 的日志与本地复跑逐字一致：
  `scope: 1 process target(s); ... scanned 214 durable source(s); skipped 2 process-state file(s)`、
  `skipped:` 清单、`summary: 0 unresolved leaks`，exit 0。此前「CI 从未接入该门禁」的
  空白已闭合，且 CI 侧只依赖仓库内脚本、不依赖用户级 skill 得到实证。
- **required check 已设置**：从该 run 的 check-run 名确认 `authority (process boundary)`
  绑定到 GitHub Actions（app_id 15368），经 API 设为 main 的 required status check；
  `enforce_admins=false`（不约束 admin 直推）、`strict=false`（不要求 PR 与 base 同步），
  required_pull_request_reviews / restrictions 均未启用；GET 复核与 PUT 一致。
  该规则只约束 PR 合并，admin 直接 push main 不受影响 —— 与 ZKC 现有工作流一致。
  若未来要连直推也强制，需把 `enforce_admins` 改为 true 并同步改工作流为分支 + PR。
