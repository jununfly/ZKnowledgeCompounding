"""Spike 05 tests: combine operator (RCS funnel + dual-layer + citation enforcement).

Funnel/citation mechanics run with deterministic stubs; persistence reuses the
spike-04 transform/produced_by cascade; the e2e test uses real Ollama (skips if down).
"""
import unittest

from models import ArtifactClaim, ModelingArtifact
from combine_op import CombineOperator, enforce_citations
from store import (
    apply_schema, connect, discard_transform, insert_node,
    persist_combine, revise_artifact,
)


def _truncate() -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE node, meta_claim, edge, context, transform, modeling_artifact CASCADE")


class Spike05Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apply_schema()

    def setUp(self):
        _truncate()


def _make_sources(cur, specs: list[tuple[str, str]]) -> list[dict]:
    return [
        {"id": insert_node(cur, t, c), "title": t, "content": c}
        for t, c in specs
    ]


class TestFunnel(Spike05Base):
    """RCS funnel: per-source conditioned summary -> score -> cap."""

    def _op(self, scores_by_title: dict[str, float], sources: list[dict],
            max_sources: int = 4) -> tuple[CombineOperator, list[str]]:
        summaries: list[str] = []

        def summarize(src, q):
            s = f"关于「{q}」：{src['title']} 的要点"
            summaries.append(s)
            return s

        def score(summary, q):
            title = summary.removeprefix("关于「" + q + "」：").removesuffix(" 的要点")
            return scores_by_title[title]

        def gen(prompt):
            # stub generation citing the real (stub-created) source ids
            return ModelingArtifact(
                title="stub artifact", kind="methodology",
                claims=[ArtifactClaim(statement="stub claim", level="pattern",
                                      confidence=0.5,
                                      evidence_ids=[s["id"] for s in sources])],
                local=[], global_insights=[],
            )

        return CombineOperator(summarize=summarize, score=score, generate=gen,
                               max_sources=max_sources), summaries

    def test_per_source_summary_is_conditioned(self):
        with connect() as conn, conn.cursor() as cur:
            sources = _make_sources(cur, [("A", "a"), ("B", "b")])
        op, summaries = self._op({"A": 0.5, "B": 0.6}, sources)
        result = op.combine("查询", sources)
        self.assertEqual(len(summaries), 2, "one summary per source (RCS step 1)")
        self.assertEqual(len(result["report"]["kept"]), 2)
        for k in result["report"]["kept"]:
            self.assertTrue(k["summary"].startswith("关于「查询」"),
                            "summary must be conditioned on the query")

    def test_source_cap_keeps_top_scored(self):
        with connect() as conn, conn.cursor() as cur:
            sources = _make_sources(cur, [(t, t) for t in ["S1", "S2", "S3", "S4", "S5", "S6"]])
        scores = {"S1": 0.9, "S2": 0.8, "S3": 0.3, "S4": 0.95, "S5": 0.2, "S6": 0.85}
        op, _ = self._op(scores, sources)
        result = op.combine("查询", sources)
        kept_titles = {k["title"] for k in result["report"]["kept"]}
        dropped_titles = {k["title"] for k in result["report"]["dropped"]}
        self.assertEqual(kept_titles, {"S4", "S1", "S6", "S2"}, "top-4 by score survive")
        self.assertEqual(dropped_titles, {"S3", "S5"}, "low scores dropped with report")


class TestCitations(Spike05Base):
    """Citation enforcement: hallucinated provenance must not survive."""

    S = {"s1", "s2", "s3"}

    def test_hallucinated_citation_dropped(self):
        artifact = {
            "title": "T", "kind": "methodology",
            "claims": [{"statement": "c1", "level": "pattern", "confidence": 0.7,
                        "evidence_ids": ["s1", "HALLUCINATED"]}],
        }
        out = enforce_citations(artifact, self.S)
        self.assertEqual(out["claims"][0]["evidence_ids"], ["s1"])
        self.assertEqual(out["evidence_refs"], ["s1"], "artifact refs recomputed from valid claims")

    def test_claim_without_valid_citation_dropped(self):
        artifact = {
            "title": "T", "kind": "mental_model",
            "claims": [
                {"statement": "bad", "level": "pattern", "confidence": 0.5,
                 "evidence_ids": ["fake1", "fake2"]},
                {"statement": "good", "level": "principle", "confidence": 0.8,
                 "evidence_ids": ["s2"]},
            ],
        }
        out = enforce_citations(artifact, self.S)
        self.assertEqual(len(out["claims"]), 1)
        self.assertEqual(out["claims"][0]["statement"], "good")
        self.assertEqual(out["_dropped_claims"], 1)

    def test_all_invalid_raises(self):
        artifact = {"title": "T", "kind": "tradeoff_map",
                    "claims": [{"statement": "x", "level": "pattern", "confidence": 0.5,
                                "evidence_ids": ["nope"]}]}
        with self.assertRaises(ValueError):
            enforce_citations(artifact, self.S)


