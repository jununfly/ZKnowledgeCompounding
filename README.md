# ZKnowledgeCompounding（ZKC）

个人「知识复利」工具：让有限的时间精力（长期）与注意力（短期）对知识产生复利。
双轨摄入（静态事实 / 动态存活）→ 调度复审（衰减驱动）→ 复利变换（蒸馏/结合/装配）→ 检索复用。

> 设计哲学：ZKC 不是更好的笔记软件，而是让注意力产生复利的外脑。
> 使用层面的操作说明见 **docs/user-guide.md**；本文只讲「怎么把它跑起来」。

## 定位声明（ADR-0001）

**本机单用户 web 应用，不做打包、不做分发、不做第二人安装支持。**
FastAPI + SSR，`localhost:8000`；存储 Postgres + pgvector；LLM 走本机 Ollama。

## 前置依赖

| 依赖 | 要求 | 说明 |
| --- | --- | --- |
| Python | 3.10+ | 见 `requirements.txt`（fastapi/uvicorn/psycopg 等，无重依赖） |
| Postgres 16 | `localhost:55433`，库名 `zkc_dev` | 需含 pgvector 扩展；本机容器名 `zkc-spike-pg` |
| Ollama | `localhost:11434` | 蒸馏/路由：`qwen3.5:4b-mlx`；embedding：`nomic-embed-text` |

> Ollama 不可用时系统**不阻塞**：路由自动降级为词法单信号或人工兜底（本地优先离线，不变量 5）。
> 连接串可用 `ZKC_PG_DSN` 覆盖，默认 `postgresql://postgres:zkc@localhost:55433/zkc_dev`。

## 启动步骤

```bash
make setup      # 安装 Python 依赖 + 本包 editable 安装（src 布局，包名仍为 zkc）
make db         # 确保 Postgres 容器在跑（首次需 docker run，见下方注释）
make migrate    # 应用全部 schema 迁移（src/zkc/migrate.py，零依赖自研迁移器）
make serve      # 启动 web：http://localhost:8000
```

> `make db` 的容器：`docker run -d --name zkc-spike-pg -p 55433:5432 \
>   -e POSTGRES_PASSWORD=zkc -e POSTGRES_USER=postgres -e POSTGRES_DB=zkc_dev \
>   pgvector/pgvector:pg16`
> （仅首次需要；之后 `docker start zkc-spike-pg`，`make db` 会自动处理。）

### 其他命令

```bash
make test       # 全量单测（根目录 + tests/ 各跑一遍 discover）
make verify     # 校验已应用迁移的 sha256 与磁盘文件一致（改历史迁移会被抓）
make dogfood    # 冷启动回归：播种 + 驱动复审/收口（需另开终端先 make serve）
```

## 页面入口

| 路径 | 作用 |
| --- | --- |
| `/` | 快捕获：粘贴一条笔记，自动分流（静态/动态）或转人工定轨 |
| `/review` | 每日复审队列（衰减到期条目 + 结果标注 + 每日收口） |
| `/browse` | 检索（结构化 + 语义双路）与复利产物浏览 |
| `/metrics` | 复利度量面板（五度量 + 复利系数） |
| `/tuning` | 阈值参数与来源标签 |

## 目录速览

```
zkc/            生产代码（routing/ingest/scheduling/distill/faithfulness/context/expiry/metrics/web）
migrations/     SQL 迁移（0001–0007，sha256 留痕，历史不可改）
scripts/        dogfood 与运维脚本（含 metrics_snapshot.py 每周复盘入口）
docs/           PRD / 架构 / 用户指南 / ADR
tests/          单测（内存 fake + 真实 PG 双后端同构）
```
