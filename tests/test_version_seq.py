"""OCC 版本号列（version_seq）验证（P1.2 遗留①+②解决）。

主张（两条上轮遗留已被解决）：
  ① 其他聚合（meta_claim / context）获与 node 同等的并发保护 —— 通过 upsert 的
     `WHERE version_seq = 调用方持有版本` 严格 OCC 实现（并发过期写被拒）。
  ② 引入 OCC / version_seq —— node 加 version_seq 列并随写自增（悲观锁 FOR UPDATE 兜底，
     last-writer-wins 不变）；update_decay/set_interval 支持显式 version_seq 严格 OCC；
     claim/context 的 upsert 默认严格 OCC。

测试矩阵：
  - Memory（总跑，无 DB 依赖）：双向版本自增 + 严格 OCC 冲突检测（memory 无悲观锁，OCC 即唯一护栏）。
  - Pg（skipUnless docker zkc-spike-pg）：同断言 + node.update_decay 的显式 version_seq 严格 OCC，
    以及 history() 镜像 version_seq。
"""
from __future__ import annotations

import os
import pathlib
import unittest
from uuid import UUID, uuid4

from zkc.repository.errors import ConcurrentModification
from zkc.repository.models import Claim, Context, Node, Track
from zkc.repository.memory import MemoryStorage

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"
ALL_UP_SQL = "\n".join(
    sorted(
        (MIGRATIONS_DIR / p).read_text()
        for p in [f.name for f in MIGRATIONS_DIR.glob("*.up.sql")]
    )
)
DEFAULT_DSN = os.environ.get("ZKC_PG_DSN", "postgresql://postgres:zkc@localhost:55433/zkc_dev")


