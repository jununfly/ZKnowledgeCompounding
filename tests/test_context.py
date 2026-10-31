"""zkc/context 装配算子（P3.4）TDD 测试：双实现契约 + PG 发现。

核心主张：seam 可替换 -> 同一份「行为契约」同时跑在内存 fake 与真实 Postgres 上。
assemble / 级联撤消 / 人审成员隔离 两个实现一致；discovery 是 pgvector 运算，仅 PG 验证。
"""
from __future__ import annotations

import os
import pathlib
import unittest
from uuid import UUID, uuid4

from zkc.context import ContextAssembler
from zkc.repository import get_storage
from zkc.repository.models import Node

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"
ALL_UP_SQL = "\n".join(
    sorted(
        (MIGRATIONS_DIR / p).read_text()
        for p in [f.name for f in MIGRATIONS_DIR.glob("*.up.sql")]
    )
)


def run_assembly_contract(store, asm) -> None:
    """同一份行为契约，内存 fake 与 PG 都应满足。无断言失败即通过。"""
    n1 = store.nodes.save(Node(track="dynamic", title="n1"))
    n2 = store.nodes.save(Node(track="dynamic", title="n2"))
    n3 = store.nodes.save(Node(track="dynamic", title="n3"))

    # ---- assemble：一 transform -> 一 context + members（均带 produced_by）----
    cid, tid = asm.assemble("higher_dim", [n1.id, n2.id], title="ctx")
    assert isinstance(cid, UUID) and isinstance(tid, UUID)
    assert set(store.contexts.list_members(cid)) == {n1.id, n2.id}
    assert store.contexts.list_for_node(n1.id)[0].id == cid

    # ---- 人审成员隔离：可单独增删，不随 transform 级联撤 ----
    asm.add_human_member(cid, n3.id)
    assert set(store.contexts.list_members(cid)) == {n1.id, n2.id, n3.id}
    asm.remove_human_member(cid, n3.id)
    assert set(store.contexts.list_members(cid)) == {n1.id, n2.id}

    # ---- 级联撤消：删 transform -> context + 全部 members 消失 ----
    removed = asm.revert(tid)
    assert removed == 1, removed
    assert store.contexts.list_members(cid) == []
    assert store.contexts.list_for_node(n1.id) == []

    # ---- 越界 scope 必须拒绝 ----
    try:
        asm.assemble("bogus", [n1.id])
        assert False, "expected ValueError for invalid scope"
    except ValueError:
        pass


def _vec(ndim: int, one_hot: int) -> list[float]:
    v = [0.0] * ndim
    v[one_hot] = 1.0
    return v


class MemoryContextTest(unittest.TestCase):
    def test_assembly_contract(self):
        store = get_storage("memory")
        asm = ContextAssembler(store)
        run_assembly_contract(store, asm)

    def test_discover_returns_empty_on_memory_fake(self):
        store = get_storage("memory")
        asm = ContextAssembler(store)
        n1 = store.nodes.save(Node(track="dynamic", title="seed"))
        assert asm.discover(n1.id) == []


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgContextTest(unittest.TestCase):
    TEST_DB = "zkc_ctx_test"

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

    def setUp(self):
        self.store = get_storage("pg")
        self.store.clear_all()
        self.asm = ContextAssembler(self.store)

    def test_assembly_contract(self):
        run_assembly_contract(self.store, self.asm)

    def test_discovery_returns_nearest_excluding_seed(self):
        # 两个正交向量：seed=[1,0,...], other=[0,1,...] -> cosine=0，seed 自身被排除
        seed = self.store.nodes.save(
            Node(track="dynamic", title="seed", embedding=_vec(768, 0))
        )
        other = self.store.nodes.save(
            Node(track="dynamic", title="other", embedding=_vec(768, 1))
        )
        results = self.asm.discover(seed.id, k=5)
        ids = {r["id"] for r in results}
        assert other.id in ids, ids
        assert seed.id not in ids, ids

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
