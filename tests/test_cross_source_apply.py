"""1-5-3 结合算子落库接线单测（apply_combine + to_modeling_artifact + revert 联调）。

机制层验证（stub operator，不依赖模型）：
  1. apply_combine 把一个 combine 产物落成一条 modeling_artifact：
     evidence_refs UUID 化（⊆ store 真实节点）、produced_by 可空可回填、
     body 存完整 artifact dict（claims/local/global/methodology_steps）；
  2. 引用全崩塌（enforce_citations ValueError）→ applied=False、不落库（宁少勿错，
     发起式操作不入队人审——区别于 apply_distill 的到期自动分支）；
  3. 源节点校验 fail-fast：id 非 UUID / 节点不存在 → LLM 未被调用即返回 applied=False；
  4. kind 按 DB CHECK 三值预校验，非法 kind 不落库；
  5. revert_artifact 级联撤销联调：apply → 节点进「已捕获」28d → 撤销 → evidence
     节点级联 capture-loss 重算回 14d（有连接），审计留痕。
PG 真实集成（kind CHECK / uuid[] / 产出行回读）见同文件 PgApplyCombineTest。
"""
from __future__ import annotations

import os
import unittest
from uuid import UUID, uuid4

from zkc import cross_source as CS
from zkc import migrate
from zkc import scheduling as S
from zkc.cross_source import ArtifactClaim, CrossSourceArtifact, CrossSourceOperator
from zkc.repository import get_storage
from zkc.repository.models import Node


def _seed_sources(store, n=3):
    """建 n 个真实 dynamic 节点，返回算子形态的 source dict（id=str(uuid)）。"""
    out = []
    for i in range(n):
        nd = store.nodes.save(Node(title=f"src{i}", content=f"内容{i}",
                                   track="dynamic", decay_score=0.0))
        out.append({"id": str(nd.id), "title": nd.title, "content": nd.content})
    return out


def _ok_artifact(sources):
    """达标产物：1 条跨源断言（引 2 个来源）。"""
    a, b = sources[0]["id"], sources[1]["id"]
    return CrossSourceArtifact(
        title="技术决策时机方法论", kind="methodology",
        claims=[ArtifactClaim(statement="绕过与拖延共同指向：返工成本随时间超线性增长",
                              level="pattern", confidence=0.8, evidence_ids=[a, b])],
        local=["各来源实体要点"], global_insights=["跨来源模式"],
        methodology_steps=["步骤一"],
    )


def _operator(sources, artifact=None, generate_hook=None):
    art = artifact if artifact is not None else _ok_artifact(sources)

    def _gen(prompt):
        if generate_hook is not None:
            generate_hook(prompt)
        return art

    return CrossSourceOperator(
        summarize=lambda s, q: s["content"], score=lambda s, q: 0.5,
        generate=_gen, complete_on_shortfall=False,
    )


class ApplyCombineTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")
        self.sources = _seed_sources(self.store)

    def _days(self, node_id) -> float:
        return self.store.nodes.get(node_id).baseline_interval.total_seconds() / 86400.0

    # ------------------------------------------------------------------
    def test_apply_persists_artifact_with_uuid_evidence_and_produced_by(self):
        tf = self.store.record_transform("combine", {"query": "q"})
        res = CS.apply_combine(self.store, "q", self.sources,
                               _operator(self.sources), produced_by=tf)
        self.assertTrue(res["applied"], res)
        ma = self.store.artifacts.get(res["artifact_id"])
        self.assertIsNotNone(ma)
        self.assertEqual(ma.title, "技术决策时机方法论")
        self.assertEqual(ma.kind, "methodology")
        # evidence_refs UUID 化且 ⊆ 真实节点（enforce_citations 排序输出，比集合）
        self.assertEqual(sorted(ma.evidence_refs),
                         sorted([UUID(self.sources[0]["id"]),
                                 UUID(self.sources[1]["id"])]))
        self.assertEqual(ma.produced_by, tf)
        # body 存完整 artifact（claims/local/global/methodology_steps）
        self.assertEqual(len(ma.body["claims"]), 1)
        self.assertEqual(ma.body["methodology_steps"], ["步骤一"])
        # report 随返回（R14 埋点聚合入口）
        self.assertIn("completion_fired", res["report"])
        # 按 evidence 反查可达
        self.assertEqual(len(self.store.artifacts.list_by_evidence(ma.evidence_refs[0])), 1)

    def test_apply_produced_by_none_default(self):
        res = CS.apply_combine(self.store, "q", self.sources, _operator(self.sources))
        self.assertTrue(res["applied"])
        self.assertIsNone(self.store.artifacts.get(res["artifact_id"]).produced_by)

    def test_apply_citation_collapse_not_persisted(self):
        bad = CrossSourceArtifact(
            title="幻觉产物", kind="mental_model",
            claims=[ArtifactClaim(statement="无据断言", level="pattern", confidence=0.9,
                                  evidence_ids=["hallucinated-id"])],
        )
        res = CS.apply_combine(self.store, "q", self.sources, _operator(self.sources, bad))
        self.assertFalse(res["applied"])
        self.assertIn("citation", res["reason"].lower())
        self.assertEqual(self.store.artifacts.list_by_evidence(UUID(self.sources[0]["id"])), [])

    def test_apply_source_validation_fail_fast_llm_not_called(self):
        called = []

        def hook(prompt):
            called.append(prompt)

        mixed = self.sources + [{"id": "not-a-uuid", "title": "x", "content": "y"}]
        res = CS.apply_combine(self.store, "q", mixed, _operator(mixed, generate_hook=hook))
        self.assertFalse(res["applied"])
        self.assertEqual(called, [], "源校验失败不得调用 LLM")

        ghost = self.sources + [{"id": str(uuid4()), "title": "幽灵", "content": "z"}]
        res = CS.apply_combine(self.store, "q", ghost, _operator(ghost, generate_hook=hook))
        self.assertFalse(res["applied"])
        self.assertEqual(called, [], "节点不存在不得调用 LLM")

    def test_apply_rejects_invalid_kind(self):
        bad = _ok_artifact(self.sources).model_copy(update={"kind": "summary"})
        res = CS.apply_combine(self.store, "q", self.sources, _operator(self.sources, bad))
        self.assertFalse(res["applied"])
        self.assertIn("kind", res["reason"])

    def test_revert_artifact_cascades_capture_loss(self):
        # 两个 evidence 节点互有连接（撤销后走有连接 14d 而非孤儿 7d）
        a = self.store.nodes.get(UUID(self.sources[0]["id"]))
        b = self.store.nodes.get(UUID(self.sources[1]["id"]))
        self.store.edges.link(a.id, b.id, "derived_from")
        S.assign_baselines(self.store)
        self.assertEqual(self._days(a.id), S._t("BASELINE_CONNECTED_DAYS"))  # 尚无产物：未捕获

        res = CS.apply_combine(self.store, "q", self.sources, _operator(self.sources))
        self.assertTrue(res["applied"])
        S.assign_baselines(self.store)
        self.assertEqual(self._days(a.id), S._t("BASELINE_CAPTURED_DAYS"))  # 产物捕获 → 28d

        rev = CS.revert_artifact(self.store, res["artifact_id"], produced_by=None)
        self.assertTrue(rev["deleted"])
        self.assertIsNone(self.store.artifacts.get(res["artifact_id"]))
        rec = next(r for r in rev["recomputed"] if r["node_id"] == a.id)
        self.assertTrue(rec["applied"])
        self.assertIn("capture-loss", rec["reason"])
        self.assertEqual(self._days(a.id), S._t("BASELINE_CONNECTED_DAYS"))


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgApplyCombineTest(unittest.TestCase):
    TEST_DB = "zkc_cross_source_apply_test"

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

    @classmethod
    def tearDownClass(cls):
        import psycopg

        c = psycopg.connect(cls._test_dsn.replace(f"/{cls.TEST_DB}", "/postgres"),
                            autocommit=True)
        c.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        c.close()
        if cls._orig_dsn is None:
            os.environ.pop("ZKC_PG_DSN", None)
        else:
            os.environ["ZKC_PG_DSN"] = cls._orig_dsn

    def setUp(self):
        self.store = get_storage("pg")
        self.store.clear_all()
        self.sources = _seed_sources(self.store)

    def test_apply_persists_and_roundtrips(self):
        tf = self.store.record_transform("combine", {"query": "q"})
        res = CS.apply_combine(self.store, "q", self.sources,
                               _operator(self.sources), produced_by=tf)
        self.assertTrue(res["applied"], res)
        ma = self.store.artifacts.get(res["artifact_id"])
        self.assertEqual([str(e) for e in sorted(ma.evidence_refs)],
                         sorted([self.sources[0]["id"], self.sources[1]["id"]]))
        self.assertEqual(ma.produced_by, tf)
        self.assertEqual(len(ma.body["claims"]), 1)
        # PG uuid[] GIN 反查
        self.assertEqual(len(self.store.artifacts.list_by_evidence(ma.evidence_refs[0])), 1)

    def test_revert_cascades_on_pg(self):
        # 两节点互连（撤销后走有连接 14d 而非孤儿 7d），与 memory 侧联调同构
        a = self.store.nodes.get(UUID(self.sources[0]["id"]))
        b = self.store.nodes.get(UUID(self.sources[1]["id"]))
        self.store.edges.link(a.id, b.id, "derived_from")
        S.assign_baselines(self.store)
        self.assertEqual(
            self.store.nodes.get(a.id).baseline_interval.total_seconds() / 86400.0,
            S._t("BASELINE_CONNECTED_DAYS"))
        res = CS.apply_combine(self.store, "q", self.sources, _operator(self.sources))
        self.assertTrue(res["applied"])
        S.assign_baselines(self.store)
        self.assertEqual(
            self.store.nodes.get(a.id).baseline_interval.total_seconds() / 86400.0,
            S._t("BASELINE_CAPTURED_DAYS"))
        rev = CS.revert_artifact(self.store, res["artifact_id"])
        self.assertTrue(rev["deleted"])
        self.assertEqual(len(rev["evidence_node_ids"]), 2)
        rec = next(r for r in rev["recomputed"] if r["node_id"] == a.id)
        self.assertTrue(rec["applied"])
        self.assertIn("capture-loss", rec["reason"])
        self.assertEqual(
            self.store.nodes.get(a.id).baseline_interval.total_seconds() / 86400.0,
            S._t("BASELINE_CONNECTED_DAYS"))
        self.assertIsNone(self.store.artifacts.get(res["artifact_id"]))


if __name__ == "__main__":
    unittest.main()