class MemoryVersionSeqTest(unittest.TestCase):
    """内存 fake：无悲观锁，OCC 是唯一的并发护栏，故严格检测冲突。"""

    def test_node_version_increments_on_each_write(self):
        store = MemoryStorage()
        n = store.nodes.save(Node(title="v0", track=Track.DYNAMIC.value, decay_score=0.0))
        self.assertEqual(n.version_seq, 1)
        n.title = "v1"
        n = store.nodes.save(n)
        self.assertEqual(n.version_seq, 2)
        n.title = "v2"
        n = store.nodes.save(n)
        self.assertEqual(n.version_seq, 3)

    def test_node_occ_rejects_stale_write(self):
        store = MemoryStorage()
        n = store.nodes.save(Node(title="v0", track=Track.DYNAMIC.value, decay_score=0.0))
        n.title = "v1"
        n = store.nodes.save(n)  # v1 -> v2
        self.assertEqual(n.version_seq, 2)
        # 持过期版本（v1）再写 → 冲突
        stale = Node(title="stale", track=Track.DYNAMIC.value, decay_score=0.0,
                     id=n.id, version_seq=1)
        with self.assertRaises(ConcurrentModification):
            store.nodes.save(stale)
        # 当前态仍是 v2，未被过期写污染
        self.assertEqual(store.nodes.get(n.id).version_seq, 2)

    def test_claim_occ_rejects_stale_write(self):
        store = MemoryStorage()
        c = store.claims.save(Claim(statement="s0", evidence_refs=[uuid4()]))
        self.assertEqual(c.version_seq, 1)
        c.statement = "s1"
        c = store.claims.save(c)  # v2
        stale = Claim(statement="stale", evidence_refs=[uuid4()], id=c.id, version_seq=1)
        with self.assertRaises(ConcurrentModification):
            store.claims.save(stale)

    def test_context_occ_rejects_stale_write(self):
        store = MemoryStorage()
        ctx = store.contexts.save(Context(scope="self_loop", label="l0"))
        self.assertEqual(ctx.version_seq, 1)
        ctx.label = "l1"
        ctx = store.contexts.save(ctx)  # v2
        stale = Context(scope="self_loop", label="stale", id=ctx.id, version_seq=1)
        with self.assertRaises(ConcurrentModification):
            store.contexts.save(stale)


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 测试需要 docker zkc-spike-pg + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgVersionSeqTest(unittest.TestCase):
    TEST_DB = "zkc_version_seq_test"

    @classmethod
    def setUpClass(cls):
        cls._orig_dsn = os.environ.get("ZKC_PG_DSN")
        base = cls._orig_dsn or DEFAULT_DSN
        cls._admin = __import__("psycopg").connect(
            base.replace("/zkc_dev", "/postgres"), autocommit=True
        )
        cls._admin.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        cls._admin.execute(f'CREATE DATABASE "{cls.TEST_DB}"')
        cls._admin.close()
        cls._test_dsn = base.replace("/zkc_dev", f"/{cls.TEST_DB}")
        c = __import__("psycopg").connect(cls._test_dsn, autocommit=True)
        c.execute(ALL_UP_SQL)
        c.close()
        os.environ["ZKC_PG_DSN"] = cls._test_dsn

    @classmethod
    def tearDownClass(cls):
        drop_c = __import__("psycopg").connect(
            cls._test_dsn.replace(f"/{cls.TEST_DB}", "/postgres"), autocommit=True
        )
        drop_c.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        drop_c.close()
        if cls._orig_dsn is None:
            os.environ.pop("ZKC_PG_DSN", None)
        else:
            os.environ["ZKC_PG_DSN"] = cls._orig_dsn

    def setUp(self):
        import psycopg
        self._conn = psycopg.connect(self._test_dsn)
        cur = self._conn.cursor()
        for t in ("node_history", "node", "meta_claim", "context"):
            cur.execute(f"DELETE FROM public.{t}")
        self._conn.commit()
        cur.close()

    def tearDown(self):
        self._conn.close()

    def _roles(self):
        import psycopg
        from zkc.repository.pg import (
            PgClaimRepository,
            PgContextRepository,
            PgNodeRepository,
        )
        return (PgNodeRepository(self._conn), PgClaimRepository(self._conn),
                PgContextRepository(self._conn))

    def test_node_version_increments_and_history_records_it(self):
        node_repo, _, _ = self._roles()
        n = node_repo.save(Node(title="v0", track=Track.DYNAMIC.value, decay_score=0.0))
        self.assertEqual(n.version_seq, 1)
        n.title = "v1"
        n = node_repo.save(n)
        self.assertEqual(n.version_seq, 2)
        hist = node_repo.history(n.id)
        self.assertTrue(all(h.version_seq is not None for h in hist))
        # 历史版本 + 当前态的 version_seq 应单调递增
        seqs = [h.version_seq for h in hist]
        self.assertEqual(seqs, sorted(seqs))

    def test_node_update_decay_strict_occ(self):
        node_repo, _, _ = self._roles()
        n = node_repo.save(Node(title="v0", track=Track.DYNAMIC.value, decay_score=0.0))
        # 兼容调用（不传 version_seq）：仅自增，悲观锁兜底 → v2
        node_repo.update_decay(n.id, 0.5)
        self.assertEqual(node_repo.get(n.id).version_seq, 2)
        # 传过期版本（v1）→ 严格 OCC 冲突
        with self.assertRaises(ConcurrentModification):
            node_repo.update_decay(n.id, 0.6, version_seq=1)
        self._conn.rollback()  # 清理被中止的事务，后续断言才可用同一连接
        self.assertEqual(node_repo.get(n.id).version_seq, 2)  # 仍是 v2，未被污染
        # 传正确当前版本（v2）→ 成功推到 v3
        node_repo.update_decay(n.id, 0.7, version_seq=2)
        self.assertEqual(node_repo.get(n.id).version_seq, 3)

    def test_claim_strict_occ(self):
        _, claim_repo, _ = self._roles()
        c = claim_repo.save(Claim(statement="s0", evidence_refs=[uuid4()]))
        self.assertEqual(c.version_seq, 1)
        c.statement = "s1"
        c = claim_repo.save(c)  # v2
        stale = Claim(statement="stale", evidence_refs=[uuid4()], id=c.id, version_seq=1)
        with self.assertRaises(ConcurrentModification):
            claim_repo.save(stale)
        self._conn.rollback()
        self.assertEqual(claim_repo.get(c.id).version_seq, 2)

    def test_context_strict_occ(self):
        _, _, ctx_repo = self._roles()
        ctx = ctx_repo.save(Context(scope="self_loop", label="l0"))
        self.assertEqual(ctx.version_seq, 1)
        ctx.label = "l1"
        ctx = ctx_repo.save(ctx)  # v2
        stale = Context(scope="self_loop", label="stale", id=ctx.id, version_seq=1)
        with self.assertRaises(ConcurrentModification):
            ctx_repo.save(stale)
        self._conn.rollback()
        # context repo 协议无 get(by id)；改为用正确当前版本（v2）继续推进，
        # 验证当前态未被过期写污染（能正常推到 v3）
        ctx.label = "l2"
        ctx = ctx_repo.save(ctx)
        self.assertEqual(ctx.version_seq, 3)


if __name__ == "__main__":
    unittest.main()
