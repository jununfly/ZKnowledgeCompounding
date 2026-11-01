"""ZKC · P5.1 存储层检索测试（切片B）。

memory 全跑（结构化 + 余弦召回 + list_all + citation_counts）；
Pg 集成用独立测试库（门控同 test_repository），验证 SQL 语义一致性
（ILIKE q / decay 区间 / order / 归档排除 / <=> kNN）。
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta
from uuid import uuid4

from zkc.repository import get_storage
from zkc.repository.models import Claim, ModelingArtifact, Node


def _node(track="dynamic", title="", content=None, decay=0.0, emb=None,
          archived=None, created=None):
    return Node(
        track=track, title=title, content=content, decay_score=decay,
        embedding=emb, archived_at=archived, created_at=created,
    )


DIM = 768  # 与 node.embedding vector(768) 对齐（spike 14）


def _vec(*vals):
    """补零到 768 维，memory/PG 两用。"""
    v = list(vals) + [0.0] * (DIM - len(vals))
    return v[:DIM]


class MemorySearchTest(unittest.TestCase):
    def setUp(self):
        from zkc.repository.memory import MemoryStorage

        self.store = MemoryStorage()  # 直接新建，内存实现无 clear_all
        base = datetime(2026, 11, 1, 12, 0, 0)
        self.n1 = self.store.nodes.save(_node(
            title="Rust 重写计划", content="brain engine trait",
            decay=0.2, emb=_vec(1.0, 0.0), created=base))
        self.n2 = self.store.nodes.save(_node(
            title="ZKC 复盘", content="衰减与注意力",
            decay=0.9, emb=_vec(0.9, 0.1),
            created=base + timedelta(days=1)))
        self.n3 = self.store.nodes.save(_node(
            title="已归档条目", content="archived stuff",
            decay=0.95, emb=_vec(0.0, 1.0), archived=base))
        self.n4 = self.store.nodes.save(_node(
            track="static", title="静态事实", decay=0.0,
            created=base - timedelta(days=1)))

    def test_search_q_substring_case_insensitive(self):
        hits = self.store.nodes.search(q="rust")
        self.assertEqual([n.id for n in hits], [self.n1.id])

    def test_search_track_filter_excludes_static(self):
        hits = self.store.nodes.search(track="dynamic")
        ids = {n.id for n in hits}
        self.assertIn(self.n1.id, ids)
        self.assertNotIn(self.n4.id, ids)

    def test_search_archived_excluded_by_default(self):
        hits = self.store.nodes.search()
        ids = {n.id for n in hits}
        self.assertNotIn(self.n3.id, ids)
        hits2 = self.store.nodes.search(include_archived=True)
        self.assertIn(self.n3.id, {n.id for n in hits2})

    def test_search_decay_range(self):
        hits = self.store.nodes.search(decay_min=0.5, decay_max=1.0)
        ids = {n.id for n in hits}
        self.assertEqual(ids, {self.n2.id})

    def test_search_order_created_desc(self):
        hits = self.store.nodes.search()
        self.assertEqual([n.id for n in hits],
                         [self.n2.id, self.n1.id, self.n4.id])

    def test_search_order_decay_desc(self):
        hits = self.store.nodes.search(order="decay_desc")
        self.assertEqual(hits[0].decay_score, 0.9)

    def test_search_invalid_order_rejected(self):
        with self.assertRaises(ValueError):
            self.store.nodes.search(order="title; DROP TABLE node")

    def test_search_limit(self):
        hits = self.store.nodes.search(limit=2)
        self.assertEqual(len(hits), 2)

    def test_embedding_knn_order_and_exclusion(self):
        hits = self.store.nodes.search_by_embedding([1.0, 0.0], k=3)
        # 已归档 n3 默认排除；n1 与查询向量同向 sim=1.0 排第一
        self.assertEqual(hits[0][0].id, self.n1.id)
        self.assertAlmostEqual(hits[0][1], 1.0, delta=1e-9)
        self.assertEqual(len(hits), 2)  # n1, n2（n3 归档、n4 无向量）
        sims = [s for _, s in hits]
        self.assertEqual(sims, sorted(sims, reverse=True))

    def test_embedding_knn_include_archived(self):
        hits = self.store.nodes.search_by_embedding([0.0, 1.0], k=5,
                                                    include_archived=True)
        self.assertIn(self.n3.id, [n.id for n, _ in hits])

    def test_claims_list_all_created_desc(self):
        c1 = self.store.claims.save(Claim(statement="早", created_at=datetime(2026, 10, 1)))
        c2 = self.store.claims.save(Claim(statement="晚", created_at=datetime(2026, 11, 1)))
        out = self.store.claims.list_all()
        self.assertEqual([c.id for c in out], [c2.id, c1.id])

    def test_artifacts_list_all(self):
        a = self.store.artifacts.save(ModelingArtifact(title="方法论A"))
        out = self.store.artifacts.list_all()
        self.assertEqual([x.id for x in out], [a.id])

    def test_citation_counts_memory_empty(self):
        self.assertEqual(self.store.citation_counts(), {})


def _run_pg_contract(store):
    """PG 侧核心断言（与 memory 同表，复用上述场景子集）。"""
    base = datetime(2026, 11, 1, 12, 0, 0)
    n1 = store.nodes.save(_node(title="Rust 重写计划", content="brain",
                                decay=0.2, emb=_vec(1.0, 0.0), created=base))
    n2 = store.nodes.save(_node(title="ZKC 复盘", decay=0.9,
                                emb=_vec(0.9, 0.1), created=base + timedelta(days=1)))
    n3 = store.nodes.save(_node(title="已归档", decay=0.95, emb=_vec(0.0, 1.0),
                                archived=base))
    # q 子串
    hits = store.nodes.search(q="rust")
    assert [n.id for n in hits] == [n1.id], "q 子串检索不符"
    # 归档默认排除
    ids = {n.id for n in store.nodes.search()}
    assert n3.id not in ids and {n1.id, n2.id} <= ids, "归档排除不符"
    # decay 区间
    ids = {n.id for n in store.nodes.search(decay_min=0.5)}
    assert ids == {n2.id}, "decay 区间不符"
    # order
    seq = [n.id for n in store.nodes.search()]
    assert seq == [n2.id, n1.id], "created_desc 排序不符"
    # kNN
    knn = store.nodes.search_by_embedding(_vec(1.0, 0.0), k=5)
    assert knn[0][0].id == n1.id, "kNN 首位不符"
    assert abs(knn[0][1] - 1.0) < 1e-6, "cosine sim 不符"
    assert n3.id not in [n.id for n, _ in knn], "kNN 应排除归档"
    # list_all + citation_counts
    c = store.claims.save(Claim(statement="s", created_at=base))
    assert [x.id for x in store.claims.list_all()] == [c.id]
    assert store.citation_counts() == {}
    a = store.artifacts.save(ModelingArtifact(title="m"))
    assert [x.id for x in store.artifacts.list_all()] == [a.id]


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgSearchTest(unittest.TestCase):
    TEST_DB = "zkc_search_test"

    @classmethod
    def setUpClass(cls):
        import psycopg
        from zkc import migrate

        cls._orig_dsn = os.environ.get("ZKC_PG_DSN")
        base_dsn = cls._orig_dsn or "postgresql://postgres:zkc@localhost:55433/zkc_dev"
        cls._pg = psycopg.connect(base_dsn.replace("/zkc_dev", "/postgres"),
                                  autocommit=True)
        cls._pg.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        cls._pg.execute(f'CREATE DATABASE "{cls.TEST_DB}"')
        cls._pg.close()
        migrate.apply_all(cls.TEST_DB)
        os.environ["ZKC_PG_DSN"] = base_dsn.replace("/zkc_dev", f"/{cls.TEST_DB}")

    def setUp(self):
        self.store = get_storage("pg")
        self.store.clear_all()

    def test_search_contract(self):
        _run_pg_contract(self.store)

    @classmethod
    def tearDownClass(cls):
        import psycopg

        cls._pg = psycopg.connect(
            (cls._orig_dsn or "postgresql://postgres:zkc@localhost:55433/zkc_dev"
             ).replace("/zkc_dev", "/postgres"), autocommit=True)
        cls._pg.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        cls._pg.close()
        if cls._orig_dsn is None:
            os.environ.pop("ZKC_PG_DSN", None)
        else:
            os.environ["ZKC_PG_DSN"] = cls._orig_dsn


if __name__ == "__main__":
    unittest.main()
