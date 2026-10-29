"""Spike 04 tests: distill loop with the two §6.4 acceptance constraints.

  C1: bitemporal writes are append-only (history rows never rewritten, only closed).
  C2: every distillation product carries produced_by and reverts by cascade.

Graph tests need Ollama (qwen2.5-coder) on localhost:11434; they skip otherwise.
"""
import unittest
import uuid

from store import (
    apply_schema, connect, discard_transform, insert_node,
    persist_distill, revise_claim,
)


def _truncate() -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE node, meta_claim, edge, context, transform CASCADE")


class Spike04Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apply_schema()

    def setUp(self):
        _truncate()


class TestBitemporalAppendOnly(Spike04Base):
    """C1: revise = close old row (tx_to only) + insert new row."""

    def test_claim_revision_is_append_only(self):
        with connect() as conn, conn.cursor() as cur:
            s1 = insert_node(cur, "MVCC 原理", "MVCC 通过事务 ID 与快照实现一致性读")
            s2 = insert_node(cur, "索引与写入放大", "每多一个索引，写入都要付出额外代价")
            t_id, c_id = persist_distill(
                cur, [s1, s2],
                {"statement": "一致性读的代价由索引写入放大承担", "level": "tradeoff",
                 "confidence": 0.6},
            )

            # snapshot the history row BEFORE revision
            cur.execute(
                "SELECT statement, level, confidence, tx_to FROM meta_claim WHERE id = %s",
                (c_id,),
            )
            before = cur.fetchone()

            new_id = revise_claim(cur, c_id, {"statement": "（人审修正）一致性与吞吐的权衡点在索引数量"})

            cur.execute(
                "SELECT statement, level, confidence, tx_to FROM meta_claim WHERE id = %s",
                (c_id,),
            )
            after = cur.fetchone()
            cur.execute(
                "SELECT statement, revises, tx_to, produced_by FROM meta_claim WHERE id = %s",
                (new_id,),
            )
            new_row = cur.fetchone()

        # history row: content columns untouched, only tx_to closed (constraint 1)
        self.assertEqual(before[0], after[0], "history statement must never be rewritten")
        self.assertEqual(before[1], after[1])
        self.assertEqual(before[2], after[2])
        self.assertIsNone(before[3])
        self.assertIsNotNone(after[3], "old row must be closed via tx_to")

        # new row: fresh content + lineage back to the old version, same transform
        self.assertEqual(new_row[0], "（人审修正）一致性与吞吐的权衡点在索引数量")
        self.assertEqual(str(new_row[1]), c_id)
        self.assertIsNone(new_row[2])

    def test_only_one_current_version(self):
        with connect() as conn, conn.cursor() as cur:
            s1 = insert_node(cur, "A", "a")
            s2 = insert_node(cur, "B", "b")
            _, c1 = persist_distill(cur, [s1, s2], {"statement": "v1", "level": "pattern", "confidence": 0.5})
            c2 = revise_claim(cur, c1, {"statement": "v2"})
            c3 = revise_claim(cur, c2, {"statement": "v3"})
            cur.execute("SELECT count(*) FROM meta_claim WHERE tx_to IS NULL")
            current = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM meta_claim")
            total = cur.fetchone()[0]
        self.assertEqual(current, 1, "exactly one current version")
        self.assertEqual(total, 3, "full lineage retained (append-only)")


class TestProducedByCascade(Spike04Base):
    """C2: discard a transform -> ALL its products are reverted."""

    def test_cascade_reverts_all_products(self):
        with connect() as conn, conn.cursor() as cur:
            s1 = insert_node(cur, "S1", "s1")
            s2 = insert_node(cur, "S2", "s2")
            t_id, c_id = persist_distill(
                cur, [s1, s2],
                {"statement": "claim from transform", "level": "pattern", "confidence": 0.7},
            )
            # a manual (human) claim and edge that must SURVIVE the revert
            cur.execute(
                "INSERT INTO meta_claim (statement, evidence_refs) VALUES (%s, %s) RETURNING id",
                ("human-written claim", [s1]),
            )
            manual_claim = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO edge (src, dst, kind) VALUES (%s, %s, 'reverse_link') RETURNING id",
                (s1, s2),
            )
            manual_edge = cur.fetchone()[0]

            stats = discard_transform(cur, t_id)

        self.assertEqual(stats["claims_removed"], 1)
        self.assertEqual(stats["edges_removed"], 1)
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM meta_claim WHERE id = %s", (c_id,))
            self.assertEqual(cur.fetchone()[0], 0, "transform's claim must be gone")
            cur.execute("SELECT count(*) FROM edge WHERE produced_by = %s", (t_id,))
            self.assertEqual(cur.fetchone()[0], 0, "transform's edge must be gone")
            cur.execute("SELECT count(*) FROM meta_claim WHERE id = %s", (manual_claim,))
            self.assertEqual(cur.fetchone()[0], 1, "manual claim must survive")
            cur.execute("SELECT count(*) FROM edge WHERE id = %s", (manual_edge,))
            self.assertEqual(cur.fetchone()[0], 1, "manual edge must survive")

    def test_claim_requires_evidence(self):
        with connect() as conn, conn.cursor() as cur:
            with self.assertRaises(Exception):
                cur.execute(
                    "INSERT INTO meta_claim (statement, evidence_refs) VALUES (%s, %s)",
                    ("no evidence", None),
                )


