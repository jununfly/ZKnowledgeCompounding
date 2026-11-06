# Windows 上安装并运行 ZKC 指南（WSL2 原生 PostgreSQL 路线）

Status: accepted (2026-11-07, 经 1-24 实机验收收敛)
Scope: 在 Windows + WSL2 主机上从零搭建 ZKC 运行时、跑通数据库迁移、并驱动 E1 每日收口写入真实 PostgreSQL。
适用场景: 本机无 Docker / Docker 被环境拦截 / 不想手编 Windows 原生 pgvector。

> 本文所有**机器相关**信息（用户名、盘符、WSL 发行版、IP、主机名）均用 `<占位符>` 表示；**项目约定**（端口、库名、密码）来自源码 `src/zkc/repository/connection.py` 的 `DEFAULT_DSN`，保持原值，无需修改。

---

## 0. 占位符约定

| 占位符 | 含义 | 示例 |
|--------|------|------|
| `<REPO>` | 项目在 Windows 侧的绝对路径 | `D:\workspace\github\jununfly\ZKnowledgeCompounding` |
| `<REPO_WSL>` | 同一项目在 WSL 内挂载路径（盘符 `X:` → `/mnt/x/...`） | `/mnt/d/workspace/github/jununfly/ZKnowledgeCompounding` |
| `<USER>` | Windows 用户名 | `jununfly` |
| `<USERPROFILE>` | Windows 用户主目录 | `C:\Users\<USER>` |
| `<WSL_DISTRO>` | WSL 发行版名（单机默认可省略 `-d`） | `Ubuntu` |
| `<WSL_IP>` | WSL 实例 IP（`wsl hostname -I` 取得） | `172.23.180.40` |

**项目约定（来自源码，保持原值，无需改动）**

| 项 | 值 | 来源 |
|----|----|------|
| PostgreSQL | 16 + pgvector **0.8.7** | `migrations/0001_*.up.sql` 头注释 `CREATE EXTENSION vector` |
| 端口 | `55433` | `connection.DEFAULT_DSN` |
| 库 | `zkc_dev` | `connection.DEFAULT_DSN` |
| 用户 | `postgres` | `connection.DEFAULT_DSN` |
| 密码 | `zkc` | `connection.DEFAULT_DSN` |
| DSN 可覆盖 | 环境变量 `ZKC_PG_DSN` | `connection.get_dsn()` |

---

## 1. 为什么走这条路线（设计取舍）

| 需求 | 结论 |
|------|------|
| 项目依赖 pgvector 扩展 | 普通 Windows EDB 安装器**无官方 pgvector 二进制**，需 MSVC 手编，易踩坑 → 排除原生 Windows PG |
| 本机可能无 Docker / Docker 被拦截 | `make db` 用的 `pgvector/pgvector:pg16` 容器跑不起来 → 改用 WSL2 apt 装同版本 PG |
| `zkc.migrate` 硬编码 `docker exec -i <container> psql` | 不依赖容器：用 **docker 垫片（shim）** 把调用翻译成本地 `psql`（零源码改动） |
| Windows 侧连不上 WSL 的 `localhost:55433` | 迁移与驱动**全部在 WSL 内执行**，PG 只在 WSL 内监听 |
| `schtasks.exe` 被沙箱 Program Blacklist 拦截 | 定时触发改由 **WorkBuddy 定时任务**（每日 23:50，命令落在 WSL 内）替代 |
| WSL 重启后 PG 不自起 | 每次执行前先 `service postgresql start`；定时任务内已含此步 |

---

## 2. Part A — WSL2 安装 PostgreSQL 16 + pgvector 0.8.7

### A.1 进入 WSL（root 身份，避免 sudo 权限问题）

在 **Windows 终端（PowerShell / Git Bash，不要进 WSL 后再敲 `wsl`）**：

```powershell
wsl -u root
```

提示符变为 `root@<HOSTNAME>:/#` 后再继续。若发行版非默认，用 `wsl -d <WSL_DISTRO> -u root`。

### A.2 加 PGDG 源并安装

```bash
# 以 root 在 WSL 内执行（无 sudo 前缀）
apt update
apt install -y curl ca-certificates gnupg lsb-release
install -d /usr/share/postgresql-common/pgdg
curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
CODENAME=$(lsb_release -cs)
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${CODENAME}-pgdg main" > /etc/apt/sources.list.d/pgdg.list
apt update
```