class TestPersist(Spike05Base):
    """Combine persistence + cascade (reuses spike-04 transform mechanism)."""

    def _persist_one(self, cur) -> tuple[str, str, list[str]]:
        sources = _make_sources(cur, [("A", "a"), ("B", "b"), ("C", "c")])
        ids = [s["id"] for s in sources]
        artifact = {
            "title": "索引与一致性权衡模型", "kind": "tradeoff_map",
            "claims": [{"statement": "写入放大由索引数量决定", "level": "tradeoff",
                        "confidence": 0.7, "evidence_ids": ids[:2]}],
            "local": ["MVCC 一致性读", "二级索引放大写入"],
            "global": ["读路径与写路径的代价互相牵制"],
            "evidence_refs": ids[:2],
        }
        return (*persist_combine(cur, ids, artifact), ids)

    def test_persist_with_provenance_and_chain_edges(self):
        with connect() as conn, conn.cursor() as cur:
            t_id, a_id, ids = self._persist_one(cur)
            cur.execute(
                "SELECT kind, produced_by, evidence_refs FROM modeling_artifact WHERE id = %s",
                (a_id,),
            )
            kind, produced_by, refs = cur.fetchone()
            cur.execute("SELECT count(*) FROM edge WHERE produced_by = %s", (t_id,))
            n_edges = cur.fetchone()[0]
        self.assertEqual(kind, "tradeoff_map")
        self.assertIsNotNone(produced_by)
        self.assertEqual([str(u) for u in refs], ids[:2])
        self.assertEqual(n_edges, 2, "chain reverse-links across fused sources")

    def test_cascade_reverts_artifact_and_edges_only(self):
        with connect() as conn, conn.cursor() as cur:
            t_id, a_id, _ = self._persist_one(cur)
            cur.execute(
                "INSERT INTO meta_claim (statement, evidence_refs) VALUES (%s, %s) RETURNING id",
                ("human claim", ["00000000-0000-0000-0000-000000000000"]),
            )
            manual_claim = cur.fetchone()[0]
            stats = discard_transform(cur, t_id)
            cur.execute("SELECT count(*) FROM modeling_artifact WHERE id = %s", (a_id,))
            artifact_gone = cur.fetchone()[0] == 0
            cur.execute("SELECT count(*) FROM meta_claim WHERE id = %s", (manual_claim,))
            manual_alive = cur.fetchone()[0] == 1
        self.assertEqual(stats, {"artifacts_removed": 1, "edges_removed": 2})
        self.assertTrue(artifact_gone)
        self.assertTrue(manual_alive, "human-written rows must survive the revert")

    def test_artifact_revision_is_append_only(self):
        with connect() as conn, conn.cursor() as cur:
            t_id, a_id, _ = self._persist_one(cur)
            cur.execute("SELECT title FROM modeling_artifact WHERE id = %s", (a_id,))
            before = cur.fetchone()[0]
            new_id = revise_artifact(cur, a_id, {"title": "（人审修正）读写权衡模型"})
            cur.execute("SELECT title, tx_to FROM modeling_artifact WHERE id = %s", (a_id,))
            old_title, old_tx_to = cur.fetchone()
            cur.execute(
                "SELECT revises, tx_to, produced_by FROM modeling_artifact WHERE id = %s",
                (new_id,),
            )
            revises, new_tx_to, produced_by = cur.fetchone()
        self.assertEqual(before, old_title, "history row content never rewritten")
        self.assertIsNotNone(old_tx_to)
        self.assertEqual(str(revises), a_id)
        self.assertIsNone(new_tx_to)
        self.assertIsNotNone(produced_by, "revision keeps transform provenance")


def _ollama_up() -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3):
            return True
    except Exception:
        return False


@unittest.skipUnless(_ollama_up(), "Ollama not reachable on :11434")
class TestE2E(Spike05Base):
    """Real Ollama: 4 sources -> funnel -> cited artifact -> persist."""

    SOURCES = [
        ("MVCC 一致性读", "MVCC 用事务 ID 与快照实现一致性读，写不阻塞读，旧版本行需要后台清理。"),
        ("索引写入放大", "每个二级索引都会放大写入成本，写入越多索引维护代价越高。"),
        ("批量导入先删索引", "大批量导入前删掉二级索引、导完重建，比边写边维护快一个量级。"),
        ("长事务危害", "长事务阻止旧版本清理，导致表膨胀，拖垮读写性能。"),
    ]

    def test_combine_produces_cited_artifact(self):
        with connect() as conn, conn.cursor() as cur:
            sources = _make_sources(cur, self.SOURCES)
        ids = [s["id"] for s in sources]

        op = CombineOperator(max_sources=3)
        result = op.combine("PostgreSQL 写放大与一致性读如何互相牵制", sources)
        artifact = result["artifact"]

        self.assertGreaterEqual(len(artifact["claims"]), 1, "at least one cited claim")
        valid = set(ids)
        for c in artifact["claims"]:
            self.assertTrue(set(c["evidence_ids"]) <= valid,
                            f"claim citations must come from real sources: {c['evidence_ids']}")
        self.assertLessEqual(len(result["report"]["kept"]), 3, "source cap respected")

        with connect() as conn, conn.cursor() as cur:
            t_id, a_id = persist_combine(cur, result["report"]["kept_ids"], artifact)
            cur.execute("SELECT count(*) FROM modeling_artifact WHERE id = %s", (a_id,))
            self.assertEqual(cur.fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