def _ollama_up() -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3):
            return True
    except Exception:
        return False


@unittest.skipUnless(_ollama_up(), "Ollama not reachable on :11434")
class TestDistillLoop(Spike04Base):
    """Full loop: extract -> interrupt -> resume -> persist, checkpoint in PG."""

    SOURCES = [
        {"title": "MVCC 原理", "content": "MVCC 通过事务 ID 与快照实现一致性读，写不阻塞读。"},
        {"title": "索引写入放大", "content": "每个二级索引都会放大写入成本，索引越多写越慢。"},
    ]

    def _sources_with_ids(self, cur):
        ids = [insert_node(cur, s["title"], s["content"]) for s in self.SOURCES]
        return [{**s, "id": i} for s, i in zip(self.SOURCES, ids)], ids

    def test_interrupt_pauses_and_nothing_is_written(self):
        from distill_graph import distill_graph, start_distill

        with connect() as conn, conn.cursor() as cur:
            sources, ids = self._sources_with_ids(cur)

        with distill_graph() as g:
            result = start_distill(g, f"thread-{uuid.uuid4().hex[:8]}", sources)

        self.assertIn("__interrupt__", result, "graph must pause at human review")
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM meta_claim WHERE evidence_refs && %s", (ids,))
            self.assertEqual(cur.fetchone()[0], 0, "nothing persisted before approval")

    def test_approve_persists_with_provenance(self):
        from distill_graph import distill_graph, resume_distill, start_distill

        with connect() as conn, conn.cursor() as cur:
            sources, ids = self._sources_with_ids(cur)

        thread = f"thread-{uuid.uuid4().hex[:8]}"
        with distill_graph() as g:
            start_distill(g, thread, sources)
            result = resume_distill(g, thread, {"approved": True})

        self.assertIsNone(result.get("error"), f"unexpected error: {result.get('error')}")
        self.assertIsNotNone(result.get("claim_id"))
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT statement, level, produced_by, evidence_refs FROM meta_claim WHERE id = %s",
                (result["claim_id"],),
            )
            row = cur.fetchone()
        self.assertIsNotNone(row, "approved claim must be in PG")
        self.assertIsNotNone(row[2], "claim must carry produced_by (constraint 2)")
        self.assertEqual([str(u) for u in row[3]], ids, "evidence_refs = source node ids")
        self.assertTrue(row[0], "statement non-empty")

    def test_resume_with_human_edit_wins(self):
        from distill_graph import distill_graph, resume_distill, start_distill

        with connect() as conn, conn.cursor() as cur:
            sources, _ = self._sources_with_ids(cur)

        thread = f"thread-{uuid.uuid4().hex[:8]}"
        edited = "（人工修正）写放大是 MVCC 一致性读的隐性代价"
        with distill_graph() as g:
            start_distill(g, thread, sources)
            result = resume_distill(g, thread, {"approved": True, "edits": {"statement": edited}})

        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT statement FROM meta_claim WHERE id = %s", (result["claim_id"],))
            self.assertEqual(cur.fetchone()[0], edited, "human edit must override draft")

    def test_rejection_persists_nothing(self):
        from distill_graph import distill_graph, resume_distill, start_distill

        with connect() as conn, conn.cursor() as cur:
            sources, ids = self._sources_with_ids(cur)

        thread = f"thread-{uuid.uuid4().hex[:8]}"
        with distill_graph() as g:
            start_distill(g, thread, sources)
            result = resume_distill(g, thread, {"approved": False})

        self.assertEqual(result.get("claim_id"), None)
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM meta_claim WHERE evidence_refs && %s", (ids,))
            self.assertEqual(cur.fetchone()[0], 0, "rejected claim must not persist")

    def test_checkpoint_survives_new_connection(self):
        """Resume works from a FRESH PostgresSaver — checkpoint lives in PG, not memory."""
        from distill_graph import distill_graph, resume_distill, start_distill

        with connect() as conn, conn.cursor() as cur:
            sources, _ = self._sources_with_ids(cur)

        thread = f"thread-{uuid.uuid4().hex[:8]}"
        with distill_graph() as g1:                     # first connection: start
            start_distill(g1, thread, sources)
        with distill_graph() as g2:                     # NEW connection: resume
            result = resume_distill(g2, thread, {"approved": True})

        self.assertIsNotNone(result.get("claim_id"),
                             "resume across fresh checkpoint connection must work")


if __name__ == "__main__":
    unittest.main()