> **若 `apt update` 末尾报 404**（新发行版代号 PGDG 尚未收录）：退回 LTS 代号，例如 `noble`（24.04）：
> ```bash
> echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt noble-pgdg main" > /etc/apt/sources.list.d/pgdg.list
> apt update
> ```
> **若 curl 拉密钥报 `SSL_read: unexpected eof`**（TLS 拦截）：用 `trusted=yes` 兜底（本地开发库可接受）：
> ```bash
> echo "deb [trusted=yes] https://apt.postgresql.org/pub/repos/apt noble-pgdg main" > /etc/apt/sources.list.d/pgdg.list
> apt update
> ```

### A.3 安装 PG16 + pgvector

```bash
apt install -y postgresql-16 postgresql-16-pgvector
service postgresql start
```

### A.4 改端口为 55433 并对 localhost 监听

```bash
sed -i "s/^#*port = .*/port = 55433/" /etc/postgresql/16/main/postgresql.conf
sed -i "s/^#*listen_addresses = .*/listen_addresses = 'localhost'/" /etc/postgresql/16/main/postgresql.conf
service postgresql restart
```

### A.5 建库、设密码（与 `DEFAULT_DSN` 一致）

```bash
su - postgres
psql -c "ALTER USER postgres WITH PASSWORD 'zkc';"
psql -c "CREATE DATABASE zkc_dev;"
psql -d zkc_dev -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
PGPASSWORD=zkc psql -h 127.0.0.1 -p 55433 -U postgres -d zkc_dev -c "SELECT version();"
exit
```

预期：最后一条 `SELECT version();` 经 **TCP 127.0.0.1:55433 + 密码 + zkc_dev** 返回 `PostgreSQL 16.x`，且 `vector` 扩展版本为 `0.8.7`。

---

## 3. Part B — Python venv（含 Windows 侧常见坑）

### B.1 优先用 WSL 内 venv（推荐）

WSL 内既有 `psql` 又能直连 `localhost:55433`，迁移与驱动**应在此执行**，避免 Windows↔WSL 网络墙。

若 WSL 提示 `python3: command not found`，先以 root 装解释器与 venv 模块：

```powershell
# Windows 侧执行
wsl -u root -e bash -c "apt update && apt install -y python3 python3-venv python3-pip"
```

> **坑**：非登录 shell 下继承的 `$PATH` 可能不含 `/usr/bin`，导致 `python3: command not found`。
> 解决：显式把系统路径写进 `PATH`（见下文 Part C 命令模板）。

### B.2 Windows 侧 venv（备用，仅当你需在 Windows 跑 Python）

Windows 自带 **Microsoft Store python 占位桩**（`C:\Users\<USER>\AppData\Local\Microsoft\WindowsApps\python.exe`）会静默空转、零输出零报错。必须用真实解释器建 venv：

```powershell
# 用真实 python 建 venv（不要用商店桩）
& "<REAL_PYTHON>" -m venv .venv
# PowerShell 调用 venv 内 python 必须加 .\ 前缀，否则被当成模块名
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

> **常见 PowerShell 报错对照**
> | 报错 | 原因 | 修法 |
> |------|------|------|
> | `无法将“source”项识别为 cmdlet` | `source` 是 bash 命令 | 直接用 `.\.venv\Scripts\python.exe` 或 `.\.venv\Scripts\Activate.ps1` |
> | `make : 无法将“make”项识别为 cmdlet` | 无 make | 用等价 `python -m ...` 命令 |
> | `无法加载模块“.venv”` | PowerShell 把 `.venv` 当模块前缀 | 加 `.\` 前缀 |
> | `import zkc` 零输出 | 实际跑在商店桩上 | 用真实 python 建 venv 重装 |

---

## 4. Part C — 数据库迁移（docker 垫片 + bootstrap 绕过）

### C.1 创建 docker 垫片（零源码改动）

`src/zkc/migrate.py` 的 `psql()` 硬编码 `docker exec -i <container> psql ...`。在仓库内新建 `.wsl-bin/docker` 把它翻译成本地 `psql`：

```bash
# 在 <REPO> 内（WSL 或 Windows 均可创建）
cat > .wsl-bin/docker <<'EOF'
#!/usr/bin/env bash
# docker shim for ZKC migrate on WSL-native PostgreSQL.
# Translates `docker exec -i <container> psql <args...>` into a local
# `psql -h 127.0.0.1 -p 55433 <args...>` against the WSL2 PostgreSQL,
# so `python -m zkc.migrate` works without a docker container.
# Only the `exec -i <container> psql` form used by src/zkc/migrate.py is supported.
set -euo pipefail

