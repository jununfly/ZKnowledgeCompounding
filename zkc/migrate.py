"""ZKC · 零依赖 schema 迁移器（P1.1）。

为什么不是 Alembic（**2026-10-31 修订，理由 1 已作废，见下**）：
- ~~理由 1（**已作废**）~~：本机 pip 无法访问 PyPI（沙箱网络受限），`alembic`/`psycopg`/
  `sqlalchemy` 均装不上。→ **2026-10-31 实测推翻**：走 Clash 代理
  （`pip install --proxy http://127.0.0.1:7890`）后 `instructor 1.17.0`、`psycopg[binary]`
  均可正常安装。故本条**不再作为选型依据**。
- 理由 2（**仍成立**）：架构第一性不变量「依赖最少」；迁移只需「按序执行 SQL +
  记录已应用版本」，用 `docker exec psql` 就够，不需要 ORM 与 Python DB 驱动。
- 代价：没有 autogenerate（不能自动 diff 模型与库）。对本阶段可接受——
  schema 由架构 §5 与 spike 证据手工维护，反而更可控。
- ⚠️ **是否回迁 Alembic 重新 open**：见实施计划 §5 **R19** / 任务 **P1.5**。
  回迁窗口 = 写业务代码之前（成本最低）。若 P1.2 引入 SQLAlchemy 模型层，应同时回迁。

设计要点：
1. **每个迁移是单事务**（`psql --single-transaction`），失败整体回滚，不留半截 schema。
2. **sha256 留痕**：应用时记录文件哈希；`verify` 会比对已应用哈希与当前文件哈希，
   **改历史迁移必须被抓到**（这是自研方案最容易踩的坑，必须有闸门）。
3. **版本表独立于领域 schema**（`schema_migration`），不进业务模型。

用法：
    python -m zkc.migrate status    [--db zkc_dev]
    python -m zkc.migrate upgrade   [--db zkc_dev] [--to 0001]
    python -m zkc.migrate downgrade [--db zkc_dev] [--to 0001]   # --to = 回滚掉该版本及之后
    python -m zkc.migrate verify    [--db zkc_dev]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

CONTAINER = os.environ.get("ZKC_PG_CONTAINER", "zkc-spike-pg")
PG_USER = os.environ.get("ZKC_PG_USER", "postgres")
DEFAULT_DB = os.environ.get("ZKC_PG_DB", "zkc_dev")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migration (
    version    text PRIMARY KEY,
    sha256     text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now(),
    note       text
);
"""


# ------------------------------------------------------------------ psql 封装

