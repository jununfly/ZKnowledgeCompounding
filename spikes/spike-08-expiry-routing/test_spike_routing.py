import unittest

from store import connect, apply_schema, truncate_all, seed_routing, ROT_THRESHOLD
from routing import (
    route_expired, apply_archive, enqueue_review, route_and_apply,
    DECISION_DISTILL, DECISION_ARCHIVE, DECISION_ABSTAIN, PRESSURE_DEFER,
)


class TestExpiryRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apply_schema()

    def setUp(self):
        with connect() as conn, conn.cursor() as cur:
            truncate_all(cur)
            self.s = seed_routing(cur)
            conn.commit()

    # 1. expired + connected + not captured -> DISTILL
    def test_expired_connected_uncaptured_distill(self):
        with connect() as conn, conn.cursor() as cur:
            d = route_expired(cur, self.s["d1"])
        self.assertTrue(d["routable"])
        self.assertEqual(d["action"], DECISION_DISTILL)

    # 2. expired + orphan -> ABSTAIN (never silently drop)
    def test_expired_orphan_abstain(self):
        with connect() as conn, conn.cursor() as cur:
            d = route_expired(cur, self.s["d2"])
        self.assertEqual(d["action"], DECISION_ABSTAIN)
        self.assertIn("orphan", d["reason"])

    # 3. expired + already captured -> ARCHIVE
    def test_expired_captured_archive(self):
        with connect() as conn, conn.cursor() as cur:
            d = route_expired(cur, self.s["d3"])
        self.assertEqual(d["action"], DECISION_ARCHIVE)

    # 4. attention pressure downgrades DISTILL -> ABSTAIN
    def test_pressure_downgrades_distill_to_abstain(self):
        with connect() as conn, conn.cursor() as cur:
            d = route_expired(cur, self.s["d1"], attention_pressure=0.9)
        self.assertEqual(d["action"], DECISION_ABSTAIN)
        self.assertGreaterEqual(PRESSURE_DEFER, 0.8)

    # 5. non-expired node is not routable
    def test_non_expired_not_routable(self):
        with connect() as conn, conn.cursor() as cur:
            d = route_expired(cur, self.s["d4"])
        self.assertFalse(d["routable"])
        self.assertIsNone(d["action"])

    # 6. apply_archive sets archived_at
    def test_apply_archive_sets_ts(self):
        with connect() as conn, conn.cursor() as cur:
            apply_archive(cur, self.s["d3"])
            cur.execute("SELECT archived_at IS NOT NULL FROM node WHERE id=%s",
                        (self.s["d3"],))
            self.assertTrue(cur.fetchone()[0])
            conn.commit()

    # 7. enqueue_review persists an open row
    def test_enqueue_review_persists(self):
        with connect() as conn, conn.cursor() as cur:
            rid = enqueue_review(cur, self.s["d2"], DECISION_ABSTAIN, "orphan")
            cur.execute("SELECT action, resolved FROM review_queue WHERE id=%s",
                        (rid,))
            action, resolved = cur.fetchone()
            self.assertEqual(action, DECISION_ABSTAIN)
            self.assertFalse(resolved)
            conn.commit()

    # 8. route_and_apply batch: d1->queue(distill), d2->queue(abstain), d3->archived
    def test_route_and_apply_batch(self):
        with connect() as conn, conn.cursor() as cur:
            for nid in (self.s["d1"], self.s["d2"], self.s["d3"]):
                route_and_apply(cur, nid)
            cur.execute("SELECT count(*) FROM review_queue")
            self.assertEqual(cur.fetchone()[0], 2)
            cur.execute("SELECT archived_at IS NOT NULL FROM node WHERE id=%s",
                        (self.s["d3"],))
            self.assertTrue(cur.fetchone()[0])
            conn.commit()

    # 9. rationale surfaces the underlying signals
    def test_rationale_carries_signals(self):
        with connect() as conn, conn.cursor() as cur:
            d = route_expired(cur, self.s["d1"])
        self.assertIn("connection_count", d["signals"])
        self.assertGreaterEqual(d["signals"]["connection_count"], 1)
        self.assertIn("already_captured", d["signals"])
        self.assertFalse(d["signals"]["already_captured"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