if [ "$#" -ge 4 ] && [ "$1" = "exec" ] && [ "$2" = "-i" ] && [ "$4" = "psql" ]; then
  # drop: docker exec -i <container> psql  -> remaining $@ are psql args
  shift 4
  export PGPASSWORD="${ZKC_PG_PASSWORD:-zkc}"
  exec /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -p 55433 "$@"
fi

echo "docker-shim: unsupported invocation: $*" >&2
exit 1
EOF
chmod +x .wsl-bin/docker
```

### C.2 执行迁移（在 WSL 内）

```powershell
# Windows 侧执行：一次性起 PG + 建 venv + 迁移 + 验证
wsl -e bash -c "cd <REPO_WSL> && \
  unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy && \
  export PATH=/mnt/<REPO_WSL>/.wsl-bin:/usr/lib/postgresql/16/bin:/usr/local/bin:/usr/bin:/bin:\$PATH && \
  python3 -m venv .venv-wsl && . .venv-wsl/bin/activate && \
  pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 60 && \
  pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 60 && \
  python -m zkc.migrate status && \
  python -m zkc.migrate upgrade && \
  python -m zkc.migrate verify"
```

> **PATH 要点**：`export PATH=/mnt/.../.wsl-bin:/usr/lib/postgresql/16/bin:/usr/local/bin:/usr/bin:/bin:$PATH`
> 必须把 `.wsl-bin`（垫片）、PG 的 `bin`、以及系统 `/usr/bin` 都显式写进 PATH，否则非登录 shell 找不到 `python3` / `psql`。
>
> **代理要点**：若 Windows 开了 Clash 等代理，`wsl -e bash` 会继承 `HTTP_PROXY=127.0.0.1:7890`，而 WSL NAT 模式访问不到该代理 → pip 卡死。先 `unset` 全部代理变量。

### C.3 绕过 `cmd_upgrade` 漏 bootstrap 的 bug

`zkc.migrate` 的 `cmd_upgrade` 在全新库上**直接查 `schema_migration` 表却从未先建表**（建表逻辑在 `cmd_status`/`cmd_verify` 的 `bootstrap()` 里）。症状：

```
RuntimeError: psql 失败 (db=zkc_dev, exit=3):
ERROR:  relation "schema_migration" does not exist
```

**绕过**：先跑一次 `python -m zkc.migrate status`（它会 `bootstrap` 建表），再 `upgrade`。脚本 C.2 已包含该顺序。

> 这是 `migrate` 工具自身 bug，**不改动源码**（符合 1-24 scope gate）。后续可在独立 fix 里给 `cmd_upgrade` 在 `ensure_database(db)` 后补一行 `bootstrap(db)`。

---

## 5. Part D — 运行 E1 每日驱动并验证真值收口

`scripts/daily_e1_driver.py` 默认 `ZKC_MODE=direct` + `ZKC_STORAGE=pg`，直接对真实 PG 写 `attention_observation`，**不需要 HTTP 服务常驻**，也**不用 memory 后端冒充**。

```powershell
# Windows 侧执行（落点在 WSL 内，PG 可达）
wsl -e bash -c "cd <REPO_WSL> && \
  unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy && \
  export PATH=/mnt/<REPO_WSL>/.wsl-bin:/usr/lib/postgresql/16/bin:/usr/local/bin:/usr/bin:/bin:\$PATH && \
  . .venv-wsl/bin/activate && \
  python scripts/daily_e1_driver.py && \
  echo '===== LOG TAIL =====' && tail -n 3 logs/e1_daily.log"
```

预期日志尾出现一行 JSONL，**核心字段**：

```json
{"as_of":"...","mode":"direct","observe_ok":true,"meter_ok":true,
 "observe":{"day":"...","pushed":0,"completed":0,"queue_remaining":0,"labeled_completed":0},
 "meter":{"...all_exit_criteria_met":false},
 "observe_ok":true,"meter_ok":true}
