"""S2 · 墓碑节点「全功能不可见」谓词（TDD 红→绿）。

对齐方案 §2 矩阵：墓碑节点对 search / search_by_embedding / list_due /
load_schedulable / discover_higher_dim / corpus / memory 后端全部不可见；
关键差异：**include_archived=True 只放开归档，不放开墓碑**（墓碑语义强于归档）。
discover_higher_dim 同时补归档过滤（阶段一查实的运行时污染漏洞）。
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone

from zkc.repository import get_storage
from zkc.repository.models import Node
from zkc.search import search
from zkc.corpus import select_corpus_nodes

from zkc import migrate


def _emb() -> list[float]:
    # PG 的 embedding 列是 vector(768)（R18 实测维度），假向量须同维。
    v = [0.0] * 768
    v[0] = 1.0
    return v


def _emb4096() -> list[float]:
    v = [0.0] * 4096
    v[0] = 1.0
    return v


class TombstoneVisibilityTest(unittest.TestCase):
    def setUp(self):
        # 子类（PG）可先设 self.store，此处不覆盖——双后端跑同一份契约。
        if not hasattr(self, "_store_injected"):
            self.store = get_storage("memory")
        self.now = datetime.now(timezone.utc)
        # 一个到期可用节点（due）+ 一个墓碑节点（同等条件，唯一差异=deleted_at）
        due = Node(
            track="dynamic", title="visible", decay_score=0.9, embedding=_emb(),
            embedding_4096=_emb4096(),
            review_interval=timedelta(days=1), last_reviewed_at=self.now - timedelta(days=10),
        )
        self.visible = self.store.nodes.save(due)
        tomb = Node(
            track="dynamic", title="tombstoned", decay_score=0.9, embedding=_emb(),
            embedding_4096=_emb4096(),
            review_interval=timedelta(days=1), last_reviewed_at=self.now - timedelta(days=10),
        )
        self.tomb = self.store.nodes.save(tomb)
        self.store.nodes.tombstone(self.tomb.id, self.now - timedelta(days=1))
        # 归档但非墓碑：用于验证 include_archived=True 只放开归档
        arch = Node(track="dynamic", title="archived", decay_score=0.9, embedding=_emb())
        self.arch = self.store.nodes.save(arch)
        self.store.nodes.archive(self.arch.id, self.now)

    def _ids(self, nodes) -> set:
        return {n.id for n in nodes}

    def test_search_default_excludes_tombstone(self):
        got = self.store.nodes.search()
        self.assertIn(self.visible.id, self._ids(got))
        self.assertNotIn(self.tomb.id, self._ids(got))

    def test_search_include_archived_does_not_expose_tombstone(self):
        got = self.store.nodes.search(include_archived=True)
        self.assertIn(self.arch.id, self._ids(got), "include_archived 应放开归档节点")
        self.assertNotIn(self.tomb.id, self._ids(got), "include_archived 不得放开墓碑节点")

    def test_search_by_embedding_excludes_tombstone(self):
        got = self.store.nodes.search_by_embedding(_emb(), k=10)
        self.assertNotIn(self.tomb.id, {n.id for n, _ in got})

    def test_search_by_embedding_include_archived_does_not_expose_tombstone(self):
        got = self.store.nodes.search_by_embedding(_emb(), k=10, include_archived=True)
        self.assertNotIn(self.tomb.id, {n.id for n, _ in got})

    def test_list_due_excludes_tombstone(self):
        got = self.store.nodes.list_due_for_review(self.now)
        self.assertIn(self.visible.id, self._ids(got))
        self.assertNotIn(self.tomb.id, self._ids(got))

    def test_load_schedulable_excludes_tombstone(self):
        got = self.store.load_schedulable()
        ids = {x.id for x in got}
        self.assertIn(self.visible.id, ids)
        self.assertNotIn(self.tomb.id, ids)

    def test_discover_higher_dim_excludes_tombstone_and_archived(self):
        # 以 visible 为种子，near 候选中混入选定的墓碑与归档节点
        tomb_near = self.store.nodes.save(Node(title="tomb-near", embedding_4096=_emb4096()))
        arch_near = self.store.nodes.save(Node(title="arch-near", embedding_4096=_emb4096()))
        self.store.nodes.tombstone(tomb_near.id, self.now - timedelta(days=1))
        self.store.nodes.archive(arch_near.id, self.now)
        got = self.store.discover_higher_dim(self.visible.id, k=10)
        ids = {str(g["id"]) for g in got}
        self.assertNotIn(str(self.tomb.id), ids)
        self.assertNotIn(str(tomb_near.id), ids, "discover 应排除墓碑节点（污染入口）")
        self.assertNotIn(str(arch_near.id), ids, "discover 应排除归档节点（阶段一漏洞）")

    def test_corpus_select_excludes_tombstone(self):
        # corpus 只收 decay>=1.0 + interval=86400 + last_reviewed=2026-11-01 的语料节点
        def corpus_node(title):
            return Node(
                track="dynamic", title=title, decay_score=1.0,
                review_interval=timedelta(days=1),
                last_reviewed_at=datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc),
            )
        keep = self.store.nodes.save(corpus_node("corpus-keep"))
        dead = self.store.nodes.save(corpus_node("corpus-tomb"))
        self.store.nodes.tombstone(dead.id, self.now - timedelta(days=1))
        got = select_corpus_nodes(self.store)
        ids = self._ids(got)
        self.assertIn(keep.id, ids, "同条件的非墓碑语料应被选中")
        self.assertNotIn(dead.id, ids, "墓碑语料不得进入 corpus")

    def test_search_facade_excludes_tombstone(self):
        # search.py 门面：结构化 + embedding 两路都不返回墓碑
        got = search(self.store, q="tombstoned", limit=10)
        self.assertNotIn(self.tomb.id, {h.node.id for h in got["hits"]})


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgTombstoneVisibilityTest(TombstoneVisibilityTest):
    """同一份可见性契约跑 PG：双后端行为一致（seam 不变式）。"""
    TEST_DB = "zkc_tombstone_vis_s2_test"

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
        migrate.apply_all(cls.TEST_DB)
        os.environ["ZKC_PG_DSN"] = cls._test_dsn

    def setUp(self):
        self.store = get_storage("pg")
        self.store.clear_all()
        self._store_injected = True
        super().setUp()

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
