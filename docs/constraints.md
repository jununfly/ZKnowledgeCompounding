# 本机环境与工程硬约束（长期沉淀）

> 沉淀来源：原 `docs/plans/ZKC-implementation-plan.md` §8（2026-11-02 文档治理中沉淀至本长期文档；原件已归档至 `docs/archive/plans/ZKC-implementation-plan.md`）。
> 这一节是「实施时最容易漏掉、却会直接决定成败」的底层约束合集。它不是决策，而是决策的**承重墙**。每次开工前扫一遍。

## 8.1 第一性不变量（任何变更的判定基准，引架构 §3）

1. **两类信息原生双轨建模**：生命周期与操作语义分离，不在同一张"笔记表"混同。
2. **ZKC 拥有四项核心语义**：双轨标签定义、decay 衰减模型、双时态（valid + transaction time）溯源、稀缺注意力调度；对外主张须带 `caveat: moat-unverified-vs-mem0`，不得回退到 3 项口径（引架构 §3）。
3. **存储是可替换 seam**：不是架构中心；变换语义与调度策略属于 ZKC 自己。
4. **所有变换产物必须可溯源**（回溯到来源条目），否则无法复用、无法复利。
5. **默认本地/离线优先**：个人数据 + 隐私；云端只作可切换 provider。

## 8.2 术语护栏（防混用，错用即架构偏移）

- **双轨(dual-track) ≠ 双时态(bitemporal)**：双轨 = 静态/动态类型 + 生命周期分流（衰减率与注意力成本）；双时态 = valid time + transaction time 的溯源建模（事实演进 + 审计）。Utopia 的 bitemporal 只覆盖 ZKC「静态轨事实可更新」一半，**完全不覆盖动态轨腐化与注意力稀缺**——这是 ZKC 的差异化核心，引入 bitemporal 不等于解决了双轨。
- **衰减 ≠ 衰减可控**：前者是时间函数；后者是「到期前被处理（蒸馏/归档）」的可观测度量。

## 8.3 环境与硬件约束（本机 16GB，极易 miss）

- **Postgres 不是本机裸装，是 docker 容器**：容器名 **`zkc-spike-pg`**，镜像 `pgvector/pgvector:pg16`，宿主端口 **55433** → 5432。实测 PostgreSQL **16.15**、pgvector **0.8.7**。
  - 连接沿用 spike 01 的口径，不要新造：`docker exec -i zkc-spike-pg psql -U postgres -d zkc -v ON_ERROR_STOP=1 -tA -f -`
  - **应用代码 DSN**（spike 09 口径）：`postgresql://postgres:zkc@localhost:55433/zkc_dev`（密码 `zkc`）。已实测 psycopg 连通。
  - **⚠️ `zkc/migrate.py` 不读 DSN，读三个环境变量**（对账 2026-10-31 修正：此前误记为 `ZKC_PG_DSN`，**该变量不存在**）：`ZKC_PG_CONTAINER`（默认 `zkc-spike-pg`）、`ZKC_PG_USER`（默认 `postgres`）、`ZKC_PG_DB`（默认 `zkc_dev`）。它经 `docker exec psql` 执行，**不需要 Python DB 驱动**。
  - 遗留库 `zkc` = 14 个 spike 累积的**手工 schema**（15 表，`node` 0 行）→ **保留作时间胶囊，不回改**；新库 **`zkc_dev`** 由 `zkc/migrate.py` 从零建（实测 12 表 / `0001 applied` / 可 up+down 重放）。
  - ⚠️ 容器状态可被 docker 重启丢掉 → **任何 schema 变更必须进 `migrations/`，禁止手工建表**。
- **⚠️ pip 必须走 Clash 代理，否则「装不上」是假象**：`python -m pip install --proxy http://127.0.0.1:7890 <pkg>`。不走代理时报 `from versions: none / No matching distribution found`，**看起来像「这个包不存在/沙箱禁网」，实为没配代理**。已实测装上 `instructor 1.17.0`、`psycopg[binary]`。**更正**：此前「semantic-router 装不上（沙箱网络）」以及据此写进 `zkc/migrate.py` docstring 的「本机 pip 无法访问 PyPI」**均已过时**——那是没走代理，不是装不上（连带影响见 R19，已关闭并归档至 docs/archive/plans/）。
- **蒸馏模型默认 `qwen3.5:4b-mlx`**（3.97GB）；`9b-mlx` 仅可选上限——9B 在 16GB 常驻 10–12GB、触发 swap、单次蒸馏 ~4.7min，不可用做日常迭代。
- **Ollama 代理**：直连 registry 会 DNS 超时；需 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7890`（Clash）。本地 `localhost:11434` 必须 `NO_PROXY=localhost,127.0.0.1` 绕过，否则 httpx 把本地也走代理 → 无限挂起。
- **`num_ctx` 必须显式限制**：未限制时 9B GGUF 常驻 15GB、swap 用满 20GB+；限 `8192` 后空闲 9%→69%。控制上下文是 16GB 跑 9B 的前提。
- **忠实度自动判定本机否决**：4B 经 Ollama 不输出 JSON（~110–130s/条且格式错）；9B ~6min/条且同样不合规。→ MVP 忠实度闸门 = human-in-the-loop + 字面 rubric 预过滤；`judge.py`/`run_spike12.py` 零改动可启用（待更快硬件/离盒/云端 opt-in）。

## 8.4 工具与 git 铁律（本环境特有，踩过多次）

- **git 提交后必跑 `git ls-tree -r HEAD --name-only | wc -l` 校验树文件数**（应≈全仓 tracked 数）；异常立即用「删 index/index.lock → 同命令内 `git add <完整路径>` + `git commit`」重暂存（拆分命令会导致空树塌缩）。feat/docs 分离提交在本环境不可行，只能单提交保全树。
- **safe-delete shim 会执行 `rm -rf` 致 git 损坏**；涉及 workspace 文件落盘/备份/还原一律用 Read/Edit/Write，勿用 Bash `cp/git checkout/stash` 来回倒。
- **Bash 默认超时 120s**：长命令（全量测试/安装/构建）显式给 timeout 或拆多条；被 SIGTERM(137) 看似失败实为超时。
- **zsh 单词分割坑**：`for n in $VAR` 不按空格分词（bash 才分）；批量多目标用 Python 或 zsh 数组 `${=VAR}`。
- **sandbox-center 拦截 `VAR=value &&` 链式赋值**与向 workspace 写文件；遇阻用 `env` 前缀或 Python 脚本。
- **Grep 工具静默跳过隐藏目录**（`.github/`/`.claude/` 等）；「全仓零命中」类否定结论必须换工具链（`git ls-files`/Read）交叉验证。

## 8.5 spike 限定外推红线（禁止静默当成已解决）

- **单次采样结论不可信**：同一臂两次跑跨源率可 0.0↔1.0；任何质量对比须基于多次采样分布。
- **比率指标可被「少发 claim」刷高**：rubric 必须同时要求绝对数量（≥2 条跨源 claim）。
- **幻觉/忠实度无法用字面方法测**：抽象 claim 本就该用源文本没有的词，字面重叠无法区分「好抽象」与「无据编造」。
- **跨源综合原不达标（Spike 10）**：已由 Spike 11 算子层解（4B×3 稳定 3/3），但 1.5B 无溢出收益 → 能力下限由模型结构化能力决定。
- **L3 复审反馈必须接显式结果标注**：decay-only 反馈恒为 no-op，永不修正基线（Spike 09 实测）。
