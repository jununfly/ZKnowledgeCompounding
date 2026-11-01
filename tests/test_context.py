"""zkc/context 装配算子（P3.4）TDD 测试：双实现契约 + PG 发现。

核心主张：seam 可替换 -> 同一份「行为契约」同时跑在内存 fake 与真实 Postgres 上。
assemble / 级联撤消 / 人审成员隔离 两个实现一致；discovery 是 pgvector 运算，仅 PG 验证。
"""
from __future__ import annotations

import os
import unittest
from datetime import date
from uuid import UUID, uuid4

from zkc import tuning
from zkc.context import ContextAssembler, ContextNamer, HigherDimProposal
from zkc.repository import get_storage
from zkc.repository.models import Node
from zkc.tuning import PLACEHOLDER

from zkc import migrate


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

    def test_propose_flags_uncalibrated_placeholder(self):
        # P3：占位阈值驱动的行为必须显式标注 calibrated=False（仍交人审，不自动当真理）
        store = get_storage("memory")
        asm = ContextAssembler(store)
        n1 = store.nodes.save(Node(track="dynamic", title="seed"))
        prop = asm.propose_higher_dim(n1.id, llm=_fake_llm)
        self.assertFalse(prop.calibrated)
        self.assertIn("未校准", prop.reason)

    def test_propose_calibrated_after_gate(self):
        # 经 calibrate() 门禁（≥14天+≥3饱和日）校准后，提议标注 calibrated=True
        store = get_storage("memory")
        asm = ContextAssembler(store)
        n1 = store.nodes.save(Node(track="dynamic", title="seed"))
        try:
            for name in ("CONTEXT_HIGHER_DIM_SIM_THRESHOLD", "CONTEXT_HIGHER_DIM_MIN_MEMBERS"):
                tuning.calibrate(name, tuning.get(name), date(2026, 12, 1),
                                 "14d+3sat", days_with_observation=14, saturated_days=3)
            prop = asm.propose_higher_dim(n1.id, llm=_fake_llm)
            self.assertTrue(prop.calibrated)
        finally:
            for name in ("CONTEXT_HIGHER_DIM_SIM_THRESHOLD", "CONTEXT_HIGHER_DIM_MIN_MEMBERS"):
                p = tuning.param(name)
                p.source = PLACEHOLDER
                p.calibrated_at = None
                p.history = []

    def test_propose_higher_dim_daily_caps_global(self):
        # P1：每日 sweep 跨种子限流（去重只防同种子，本函数防全库每日过量）
        store = get_storage("memory")
        asm = ContextAssembler(store)
        seeds = [uuid4() for _ in range(3)]

        def fake_propose(sid, k=5, llm=None, *, sim_threshold=None, min_members=None):
            return HigherDimProposal(seed_node_id=sid, neighbor_ids=[uuid4()],
                                    similarities=[0.9], suggested_title="x",
                                    would_create=True, reason="ok",
                                    existing_context_id=None, calibrated=True)

        asm.propose_higher_dim = fake_propose  # 绕过向量发现，隔离 sweep 逻辑
        day = date(2026, 11, 1)
        props, status = asm.propose_higher_dim_daily(seeds, day, max_per_day=2)
        self.assertEqual(status["cap"], 2)
        self.assertEqual(status["used"], 2)
        self.assertTrue(status["truncated"])
        self.assertTrue(props[0].would_create)
        self.assertTrue(props[1].would_create)
        self.assertFalse(props[2].would_create)
        self.assertIn("上限已达", props[2].reason)
        self.assertEqual(store.attention.count_proposals(day, "higher_dim"), 2)
        # 同日再 sweep：已达 cap，全部截断
        props2, status2 = asm.propose_higher_dim_daily(seeds, day, max_per_day=2)
        self.assertEqual(status2["used"], 2)
        self.assertFalse(any(p.would_create for p in props2))

    def test_naming_llm_and_fallback(self):
        namer = ContextNamer()
        # LLM 路径
        assert namer.name(["机器学习模型训练", "训练中的过拟合"], _fake_llm) == "聚合主题X"
        # 退化路径：确定性、非空、含条数
        fb = namer.name(["机器学习模型训练方法", "模型训练中的过拟合"], None)
        assert fb and "条）" in fb
        assert namer.name(["机器学习模型训练方法", "模型训练中的过拟合"], None) == fb

    def test_daily_excludes_dismissed_seeds(self):
        # 当日被忽略的种子须被 sweep 跳过（dismiss 真生效，否则每刷新都再提议）
        store = get_storage("memory")
        asm = ContextAssembler(store)
        sid = uuid4()
        day = date(2026, 11, 3)
        # 模拟人工忽略：落 proposal_log(kind='higher_dim_dismissed', seed_id)
        store.attention.record_proposal(day, "higher_dim_dismissed", sid)
        self.assertIn(sid, store.attention.dismissed_seed_ids(day))
        props, status = asm.propose_higher_dim_daily(
            [sid], day, max_per_day=5, excluded=store.attention.dismissed_seed_ids(day))
        self.assertEqual(len(props), 1)
        self.assertFalse(props[0].would_create)
        self.assertIn("已被人工忽略", props[0].reason)
        # 未创建的被忽略种子不占每日额度
        self.assertEqual(store.attention.count_proposals(day, "higher_dim"), 0)


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
        # 经迁移权威按文件 apply（不再拼接 SQL）
        migrate.apply_all(cls.TEST_DB)
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

    def test_propose_higher_dim_daily_caps_across_seeds(self):
        # P1：PG 下验证跨种子每日限流 + proposal_log 持久化（去重只防同种子，本函数防全库过量）
        seed = self.store.nodes.save(
            Node(track="dynamic", title="种子主题", embedding=_vec_close(768, 0)))
        self.store.nodes.save(
            Node(track="dynamic", title="近邻A", embedding=_vec_close(768, 0, 1, 0.01)))
        self.store.nodes.save(
            Node(track="dynamic", title="近邻B", embedding=_vec_close(768, 0, 2, 0.02)))
        other_seed = self.store.nodes.save(
            Node(track="dynamic", title="另一个种子", embedding=_vec_close(768, 3)))
        self.store.nodes.save(
            Node(track="dynamic", title="os近邻A", embedding=_vec_close(768, 3, 4, 0.01)))
        self.store.nodes.save(
            Node(track="dynamic", title="os近邻B", embedding=_vec_close(768, 3, 5, 0.02)))

        day = date(2026, 11, 2)
        props, status = self.asm.propose_higher_dim_daily(
            [seed.id, other_seed.id], day, k=5, llm=_fake_llm, max_per_day=1)
        created = [p for p in props if p.would_create]
        self.assertEqual(len(created), 1, "cap=1 -> 仅首条种子可创建")
        self.assertEqual(status["used"], 1)
        self.assertTrue(status["truncated"])
        self.assertEqual(self.store.attention.count_proposals(day, "higher_dim"), 1)

    def test_daily_excludes_dismissed_seeds_pg(self):
        # PG 路径：dismiss 落 proposal_log(seed_id)，dismissed_seed_ids 当日返回该种子
        # seed_id 有 FK 到 node，必须用真实存在的节点 id（否则 ForeignKeyViolation）
        day = date(2026, 11, 4)
        seed = self.store.nodes.save(Node(
            track="dynamic", title="dismiss-seed", decay_score=0.0,
            embedding=_vec_close(768, 1, 1, 0.0)))
        sid = seed.id
        self.store.attention.record_proposal(day, "higher_dim_dismissed", sid)
        self.assertIn(sid, self.store.attention.dismissed_seed_ids(day))
        # 创建型提议也带 seed_id 但不进 dismissed 集
        self.store.attention.record_proposal(day, "higher_dim", sid)
        self.assertEqual(self.store.attention.count_proposals(day, "higher_dim"), 1)
        self.assertIn(sid, self.store.attention.dismissed_seed_ids(day))

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
