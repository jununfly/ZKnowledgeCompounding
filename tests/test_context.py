"""zkc/context 装配算子（P3.4）TDD 测试：双实现契约 + PG 发现。

核心主张：seam 可替换 -> 同一份「行为契约」同时跑在内存 fake 与真实 Postgres 上。
assemble / 级联撤消 / 人审成员隔离 两个实现一致；discovery 是 pgvector 运算，仅 PG 验证。
"""
from __future__ import annotations

import os
import pathlib
import unittest
from uuid import UUID, uuid4

from zkc.context import ContextAssembler, ContextNamer, HigherDimProposal
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


def _vec_close(ndim: int, primary: int, secondary: int | None = None,
               secondary_val: float = 0.0) -> list[float]:
    """构造与 one-hot(primary) 高度相似的向量（用于跨阈值近邻模拟）。"""
    v = [0.0] * ndim
    v[primary] = 1.0 - secondary_val
    if secondary is not None:
        v[secondary] = secondary_val
    return v


def _fake_llm(prompt: str) -> str:
    """测试用 LLM：恒定返回确定性标题，免 Ollama/网络。"""
    return "聚合主题X"


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

    def test_propose_no_neighbors_would_not_create(self):
        store = get_storage("memory")
        asm = ContextAssembler(store)
        n1 = store.nodes.save(Node(track="dynamic", title="seed"))
        prop = asm.propose_higher_dim(n1.id, llm=_fake_llm)
        assert prop.neighbor_ids == []
        assert prop.would_create is False
        assert "近邻不足" in prop.reason
        # 闸门拒绝自动创建
        try:
            asm.create_higher_dim(prop)
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_naming_llm_and_fallback(self):
        namer = ContextNamer()
        # LLM 路径
        assert namer.name(["机器学习模型训练", "训练中的过拟合"], _fake_llm) == "聚合主题X"
        # 退化路径：确定性、非空、含条数
        fb = namer.name(["机器学习模型训练方法", "模型训练中的过拟合"], None)
        assert fb and "条）" in fb
        assert namer.name(["机器学习模型训练方法", "模型训练中的过拟合"], None) == fb


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

    def test_propose_passes_gates_then_create(self):
        seed = self.store.nodes.save(
            Node(track="dynamic", title="种子主题", embedding=_vec_close(768, 0)))
        na = self.store.nodes.save(
            Node(track="dynamic", title="近邻A", embedding=_vec_close(768, 0, 1, 0.01)))
        nb = self.store.nodes.save(
            Node(track="dynamic", title="近邻B", embedding=_vec_close(768, 0, 2, 0.02)))
        self.store.nodes.save(
            Node(track="dynamic", title="不相关", embedding=_vec_close(768, 1)))

        prop = self.asm.propose_higher_dim(seed.id, k=5, llm=_fake_llm)
        assert prop.would_create is True, prop.reason
        assert set(prop.neighbor_ids) == {na.id, nb.id}, prop.neighbor_ids
        assert prop.suggested_title == "聚合主题X"

        cid, tid = self.asm.create_higher_dim(prop)
        assert isinstance(cid, UUID) and isinstance(tid, UUID)
        assert set(self.store.contexts.list_members(cid)) == {seed.id, na.id, nb.id}
        ctx = self.store.contexts.list_for_node(seed.id)[0]
        assert ctx.scope == "higher_dim" and ctx.title == "聚合主题X"

        # 级联撤销
        assert self.asm.revert(tid) == 1
        assert self.store.contexts.list_members(cid) == []

    def test_propose_dedup_existing(self):
        seed = self.store.nodes.save(
            Node(track="dynamic", title="种子", embedding=_vec_close(768, 0)))
        self.store.nodes.save(
            Node(track="dynamic", title="近邻A", embedding=_vec_close(768, 0, 1, 0.01)))
        self.store.nodes.save(
            Node(track="dynamic", title="近邻B", embedding=_vec_close(768, 0, 2, 0.02)))

        prop = self.asm.propose_higher_dim(seed.id, llm=_fake_llm)
        assert prop.would_create is True
        cid, _ = self.asm.create_higher_dim(prop)

        prop2 = self.asm.propose_higher_dim(seed.id, llm=_fake_llm)
        assert prop2.would_create is False
        assert prop2.existing_context_id == cid
        assert "已存在" in prop2.reason

    def test_propose_fallback_naming_when_no_llm(self):
        seed = self.store.nodes.save(
            Node(track="dynamic", title="机器学习模型训练方法", embedding=_vec_close(768, 0)))
        self.store.nodes.save(
            Node(track="dynamic", title="近邻A", embedding=_vec_close(768, 0, 1, 0.01)))
        self.store.nodes.save(
            Node(track="dynamic", title="近邻B", embedding=_vec_close(768, 0, 2, 0.02)))

        prop = self.asm.propose_higher_dim(seed.id, llm=None)
        assert prop.would_create is True
        assert prop.suggested_title and "条）" in prop.suggested_title

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


class NamingTest(unittest.TestCase):
    """T4.1 命名（provider 无关，免 DB / 免 Ollama）。"""

    def test_llm_path_returns_clean_title(self):
        namer = ContextNamer()
        assert namer.name(["a", "b"], _fake_llm) == "聚合主题X"

    def test_fallback_deterministic_nonempty(self):
        namer = ContextNamer()
        a = namer.name(["机器学习模型训练方法", "模型训练中的过拟合"], None)
        b = namer.name(["机器学习模型训练方法", "模型训练中的过拟合"], None)
        assert a and a == b and "条）" in a

    def test_fallback_empty_input(self):
        namer = ContextNamer()
        assert "未命名" in namer.name([], None)

    def test_clean_title_strips_quotes_and_multiline(self):
        from zkc.context import _clean_title

        assert _clean_title('"标题"\n多余') == "标题"
        assert _clean_title("第一行\n第二行") == "第一行"


if __name__ == "__main__":
    unittest.main()
