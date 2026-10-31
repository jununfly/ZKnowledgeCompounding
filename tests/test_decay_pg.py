"""zkc/decay 真实 PG 集成实测（P1.3：「decay 触发器实测」）。

在真实 Postgres（zkc-spike-pg）上的临时库跑全部迁移（0001/0002/0003），验证：
1. refresh_decay 把动态轨 decay_score 按线性模型写回；静态轨恒 0 且不被写。
2. （c2 决议 A-1a）refresh 只重写派生的 decay_score，不写 node_history、不 bump
   tx_from —— 历史只存事实演进，派生量不进双时态版本链。
3. list_due_for_review 阈值来自 tuning（SURFACE_THRESHOLD），到期+超阈才入选。

需要 docker + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过。
"""
from __future__ import annotations

import os
import pathlib
import unittest
from datetime import datetime, timedelta
from uuid import uuid4

from zkc.decay import refresh_decay
from zkc.repository import get_storage
from zkc.repository.models import Node

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"
ALL_UP_SQL = "\n".join(
    sorted((MIGRATIONS_DIR / p).read_text() for p in [f.name for f in MIGRATIONS_DIR.glob("*.up.sql")])
)


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgDecayTest(unittest.TestCase):
    TEST_DB = "zkc_decay_test"

    @classmethod
    def setUpClass(cls):
        import psycopg

        cls._orig_dsn = os.environ.get("ZKC_PG_DSN")
        base_dsn = cls._orig_dsn or "postgresql://postgres:zkc@localhost:55433/zkc_dev"
        cls._pg = psycopg.connect(base_dsn.replace("/zkc_dev", "/postgres"), autocommit=True)
        cls._pg.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        cls._pg.execute(f'CREATE DATABASE "{cls.TEST_DB}"')
        cls._pg.close()
        cls._test_dsn = base_dsn.replace("/zkc_dev", f"/{cls.TEST_DB}")
        c = psycopg.connect(cls._test_dsn, autocommit=True)
        c.execute(ALL_UP_SQL)
        c.close()
        os.environ["ZKC_PG_DSN"] = cls._test_dsn

    @classmethod
    def tearDownClass(cls):
        import psycopg

        c = psycopg.connect(cls._test_dsn.replace(f"/{cls.TEST_DB}", "/postgres"), autocommit=True)
        c.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        c.close()
        if cls._orig_dsn is None:
            os.environ.pop("ZKC_PG_DSN", None)
        else:
            os.environ["ZKC_PG_DSN"] = cls._orig_dsn

    def setUp(self):
        self.store = get_storage("pg")
        self.store.clear_all()
        self.now = datetime(2026, 6, 1, 12, 0, 0)

    def test_refresh_writes_linear_score(self):
        dyn = self.store.nodes.save(Node(
            track="dynamic", title="dyn",
            review_interval=timedelta(days=10),
            last_reviewed_at=self.now - timedelta(days=5),
            decay_score=0.0,
        ))
        static = self.store.nodes.save(Node(
            track="static", title="static",
            review_interval=timedelta(days=10),
            last_reviewed_at=self.now - timedelta(days=5),
            decay_score=0.0,
        ))
        n = refresh_decay(self.store.nodes, self.now)
        self.assertEqual(n, 1)  # 仅 dynamic 被刷新
        self.assertAlmostEqual(self.store.nodes.get(dyn.id).decay_score, 0.5)  # 5/10
        self.assertEqual(self.store.nodes.get(static.id).decay_score, 0.0)

    def test_refresh_is_derived_only_not_versioned(self):
        # c2 决议 A-1a（2026-10-31）：decay_score 是 compute_decay_score 的派生投影，
        # refresh 只重写该派生列，不写 node_history、不 bump tx_from（tx_from 始终标记
        # 「上次事实变更」）。历史膨胀与溯源噪声因此被杜绝。
        dyn = self.store.nodes.save(Node(
            track="dynamic", title="v0",
            review_interval=timedelta(days=10),
            last_reviewed_at=self.now - timedelta(days=5),
            decay_score=0.0,
        ))
        before = len(self.store.nodes.history(dyn.id))
        before_tx_from = self.store.nodes.get(dyn.id).tx_from
        refresh_decay(self.store.nodes, self.now)
        after = len(self.store.nodes.history(dyn.id))
        # refresh 调 update_decay → 不产生历史快照（派生量不进双时态版本链）
        self.assertEqual(after, before)
        # 派生量照算不误：仍按线性刷新到 0.5（5/10）
        self.assertAlmostEqual(self.store.nodes.get(dyn.id).decay_score, 0.5)
        # tx_from 不 bump（始终标记「上次事实变更」，而非派生重算）
        self.assertEqual(self.store.nodes.get(dyn.id).tx_from, before_tx_from)
        # 当前态仍是最后一次写，tx_to 为 NULL
        self.assertIsNone(self.store.nodes.get(dyn.id).tx_to)

    def test_list_due_for_review_uses_tuning_threshold_and_due(self):
        # 到期且 decay>=SURFACE(0.6)：last_reviewed_at = now-12d, interval=10d
        due = self.store.nodes.save(Node(
            track="dynamic", title="due",
            review_interval=timedelta(days=10),
            last_reviewed_at=self.now - timedelta(days=12),
            decay_score=0.0,
        ))
        refresh_decay(self.store.nodes, self.now)  # 写回 12/10 = 1.0
        # 未到期（虽 decay 高）
        not_due = self.store.nodes.save(Node(
            track="dynamic", title="notdue",
            review_interval=timedelta(days=10),
            last_reviewed_at=self.now - timedelta(days=8),
            decay_score=1.0,
        ))
        due_list = self.store.nodes.list_due_for_review(self.now)
        ids = {n.id for n in due_list}
        self.assertIn(due.id, ids)
        self.assertNotIn(not_due.id, ids)


if __name__ == "__main__":
    unittest.main()
