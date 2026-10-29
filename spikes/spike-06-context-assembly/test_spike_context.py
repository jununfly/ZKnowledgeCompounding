"""Spike 06 tests: context topology assembly (T4.1 discovery + T4.2 membership).

Validates the design decision to model membership as a junction table (context_member)
carrying produced_by (cascade-undo) + weight, superseding architecture §5's uuid[] sketch.
"""
import unittest

import psycopg

from context_assembly import ContextAssembly
from store import apply_schema, connect, discard_assembly, insert_node, insert_node_vec


def _make_vec(cluster: int, dim: int = 1024, width: int = 64) -> str:
    v = [0.0] * dim
    for i in range(cluster * width, cluster * width + width):
        v[i] = 1.0
    return "[" + ",".join(str(x) for x in v) + "]"


def _truncate() -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE node, meta_claim, edge, context, context_member, transform, modeling_artifact CASCADE"
        )


class Spike06Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apply_schema()

    def setUp(self):
        _truncate()
        self.op = ContextAssembly()


class TestScopeEnforced(Spike06Base):
    def test_scope_enum_enforced(self):
        # base schema models scope as a Postgres ENUM `context_scope` (tighter than §5's text sketch)
        with connect() as conn, conn.cursor() as cur:
            with self.assertRaises(psycopg.errors.InvalidTextRepresentation):
                cur.execute("INSERT INTO context (scope) VALUES ('bogus')")


class TestCreate(Spike06Base):
    def test_create_self_loop_and_higher_dim(self):
        with connect() as conn, conn.cursor() as cur:
            sl = self.op.create_context(cur, "self_loop", "A 的自闭环")
            hd = self.op.create_context(cur, "higher_dim", "主题 X 更高维")
            cur.execute("SELECT scope, title FROM context WHERE id = ANY(%s)",
                        ([sl, hd],))
            rows = {(r[0], r[1]) for r in cur.fetchall()}
        self.assertEqual(rows, {("self_loop", "A 的自闭环"),
                               ("higher_dim", "主题 X 更高维")})


class TestAssemble(Spike06Base):
    def test_assemble_records_produced_by(self):
        with connect() as conn, conn.cursor() as cur:
            a, b, c = (insert_node(cur, t, t) for t in ("A", "B", "C"))
            c_id, t_id = self.op.assemble(cur, "higher_dim", [a, b, c], "主题 X")
            cur.execute(
                "SELECT produced_by FROM context_member WHERE context_id = %s", (c_id,))
            produced = {str(r[0]) for r in cur.fetchall()}
        self.assertEqual(produced, {t_id}, "every member row carries the assembly transform id")

    def test_bidirectional_query(self):
        with connect() as conn, conn.cursor() as cur:
            a, b = insert_node(cur, "A", "a"), insert_node(cur, "B", "b")
            c_id, _ = self.op.assemble(cur, "higher_dim", [a, b], "AB")
            ctxs = self.op.contexts_of(cur, a)
            members = self.op.members_of(cur, c_id)
        self.assertEqual([(str(r[0]), r[1], r[2]) for r in ctxs],
                         [(c_id, "higher_dim", "AB")])
        self.assertEqual({str(m[0]) for m in members}, {a, b})


class TestCascadeUndo(Spike06Base):
    def test_cascade_removes_context_and_members(self):
        with connect() as conn, conn.cursor() as cur:
            a, b = insert_node(cur, "A", "a"), insert_node(cur, "B", "b")
            c_id, t_id = self.op.assemble(cur, "higher_dim", [a, b], "AB")
            # unrelated human context must survive the revert
            human_ctx = self.op.create_context(cur, "higher_dim", "human")
            self.op.add_member_human(cur, human_ctx, a)
            stats = discard_assembly(cur, t_id)
            cur.execute("SELECT count(*) FROM context WHERE id = %s", (c_id,))
            gone = cur.fetchone()[0] == 0
            cur.execute("SELECT count(*) FROM context_member WHERE context_id = %s", (c_id,))
            members_gone = cur.fetchone()[0] == 0
            cur.execute("SELECT count(*) FROM context WHERE id = %s", (human_ctx,))
            human_alive = cur.fetchone()[0] == 1
        self.assertEqual(stats, {"contexts_removed": 1, "members_removed": 2})
        self.assertTrue(gone and members_gone)
        self.assertTrue(human_alive, "human context/members survive the transform revert")

    def test_self_loop_independent_of_higher_dim(self):
        with connect() as conn, conn.cursor() as cur:
            a, b, c = (insert_node(cur, t, t) for t in ("A", "B", "C"))
            _, t_self = self.op.assemble(cur, "self_loop", [a], "A 自闭环")
            c_hd, t_hd = self.op.assemble(cur, "higher_dim", [a, b, c], "ABC 更高维")
            discard_assembly(cur, t_self)
            ctxs = [str(r[0]) for r in self.op.contexts_of(cur, a)]
        self.assertEqual(ctxs, [c_hd], "higher_dim context survives self_loop revert")


