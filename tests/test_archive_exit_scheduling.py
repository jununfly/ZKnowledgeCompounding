"""D2 彻底收口：归档节点必须退出**整个**调度回路。

覆盖上一轮遗留的三处缺口：
  ① refresh_decay 仍触碰归档节点（写放大）；
  ② PG 侧只有静态源码断言，缺真实 PG 集成验证；
  ③ 契约未固化、无机械闸防回归（check_invariant 的 P3 谓词）。
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zkc import decay, migrate
from zkc.repository import get_storage
from zkc.repository.models import Node

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_invariant.py"
_spec = importlib.util.spec_from_file_location("zkc_ci_p3", SCRIPT)
ci = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ci)

NOW = datetime.now(timezone.utc)


def _due_node(title):
    return Node(
        title=title, track="dynamic", decay_score=1.0,
        review_interval=timedelta(days=1),
        last_reviewed_at=NOW - timedelta(days=3),
        created_at=NOW - timedelta(days=3),
    )


class MemoryRefreshDecayTest(unittest.TestCase):
    """纯内存：refresh_decay 不得触碰已归档节点。"""

    def test_refresh_decay_skips_archived(self):
        store = get_storage("memory")
        active = store.nodes.save(_due_node("活跃"))
        archived = store.nodes.save(_due_node("已归档"))
        store.nodes.archive(archived.id, NOW)

        calls = []
        original = store.nodes.update_decay

        def spy(*args, **kwargs):
            calls.append(args[0])
            return original(*args, **kwargs)

        store.nodes.update_decay = spy
        refreshed = decay.refresh_decay(store.nodes, NOW)
        self.assertEqual(refreshed, 1)
        self.assertEqual(calls, [active.id])

    def test_due_excludes_archived_after_refresh(self):
        store = get_storage("memory")
        active = store.nodes.save(_due_node("活跃"))
        archived = store.nodes.save(_due_node("已归档"))
        store.nodes.archive(archived.id, NOW)
        decay.refresh_decay(store.nodes, NOW)
        due = store.nodes.list_due_for_review(NOW)
        self.assertEqual([n.id for n in due], [active.id])


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg + psycopg",
)
class PgArchiveExitTest(unittest.TestCase):
    """真实 PG：SQL 过滤 + 维护扫描都必须排除归档节点。"""

    TEST_DB = "zkc_archive_exit_test"

    @classmethod
    def setUpClass(cls):
        import psycopg

        cls._orig_dsn = os.environ.get("ZKC_PG_DSN")
        base_dsn = cls._orig_dsn or "postgresql://postgres:zkc@localhost:55433/zkc_dev"
        conn = psycopg.connect(base_dsn.replace("/zkc_dev", "/postgres"), autocommit=True)
        conn.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{cls.TEST_DB}"')
        conn.close()
        cls._test_dsn = base_dsn.replace("/zkc_dev", f"/{cls.TEST_DB}")
        migrate.apply_all(cls.TEST_DB)
        os.environ["ZKC_PG_DSN"] = cls._test_dsn

    def setUp(self):
        self.store = get_storage("pg")
        self.store.clear_all()

    def test_archived_node_never_in_due_and_never_refreshed(self):
        active = self.store.nodes.save(_due_node("活跃条目"))
        archived = self.store.nodes.save(_due_node("归档条目"))
        self.store.nodes.archive(archived.id, NOW)

        due = self.store.nodes.list_due_for_review(NOW)
        self.assertEqual([n.id for n in due], [active.id], "PG SQL 必须排除已归档节点")

        calls = []
        original = self.store.nodes.update_decay

        def spy(*args, **kwargs):
            calls.append(args[0])
            return original(*args, **kwargs)

        self.store.nodes.update_decay = spy
        refreshed = decay.refresh_decay(self.store.nodes, NOW)
        self.assertEqual(refreshed, 1)
        self.assertEqual(calls, [active.id], "PG 衰减维护扫描不得触碰归档节点")

    @classmethod
    def tearDownClass(cls):
        import psycopg

        base = cls._test_dsn.replace(f"/{cls.TEST_DB}", "/postgres")
        conn = psycopg.connect(base, autocommit=True)
        conn.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        conn.close()
        if cls._orig_dsn is None:
            os.environ.pop("ZKC_PG_DSN", None)
        else:
            os.environ["ZKC_PG_DSN"] = cls._orig_dsn


# ---------------------------------------------------------------- P3 机械谓词
_GOOD_PG = '''class Pg:
    def list_due_for_review(self, as_of):
        return query("SELECT * FROM node WHERE decay_score >= 0.6 AND archived_at IS NULL")
'''
_BAD_PG = '''class Pg:
    def list_due_for_review(self, as_of):
        return query("SELECT * FROM node WHERE decay_score >= 0.6")
'''
_GOOD_MEM = '''class Mem:
    def list_due_for_review(self, as_of):
        for n in rows:
            if n.archived_at is not None:
                continue
'''
_GOOD_DECAY = '''def refresh_decay(repo, now):
    for node in repo.list_by_track("dynamic"):
        if getattr(node, "archived_at", None) is not None:
            continue
'''
_BAD_DECAY = '''def refresh_decay(repo, now):
    for node in repo.list_by_track("dynamic"):
        repo.update_decay(node.id, 0.5)
'''


def _p3_fixture(pg=None, mem=None, dec=None):
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    (root / "migrations").mkdir()
    (root / "src" / "zkc" / "repository").mkdir(parents=True)
    (root / "migrations" / "0001.up.sql").write_text(
        "CREATE TABLE public.meta_claim (evidence_refs uuid[] NOT NULL);", encoding="utf-8")
    (root / "src" / "zkc" / "tuning.py").write_text("VALUE = 1\n", encoding="utf-8")
    for name, body in (("repository/pg.py", pg), ("repository/memory.py", mem),
                       ("decay.py", dec)):
        if body is not None:
            (root / "src" / "zkc" / name).write_text(body, encoding="utf-8")
    return tmp, root


class P3InvariantTest(unittest.TestCase):
    def test_p3_clean_fixture_passes(self):
        tmp, root = _p3_fixture(_GOOD_PG, _GOOD_MEM, _GOOD_DECAY)
        with tmp:
            lines, violations = ci.evaluate(root)
            self.assertEqual(violations, 0, "\n".join(lines))
            self.assertTrue(any("P3" in line for line in lines))

    def test_p3_missing_pg_filter_is_detected(self):
        tmp, root = _p3_fixture(_BAD_PG, _GOOD_MEM, _GOOD_DECAY)
        with tmp:
            lines, violations = ci.evaluate(root)
            self.assertGreaterEqual(violations, 1)
            self.assertTrue(any("E_INVARIANT_ARCHIVE" in line for line in lines))

    def test_p3_refresh_decay_without_skip_is_detected(self):
        tmp, root = _p3_fixture(_GOOD_PG, _GOOD_MEM, _BAD_DECAY)
        with tmp:
            lines, violations = ci.evaluate(root)
            self.assertGreaterEqual(violations, 1)
            self.assertTrue(any("refresh_decay" in line for line in lines))

    def test_p3_real_repository_is_clean(self):
        lines, violations = ci.evaluate(ROOT)
        self.assertEqual(violations, 0, "\n".join(lines))
        self.assertTrue(any("[P3]" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
