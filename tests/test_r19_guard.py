"""R19 决策锁 · 不回迁 Alembic 不变量（guard / characterization 测试）。

R19 已于 P1.5 收口关闭（2026-10-31 决策 + 本次收口）：维持自研零依赖迁移器
``zkc/migrate.py``，**不**引入 SQLAlchemy / Alembic。

本测试把该架构决策锁成可执行契约，防止未来静默漂移：
1. 迁移权威 = 自研 ``zkc.migrate``（而非 Alembic）；暴露 CLI 入口且能发现 0001 基线迁移。
2. ``zkc/`` 业务代码不得 ``import sqlalchemy`` / ``import alembic``
   （raw SQL + repository seam 不变量，保持 Kuzu / TerminusDB 可替换）。
3. ``requirements.txt`` 不得声明 ``sqlalchemy`` / ``alembic``（第一性不变量「依赖最少」）。

若日后 P1.2 演进为 SQLAlchemy ORM 模型层，本测试会变红 —— 这正是设计意图：
红 = 触发 R19 重新 open 并同步回迁 Alembic。

测试为纯静态扫描 + import，不依赖 docker / Postgres，秒级可跑。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZKC = ROOT / "zkc"
REQ = ROOT / "requirements.txt"

# R19 锁：禁止出现的顶层 / from 导入
FORBIDDEN_MODULES = ("sqlalchemy", "alembic")

_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
    re.MULTILINE,
)


def _module_of(match: re.Match) -> str:
    return (match.group(1) or match.group(2)).split(".")[0]


def _collect_py_under(base: Path) -> list[Path]:
    return sorted(p for p in base.rglob("*.py"))


class R19NoAlembicGuard(unittest.TestCase):
    def test_zkc_no_sqlalchemy_alembic_imports(self) -> None:
        """zkc/ 业务代码不得 import sqlalchemy / alembic（raw SQL + seam 不变量）。"""
        violations: list[str] = []
        for path in _collect_py_under(ZKC):
            text = path.read_text(encoding="utf-8")
            for m in _IMPORT_RE.finditer(text):
                mod = _module_of(m)
                if mod in FORBIDDEN_MODULES:
                    violations.append(f"{path.relative_to(ROOT)}: {m.group(0).strip()}")
        self.assertEqual(
            violations,
            [],
            "R19 锁被破坏：zkc/ 出现 SQLAlchemy/Alembic import，需重新 open R19 并回迁 Alembic。\n"
            + "\n".join(violations),
        )

    def test_requirements_excludes_sqlalchemy_alembic(self) -> None:
        """依赖面不得声明 sqlalchemy / alembic（minimal-deps 第一性不变量）。"""
        declared = REQ.read_text(encoding="utf-8").lower()
        bad = [m for m in FORBIDDEN_MODULES if m in declared]
        self.assertEqual(
            bad,
            [],
            f"R19 锁被破坏：requirements.txt 声明了 {bad}，需重新 open R19。",
        )

    def test_migrate_is_migration_authority(self) -> None:
        """迁移权威 = 自研 zkc.migrate（非 Alembic）：暴露 CLI 入口且管理 0001 基线迁移。"""
        import zkc.migrate as m

        self.assertTrue(callable(m.main), "zkc.migrate.main 必须是可调用的 CLI 入口")
        discovered = m.discover()
        names = [name for name, _up, _down in discovered]
        self.assertTrue(names, "zkc.migrate 应至少发现 0001 基线迁移")
        self.assertTrue(
            any(n.startswith("0001") for n in names),
            "0001 基线迁移必须由 zkc.migrate 管理（而非 Alembic）",
        )


if __name__ == "__main__":
    unittest.main()