def psql(db: str, sql: str, *args: str, single_transaction: bool = False) -> str:
    """经 docker exec 执行 psql。ON_ERROR_STOP=1 保证错即停。"""
    cmd = [
        "docker", "exec", "-i", CONTAINER, "psql",
        "-U", PG_USER, "-d", db, "-v", "ON_ERROR_STOP=1", "-tA",
    ]
    if single_transaction:
        cmd.append("--single-transaction")
    cmd.extend(args)
    cmd.extend(["-f", "-"])
    res = subprocess.run(cmd, input=sql, text=True, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(
            f"psql 失败 (db={db}, exit={res.returncode}):\n"
            f"{res.stderr.strip()}\n--- SQL ---\n{sql[:2000]}"
        )
    return res.stdout.strip()


def ensure_database(db: str) -> None:
    """建库（幂等）。`postgres` 库一定存在，用它做 CREATE DATABASE。"""
    exists = psql(
        "postgres",
        "SELECT 1 FROM pg_database WHERE datname = :'db';",
        "-v", f"db={db}",
    )
    if exists.strip() != "1":
        # CREATE DATABASE 不能含参数绑定，库名来自 CLI/环境变量，做一次白名单校验
        if not db.replace("_", "").isalnum():
            raise ValueError(f"非法库名 {db!r}（只允许字母、数字、下划线）")
        psql("postgres", f'CREATE DATABASE "{db}";')
        print(f"created database: {db}")


def bootstrap(db: str) -> None:
    psql(db, _BOOTSTRAP)


# ------------------------------------------------------------------ 迁移发现

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover() -> list[tuple[str, Path, Path]]:
    """返回 [(version, up_path, down_path)]，按 version 升序。"""
    items: list[tuple[str, Path, Path]] = []
    for up in sorted(MIGRATIONS_DIR.glob("*.up.sql")):
        version = up.name.split("_", 1)[0]
        down = up.with_suffix("").with_suffix(".down.sql")
        # 0001_baseline_d1_d9.up.sql → 0001_baseline_d1_d9.down.sql
        down = up.parent / (up.name[: -len(".up.sql")] + ".down.sql")
        if not down.exists():
            raise FileNotFoundError(f"{up.name} 缺少对应的 down 脚本：{down.name}")
        items.append((version, up, down))
    return items


def applied(db: str) -> dict[str, str]:
    """已应用版本 → sha256。"""
    out = psql(db, "SELECT version || ' ' || sha256 FROM schema_migration ORDER BY version;")
    pairs: dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        v, _, h = line.partition(" ")
        pairs[v] = h.strip()
    return pairs


# ------------------------------------------------------------------ 命令

def cmd_status(db: str) -> int:
    bootstrap(db)
    done = applied(db)
    for version, up, _ in discover():
        state = "applied" if version in done else "pending"
        print(f"  {version}  {state:8s} sha={_sha(up)[:12]}  {up.name}")
    if not discover():
        print("  (no migrations)")
    return 0


def cmd_upgrade(db: str, to: str | None) -> int:
    ensure_database(db)
    bootstrap(db)
    done = applied(db)
    for version, up, _ in discover():
        if version in done:
            continue
        if to is not None and version > to:
            break
        sha = _sha(up)
        print(f"applying {up.name} ...")
        sql = up.read_text() + "\n"
        sql += (
            "\nINSERT INTO schema_migration (version, sha256, note) VALUES "
            f"('{version}', '{sha}', '{up.name}');\n"
        )
        psql(db, sql, single_transaction=True)
        print(f"  ✓ {version} applied (sha={sha[:12]})")
    return 0


def cmd_downgrade(db: str, to: str | None) -> int:
    ensure_database(db)
    bootstrap(db)
    done = applied(db)
    for version, _, down in reversed(discover()):
        if version not in done:
            continue
        if to is not None and version < to:
            break
        print(f"reverting {down.name} ...")
        sql = down.read_text() + "\n"
        sql += f"\nDELETE FROM schema_migration WHERE version = '{version}';\n"
        psql(db, sql, single_transaction=True)
        print(f"  ✓ {version} reverted")
    return 0


def cmd_verify(db: str) -> int:
    """已应用迁移的 sha 必须与磁盘文件一致——改历史迁移必须被抓到。"""
    bootstrap(db)
    done = applied(db)
    bad = 0
    for version, up, _ in discover():
        if version not in done:
            continue
        disk, recorded = _sha(up), done[version]
        if disk != recorded:
            print(f"  ✗ {version}: 文件已改动！记录 sha={recorded[:12]} 当前 sha={disk[:12]}")
            bad += 1
        else:
            print(f"  ✓ {version}: sha 一致 ({disk[:12]})")
    if bad:
        print(f"\n{bad} 个已应用迁移被改动 —— 历史迁移不可变，请新增迁移而不是改旧的。")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ZKC schema migrator (zero-dependency)")
    ap.add_argument("command", choices=["status", "upgrade", "downgrade", "verify"])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--to", default=None, help="目标 version（upgrade: 到该版本为止；downgrade: 回滚该版本及之后）")
    a = ap.parse_args(argv)
    fn = {
        "status": lambda: cmd_status(a.db),
        "upgrade": lambda: cmd_upgrade(a.db, a.to),
        "downgrade": lambda: cmd_downgrade(a.db, a.to),
        "verify": lambda: cmd_verify(a.db),
    }[a.command]
    return fn()


if __name__ == "__main__":
    sys.exit(main())