```

判定标准：`mode:direct` + `observe_ok:true` 即证明**真实 PG 写入成功**（非 memory 冒充）。`pushed/completed=0` 仅表示全新库暂无复审活动，机制本身已成立。

**落库双保险（查看 `attention_observation` 表）**：

```powershell
wsl -u root -e bash -c "export PATH=/usr/lib/postgresql/16/bin:\$PATH; PGPASSWORD=zkc psql -h 127.0.0.1 -p 55433 -U postgres -d zkc_dev -c \"SELECT day, pushed, completed, queue_remaining FROM attention_observation ORDER BY day DESC LIMIT 3;\""
```

---

## 6. Part E — 定时执行（替代被黑名单的 schtasks）

原生 Windows `schtasks.exe` 在本沙箱被 Program Blacklist 拦截，且 Windows 侧连不到 WSL 的 PG。改用 **WorkBuddy 定时任务**，命令落在 WSL 内、每日 23:50，与 macOS launchd 触发语义对齐：

- **名称**：`ZKC Daily E1 Driver (WSL+PG)`
- **频率**：`FREQ=DAILY;BYHOUR=23;BYMINUTE=50`
- **命令**（在 WSL 内先保 PG 在线再跑 driver）：

```bash
wsl -u root -e bash -c "service postgresql start; sleep 2; cd <REPO_WSL> && export PATH=/usr/lib/postgresql/16/bin:/usr/local/bin:/usr/bin:/bin:\$PATH && . .venv-wsl/bin/activate && python scripts/daily_e1_driver.py"
```

> 若你的环境**未**拦截 schtasks，也可改用原生「任务计划程序」注册 `install_daily_driver.bat`（见 `docs/zj-adr/0007-*.md` §5.1 四步清单），命令契约经 `--dry-run` 验证一致：
> `schtasks /create /tn "ZKC Daily E1" /tr "...\scripts\daily_e1_driver.bat" /sc daily /st 23:50 /f`

---

## 7. 排错速查（FAQ）

| 现象 | 根因 | 修法 |
|------|------|------|
| `wsl: 检测到 localhost 代理配置…NAT 模式不支持 localhost 代理` + `python3: command not found` | 继承代理 + PATH 缺系统目录 | `unset` 代理；`export PATH=.../usr/bin:/bin:$PATH` |
| `FileNotFoundError: [Errno 2] No such file or directory: 'docker'` | `zkc.migrate` 调 docker，但 WSL 无 docker | 用 `.wsl-bin/docker` 垫片（Part C.1），并把该目录放 PATH 最前 |
| `Connection refused ... 127.0.0.1:55433` | WSL 重启后 PG 没自起 | `wsl -u root -e bash -c "service postgresql start"` |
| `relation "schema_migration" does not exist` | `cmd_upgrade` 漏 bootstrap | 先 `zkc.migrate status` 再 `upgrade` |
| Windows 侧 `Test-NetConnection localhost 55433` → `TcpTestSucceeded: False` | Windows↔WSL localhost 转发未生效 | 迁移/驱动改在 WSL 内执行；勿从 Windows 侧直连 |
| `psql: command not found`（WSL 内 migrate 时） | PATH 未含 PG bin | `export PATH=/usr/lib/postgresql/16/bin:$PATH` |
| `pip` 从 `files.pythonhosted.org` 超时 | 网络到官方源不稳 | 换镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| PowerShell `source`/`make`/`.venv` 报错 | Windows 语法差异 | 见 Part B.2 对照表 |

---

## 8. 附录 — 环境变量与 DSN

| 变量 | 作用 | 默认 |
|------|------|------|
| `ZKC_PG_DSN` | 覆盖数据库连接 | `postgresql://postgres:zkc@localhost:55433/zkc_dev` |
| `ZKC_PG_PASSWORD` | 垫片连接 PG 的密码（仅垫片用） | `zkc` |
| `ZKC_STORAGE` | 存储后端 | `pg`（driver 默认） |
| `ZKC_MODE` | 驱动模式 | `direct`（driver 默认，直写 PG） |

> 只要 WSL 内 PG 跑在 `55433 / zkc_dev / postgres / zkc`，`ZKC_PG_DSN` 与 `DATABASE_URL` **均无需设置**，`connection.get_dsn()` 回落到 `DEFAULT_DSN` 直连。
