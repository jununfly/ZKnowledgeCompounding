"""S5 · 真删执行 + 独立审计红→绿。

真删 = 过闸门(S4) → 删 node 行 → FK CASCADE 清关联（node_history/edge/
context_member/citation/interval_adjustment/proposal_log/review_queue）→
写独立 purge 审计（node_id 无 FK、不记 content）。attention_observation 按天聚合不回退。

PG 真库验证 CASCADE（核心风险）；memory 验证应用层等价清理。
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from zkc.repository import get_storage
from zkc.repository.models import Node
from zkc.purge import purge_node
from zkc.tombstone import mark_tombstone
from zkc import migrate


class MemoryPurgeTest(unittest.TestCase):
    def test_purge_removes_node_and_audits(self):
        store = get_storage("memory")
        now = datetime.now(timezone.utc)
        n = store.nodes.save(Node(track="dynamic", title="to-purge", decay_score=1.0))
        mark_tombstone(store, n.id, operator="zj", at=now - timedelta(days=8))
        res = purge_node(store, n.id, operator="zj", at=now)
        self.assertTrue(res["purged"])
        self.assertIsNone(store.nodes.get(n.id))
        audits = store.list_deletion_audit(n.id)
        self.assertEqual([a.event_kind for a in audits], ["tombstone", "purge"])
        purge = audits[-1]
        self.assertEqual(purge.ttl_days, 7)
        self.assertEqual(purge.operator, "zj")
        self.assertEqual(purge.title, "to-purge")
        self.assertNotIn("content", purge.__dict__)

    def test_purge_blocked_by_reference(self):
        store = get_storage("memory")
        now = datetime.now(timezone.utc)
        n = store.nodes.save(Node(track="dynamic", title="ref'd", decay_score=1.0))
        mark_tombstone(store, n.id, operator="zj", at=now - timedelta(days=8))
        store.claims.save(__import__("zkc.repository.models", fromlist=["Claim"]).Claim(
            statement="s", evidence_refs=[n.id]))
        res = purge_node(store, n.id, operator="zj", at=now)
        self.assertFalse(res["purged"])
        self.assertIsNotNone(store.nodes.get(n.id), "被引用不得真删")


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 真库 CASCADE 验证需要 docker zkc-spike-pg",
)
class PgPurgeCascadeTest(unittest.TestCase):
    TEST_DB = "zkc_purge_exec_test"

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls._orig_dsn = os.environ.get("ZKC_PG_DSN")
        base = cls._orig_dsn or "postgresql://postgres:zkc@localhost:55433/zkc_dev"
        cls._pg = psycopg.connect(base.replace("/zkc_dev", "/postgres"), autocommit=True)
        cls._pg.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        cls._pg.execute(f'CREATE DATABASE "{cls.TEST_DB}"')
        cls._pg.close()
        cls._test_dsn = base.replace("/zkc_dev", f"/{cls.TEST_DB}")
        migrate.apply_all(cls.TEST_DB)
        os.environ["ZKC_PG_DSN"] = cls._test_dsn

    def setUp(self):
        self.store = get_storage("pg")
        self.store.clear_all()
        self.now = datetime.now(timezone.utc)

    def _seed_node(self):
        n = self.store.nodes.save(Node(track="dynamic", title="pg-purge", decay_score=1.0))
        mark_tombstone(self.store, n.id, operator="zj", at=self.now - timedelta(days=8))
        return n

    def test_cascade_clears_history_but_attention_survives(self):
        from zkc.repository.connection import connect
        n = self._seed_node()
        c = connect(); cur = c.cursor()
        cur.execute("SELECT count(*) FROM public.node_history WHERE id=%s", (n.id,))
        self.assertGreater(cur.fetchone()[0], 0, "前置：应有版本历史")

        # attention_observation 是全局按天聚合，删 node 不回退
        from zkc.repository.models import AttentionObservation
        self.store.attention.record_observation(AttentionObservation(
            day=(self.now - timedelta(days=1)).date(),
            pushed=3, completed=2, queue_remaining=1, labeled_completed=1))
        before = self.store.attention.get((self.now - timedelta(days=1)).date())
        self.assertIsNotNone(before)

        res = purge_node(self.store, n.id, operator="zj", at=self.now)
        self.assertTrue(res["purged"])
        cur.execute("SELECT count(*) FROM public.node WHERE id=%s", (n.id,))
        self.assertEqual(cur.fetchone()[0], 0)
        cur.execute("SELECT count(*) FROM public.node_history WHERE id=%s", (n.id,))
        self.assertEqual(cur.fetchone()[0], 0, "node_history 应随 CASCADE 清")
        after = self.store.attention.get((self.now - timedelta(days=1)).date())
        self.assertEqual(after.completed, 2, "attention 观测不回退")
        audits = self.store.list_deletion_audit(n.id)
        self.assertEqual([a.event_kind for a in audits], ["tombstone", "purge"])
        c.close()

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


if __name__ == "__main__":
    unittest.main()
