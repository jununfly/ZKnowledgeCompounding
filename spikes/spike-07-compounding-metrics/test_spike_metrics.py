import unittest

from store import apply_schema, connect, truncate_all, seed_scenario, insert_node, \
    insert_claim, insert_transform, insert_citation
from metrics import (connection_density, reuse_rate, methodology_output,
                     decay_controllability, compounding_factor, report,
                     ROT_THRESHOLD)


class TestCompoundingMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apply_schema()

    def setUp(self):
        with connect() as conn, conn.cursor() as cur:
            truncate_all(cur)
            self.ids = seed_scenario(cur)
            conn.commit()

    def tearDown(self):
        with connect() as conn, conn.cursor() as cur:
            truncate_all(cur)
            conn.commit()

    def test_connection_density(self):
        with connect() as conn, conn.cursor() as cur:
            self.assertAlmostEqual(connection_density(cur), 0.25, places=6)

    def test_reuse_rate(self):
        with connect() as conn, conn.cursor() as cur:
            rate, per = reuse_rate(cur)
            self.assertAlmostEqual(rate, 0.5, places=6)
            self.assertAlmostEqual(per, 0.5, places=6)

    def test_methodology_output(self):
        with connect() as conn, conn.cursor() as cur:
            self.assertEqual(methodology_output(cur), 1)

    def test_decay_controllability(self):
        with connect() as conn, conn.cursor() as cur:
            # d1 archived (handled), d2 leaked -> 1/2
            self.assertAlmostEqual(decay_controllability(cur), 0.5, places=6)

    def test_compounding_factor(self):
        with connect() as conn, conn.cursor() as cur:
            # (0.25 + 0.5 + 0.1 + 0.5) / 4 = 0.3375 ; method_target=10 -> mo_norm=0.1
            self.assertAlmostEqual(compounding_factor(cur), 0.3375, places=6)

    def test_report_shape(self):
        with connect() as conn, conn.cursor() as cur:
            r = report(cur)
            self.assertEqual(r.methodology_output, 1)
            self.assertAlmostEqual(r.compounding_factor, 0.3375, places=6)

    def test_empty_db_safe(self):
        with connect() as conn, conn.cursor() as cur:
            truncate_all(cur)
            conn.commit()
        with connect() as conn, conn.cursor() as cur:
            self.assertEqual(connection_density(cur), 0.0)
            rate, per = reuse_rate(cur)
            self.assertEqual((rate, per), (0.0, 0.0))
            self.assertEqual(methodology_output(cur), 0)
            self.assertEqual(decay_controllability(cur), 0.0)
            self.assertEqual(compounding_factor(cur), 0.0)

    def test_expired_referenced_counts_handled(self):
        # an expired dynamic node referenced in a claim's evidence_refs counts as handled
        with connect() as conn, conn.cursor() as cur:
            truncate_all(cur)
            s = insert_node(cur, "sr", "ref-src", "static")
            d = insert_node(cur, "dr", "expired referenced", "dynamic", decay_score=0.95)
            insert_claim(cur, "cr", "fact", [d])
            conn.commit()
        with connect() as conn, conn.cursor() as cur:
            self.assertAlmostEqual(decay_controllability(cur), 1.0, places=6)

    def test_citation_cascade_undo(self):
        # T6.2 instrumentation follows the produced_by cascade-undo invariant
        with connect() as conn, conn.cursor() as cur:
            s = insert_node(cur, "sx", "x", "static")
            c = insert_claim(cur, "cx", "fact", [s])
            t = insert_transform(cur, "distill")
            cid = insert_citation(cur, s, c, produced_by=t)
            cur.execute("SELECT count(*) FROM citation WHERE id = %s", (cid,))
            self.assertEqual(cur.fetchone()[0], 1)
            cur.execute("DELETE FROM transform WHERE id = %s", (t,))
            cur.execute("SELECT count(*) FROM citation WHERE id = %s", (cid,))
            self.assertEqual(cur.fetchone()[0], 0, "citation must cascade on transform delete")


if __name__ == "__main__":
    unittest.main()