class TestHumanMembership(Spike06Base):
    def test_human_member_removable_without_transform(self):
        with connect() as conn, conn.cursor() as cur:
            a = insert_node(cur, "A", "a")
            ctx = self.op.create_context(cur, "higher_dim", "human")
            self.op.add_member_human(cur, ctx, a, weight=0.5)
            self.op.remove_member_human(cur, ctx, a)
            members = self.op.members_of(cur, ctx)
        self.assertEqual(members, [], "human membership removable directly")

    def test_transform_member_protected_from_human_remove(self):
        with connect() as conn, conn.cursor() as cur:
            a, b = insert_node(cur, "A", "a"), insert_node(cur, "B", "b")
            c_id, _ = self.op.assemble(cur, "higher_dim", [a, b], "AB")
            self.op.remove_member_human(cur, c_id, a)  # produced_by NOT NULL -> no-op
            members = self.op.members_of(cur, c_id)
        self.assertEqual({str(m[0]) for m in members}, {a, b},
                         "transform-produced member not deletable via human path")


class TestDiscovery(Spike06Base):
    def test_discovery_clusters_by_embedding(self):
        with connect() as conn, conn.cursor() as cur:
            c0 = [insert_node_vec(cur, f"c0-{i}", "x", _make_vec(0)) for i in range(3)]
            c1 = [insert_node_vec(cur, f"c1-{i}", "x", _make_vec(1)) for i in range(3)]
            seed = c0[0]
            found = self.op.discover_higher_dim(cur, seed, k=5)
            found_ids = [str(r[0]) for r in found]
            sims = [r[2] for r in found]
        # seed is excluded; the other two same-cluster peers must precede every cross-cluster node
        c0_set, c1_set = set(c0), set(c1)
        self.assertEqual(set(found_ids), (c0_set | c1_set) - {seed}, "returns all non-seed nodes within k")
        c0_idx = [i for i, x in enumerate(found_ids) if x in c0_set]
        c1_idx = [i for i, x in enumerate(found_ids) if x in c1_set]
        self.assertTrue(max(c0_idx) < min(c1_idx), "all same-cluster peers precede cross-cluster")
        self.assertTrue(all(sims[i] >= sims[i + 1] for i in range(len(sims) - 1)),
                        "results ordered by descending similarity")
        self.assertGreater(sims[0], 0.99, "same-cluster similarity ~ 1.0")
        self.assertLessEqual(sims[-1], 0.01, "cross-cluster similarity near 0 (orthogonal via cosine)")


class TestWeighting(Spike06Base):
    def test_members_ordered_by_weight_desc(self):
        with connect() as conn, conn.cursor() as cur:
            a, b, c = (insert_node(cur, t, t) for t in ("A", "B", "C"))
            ctx = self.op.create_context(cur, "higher_dim", "weighted")
            self.op.add_member_human(cur, ctx, a, weight=0.3)
            self.op.add_member_human(cur, ctx, b, weight=0.9)
            self.op.add_member_human(cur, ctx, c, weight=0.6)
            members = self.op.members_of(cur, ctx)
        weights = [m[1] for m in members]
        self.assertEqual(weights, [0.9, 0.6, 0.3], "descending weight order")


if __name__ == "__main__":
    unittest.main(verbosity=2)
